import asyncio
import json
import secrets
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app import websearch
from app.config import Settings
from app.ingest import insert_document, validate_record
from app.main import create_app
from app.store import Store
from scripts import data_repair
from test_websearch import add_source, fake_fetch, fake_model, process

HEADERS = {'X-Requested-With': 'risk-workbench'}


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'data', model_mode='external', model_base_url='https://example.com/v1',
                              model_name='test', model_api_key='test'), run_worker=False)
    store = app.state.store
    rules = store.setting('rules')
    rules['confirmed'] = True
    store.set_setting('rules', rules)
    with TestClient(app, headers=HEADERS) as c:
        c.post('/api/auth/setup', json={'password': secrets.token_urlsafe(16)})
        yield c


# --- ingest dates -----------------------------------------------------------

def test_validate_record_never_invents_a_date():
    assert validate_record({'title': '无日期资料', 'body': '正文中提到 2024-01-05 的会议安排。'})['date'] == ''
    with pytest.raises(ValueError):
        validate_record({'title': 't', 'body': 'b', 'date': '2024/01/05'})


def test_insert_document_records_date_source(tmp_path):
    store = Store(tmp_path)
    dated, _ = insert_document(store, {'title': 'a', 'body': '正文一', 'date': '2024-02-02'})
    undated, _ = insert_document(store, {'title': 'b', 'body': '正文二'})
    fed, _ = insert_document(store, {'title': 'c', 'body': '正文三', 'date': '2024-03-03'},
                             meta={'date_source': 'feed', 'archived_at': '2024-03-04', 'fetched_at': '2024-03-05T00:00:00'})
    rows = {r['id']: r for r in store.rows('SELECT id,date,date_source,archived_at,fetched_at FROM documents')}
    assert rows[dated]['date_source'] == 'provided'
    assert rows[undated]['date'] == '' and rows[undated]['date_source'] == ''
    assert rows[fed]['date_source'] == 'feed' and rows[fed]['archived_at'] == '2024-03-04'


def test_startup_marks_unknown_dates_as_legacy_once(tmp_path):
    store = Store(tmp_path)
    with store.db() as db:
        db.execute("""INSERT INTO documents(title,body,date,kind,allow_external,demo,digest,created_at,date_source)
                      VALUES ('旧资料','旧正文','2023-01-01','event',0,0,'d1','2024-01-01T00:00:00+00:00','')""")
    store = Store(tmp_path)
    assert store.one('SELECT date_source FROM documents')['date_source'] == 'legacy'
    with store.db() as db:
        db.execute("UPDATE documents SET date_source='removed', date='', date_legacy='2023-01-01'")
    store = Store(tmp_path)
    assert store.one('SELECT date_source FROM documents')['date_source'] == 'removed'


@pytest.mark.parametrize('method,title,expected,archived', [
    ('direct', '原料供应通报', 'page_meta', ''),
    ('rss', '原料供应通报', 'feed', ''),
    ('api', '原料供应通报', 'api', ''),
    ('archive', '［网页存档 2024-06-01］原料供应通报', 'page_meta', '2024-06-01'),
])
def test_website_import_keeps_date_provenance(client, monkeypatch, method, title, expected, archived):
    monkeypatch.setattr(websearch, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(websearch, 'fetch_page', fake_fetch)
    monkeypatch.setattr(websearch.model, 'call_model', fake_model)
    store = client.app.state.store
    run = process(client, add_source(client))
    page = next(p for p in run['items'] if p['relevant'])['id']
    with store.db() as db:
        db.execute('UPDATE web_pages SET date=?,method=?,title=? WHERE id=?', ('2024-05-20', method, title, page))
    doc = client.post('/api/web/import', json={'page_ids': [page], 'kind': 'knowledge'}).json()['items'][0]['id']
    row = store.one('SELECT date,date_source,archived_at,fetched_at FROM documents WHERE id=?', (doc,))
    assert row['date'] == '2024-05-20' and row['date_source'] == expected
    assert row['archived_at'] == archived and row['fetched_at']


def test_website_import_without_page_date_stays_undated(client, monkeypatch):
    monkeypatch.setattr(websearch, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(websearch, 'fetch_page', fake_fetch)
    monkeypatch.setattr(websearch.model, 'call_model', fake_model)
    run = process(client, add_source(client))
    page = next(p for p in run['items'] if p['relevant'])['id']
    doc = client.post('/api/web/import', json={'page_ids': [page], 'kind': 'knowledge'}).json()['items'][0]['id']
    row = client.app.state.store.one('SELECT date,date_source FROM documents WHERE id=?', (doc,))
    assert row['date'] == '' and row['date_source'] == ''


# --- date repair ------------------------------------------------------------

def legacy_doc(db, title, date, created='2024-07-01T08:00:00+00:00', body='正文内容', file_path=''):
    return db.execute(
        """INSERT INTO documents(title,body,date,kind,allow_external,demo,digest,created_at,date_source,file_path)
           VALUES (?,?,?,'knowledge',1,0,?,?,'legacy',?)""",
        (title, body, date, secrets.token_hex(8), created, file_path),
    ).lastrowid


@pytest.fixture
def legacy(tmp_path):
    data = tmp_path / 'data'
    store = Store(data)
    from app import companies
    companies.initialize(store)
    websearch.initialize(store)
    with store.db() as db:
        run = db.execute("INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (1,'{}','completed','x')").lastrowid

        def page(snapshot, date, method='direct', title='页面'):
            db.execute("""INSERT INTO web_pages(run_id,url,title,body,date,fetched_at,digest,snapshot,method)
                          VALUES (?,?,?,?,?,?,?,?,?)""",
                       (run, f'https://e.example/{snapshot}', title, 'b', date, '2024-07-02T00:00:00+00:00',
                        secrets.token_hex(8), snapshot, method))
        page('s1.html', '')
        page('s3.html', '2023-01-02', method='rss')
        ids = {
            'web_no_page_date': legacy_doc(db, '网页一', '2024-07-01', file_path='s1.html'),
            'archive_stamp_match': legacy_doc(db, '［网页存档 2024-03-03］旧页面', '2024-03-03'),
            'web_page_date_match': legacy_doc(db, '网页三', '2023-01-02', file_path='s3.html'),
            'import_day_match': legacy_doc(db, '手工资料', '2024-07-01'),
            'text_first_date_match': legacy_doc(db, '公告', '2022-09-09', body='2022-09-09 发布的公告正文'),
            'keep_legacy': legacy_doc(db, '其他资料', '2021-01-01'),
        }
    return data, ids


def test_date_audit_classifies_every_case(legacy, tmp_path):
    data, ids = legacy
    report = data_repair.date_audit(data, tmp_path / 'report.json')
    got = {item['id']: (item['classification'], item['action']) for item in report['items']}
    expected_action = {'web_no_page_date': 'clear', 'archive_stamp_match': 'clear', 'web_page_date_match': 'mark',
                       'import_day_match': 'clear', 'text_first_date_match': 'review', 'keep_legacy': 'keep'}
    assert got == {ids[name]: (name, action) for name, action in expected_action.items()}
    marked = next(i for i in report['items'] if i['id'] == ids['web_page_date_match'])
    assert marked['mark_source'] == 'feed'


def test_date_apply_is_idempotent_backed_up_and_reversible(legacy, tmp_path):
    data, ids = legacy
    report = tmp_path / 'report.json'
    data_repair.date_audit(data, report)
    before = {r['id']: dict(r) for r in Store(data).rows('SELECT id,date,date_source,date_legacy FROM documents')}
    counts = data_repair.date_apply(data, report, exclude=str(ids['import_day_match']), backup=tmp_path / 'b1.db')
    assert counts == {'cleared': 2, 'marked': 1, 'kept': 3, 'unchanged': 0}
    assert (tmp_path / 'b1.db').exists()
    backup = sqlite3.connect(tmp_path / 'b1.db')
    assert backup.execute("SELECT COUNT(*) FROM documents WHERE date_source='legacy'").fetchone()[0] == 6
    backup.close()
    store = Store(data)
    rows = {r['id']: r for r in store.rows('SELECT id,date,date_source,date_legacy FROM documents')}
    cleared = rows[ids['web_no_page_date']]
    assert cleared['date'] == '' and cleared['date_source'] == 'removed' and cleared['date_legacy'] == '2024-07-01'
    assert rows[ids['web_page_date_match']]['date_source'] == 'feed'
    assert rows[ids['import_day_match']]['date_source'] == 'legacy'
    assert rows[ids['text_first_date_match']]['date_source'] == 'legacy'
    again = data_repair.date_apply(data, report, exclude=str(ids['import_day_match']), backup=tmp_path / 'b2.db')
    assert again == {'cleared': 0, 'marked': 0, 'kept': 3, 'unchanged': 3}
    assert store.one("SELECT COUNT(*) n FROM audit WHERE action='dates_repaired'")['n'] == 2
    log = json.loads((tmp_path / 'report.json.applied.json').read_text(encoding='utf-8'))
    assert len(log['changes']) == 3
    assert data_repair.date_revert(data, tmp_path / 'report.json.applied.json') == 3
    after = {r['id']: dict(r) for r in Store(data).rows('SELECT id,date,date_source,date_legacy FROM documents')}
    assert after == before


def test_date_apply_include_review_and_backup_refuses_overwrite(legacy, tmp_path):
    data, ids = legacy
    report = tmp_path / 'report.json'
    data_repair.date_audit(data, report)
    data_repair.date_apply(data, report, include_review=True, backup=tmp_path / 'b.db')
    assert Store(data).one('SELECT date FROM documents WHERE id=?', (ids['text_first_date_match'],))['date'] == ''
    with pytest.raises(ValueError):
        data_repair.date_apply(data, report, backup=tmp_path / 'b.db')


def test_date_apply_aborts_when_database_changed(legacy, tmp_path):
    data, _ = legacy
    report = tmp_path / 'report.json'
    data_repair.date_audit(data, report)
    with Store(data).db() as db:
        legacy_doc(db, '审计后新增', '2020-01-01')
    with pytest.raises(ValueError, match='指纹'):
        data_repair.date_apply(data, report, backup=tmp_path / 'b.db')
    assert not (tmp_path / 'b.db').exists()


def test_date_audit_is_read_only(legacy, tmp_path):
    data, _ = legacy
    before = (data / 'risk.db').read_bytes()
    data_repair.date_audit(data, tmp_path / 'r.json')
    assert Store(data).one("SELECT COUNT(*) n FROM documents WHERE date_source='legacy'")['n'] == 6
    assert len(before) > 0


# --- quarantine -------------------------------------------------------------

def analysed_event(client, monkeypatch, title='园区核查通知'):
    doc = client.post('/api/documents', json={'title': title, 'body': '园区企业需在月底前提交年度核查材料，逾期暂停采购。',
                                              'kind': 'event', 'allow_external': True, 'date': '2024-04-04'}).json()['id']
    job = client.post('/api/jobs', json={'document_ids': [doc]}).json()['items'][0]['id']

    async def fake(_settings, payload, **_kwargs):
        ref = [r['reference'] for r in payload['references'] if r['reference'].startswith('S')][0]
        return {'decision': 'risk', 'reason': '测试', 'events': [{
            'title': f'{title}风险', 'category': '准入审批限制风险', 'level': 'lv1', 'summary': '逾期暂停采购',
            'impact': '影响生产', 'recommendation': '按期提交',
            'evidence': [{'reference': ref, 'quote': '园区企业需在月底前提交年度核查材料', 'reason': '直接说明'}]}]}, {}
    monkeypatch.setattr('app.jobs.model.call_model', fake)
    store = client.app.state.store
    asyncio.run(client.app.state.worker.process(store.one('SELECT * FROM jobs WHERE id=?', (job,))))
    event = store.one('SELECT e.id FROM events e JOIN analyses a ON a.id=e.analysis_id WHERE a.document_id=?', (doc,))['id']
    return doc, event


def test_quarantine_dry_run_mismatch_and_apply(client, monkeypatch, tmp_path):
    store = client.app.state.store
    data = store.directory
    doc, event = analysed_event(client, monkeypatch)
    keep_doc, keep_event = analysed_event(client, monkeypatch, title='保留资料')
    knowledge, _ = insert_document(store, {'title': '可疑法规', 'body': '外籍劳工可疑法规正文内容。', 'source': 's'}, 'knowledge', True)
    ids = f'{doc},{knowledge}'
    dry = data_repair.quarantine(data, ids, str(event), '来源存疑', tmp_path / 'ev', apply=False)
    assert dry['applied'] is False and not (tmp_path / 'ev').exists()
    assert store.one('SELECT quarantined_at FROM documents WHERE id=?', (doc,))['quarantined_at'] is None
    with pytest.raises(ValueError, match='关联事件不匹配'):
        data_repair.quarantine(data, ids, f'{event},{keep_event}', '来源存疑', tmp_path / 'ev', apply=True)
    with pytest.raises(ValueError, match='数据目录之外'):
        data_repair.quarantine(data, ids, str(event), '来源存疑', data / 'ev', apply=True)
    queued = store.one('SELECT id FROM jobs WHERE document_id=? ORDER BY id DESC', (doc,))['id']
    with store.db() as db:
        db.execute("UPDATE jobs SET status='queued' WHERE id=?", (queued,))
    result = data_repair.quarantine(data, ids, str(event), '来源存疑', tmp_path / 'ev', apply=True)
    assert result['quarantined'] == [doc, knowledge]
    row = store.one('SELECT * FROM documents WHERE id=?', (doc,))
    assert row['quarantined_at'] and row['quarantine_reason'] == '来源存疑'
    assert row['date'] == '' and row['date_legacy'] == '2024-04-04' and row['date_source'] == 'removed'
    assert row['allow_external'] == 0
    assert store.one('SELECT status FROM jobs WHERE id=?', (queued,))['status'] == 'cancelled'
    manifest = json.loads((tmp_path / 'ev' / 'manifest.json').read_text(encoding='utf-8'))
    evidence = json.loads((tmp_path / 'ev' / 'evidence.json').read_text(encoding='utf-8'))
    assert 'evidence.json' in manifest and {d['id'] for d in evidence['documents']} == {doc, knowledge}
    assert [e['id'] for e in evidence['events']] == [event]
    assert (tmp_path / 'ev' / 'database-before.db').exists()
    assert (tmp_path / 'ev').stat().st_mode & 0o777 == 0o700
    audits = store.rows("SELECT detail,company_id FROM audit WHERE action='documents_quarantined'")
    assert len(audits) == 2 and any(f'events={event}' in a['detail'] for a in audits)

    # Excluded from listings, statistics, reports, exports, search and analysis.
    assert [e['id'] for e in client.get('/api/events').json()['items']] == [keep_event]
    assert client.get('/api/overview').json()['total'] == 1
    assert [i['id'] for i in client.get('/api/report').json()['items']] == [keep_event]
    assert '园区核查通知风险' not in client.get('/api/export/events').text
    assert knowledge not in [i['document_id'] for i in client.get('/api/knowledge/search?q=外籍劳工').json()['items']]
    assert client.post('/api/jobs', json={'document_ids': [doc]}).status_code == 400
    flight = client.post('/api/jobs/preflight', json={'document_ids': [doc]}).json()
    assert '资料已隔离（待核实）' in flight['items'][0]['issues'] and flight['ready'] is False
    opened = client.get(f'/api/events/{event}')
    assert opened.status_code == 200 and opened.json()['quarantined_at']
    assert client.delete(f'/api/documents/{doc}').status_code == 409
    assert client.patch(f'/api/documents/{doc}/policy', json={'allow_external': True}).status_code == 404
    listed = {r['id']: r for r in client.get('/api/documents?kind=event').json()['items']}
    assert listed[doc]['quarantined_at'] and keep_doc in listed

    # Re-running is a no-op; unquarantine restores visibility but not the removed date.
    again = data_repair.quarantine(data, ids, str(event), '来源存疑', tmp_path / 'ev2', apply=True)
    assert again.get('skipped') is True and not (tmp_path / 'ev2').exists()
    assert data_repair.unquarantine(data, str(doc), '核实无误', apply=True) == [doc]
    assert data_repair.unquarantine(data, str(doc), '核实无误', apply=True) == []
    restored = store.one('SELECT quarantined_at,date,allow_external FROM documents WHERE id=?', (doc,))
    assert restored['quarantined_at'] is None and restored['date'] == '' and restored['allow_external'] == 0
    assert event in [e['id'] for e in client.get('/api/events').json()['items']]


def test_quarantine_rejects_missing_documents(client, tmp_path):
    with pytest.raises(ValueError, match='目标资料不完整'):
        data_repair.quarantine(client.app.state.store.directory, '999', '', '原因', tmp_path / 'ev', apply=True)
    with pytest.raises(ValueError):
        data_repair.quarantine(client.app.state.store.directory, '999', '', '  ', tmp_path / 'ev', apply=True)
