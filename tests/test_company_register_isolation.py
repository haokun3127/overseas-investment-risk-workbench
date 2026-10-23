import asyncio
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

HEADERS = {"X-Requested-With": "risk-workbench"}

def test_company_registration_and_strict_tenant_isolation(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        model_mode="external",
        model_base_url="https://example.com/v1",
        model_name="test-model",
        model_api_key="test-key",
    )
    app = create_app(settings, run_worker=False)
    store = app.state.store
    rules = store.setting("rules")
    rules["confirmed"] = True
    store.set_setting("rules", rules)

    # Seed a public law in the shared knowledge base (company_id=None)
    from app.ingest import insert_document
    pub_law_id, _ = insert_document(
        store,
        {"title": "Permenaker Nomor 5 Tahun 2025", "body": "Peraturan ketenagakerjaan tenaga kerja asing RPTKA DKPTKA.", "source": "印尼劳工部"},
        kind="knowledge",
        allow_external=True,
    )
    with store.db() as db:
        db.execute("UPDATE documents SET zh_summary='印尼劳工部外籍劳工条例', zh_state='done' WHERE id=?", (pub_law_id,))

    with TestClient(app, headers=HEADERS) as client_a, TestClient(app, headers=HEADERS) as client_b:
        # 1. Register Company A
        r_a = client_a.post("/api/auth/register", json={
            "username": "nickel_id",
            "password": "password-a-123",
            "name": "中苏拉威西镍业（印尼）有限公司",
            "industry": "镍矿冶炼",
            "business": "红土镍矿湿法冶炼与氢氧化镍钴出口",
            "location": "中苏拉威西省莫罗瓦利工业园",
            "concerns": "矿业权RKAB审批與镍矿出口政策",
            "allow_external": True,
        })
        assert r_a.status_code == 200
        cid_a = r_a.json()["company_id"]

        # Company A uploads an event document and runs risk analysis
        doc_a = client_a.post("/api/documents", json={
            "title": "莫罗瓦利园区RKAB配额核查通知",
            "body": "园区镍冶炼企业需在月底前提交RKAB年度生产配额核查材料，逾期暂停矿石采购。",
            "kind": "event",
            "allow_external": True,
        }).json()["id"]
        job_a = client_a.post("/api/jobs", json={"document_ids": [doc_a]}).json()["items"][0]["id"]

        async def fake_model(s, payload, **kwargs):
            ref_key = [r["reference"] for r in payload["references"] if r["reference"].startswith("S")][0]
            return {
                "decision": "risk",
                "reason": "涉及RKAB配额暂停风险",
                "events": [{
                    "title": "RKAB配额核查逾期暂停采购风险",
                    "category": "政策与监管",
                    "level": "red",
                    "summary": "逾期未交RKAB材料将暂停矿石采购",
                    "impact": "影响冶炼产线原料供应",
                    "recommendation": "按期提交RKAB核查材料",
                    "evidence": [{"reference": ref_key, "quote": "园区镍冶炼企业需在月底前提交RKAB年度生产配额核查材料", "reason": "直接说明配额核查要求"}],
                }],
            }, {}
        monkeypatch.setattr("app.jobs.model.call_model", fake_model)
        asyncio.run(app.state.worker.process(store.one("SELECT * FROM jobs WHERE id=?", (job_a,))))

        # Verify Company A sees its own company, document, job, event, and overview
        assert [c["id"] for c in client_a.get("/api/companies").json()["items"]] == [cid_a]
        assert client_a.get("/api/companies").json()["scoped"] is True
        assert [d["id"] for d in client_a.get("/api/documents?kind=event").json()["items"]] == [doc_a]
        events_a = client_a.get("/api/events").json()["items"]
        assert len(events_a) == 1 and events_a[0]["title"] == "RKAB配额核查逾期暂停采购风险"
        event_a_id = events_a[0]["id"]

        # 2. Register Company B
        r_b = client_b.post("/api/auth/register", json={
            "username": "solar_id",
            "password": "password-b-123",
            "name": "巴淡岛光伏组件（印尼）有限公司",
            "industry": "光伏新能源",
            "business": "光伏组件组装与本地化率TKDN认证",
            "location": "廖内群岛省巴淡自由贸易区",
            "concerns": "光伏组件TKDN本地化率与进口清关",
            "allow_external": True,
        })
        assert r_b.status_code == 200
        cid_b = r_b.json()["company_id"]
        assert cid_b != cid_a

        # 3. Verify strict isolation for Company B
        # Company B only sees its own company profile
        comp_b = client_b.get("/api/companies").json()
        assert [c["id"] for c in comp_b["items"]] == [cid_b]
        assert comp_b["items"][0]["name"] == "巴淡岛光伏组件（印尼）有限公司"
        assert client_b.put(f"/api/companies/{cid_a}", json={"name": "篡改"}).status_code == 403
        assert client_b.post(f"/api/companies/{cid_a}/activate").status_code == 403

        # Company B cannot see Company A documents, jobs, or events
        assert client_b.get("/api/documents?kind=event").json()["items"] == []
        assert client_b.get(f"/api/documents/{doc_a}").status_code == 404
        assert client_b.delete(f"/api/documents/{doc_a}").status_code == 404
        assert client_b.get("/api/jobs").json()["items"] == []
        assert client_b.get("/api/events").json()["items"] == []
        assert client_b.get(f"/api/events/{event_a_id}").status_code == 404
        assert client_b.get("/api/overview").json()["total"] == 0
        assert client_b.get("/api/report").json()["total"] == 0

        # 4. Knowledge base: Company B can search shared public laws (with Chinese cross-lingual expansion!) and its own profile, but NOT Company A profile
        kb_hits_a = client_b.get("/api/knowledge/search?q=莫罗瓦利 镍矿冶炼").json()["items"]
        assert all(h["title"] != "公司档案 · 中苏拉威西镍业（印尼）有限公司" for h in kb_hits_a)
        kb_hits_b = client_b.get("/api/knowledge/search?q=巴淡岛 光伏组件").json()["items"]
        assert any(h["title"] == "公司档案 · 巴淡岛光伏组件（印尼）有限公司" for h in kb_hits_b)
        kb_hits_law = client_b.get("/api/knowledge/search?q=外籍劳工").json()["items"]
        assert any(h["document_id"] == pub_law_id for h in kb_hits_law)
