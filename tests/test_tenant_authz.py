import asyncio
import secrets
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.ingest import insert_document
from app.main import create_app
from app import websearch
from app.store import Store
from test_websearch import add_source, fake_fetch, fake_model, process

HEADERS = {'X-Requested-With': 'risk-workbench'}


def password():
    return secrets.token_urlsafe(16)


@pytest.fixture
def app(tmp_path):
    application = create_app(Settings(data_dir=tmp_path, model_mode='external', model_base_url='https://example.com/v1',
                                      model_name='test', model_api_key='test'), run_worker=False)
    store = application.state.store
    rules = store.setting('rules')
    rules['confirmed'] = True
    store.set_setting('rules', rules)
    return application


@pytest.fixture
def admin(app):
    with TestClient(app, headers=HEADERS) as c:
        c.admin_password = password()
        assert c.post('/api/auth/setup', json={'password': c.admin_password}).status_code == 200
        yield c


def register(app, username, name):
    c = TestClient(app, headers=HEADERS)
    c.__enter__()
    r = c.post('/api/auth/register', json={'username': username, 'password': password(), 'name': name, 'allow_external': True})
    assert r.status_code == 200, r.text
    c.company_id = r.json()['company_id']
    return c


@pytest.fixture
def companies(app, admin):
    a = register(app, 'tenant_a', '甲测试公司')
    b = register(app, 'tenant_b', '乙测试公司')
    yield a, b
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def add_event(c, title='供应链资料', body='园区企业需在月底前提交年度核查材料，逾期将暂停原料采购。'):
    r = c.post('/api/documents', json={'title': title, 'body': body, 'kind': 'event', 'allow_external': True})
    assert r.status_code == 200, r.text
    return r.json()['id']


def analyse(app, c, doc_id, monkeypatch, captured=None):
    r = c.post('/api/jobs', json={'document_ids': [doc_id]})
    assert r.status_code == 200, r.text
    job = r.json()['items'][0]['id']

    async def fake(_settings, payload, **_kwargs):
        if captured is not None:
            captured.append(payload)
        ref = [r['reference'] for r in payload['references'] if r['reference'].startswith('S')][0]
        return {'decision': 'risk', 'reason': '测试', 'events': [{
            'title': '原料采购暂停风险', 'category': '政策与监管', 'level': 'orange', 'summary': '逾期暂停采购',
            'impact': '影响生产', 'recommendation': '按期提交',
            'evidence': [{'reference': ref, 'quote': '园区企业需在月底前提交年度核查材料', 'reason': '直接说明'}]}]}, {}
    monkeypatch.setattr('app.jobs.model.call_model', fake)
    store = app.state.store
    asyncio.run(app.state.worker.process(store.one('SELECT * FROM jobs WHERE id=?', (job,))))
    return job


# --- admin-only endpoints -------------------------------------------------

def test_company_user_cannot_call_admin_endpoints(app, companies, monkeypatch):
    a, _ = companies
    called = []

    async def must_not_run(*_args, **_kwargs):
        called.append(True)
        raise AssertionError('model must not be called for company users')
    monkeypatch.setattr('app.main.model.call_model', must_not_run)
    rules = app.state.store.setting('rules')
    assert a.put('/api/rules', json=rules).status_code == 403
    assert a.post('/api/model/check').status_code == 403
    assert a.get('/api/runtime').status_code == 403
    assert a.post('/api/demo').status_code == 403
    assert a.delete('/api/demo').status_code == 403
    assert called == []
    assert app.state.store.one('SELECT COUNT(*) n FROM documents WHERE demo=1')['n'] == 0


def test_admin_can_call_admin_endpoints(admin):
    assert admin.get('/api/runtime').status_code == 200
    assert admin.post('/api/demo').status_code == 200
    assert admin.delete('/api/demo').status_code == 200


WEB_ROUTES = [
    ('get', '/api/web/health'),
    ('get', '/api/web/sources'), ('post', '/api/web/sources/import'), ('post', '/api/web/sources/1/toggle'),
    ('delete', '/api/web/sources/1'), ('post', '/api/web/runs/group'), ('post', '/api/web/sources'),
    ('put', '/api/web/sources/1'), ('post', '/api/web/sources/1/pause'), ('post', '/api/web/runs'),
    ('get', '/api/web/runs'), ('post', '/api/web/runs/batch/cancel'), ('get', '/api/web/discoveries'),
    ('get', '/api/web/runs/1'), ('post', '/api/web/runs/1/cancel'), ('post', '/api/web/runs/1/review'),
    ('get', '/api/web/pages/1'), ('post', '/api/web/import'),
]


@pytest.mark.parametrize('method,path', WEB_ROUTES)
def test_website_routes_are_admin_only(app, companies, method, path):
    a, _ = companies
    kwargs = {} if method in ('get', 'delete') else {'json': {}}
    assert getattr(a, method)(path, **kwargs).status_code == 403
    with TestClient(app, headers=HEADERS) as anonymous:
        assert getattr(anonymous, method)(path, **kwargs).status_code == 401


def test_website_route_inventory_is_complete(app):
    def normalize(path):
        return '/'.join('{x}' if part.startswith('{') or part == '1' else part for part in path.split('/'))
    routes = {(method, normalize(path)) for path, ops in app.openapi()['paths'].items() if path.startswith('/api/web')
              for method in ops}
    assert routes == {(method, normalize(path)) for method, path in WEB_ROUTES}


# --- CSRF ---------------------------------------------------------------

def test_csrf_header_and_origin_are_required(admin):
    with TestClient(admin.app) as bare:
        bare.cookies.update(admin.cookies)
        assert bare.post('/api/documents', json={'title': 't', 'body': '正文内容足够长用于测试。'}).status_code == 403
    r = admin.post('/api/documents', json={'title': 't', 'body': '正文内容足够长用于测试。'},
                   headers={'Origin': 'https://evil.example'})
    assert r.status_code == 403
    assert admin.app.state.store.one('SELECT COUNT(*) n FROM documents')['n'] == 0


# --- tenant isolation -----------------------------------------------------

def test_cross_company_access_is_404(app, companies, monkeypatch):
    a, b = companies
    doc = add_event(a)
    job = analyse(app, a, doc, monkeypatch)
    event = a.get('/api/events').json()['items'][0]['id']
    queued = a.post('/api/jobs', json={'document_ids': [doc]}).json()['items'][0]['id']
    assert b.get(f'/api/documents/{doc}').status_code == 404
    assert b.get(f'/api/documents/{doc}/file').status_code == 404
    assert b.patch(f'/api/documents/{doc}/policy', json={'allow_external': False}).status_code == 404
    assert b.delete(f'/api/documents/{doc}').status_code == 404
    assert b.post(f'/api/jobs/{queued}/cancel').status_code == 404
    assert b.get(f'/api/events/{event}').status_code == 404
    assert b.put(f'/api/events/{event}/review', json={'status': 'accepted', 'note': ''}).status_code == 404
    assert b.get('/api/events').json()['total'] == 0
    assert b.get('/api/jobs').json()['total'] == 0
    assert b.get('/api/jobs/active').json()['active'] == 0
    assert a.get('/api/jobs/active').json()['active'] == 1
    assert b.get('/api/report').json()['total'] == 0
    assert '原料采购暂停风险' not in b.get('/api/export/events').text
    assert job and a.get(f'/api/documents/{doc}').status_code == 200


def test_public_knowledge_is_read_only_for_companies(app, companies):
    a, _ = companies
    store = app.state.store
    public, _ = insert_document(store, {'title': '公共法规', 'body': '公共法规正文，用于只读测试。', 'source': 's', 'date': ''},
                                'knowledge', True)
    detail = a.get(f'/api/documents/{public}')
    assert detail.status_code == 200 and detail.json()['editable'] is False
    listed = {row['id']: row for row in a.get('/api/documents?kind=knowledge').json()['items']}
    assert listed[public]['editable'] is False
    assert a.delete(f'/api/documents/{public}').status_code == 404
    assert a.patch(f'/api/documents/{public}/policy', json={'allow_external': False}).status_code == 404
    own = a.post('/api/documents', json={'title': '自有资料', 'body': '本公司知识库资料正文内容。', 'kind': 'knowledge'}).json()['id']
    listed = {row['id']: row for row in a.get('/api/documents?kind=knowledge').json()['items']}
    assert listed[own]['editable'] is True
    assert store.one('SELECT allow_external FROM documents WHERE id=?', (public,))['allow_external'] == 1


def test_settings_hide_admin_fields_from_companies(companies, admin):
    a, _ = companies
    data = a.get('/api/settings').json()
    assert data['role'] == 'company' and data['can_manage'] is False
    assert data['base_url'] is None and data['wire_api'] is None
    full = admin.get('/api/settings').json()
    assert full['role'] == 'admin' and full['base_url'] == 'https://example.com/v1'


# --- audit scoping --------------------------------------------------------

def test_recent_activity_is_scoped_by_company_id(app, admin):
    store = app.state.store
    clients = {}
    for index in range(11):
        clients[index + 1] = register(app, f'tenant_{index:02d}', f'测试公司{index:02d}')
    try:
        ids = {n: c.company_id for n, c in clients.items()}
        assert ids[1] != ids[10] != ids[11]
        add_event(clients[10], title='十号公司资料')
        for n in (1, 11):
            details = [r['detail'] for r in clients[n].get('/api/workspace').json()['recent_activity']]
            assert all('十号公司资料' not in d for d in details)
            assert all(f'company={ids[10]}' not in d for d in details)
        assert any(r['action'] == 'document_added' or 'document' in r['action']
                   for r in clients[10].get('/api/workspace').json()['recent_activity'])
    finally:
        for c in clients.values():
            c.__exit__(None, None, None)
    assert store.one('SELECT COUNT(*) n FROM audit WHERE company_id IS NULL AND detail LIKE ?', (f'%company={ids[10]}%',))['n'] == 0


def test_legacy_audit_backfill_is_exact_and_idempotent(tmp_path):
    store = Store(tmp_path)
    rows = [
        ('events_exported', 'count=3, scope=all, company=1'),
        ('events_exported', 'count=3, scope=all, company=10'),
        ('company_saved', 'id=11, name=x'),
        ('document_deleted', 'id=11, kind=event, events=0'),
        ('events_exported', 'count=1, scope=all, company=None'),
    ]
    with store.db() as db:
        for action, detail in rows:
            db.execute('INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,NULL)', (action, detail, 'x'))
    for _ in range(2):
        store = Store(tmp_path)
        got = [r['company_id'] for r in store.rows('SELECT company_id FROM audit ORDER BY id')]
        assert got == [1, 10, 11, None, None]


# --- session-scoped active company ---------------------------------------

def test_active_company_is_per_session(app, admin):
    first = admin.post('/api/companies', json={'name': '一号公司'}).json()['id']
    with TestClient(app, headers=HEADERS) as other:
        assert other.post('/api/auth/login', json={'username': 'admin', 'password': admin.admin_password}).status_code == 200
        assert other.get('/api/companies').json()['active_id'] is None
        second = other.post('/api/companies', json={'name': '二号公司'}).json()['id']
        assert other.get('/api/companies').json()['active_id'] == second
        assert admin.get('/api/companies').json()['active_id'] == first
        assert other.post(f'/api/companies/{first}/activate').status_code == 200
        assert other.get('/api/companies').json()['active_id'] == first
    assert admin.put(f'/api/companies/{second}', json={'name': '二号公司改'}).status_code == 200
    assert admin.get('/api/companies').json()['active_id'] == first
    assert app.state.store.setting('active_company') in (None, first)


def test_analysis_background_uses_owner_then_session_company(app, admin, companies, monkeypatch):
    a, _ = companies
    store = app.state.store
    with store.db() as db:
        db.execute("UPDATE companies SET profile_json=json_set(profile_json,'$.industry','甲行业') WHERE id=?", (a.company_id,))
    captured = []
    analyse(app, a, add_event(a), monkeypatch, captured)
    assert captured[-1]['company']['name'] == '甲测试公司'
    selected = admin.post('/api/companies', json={'name': '管理员选中公司', 'industry': '选中行业', 'allow_external': True}).json()['id']
    admin_doc = add_event(admin, title='管理员资料')
    assert store.one('SELECT company_id FROM documents WHERE id=?', (admin_doc,))['company_id'] is None
    analyse(app, admin, admin_doc, monkeypatch, captured)
    assert captured[-1]['company']['name'] == '管理员选中公司' and selected
    a_doc = store.one("SELECT id FROM documents WHERE company_id=? AND kind='event' LIMIT 1", (a.company_id,))['id']
    with store.db() as db:
        db.execute("UPDATE jobs SET status='completed' WHERE document_id=?", (a_doc,))
    analyse(app, admin, a_doc, monkeypatch, captured)
    assert captured[-1]['company']['name'] == '甲测试公司'


# --- website ownership -----------------------------------------------------

def test_website_import_ownership(app, admin, monkeypatch):
    monkeypatch.setattr(websearch, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(websearch, 'fetch_page', fake_fetch)
    monkeypatch.setattr(websearch.model, 'call_model', fake_model)
    store = app.state.store
    run = process(admin, add_source(admin))
    page = next(p for p in run['items'] if p['relevant'])['id']
    assert admin.post('/api/web/import', json={'page_ids': [page], 'kind': 'event'}).status_code == 400
    assert admin.post('/api/web/import', json={'page_ids': [page], 'kind': 'event', 'company_id': 9999}).status_code == 400
    assert store.one('SELECT COUNT(*) n FROM documents')['n'] == 0
    knowledge = admin.post('/api/web/import', json={'page_ids': [page], 'kind': 'knowledge'}).json()['items'][0]['id']
    assert store.one('SELECT company_id FROM documents WHERE id=?', (knowledge,))['company_id'] is None
    selected = admin.post('/api/companies', json={'name': '网站归属公司', 'allow_external': True}).json()['id']
    event = admin.post('/api/web/import', json={'page_ids': [page], 'kind': 'event'}).json()['items'][0]['id']
    assert store.one('SELECT company_id FROM documents WHERE id=?', (event,))['company_id'] == selected
    audit = store.one("SELECT company_id FROM audit WHERE action='website_imported' ORDER BY id DESC LIMIT 1")
    assert audit['company_id'] == selected


def test_auto_import_source_requires_valid_target(admin):
    bad = admin.post('/api/web/sources', json={'name': '自动入库', 'url': 'https://source.example/news/',
                                               'keywords': '港口', 'auto_import': 'event', 'target_company_id': 9999})
    assert bad.status_code in (400, 404)


# --- legacy sessions ------------------------------------------------------

def test_legacy_session_without_role_is_rejected(app, admin):
    store = app.state.store
    with store.db() as db:
        db.execute("UPDATE sessions SET username=''")
    assert admin.get('/api/documents').status_code == 401
    assert store.one('SELECT COUNT(*) n FROM sessions')['n'] == 0
    assert admin.get('/api/auth/status').json().get('authenticated') is False


def test_migrate_clears_sessions(app, admin):
    from scripts.data_repair import migrate
    report = migrate(app.state.store.directory)
    assert report['sessions_cleared'] >= 1 and all(report['migrated'].values())
    assert admin.get('/api/documents').status_code == 401
