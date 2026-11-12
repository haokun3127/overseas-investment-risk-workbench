import io
import json
from docx import Document
import pytest
from app.consultation import verify_answer
from app.ingest import insert_document
from test_tenant_authz import app, admin, companies
from test_meeting import data


def test_metadata_audit_revision_and_immutable_source(admin, companies):
    tenant, _ = companies
    store = admin.app.state.store
    did, _ = insert_document(store, {
        'title': '法规原标题', 'body': '设备进口需要核实审批程序以及适用版本。',
        'date': '2025-01-02', 'source': '旧来源',
    }, 'knowledge')
    original = store.one('SELECT * FROM documents WHERE id=?', (did,))
    chunks = store.rows('SELECT * FROM chunks WHERE document_id=?', (did,))
    endpoint = f'/api/documents/{did}/metadata'
    payload = {'revision': original['legal_revision'], 'title': '法规更正标题',
               'date': '', 'source': '发布机关', 'url': 'https://law.example/1',
               'reason': '原文没有明确发布日期，撤销误填日期'}
    assert tenant.put(endpoint, json=payload).status_code == 403
    assert tenant.get(endpoint+'-history').status_code == 403
    response = admin.put(endpoint, json=payload)
    assert response.status_code == 200, response.text
    assert admin.put(endpoint, json=payload).status_code == 409
    row = store.one('SELECT * FROM documents WHERE id=?', (did,))
    assert row['title'] == payload['title'] and row['date'] == ''
    assert row['date_legacy'] == '2025-01-02' and row['date_source'] == 'removed'
    assert row['legal_revision'] == original['legal_revision']+1
    assert all(row[k] == original[k] for k in ('body', 'digest', 'company_id', 'legal_meta'))
    assert chunks == store.rows('SELECT * FROM chunks WHERE document_id=?', (did,))
    history = admin.get(endpoint+'-history').json()['items']
    assert len(history) == 1 and history[0]['actor'] == 'admin'
    assert history[0]['before']['date'] == '2025-01-02'
    assert history[0]['after']['url'] == payload['url']
    for extra in ({'url': 'javascript:alert(1)'}, {'url': 'https://name:example@example.com'},
                  {'date': '2026-02-30'}, {'title': '   '}):
        r = admin.put(endpoint, json={**payload, 'revision': row['legal_revision'], **extra})
        assert r.status_code == 400, r.text


def test_metadata_cannot_modify_event_profile_or_quarantine(admin, companies):
    tenant, _ = companies
    store = admin.app.state.store
    event, _ = insert_document(store, {'title': '事项', 'body': '用于核实的事项事实原文。'})
    profile = store.one('SELECT document_id FROM companies WHERE id=?', (tenant.company_id,))['document_id']
    quarantined, _ = insert_document(store, {'title': '隔离法规', 'body': '隔离资料不能直接修改。'}, 'knowledge')
    with store.db() as db:
        db.execute("UPDATE documents SET quarantined_at='2026-01-01' WHERE id=?", (quarantined,))
    payload = {'revision': 0, 'title': '更正', 'reason': '核对后更正'}
    for did, status in ((event, 404), (profile, 409), (quarantined, 409)):
        assert admin.put(f'/api/documents/{did}/metadata', json=payload).status_code == status


def test_action_basis_scope_effectivity_and_revision(admin, companies):
    tenant, other = companies
    store = admin.app.state.store
    eid = admin.post('/api/events', json=data(tenant.company_id)).json()['id']
    original = admin.get(f'/api/events/{eid}').json()['result']
    quote = '合同成立后当事人应当依照约定履行义务。'
    law, _ = insert_document(store, {'title': '合同法律依据', 'body': quote,
                                    'legal_metadata': {'category': 'id_law', 'validity': 'unknown'}}, 'knowledge')
    endpoint = f'/api/events/{eid}/actions/0/basis'
    payload = {'revision': 0, 'document_id': law, 'quote': quote, 'reason': '支持核实合同履行义务'}
    assert tenant.post(endpoint, json=payload).status_code == 403
    assert admin.post(endpoint, json=payload).status_code == 400
    with store.db() as db:
        db.execute('UPDATE documents SET legal_meta=? WHERE id=?',
                   (json.dumps({'category': 'id_law', 'validity': 'in_force'}), law))
    assert admin.post(endpoint, json={**payload, 'quote': '这段内容并不存在于原文之中。'}).status_code == 400
    response = admin.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    assert admin.post(endpoint, json=payload).status_code == 409
    assert admin.post(endpoint, json={**payload, 'revision': 1}).status_code == 400
    current = admin.get(f'/api/events/{eid}').json()
    assert current['result'] == original and current['revision'] == 1
    assert current['actions'][0]['basis'][0]['manual']
    assert current['changes'][0]['action'] == 'action_basis'
    private, _ = insert_document(store, {'title': '其他企业法律意见', 'body': quote,
        'legal_metadata': {'category': 'judgment'}}, 'knowledge', company_id=other.company_id)
    assert admin.post(endpoint, json={**payload, 'document_id': private, 'revision': 1}).status_code == 400
    foreign_profile = store.one('SELECT document_id FROM companies WHERE id=?', (other.company_id,))['document_id']
    text = store.one('SELECT body FROM documents WHERE id=?', (foreign_profile,))['body']
    assert admin.post(f'/api/events/{eid}/evidence', json={
        **payload, 'document_id': foreign_profile, 'quote': text, 'revision': 1}).status_code == 400


def sources():
    return {'S1': {'text': '合同成立后当事人应当依照约定履行义务。', 'document_id': 1,
                   'title': '合同法原文', 'source': '发布机关', 'date': '2025-01-01', 'locator': '第一条',
                   'legal_metadata': {'category': 'id_law', 'validity': 'in_force'}}}


def partial(report=False):
    return {'status': 'insufficient', 'gaps': {
        'missing_facts': ['尚未提供合同签订时间。'], 'missing_basis': ['缺少争议解决条款。'],
        'conflicts': ['两份材料的履行日期不同。'], 'affected': ['不能判断起诉期限。'],
        'needed': ['请补充签字版合同。']},
        'blocks': [{'text': '当事人应当依照合同约定履行义务。',
                    **({'section': 'basis'} if report else {}),
                    'citations': [{'ref': 'S1', 'unit_id': 'S1:1'}]}]}


def test_insufficient_preserves_verified_partial_and_concrete_gaps():
    answer = verify_answer(partial(), sources(), question='合同履行如何判断？')
    assert answer['status'] == 'insufficient'
    assert answer['blocks'][0]['citations'] == [1]
    assert answer['sources'][0]['quote'] == sources()['S1']['text']
    assert answer['explanation']['needed'] == ['请补充签字版合同。']
    assert answer['explanation']['known_materials'] == ['合同法原文']
    assert answer['explanation']['question'] == '合同履行如何判断？'
    empty = verify_answer({'status': 'insufficient'}, {})
    assert empty['explanation']['missing_basis'] and not empty['blocks']
    old = verify_answer({'status': 'insufficient'}, sources())
    assert '模型未确认' in old['explanation']['missing_basis'][0]
    malformed = partial()
    malformed['gaps']['missing_facts'] = '缺事实'
    with pytest.raises(ValueError):
        verify_answer(malformed, sources())
    malformed = partial()
    malformed['blocks'][0]['citations'][0]['unit_id'] = 'S1:999'
    with pytest.raises(ValueError):
        verify_answer(malformed, sources())


def test_partial_consultation_report_word(admin, monkeypatch):
    monkeypatch.setattr('app.consultation.find_report_sources', lambda *a: sources())
    async def model(*a, **kw):
        return partial(True), {}
    monkeypatch.setattr('app.consultation.model.call_model', model)
    response = admin.post('/api/consultation', json={'question': '合同履行义务', 'mode': 'report'})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer['status'] == 'insufficient' and answer['report_id']
    word = admin.get(f"/api/consultation/reports/{answer['report_id']}/docx")
    text = '\n'.join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
    assert '资料缺口与补充建议' in text and '请补充签字版合同。' in text
    assert '合同法原文' in text and '法律依据' in text


def test_company_can_read_own_gaps_without_full_analysis_or_other_tenant(admin, companies):
    tenant, other = companies
    store = admin.app.state.store
    from app.store import now
    for cid, title in ((tenant.company_id, '本企业合同'), (other.company_id, '另一企业私密合同')):
        did, _ = insert_document(store, {'title': title, 'body': '已有付款事实，但尚未提供签订日期和争议解决条款。'}, company_id=cid)
        with store.db() as db:
            db.execute('''INSERT INTO analyses(document_id,version,decision,model,mode,rules_json,
                knowledge_json,result_json,created_at,duration_ms,usage_json) VALUES (?,1,'insufficient',
                'test','external','{}','[]',?,?,0,'{}')''',
                (did, json.dumps({'parts': [{'decision': 'insufficient', 'reason': title+'：缺签订日期，不能确定适用版本，请补充签字合同。'}]}), now()))
    result = tenant.get('/api/overview').json()
    assert len(result['evidence_gaps']) == 1 and result['evidence_gaps'][0]['title'] == '本企业合同'
    assert '请补充签字合同' in result['evidence_gaps'][0]['reason']
    assert '另一企业' not in json.dumps(result, ensure_ascii=False)
    assert result['total'] == 0 and {'decision': 'insufficient', 'count': 1} in result['decisions']
    assert not any(d['decision'] == 'non_risk' for d in result['decisions'])


def test_admin_provisions_account_for_existing_company_without_switching_session(admin, companies):
    tenant, _ = companies
    from fastapi.testclient import TestClient
    from test_tenant_authz import HEADERS
    endpoint = '/api/company-users'
    payload = {'username': 'new_company_reader', 'password': 'local-test-only', 'company_id': tenant.company_id}
    count = admin.app.state.store.one('SELECT count(*) n FROM companies')['n']
    assert tenant.post(endpoint, json=payload).status_code == 403
    assert tenant.get(endpoint).status_code == 403
    with TestClient(admin.app, headers=HEADERS) as anon:
        assert anon.post('/api/auth/register', json={'username':'anonymous_user','password':'local-test-only','name':'任意公司'}).status_code == 401
        assert anon.post(endpoint, json=payload).status_code == 401
        assert admin.post(endpoint, json=payload).status_code == 200
        assert admin.get('/api/auth/status').json()['role'] == 'admin'
        assert admin.app.state.store.one('SELECT count(*) n FROM companies')['n'] == count
        assert admin.post(endpoint, json={**payload, 'username': 'NEW_COMPANY_READER'}).status_code == 409
        listing = admin.get(endpoint).json()
        assert 'hash' not in json.dumps(listing) and 'password' not in json.dumps(listing)
        assert anon.post('/api/auth/login', json={'username':payload['username'],'password':payload['password']}).status_code == 200
        assert anon.get('/api/auth/status').json()['company_id'] == tenant.company_id
        assert anon.post('/api/auth/register', json={'username':'other_user','password':'local-test-only','name':'另一企业'}).status_code == 403
