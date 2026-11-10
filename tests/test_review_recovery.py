import asyncio
import json
import socket

import pytest

from app import websearch as web
from test_websearch import add_source, fake_fetch, fake_model, process, web_client


def test_quote_repair_selects_exact_original_without_changing_decision(web_client, monkeypatch):
    monkeypatch.setattr(web, 'fetch_page', fake_fetch)
    calls = []

    async def model(settings, payload, system=None):
        calls.append(system)
        if system == web.QUOTE_REPAIR_SYSTEM:
            page_id = payload['pages'][0]['id']
            unit = next(u for u in payload['citation_units'] if u['reference'] == str(page_id))
            return {'items': [{'id': page_id, 'unit_id': unit['unit_id']}]}, {'total_tokens': 11}
        return {'items': [{'id': p['id'], 'relevant': True, 'reason': '原文涉及港口供应中断',
                           'quote': '模型改写后的不连续文字，不得直接接受'} for p in payload['pages']]}, {'total_tokens': 12}

    monkeypatch.setattr(web.model, 'call_model', model)
    run = process(web_client, add_source(web_client, max_pages=1))
    page = run['items'][0]
    original = web_client.get('/api/web/pages/' + str(page['id'])).json()
    assert page['quote'] in original['body']
    assert page['reason'] == '原文涉及港口供应中断' and page['relevant'] == 1
    assert page['review_origin'] == 'quote_repair'
    assert run['model_responses'] == 2 and not run['error']
    assert calls == [web.SEARCH_SYSTEM, web.QUOTE_REPAIR_SYSTEM]
    assert not web_client.get('/api/documents').json()['items']


@pytest.mark.parametrize('patch_kind', ['cross_page', 'unknown', 'change_decision', 'duplicate'])
def test_invalid_quote_patch_never_bypasses_validation(web_client, monkeypatch, patch_kind):
    collector = web_client.app.state.collector
    pages = [{'id': 1, 'title': '甲', 'body': '港口出现设备故障，库存仅余三天。'},
             {'id': 2, 'title': '乙', 'body': '有关部门发布新的劳工工资条例。'}]

    async def model(settings, payload, system=None):
        if system == web.SEARCH_SYSTEM:
            return {'items': [{'id': 1, 'relevant': True, 'reason': '有供应问题', 'quote': '并不存在的引文'},
                              {'id': 2, 'relevant': False, 'reason': '主题不相关', 'quote': ''}]}, {}
        unit_id = '2:1' if patch_kind == 'cross_page' else ('missing' if patch_kind == 'unknown' else '1:1')
        item = {'id': 1, 'unit_id': unit_id}
        if patch_kind == 'change_decision': item['relevant'] = False
        return {'items': [item, item] if patch_kind == 'duplicate' else [item]}, {}

    monkeypatch.setattr(web.model, 'call_model', model)
    issues = {}
    verdicts = asyncio.run(collector.review({'keywords': '港口'}, pages, [], issues))
    assert 1 not in verdicts and verdicts[2][0] is False
    assert '连续原文' in issues[1] and '仍未通过' in issues[1]


def test_duplicate_page_verdicts_rejected_with_specific_reason(web_client, monkeypatch):
    async def model(*args, **kwargs):
        item = {'id': 1, 'relevant': False, 'reason': '无关', 'quote': ''}
        return {'items': [item, item]}, {}

    monkeypatch.setattr(web.model, 'call_model', model)
    issues = {}
    verdicts = asyncio.run(web_client.app.state.collector.review(
        {'keywords': '港口'}, [{'id': 1, 'title': '公告', 'body': '真实的原文内容。'}], [], issues))
    assert not verdicts and '重复' in issues[1]


def test_paused_source_manual_run_keeps_schedule_off_and_status_visible(web_client, monkeypatch):
    monkeypatch.setattr(web, 'fetch_page', fake_fetch)
    monkeypatch.setattr(web.model, 'call_model', fake_model)
    sid = add_source(web_client, max_pages=1, category='公开资料', interval_hours=24)
    web_client.post(f'/api/web/sources/{sid}/toggle', json={'enabled': False})
    run = process(web_client, sid)
    source = web_client.get('/api/web/sources').json()['items'][0]
    assert source['enabled'] == 0 and source['interval_hours'] == 24
    assert run['status'] == 'completed' and source['last_pages'] == 1 and source['last_undecided'] == 0
    assert source['run_count'] == 1 and source['ok_count'] == 1
    assert run['items'][0]['review_origin'] == 'model' and run['model_responses'] == 1
    assert web_client.post('/api/web/runs/group', json={'category': '公开资料'}).status_code == 400


def test_review_only_not_counted_as_new_fetch_and_unverified_exposed(web_client, monkeypatch):
    monkeypatch.setattr(web, 'fetch_page', fake_fetch)

    async def invalid(*args, **kwargs): return {'items': []}, {'total_tokens': 1}

    monkeypatch.setattr(web.model, 'call_model', invalid)
    sid = add_source(web_client, max_pages=1)
    run = process(web_client, sid)
    assert run['items'][0]['relevant'] is None
    assert '模型未返回' in run['items'][0]['reason']
    assert web_client.post(f"/api/web/runs/{run['id']}/review").status_code == 200
    queued = web_client.app.state.store.one('SELECT * FROM web_runs WHERE id=?', (run['id'],))
    asyncio.run(web_client.app.state.collector.process(queued))
    source = web_client.get('/api/web/sources').json()['items'][0]
    assert source['last_review_only'] == 1 and source['last_undecided'] == 1
    assert source['run_count'] == 1 and source['ok_count'] == 1


def test_403_html_tries_isolated_renderer_before_archive(web_client, monkeypatch):
    def fetch(url, *args, **kwargs):
        if url.endswith('robots.txt'): return url, '', b'', 'text/plain'
        raise web.HttpStatus(403)

    def render(url):
        html = '<title>原料供应通报</title><article>港口设备故障导致原料延迟七天，库存仅能维持三天生产。</article>'
        return url, html

    monkeypatch.setattr(web, 'fetch_page', fetch)
    monkeypatch.setattr(web, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(web, 'RENDERER', ('127.0.0.1', 8791, '/render'))
    monkeypatch.setattr(web, 'public_address', lambda *args: '8.8.8.8')
    monkeypatch.setattr(web, 'render_page', render)
    monkeypatch.setattr(web.model, 'call_model', fake_model)
    run = process(web_client, add_source(web_client, max_pages=1))
    assert run['status'] == 'completed' and run['items'][0]['method'] == 'render'
    assert run['items'][0]['relevant'] == 1


@pytest.mark.parametrize('status', [401, 404, 410, 429])
def test_renderer_not_used_to_bypass_auth_missing_page_or_rate_limit(web_client, monkeypatch, status):
    def fetch(url, *args, **kwargs):
        if url.endswith('robots.txt'): return url, '', b'', 'text/plain'
        raise web.HttpStatus(status)

    def render(*args): raise AssertionError('Must not render this response')

    monkeypatch.setattr(web, 'fetch_page', fetch)
    monkeypatch.setattr(web, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(web, 'RENDERER', ('127.0.0.1', 8791, '/render'))
    monkeypatch.setattr(web, 'render_page', render)
    run = process(web_client, add_source(web_client, max_pages=1))
    assert run['status'] == 'failed'


def test_trusted_public_dns_stays_allowlisted_and_rejects_private_answers(monkeypatch):
    class Response:
        status = 200

        def read(self, limit):
            return json.dumps({'Status': 0, 'Question': [{'name': 'newsroom.tiktok.com.', 'type': 1}],
                               'Answer': [{'type': 1, 'TTL': 30, 'data': '10.0.0.1'}]}).encode()

    class Connection:
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass

    monkeypatch.setattr(web, 'PUBLIC_DNS_CACHE', {})
    monkeypatch.setattr(web, 'PinnedConnection', Connection)
    with pytest.raises(ValueError, match='不允许'): web.trusted_public_address('attacker.example')
    with pytest.raises(ValueError, match='公网地址'): web.trusted_public_address('newsroom.tiktok.com')


def test_poisoned_vetted_domain_uses_public_answer_but_private_hosts_still_rejected(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    monkeypatch.setattr(web, 'trusted_public_address', lambda host: '23.46.230.110')
    assert web.public_address('newsroom.tiktok.com', 443) == '23.46.230.110'
    for host in ('127.0.0.1', 'localhost', 'example.com', '169.254.169.254'):
        with pytest.raises(ValueError): web.public_address(host, 443)
