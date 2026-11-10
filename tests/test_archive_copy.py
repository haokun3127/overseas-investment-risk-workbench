import gzip
import hashlib
import json
from datetime import datetime, timezone

import pytest

from app import websearch as web
from app.archive_copy import ORIGINAL, TARGET, TITLE, _digest, read_archive_copy
from test_websearch import add_source, process, web_client


def write_archive(directory, *, target=TARGET, status='200 OK', date='2022-10-12', section=True,
                  warc_digest=None, payload_digest=None, extra=b''):
    root = directory / 'archive-copies'
    root.mkdir(exist_ok=True)
    html = ('<html><title>' + TITLE + '</title><h3>' + TITLE + '</h3>'
            '<div class="ly mt20 center">来源：中国上市公司协会&nbsp; 发布时间：' + date + '</div>'
            '<article>一、公司简介 二、杜库达油化工厂项目情况 三、社会责任 '
            + ('四、海外投资遇到的风险挑战 ' if section else '')
            + '杜库达工厂需要加强跨国业务整合和管理。' * 110 + '</article></html>')
    body = html.encode()
    block = (f'HTTP/1.1 {status}\r\nContent-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n'.encode() + body)
    captured = '2024-10-03T22:36:10Z'
    record = '<urn:uuid:8344e1a3-17e6-4e7a-afc4-6388eb8418c9>'
    head = (f'WARC/1.0\r\nWARC-Type: response\r\nContent-Length: {len(block)}\r\n'
            f'WARC-Target-URI: {target}\r\nWARC-Record-ID: {record}\r\nWARC-Date: {captured}\r\n'
            f'WARC-Block-Digest: sha1:{warc_digest or _digest(block)}\r\n'
            f'WARC-Payload-Digest: sha1:{payload_digest or _digest(body)}\r\n\r\n')
    compressed = gzip.compress(head.encode() + block + b'\r\n\r\n' + extra)
    filename = 'capco-zanyu.warc.gz'
    (root / filename).write_bytes(compressed)
    path = 'crawl-data/CC-MAIN-2024-42/segments/1727944253246.33/warc/CC-MAIN-20241003220556-20241004010556-00601.warc.gz'
    item = dict(url=ORIGINAL, target_url=TARGET, provider='Common Crawl', collection='CC-MAIN-2024-42',
                warc_path=path, retrieval_url='https://data.commoncrawl.org/' + path,
                file=filename, sha256=hashlib.sha256(compressed).hexdigest(), length=len(compressed),
                offset=636250000, record_id=record, captured_at=captured, payload_digest=_digest(body),
                retrieved_at=datetime.now(timezone.utc).isoformat())
    save(root, [item])
    return root, item, html


def save(root, items):
    (root / 'manifest.json').write_text(json.dumps({'version': 1, 'items': items}), encoding='utf-8')


def test_valid_warc_preserves_html_and_separates_all_dates(tmp_path):
    _, item, html = write_archive(tmp_path)
    result = read_archive_copy(tmp_path, ORIGINAL)
    assert result['html'] == html and result['raw'] == html.encode()
    assert result['date'] == '2022-10-12' and result['archived_at'] == '2024-10-03'
    assert result['retrieved_at'] == item['retrieved_at']
    assert read_archive_copy(tmp_path, TARGET)['raw'] == html.encode()


@pytest.mark.parametrize('url', [TARGET+'?v=1', TARGET+'#x', TARGET.replace('https:', 'http:'),
                                TARGET.replace('www.capco.org.cn', '127.0.0.1'), TARGET+'x'])
def test_archive_cannot_be_used_for_other_urls(tmp_path, url):
    write_archive(tmp_path)
    assert read_archive_copy(tmp_path, url) is None


def test_missing_archive_returns_none(tmp_path):
    assert read_archive_copy(tmp_path, ORIGINAL) is None


@pytest.mark.parametrize('change', [
    {'file': '../outside.warc.gz'}, {'sha256': '0'*64}, {'length': 0}, {'offset': -1},
    {'provider': 'Search snippet'}, {'target_url': 'https://untrusted.example/'},
    {'retrieval_url': 'https://untrusted.example/file'}, {'collection': '../other'},
    {'warc_path': 'crawl-data/../private'}, {'record_id': '<urn:uuid:wrong>'},
    {'captured_at': '2024-10-04T22:36:10Z'}, {'retrieved_at': '2024-10-02T00:00:00Z'},
    {'retrieved_at': '2026-01-01'}, {'payload_digest': 'WRONG'},
])
def test_invalid_provenance_never_used(tmp_path, change):
    root, item, _ = write_archive(tmp_path)
    save(root, [dict(item, **change)])
    with pytest.raises(ValueError):
        read_archive_copy(tmp_path, ORIGINAL)


@pytest.mark.parametrize('changes', [
    {'target': 'https://wrong.example/'}, {'status': '304 Not Modified'},
    {'warc_digest': 'WRONG'}, {'payload_digest': 'WRONG'}, {'extra': b'WARC/1.0\r\n'},
    {'date': '2024-10-03'}, {'section': False},
])
def test_hash_alone_does_not_accept_incomplete_or_wrong_response(tmp_path, changes):
    write_archive(tmp_path, **changes)
    with pytest.raises(ValueError):
        read_archive_copy(tmp_path, ORIGINAL)


def test_duplicate_manifest_entry_is_rejected(tmp_path):
    root, item, _ = write_archive(tmp_path)
    save(root, [item, item])
    with pytest.raises(ValueError, match='多个存档'):
        read_archive_copy(tmp_path, ORIGINAL)


def test_archive_fallback_reviews_real_extracted_body(web_client, monkeypatch):
    c = web_client
    _, item, html = write_archive(c.app.state.store.directory)
    def empty_page(url, *a, **k):
        if url.endswith('robots.txt'):
            return url, '', b'', 'text/plain'
        text = '<html><div id="app"></div></html>'
        return url, text, text.encode(), 'text/html'
    calls = []
    async def model(settings, payload, system=None):
        calls.append(payload)
        return {'items': [{'id': p['id'], 'relevant': True, 'reason': 'Management risk.',
                           'quote': '杜库达工厂需要加强跨国业务整合和管理。'} for p in payload['pages']]}, {'total_tokens': 20}
    monkeypatch.setattr(web, 'RENDERER', '')
    monkeypatch.setattr(web, 'fetch_page', empty_page)
    monkeypatch.setattr(web.model, 'call_model', model)
    run = process(c, add_source(c, url=ORIGINAL, max_pages=1))
    assert run['status'] == 'completed' and len(calls) == 1
    page = c.get('/api/web/pages/' + str(run['items'][0]['id'])).json()
    assert page['method'] == 'archive_copy' and page['url'] == ORIGINAL
    assert page['archived_at'] == '2024-10-03' and page['title'].startswith('［网页存档 2024-10-03］')
    assert page['date'] == '2022-10-12' and page['date_source'] == 'page_text'
    assert page['fetched_at'] == item['retrieved_at'] and run['items'][0]['quote'] in page['body']
    assert run['items'][0]['relevant'] == 1 and run['errors']
    assert not c.get('/api/documents').json()['items']
    stored = c.app.state.store.one('SELECT snapshot FROM web_pages WHERE id=?', (page['id'],))
    assert (c.app.state.store.directory/'uploads'/stored['snapshot']).read_bytes() == html.encode()


def test_robots_disallow_prevents_archive_fallback(web_client, monkeypatch):
    c = web_client
    write_archive(c.app.state.store.directory)
    def blocked(url, *a, **k):
        if url.endswith('robots.txt'):
            text = 'User-agent: *\nDisallow: /\n'
            return url, text, text.encode(), 'text/plain'
        raise AssertionError('Must not fetch disallowed page')
    monkeypatch.setattr(web, 'fetch_page', blocked)
    run = process(c, add_source(c, url=ORIGINAL, max_pages=1))
    assert run['status'] == 'failed' and not run['items']


def test_live_page_still_has_priority(web_client, monkeypatch):
    c = web_client
    write_archive(c.app.state.store.directory)
    from test_websearch import fake_fetch, fake_model
    monkeypatch.setattr(web, 'fetch_page', fake_fetch)
    monkeypatch.setattr(web.model, 'call_model', fake_model)
    run = process(c, add_source(c, url=ORIGINAL, max_pages=1))
    assert run['status'] == 'completed' and run['items'][0]['method'] == 'direct'
