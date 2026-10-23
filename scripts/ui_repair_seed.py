"""Seed and serve an isolated instance for scripts/ui_repair_test.cjs.

  python -m scripts.ui_repair_seed seed --data-dir /tmp/x --out /tmp/x-creds.json
  python -m scripts.ui_repair_seed serve --data-dir /tmp/x --port 8765

Passwords are generated at runtime and written only to the --out file (mode 600).
The background worker is disabled, so no model is ever called and queued jobs stay queued.
"""
import argparse
import asyncio
import json
import os
import secrets
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

HEADERS = {"X-Requested-With": "risk-workbench"}
FAKE_MODEL = {"model_mode": "external", "model_base_url": "https://model.invalid/v1", "model_name": "ui-test-model",
              "model_api_key": "ui-test-not-a-key"}

LAW_PARAGRAPH = (
    "Peraturan ini mengatur penggunaan tenaga kerja asing oleh pemberi kerja. "
    "Setiap pemberi kerja tenaga kerja asing wajib memiliki RPTKA yang disahkan oleh Menteri. "
)
LONG_LAW = "\n\n".join(
    f"Pasal {i}. " + LAW_PARAGRAPH * 3 + ("外籍劳工（tenaga kerja asing）应当在入境前取得工作许可。" if i % 3 == 0 else "")
    for i in range(1, 22)
)


def settings_for(data_dir):
    return Settings(data_dir=Path(data_dir), **FAKE_MODEL)


def fake_result(payload):
    ref = [r["reference"] for r in payload["references"] if r["reference"].startswith("S")][0]
    quote = payload["references"][0]["text"][:30]
    knowledge = [r for r in payload["references"] if r["reference"].startswith("K")]
    evidence = [{"reference": ref, "quote": quote, "reason": "输入资料直接说明风险"}]
    if knowledge:
        evidence.append({"reference": knowledge[0]["reference"], "quote": knowledge[0]["text"][:30], "reason": "法规依据"})
    return {"decision": "risk", "reason": "UI 测试", "events": [{
        "title": f"UI 测试风险：{payload['document']['title'][:20]}", "category": "政策与监管", "level": "orange",
        "summary": "测试摘要", "impact": "测试影响", "recommendation": "测试建议", "evidence": evidence}]}


def seed(data_dir, out):
    data_dir = Path(data_dir)
    if data_dir.exists() and any(data_dir.iterdir()):
        raise SystemExit(f"{data_dir} 已存在且非空，拒绝覆盖。")
    app = create_app(settings_for(data_dir), run_worker=False)
    store = app.state.store
    creds = {
        "admin_password": secrets.token_urlsafe(18),
        "company_user": "ui_company_a",
        "company_password": secrets.token_urlsafe(18),
    }
    from app import jobs as jobs_module

    async def fake_call(_settings, payload, **_kwargs):
        return fake_result(payload), {}
    jobs_module.model.call_model = fake_call
    with TestClient(app, headers=HEADERS) as admin, TestClient(app, headers=HEADERS) as company:
        assert admin.post("/api/auth/setup", json={"password": creds["admin_password"]}).status_code == 200
        rules = store.setting("rules")
        rules["confirmed"] = True
        store.set_setting("rules", rules)
        reg = company.post("/api/auth/register", json={
            "username": creds["company_user"], "password": creds["company_password"], "name": "界面测试甲公司",
            "industry": "镍冶炼", "allow_external": True})
        assert reg.status_code == 200, reg.text
        admin.post("/api/companies", json={"name": "管理员背景测试公司", "industry": "纺织", "allow_external": True})

        from app.ingest import insert_document
        long_id, _ = insert_document(store, {"title": "Permenaker Nomor 8 Tahun 2021 tentang TKA", "body": LONG_LAW,
                                             "source": "Kemnaker", "date": "2021-03-01"}, "knowledge", True)
        with store.db() as db:
            db.execute("UPDATE documents SET zh_summary=?,zh_keywords=?,zh_state='done' WHERE id=?",
                       ("印尼劳工部关于外籍劳工使用的部长条例，规定 RPTKA 审批与雇主义务，内容较长用于测试全文阅读和命中跳转。" * 2,
                        "外籍劳工、RPTKA、工作许可", long_id))
        for index in range(9):
            insert_document(store, {"title": f"外籍劳工政策解读 {index + 1}", "body": f"第{index + 1}篇：外籍劳工工作许可办理需要用工计划。" * 4,
                                    "source": "测试来源", "date": ""}, "knowledge", True,
                            meta={"date_source": "page_meta"})
        insert_document(store, {"title": "［网页存档 2024-01-01］外籍劳工新规通知", "body": "外籍劳工新规通知正文（存档版本）。" * 3,
                                "source": "e.go.id", "url": "https://www.e.go.id/berita/1/", "date": ""}, "knowledge", True,
                        meta={"archived_at": "2024-01-01"})
        insert_document(store, {"title": "外籍劳工新规通知", "body": "外籍劳工新规通知正文（现行版本）。" * 3,
                                "source": "e.go.id", "url": "https://e.go.id/berita/1", "date": "2024-02-02"}, "knowledge", True,
                        meta={"date_source": "page_meta"})
        insert_document(store, {"title": "标记转义测试 a<mark>&amp;", "body": "检索词 mark 与 amp 出现在 a<mark>&amp; 正文中。",
                                "source": "测试", "date": ""}, "knowledge", True)

        event_ids = []
        for index in range(36):
            r = admin.post("/api/documents", json={
                "title": f"界面测试资料 {index + 1:02d}", "body": f"园区企业需在月底前提交第{index + 1}批年度核查材料，逾期暂停原料采购。外籍劳工工作许可。",
                "kind": "event", "allow_external": True, "date": f"2024-0{1 + index % 9}-1{index % 9}"})
            event_ids.append(r.json()["id"])
        for doc_id in event_ids[:4]:
            job = admin.post("/api/jobs", json={"document_ids": [doc_id]}).json()["items"][0]["id"]
            asyncio.run(app.state.worker.process(store.one("SELECT * FROM jobs WHERE id=?", (job,))))
        queued = admin.post("/api/jobs", json={"document_ids": [event_ids[10]]}).json()["items"][0]["id"]
        own = company.post("/api/documents", json={"title": "甲公司内部资料", "body": "甲公司园区核查材料需月底前提交，逾期暂停原料采购。",
                                                   "kind": "event", "allow_external": True}).json()["id"]
        job = company.post("/api/jobs", json={"document_ids": [own]}).json()["items"][0]["id"]
        asyncio.run(app.state.worker.process(store.one("SELECT * FROM jobs WHERE id=?", (job,))))
        company.post("/api/documents", json={"title": "甲公司知识资料", "body": "甲公司自有外籍劳工管理制度。", "kind": "knowledge"})
        assert admin.post("/api/demo").status_code == 200
    creds["queued_job"] = queued
    creds["long_document"] = long_id
    out = Path(out)
    out.write_text(json.dumps(creds), encoding="utf-8")
    os.chmod(out, 0o600)
    print(json.dumps({"data_dir": str(data_dir), "creds": str(out), "queued_job": queued}))


def seed_empty(data_dir, out):
    """A workspace with documents but no analysis yet: the overview's empty state."""
    data_dir = Path(data_dir)
    if data_dir.exists() and any(data_dir.iterdir()):
        raise SystemExit(f"{data_dir} 已存在且非空，拒绝覆盖。")
    app = create_app(settings_for(data_dir), run_worker=False)
    store = app.state.store
    creds = {
        "admin_password": secrets.token_urlsafe(18),
        "company_user": "ui_company_empty",
        "company_password": secrets.token_urlsafe(18),
    }
    with TestClient(app, headers=HEADERS) as admin, TestClient(app, headers=HEADERS) as company:
        assert admin.post("/api/auth/setup", json={"password": creds["admin_password"]}).status_code == 200
        rules = store.setting("rules")
        rules["confirmed"] = True
        store.set_setting("rules", rules)
        reg = company.post("/api/auth/register", json={
            "username": creds["company_user"], "password": creds["company_password"], "name": "界面测试空白公司",
            "industry": "镍冶炼", "allow_external": True})
        assert reg.status_code == 200, reg.text
        for index in range(4):
            r = admin.post("/api/documents", json={
                "title": f"待分析资料 {index + 1:02d}", "body": f"园区企业需在月底前提交第{index + 1}批年度核查材料。",
                "kind": "event", "allow_external": True, "date": f"2024-0{index + 1}-15"})
            assert r.status_code == 200, r.text
    out = Path(out)
    out.write_text(json.dumps(creds), encoding="utf-8")
    os.chmod(out, 0o600)
    print(json.dumps({"data_dir": str(data_dir), "creds": str(out)}))


def serve(data_dir, port):
    import uvicorn
    uvicorn.run(create_app(settings_for(data_dir), run_worker=False), host="127.0.0.1", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument("--data-dir", required=True)
    seed_parser.add_argument("--out", required=True)
    empty_parser = sub.add_parser("seed-empty")
    empty_parser.add_argument("--data-dir", required=True)
    empty_parser.add_argument("--out", required=True)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--data-dir", required=True)
    serve_parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.data_dir, args.out)
    elif args.command == "seed-empty":
        seed_empty(args.data_dir, args.out)
    else:
        serve(args.data_dir, args.port)


if __name__ == "__main__":
    main()
