import asyncio
import copy
import json
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.store import DEFAULT_RULES
from app import websites, model

HEADERS = {'X-Requested-With': 'risk-workbench'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, search_api_key='isolated-search-key',
                        model_base_url='https://model.example/v1', model_name='test', model_api_key='isolated-model-key')
    app = create_app(settings, run_worker=False)
    async def search(settings, request):
        return app.state.search_rows
    monkeypatch.setitem(websites.PROVIDERS, 'tavily', search)
    app.state.search_rows = [{'url': 'https://example.com/news/a', 'title': '供电风险公告',
        'content': '检索摘要不作为原文证据', 'raw_content': '某工业园区供电设施故障，生产线暂停，需要核实恢复时间。',
        'published_date': '2026-10-09'}]
    with TestClient(app, headers=HEADERS) as c:
        assert c.post('/api/auth/setup', json={'password': 'website-tests-only'}).status_code == 200
        yield c


def source(c, url='https://example.com/news/'):
    r = c.post('/api/websites/sources', json={'name': '测试公告', 'url': url})
    assert r.status_code == 200, r.text
    return r.json()['id']


def search(c, ids, **kwargs):
    r = c.post('/api/websites/searches', json={'source_ids': ids, 'query': '供电', **kwargs})
    assert r.status_code == 200, r.text
    task_id = r.json()['id']
    asyncio.run(c.app.state.website_worker.process(c.app.state.store.one('SELECT * FROM website_searches WHERE id=?', (task_id,))))
    return c.get(f'/api/websites/searches/{task_id}').json()


def import_result(c, result, **kwargs):
    return c.post(f'/api/websites/results/{result["id"]}/import', json={'kind': 'knowledge', **kwargs})


def test_website_import_search_and_risk_analysis(client, monkeypatch):
    result = search(client, [source(client)])['items'][0]
    doc = import_result(client, result).json()
    assert doc['created']
    assert client.get('/api/knowledge/search?q=供电').json()['items'][0]['document_id'] == doc['id']
    event_id = import_result(client, result, kind='event').json()['id']
    assert event_id != doc['id']
    assert not client.get(f'/api/documents/{event_id}').json()['allow_external']
    rules = copy.deepcopy(DEFAULT_RULES)
    rules['confirmed'] = True
    assert client.put('/api/rules', json=rules).status_code == 200
    assert client.post('/api/jobs', json={'document_ids': [event_id]}).status_code == 400
    # Reimporting with a checked box must not escalate existing authorization.
    assert not import_result(client, result, kind='event', allow_external=True).json()['created']
    assert not client.get(f'/api/documents/{event_id}').json()['allow_external']
    assert client.patch(f'/api/documents/{event_id}/policy', json={'allow_external': True}).status_code == 200
    async def analyze(settings, payload):
        ref = next(r for r in payload['references'] if r['kind'] == 'source')
        assert not any(r['kind'] == 'knowledge' for r in payload['references'])
        return {'decision': 'risk', 'reason': '合成测试', 'events': [{'title': '供电中断', 'category': '环境与安全',
            'level': 'red', 'summary': '暂停生产', 'impact': '潜在影响：生产中断', 'recommendation': '核实恢复时间',
            'evidence': [{'reference': ref['reference'], 'quote': '供电设施故障，生产线暂停', 'reason': '支持停产判断'}]}]}, {}
    monkeypatch.setattr(model, 'call_model', analyze)
    job_id = client.post('/api/jobs', json={'document_ids': [event_id]}).json()['items'][0]['id']
    store = client.app.state.store
    asyncio.run(client.app.state.worker.process(store.one('SELECT * FROM jobs WHERE id=?', (job_id,))))
    assert store.one('SELECT status FROM jobs WHERE id=?', (job_id,))['status'] == 'completed'
    event = client.get('/api/events?demo=real').json()['items'][0]
    evidence = client.get(f'/api/events/{event["id"]}').json()['evidence'][0]
    assert evidence['document_id'] == event_id
    origin = client.get(f'/api/documents/{event_id}').json()['website_origin']
    assert origin['url'] == result['url'] and origin['version_id'] == result['version_id']


def test_versions_duplicates_and_distinct_origins(client):
    sid = source(client)
    first = search(client, [sid])['items'][0]
    original_id = import_result(client, first).json()['id']
    same = search(client, [sid])['items'][0]
    assert same['duplicate'] and same['version_id'] == first['version_id']
    assert import_result(client, same).json() == {'id': original_id, 'created': False, 'kind': 'knowledge'}
    client.app.state.search_rows[0]['raw_content'] += '最新公告：恢复时间推迟。'
    updated = search(client, [sid])['items'][0]
    assert updated['version_id'] != first['version_id']
    assert import_result(client, updated).json()['id'] != original_id
    assert '恢复时间推迟' not in client.get(f'/api/documents/{original_id}').json()['body']
    client.app.state.search_rows[0]['url'] = 'https://example.com/news/b'
    other = search(client, [sid])['items'][0]
    assert import_result(client, other).json()['id'] != import_result(client, updated).json()['id']


def test_scope_summary_dates_and_size(client):
    row = client.app.state.search_rows[0]
    client.app.state.search_rows = [
        {**row, 'url': 'https://example.com.evil.test/news/a'},
        {**row, 'url': 'https://example.com/newsletter/a'},
        {**row, 'url': 'https://example.com/news/a', 'final_url': 'https://other.example/news/a'},
        {**row, 'url': 'https://example.com/news/old', 'published_date': '2020-01-01'},
        {**row, 'url': 'https://example.com/news/summary', 'raw_content': None},
        {**row, 'url': 'https://example.com/news/large', 'raw_content': 'x' * 60001},
        {**row, 'url': 'https://example.com/news/unknown', 'published_date': ''},
        {**row, 'url': 'https://example.com/news/dated', 'published_date': '2026-10-09T11:23:00Z'},
    ]
    result = search(client, [source(client)], date_from='2026-10-01', date_to='2026-10-10')
    assert result['task']['status'] == 'partial' and result['task']['rejected'] == 4
    assert len(result['items']) == 4
    for item in result['items']:
        r = import_result(client, item)
        assert r.status_code == (200 if item['url'].endswith('/dated') else 409)
    assert client.app.state.store.one('SELECT COUNT(*) n FROM documents')['n'] == 1


@pytest.mark.parametrize('url', ['http://example.com/', 'https://127.0.0.1/', 'https://10.0.0.1/',
    'https://localhost/', 'https://host.internal/', 'https://user:pass@example.com/',
    'https://example.com:8443/', 'https://example.com/news/%252e%252e/admin', 'https://example.com/news?redirect=x'])
def test_invalid_source_urls(client, url):
    assert client.post('/api/websites/sources', json={'name': '测试', 'url': url}).status_code == 400


def test_task_validation_authentication_and_idempotency(client):
    sid = source(client)
    assert client.post('/api/websites/sources', json={'name': '重复', 'url': 'https://example.com/news/'}).status_code == 409
    body = {'source_ids': [sid], 'query': '供电'}
    first = client.post('/api/websites/searches', json=body).json()
    assert client.post('/api/websites/searches', json=body).json() == {'id': first['id'], 'created': False}
    assert client.post('/api/websites/searches', json={**body, 'query': ' '}).status_code == 400
    assert client.post('/api/websites/searches', json={**body, 'date_from': '2026-10-10', 'date_to': '2026-10-01'}).status_code == 400
    assert client.post('/api/websites/searches', json={**body, 'limit': 21}).status_code == 422
    assert client.put(f'/api/websites/sources/{sid}', json={'name': '停用', 'url': 'https://example.com/news/', 'enabled': False}).status_code == 200
    assert client.post('/api/websites/searches', json=body).status_code == 400
    assert 'isolated-search-key' not in client.get('/api/websites/config').text
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/websites/sources').status_code == 401
    assert client.post('/api/websites/sources', headers={'X-Requested-With': ''}, json={}).status_code == 403


def test_ignore_failure_and_restart(client, monkeypatch):
    sid = source(client)
    item = search(client, [sid])['items'][0]
    assert client.post(f'/api/websites/results/{item["id"]}/ignore').status_code == 200
    assert import_result(client, item).status_code == 409
    async def failed(settings, request):
        raise httpx.ConnectError('must not expose sensitive diagnostics')
    monkeypatch.setitem(websites.PROVIDERS, 'tavily', failed)
    failure = search(client, [sid])
    assert failure['task']['status'] == 'failed'
    assert 'sensitive' not in failure['task']['error']
    store = client.app.state.store
    with store.db() as db:
        db.execute("UPDATE website_searches SET status='running' WHERE id=?", (failure['task']['id'],))
    websites.initialize(store)
    assert '重启' in store.one('SELECT error FROM website_searches WHERE id=?', (failure['task']['id'],))['error']
    client.app.state.settings.search_api_key = ''
    assert client.post('/api/websites/searches', json={'source_ids': [sid], 'query': '供电'}).status_code == 409


def test_tavily_protocol_and_failure(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path, search_api_key='transport-test-only')
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))])
    actual_client = httpx.AsyncClient
    seen = []
    def handler(request):
        assert str(request.url) == 'https://api.tavily.com/search'
        assert request.headers['authorization'] == 'Bearer transport-test-only'
        payload = json.loads(request.content)
        assert payload['include_domains'] == ['example.com']
        assert payload['include_raw_content'] == 'text' and not payload['include_answer']
        assert payload['start_date'] == '2026-10-01'
        seen.append(payload)
        return httpx.Response(200, json={'results': [{'title': '协议测试', 'url': 'https://example.com/a', 'raw_content': '来源正文'}]})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: actual_client(transport=httpx.MockTransport(handler), **kwargs))
    request = {'sources': [{'url': 'https://example.com/news/'}], 'query': '供电', 'limit': 5, 'date_from': '2026-10-01'}
    assert asyncio.run(websites.tavily_search(settings, request))[0]['raw_content'] == '来源正文'
    assert len(seen) == 1
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: actual_client(transport=httpx.MockTransport(lambda r: httpx.Response(429, text='secret response')), **kwargs))
    with pytest.raises(ValueError, match='HTTP 429'):
        asyncio.run(websites.tavily_search(settings, request))
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    with pytest.raises(ValueError, match='公开地址'):
        asyncio.run(websites.tavily_search(settings, request))
