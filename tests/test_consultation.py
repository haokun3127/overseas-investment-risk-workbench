import secrets

from fastapi.testclient import TestClient

from app import consultation
from app.config import Settings
from app.ingest import insert_document
from app.main import create_app


HEADERS = {"X-Requested-With": "risk-workbench"}
EVIDENCE = "合成政策规定，园区每季度需要提交环境监测记录。"


def app_for(tmp_path):
    return create_app(Settings(data_dir=tmp_path, model_base_url="https://example.com/v1",
                               model_name="test-model", model_api_key="test-key", model_store=True), run_worker=False)


def doc(store, title, text=EVIDENCE, **kwargs):
    doc_id = insert_document(store, {"title": title, "body": text}, kind="knowledge", **kwargs)[0]
    if kwargs.get("allow_external") is False:
        with store.db() as db:
            db.execute("UPDATE documents SET allow_external=0 WHERE id=?", (doc_id,))
    return doc_id


def setup(client):
    assert client.post("/api/auth/setup", json={"password": secrets.token_urlsafe(18)}).status_code == 200


def test_answer_uses_retrieved_original_and_returns_verified_citation(tmp_path, monkeypatch):
    app = app_for(tmp_path)
    document_id = doc(app.state.store, "环境监测记录", allow_external=True)

    async def answer(settings, payload, **kwargs):
        assert settings.model_store is False
        assert payload["previous_questions"] == ["园区有哪些环境要求？"]
        assert EVIDENCE in payload["evidence"][0]["text"]
        return {"status": "answered", "blocks": [{"text": "园区每季度提交一次监测记录。",
                "citations": [{"ref": payload["evidence"][0]["ref"], "quote": EVIDENCE}]}]}, {}

    monkeypatch.setattr(consultation.model, "call_model", answer)
    with TestClient(app, headers=HEADERS) as client:
        assert client.post("/api/consultation", json={"question": "环境监测记录"}).status_code == 401
        setup(client)
        result = client.post("/api/consultation", json={"question": "多久提交环境监测记录？",
                            "previous_questions": ["园区有哪些环境要求？"]})
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["blocks"][0]["citations"] == [1]
        assert body["sources"][0]["document_id"] == document_id
        assert body["sources"][0]["quote"] == EVIDENCE
        assert client.get(f"/api/documents/{document_id}").status_code == 200


def test_scope_is_rechecked_before_any_content_reaches_model(tmp_path, monkeypatch):
    app = app_for(tmp_path)
    with TestClient(app, headers=HEADERS) as admin, TestClient(app, headers=HEADERS) as tenant, TestClient(app, headers=HEADERS) as other:
        setup(admin)
        tenant.cookies.update(admin.cookies)
        other.cookies.update(admin.cookies)
        company = tenant.post("/api/auth/register", json={
            "username": "fixture_tenant", "password": secrets.token_urlsafe(18), "name": "合成企业",
        }).json()["company_id"]
        other_company = other.post("/api/auth/register", json={
            "username": "fixture_other", "password": secrets.token_urlsafe(18), "name": "另一个合成企业",
        }).json()["company_id"]
        own = doc(app.state.store, "企业内部合成资料", allow_external=True, company_id=company)
        public = doc(app.state.store, "公开合成资料", allow_external=True)
        doc(app.state.store, "未授权合成资料", allow_external=False, company_id=company)
        foreign = doc(app.state.store, "其他企业合成资料", allow_external=True, company_id=other_company)
        doc(app.state.store, "演示合成资料", allow_external=True, demo=True)
        quarantined = doc(app.state.store, "隔离合成资料", text=EVIDENCE+"此条为独立隔离资料。", allow_external=True)
        with app.state.store.db() as db:
            db.execute("UPDATE documents SET quarantined_at='2026-01-01' WHERE id=?", (quarantined,))
        rows = app.state.store.rows("SELECT id FROM chunks ORDER BY id DESC")
        monkeypatch.setattr(consultation, "retrieve", lambda *a, **kw: rows)
        seen = []

        async def answer(settings, payload, **kwargs):
            seen.append({row["title"] for row in payload["evidence"]})
            return {"status": "insufficient", "blocks": []}, {}

        monkeypatch.setattr(consultation.model, "call_model", answer)
        assert tenant.post("/api/consultation", json={"question":"环境监测","company_id":other_company}).status_code == 403
        assert not seen
        assert admin.post("/api/consultation", json={"question":"环境监测"}).status_code == 200
        assert seen[-1] == {"公开合成资料"}
        assert other.post("/api/consultation", json={"question":"环境监测"}).status_code == 403
        assert admin.post(f"/api/companies/{company}/activate").status_code == 200
        assert admin.post("/api/consultation", json={"question":"环境监测","company_id":company}).status_code == 200
        assert seen[-1] == {"公开合成资料"}  # generic consultation ignores selected/private context
        for identifier in (own,public,foreign):
            assert tenant.get(f"/api/documents/{identifier}").status_code == 403
        assert other.get(f"/api/documents/{own}").status_code == 403


def test_no_eligible_source_skips_model_and_unverified_quote_is_rejected(tmp_path, monkeypatch):
    app = app_for(tmp_path)
    calls = []

    async def answer(settings, payload, **kwargs):
        calls.append(payload)
        return {"status": "answered", "blocks": [{"text": "合成回答。",
                "citations": [{"ref": "S1", "quote": "原文里不存在的伪造引文"}]}]}, {}

    monkeypatch.setattr(consultation.model, "call_model", answer)
    with TestClient(app, headers=HEADERS) as client:
        setup(client)
        doc(app.state.store, "环境监测记录", allow_external=False)
        result = client.post("/api/consultation", json={"question": "环境监测记录"})
        assert result.status_code == 200 and result.json()["status"] == "insufficient"
        assert not calls
        doc(app.state.store, "环境监测记录补充", text=EVIDENCE + "这是补充说明。", allow_external=True)
        result = client.post("/api/consultation", json={"question": "环境监测记录"})
        assert result.status_code == 502 and "原文校验" in result.json()["detail"]
        assert len(calls) == 1
