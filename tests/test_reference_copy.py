import hashlib
import json
from datetime import datetime, timezone

import pytest

from app import websearch as web
from app.reference_copy import read_reference_copy
from test_websearch import add_source, process, web_client

URL = 'https://kppu.go.id/uploads/siaran-pers/1768909063_Siaran-Pers-No.066_KPPU-PR_IX_2025.pdf'


def write_copy(directory):
    root = directory / 'reference-copies'
    root.mkdir()
    body = ('SIARAN PERS KPPU\nNomor 066/KPPU-PR/IX/2025\n'
            + 'TikTok acquisition notification facts and administrative obligations.\n' * 30
            + 'Siaran pers ini dipublikasikan pada 29 September 2025 oleh Deswin Nur.\n')
    raw = ('Title: document.pdf\nURL Source: ' + URL
           + '\nPublished Time: Tue, 20 Jan 2026 11:37:43 GMT\nNumber of Pages: 3\n\nMarkdown Content:\n' + body).encode()
    (root / '066.txt').write_bytes(raw)
    item = {'url': URL, 'file': '066.txt', 'sha256': hashlib.sha256(raw).hexdigest(),
            'title': 'KPPU 066', 'date': '2025-09-29', 'provider': 'Jina Reader',
            'retrieval_url': 'https://r.jina.ai/' + URL,
            'retrieved_at': datetime.now(timezone.utc).isoformat()}
    (root / 'manifest.json').write_text(json.dumps({'version': 1, 'items': [item]}))
    return root, item, body


def save_manifest(root, items):
    (root / 'manifest.json').write_text(json.dumps({'version': 1, 'items': items}))


def test_verified_copy_keeps_exact_text_and_uses_document_date(tmp_path):
    _, item, body = write_copy(tmp_path)
    found = read_reference_copy(tmp_path, URL)
    assert found['body'] == body
    assert found['date'] == '2025-09-29' and found['date'] != '2026-01-20'
    assert found['title'].startswith('［PDF文本副本］')
    assert found['retrieval_url'] == item['retrieval_url']


@pytest.mark.parametrize('url', ['http://kppu.go.id/x.pdf', 'https://other.example/x.pdf',
                                URL + '?modified=1', URL.replace('kppu.go.id', 'kppu.go.id@127.0.0.1'),
                                URL.replace('/uploads/siaran-pers/', '/private/')])
def test_unlisted_urls_never_use_copy(tmp_path, url):
    write_copy(tmp_path)
    assert read_reference_copy(tmp_path, url) is None


def test_no_manifest_or_unmatched_reference_returns_none(tmp_path):
    assert read_reference_copy(tmp_path, URL) is None
    write_copy(tmp_path)
    assert read_reference_copy(tmp_path, URL.replace('1768909063', '1768909064')) is None


@pytest.mark.parametrize('change', [
    {'file': '../outside.txt'}, {'sha256': '0'*64}, {'date': '2026-01-20'},
    {'retrieval_url': 'https://untrusted.example/'}, {'retrieved_at': '2026-01-01'},
])
def test_invalid_metadata_is_rejected(tmp_path, change):
    root, item, _ = write_copy(tmp_path)
    save_manifest(root, [dict(item, **change)])
    with pytest.raises(ValueError):
        read_reference_copy(tmp_path, URL)


def test_duplicate_reference_is_rejected(tmp_path):
    root, item, _ = write_copy(tmp_path)
    save_manifest(root, [item, item])
    with pytest.raises(ValueError, match='多个副本'):
        read_reference_copy(tmp_path, URL)


def test_content_identity_is_checked_even_with_matching_hash(tmp_path):
    root, item, _ = write_copy(tmp_path)
    file = root / item['file']
    file.write_bytes(file.read_bytes().replace(b'066/KPPU', b'999/KPPU'))
    item['sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
    save_manifest(root, [item])
    with pytest.raises(ValueError, match='文件编号'):
        read_reference_copy(tmp_path, URL)


def test_windows_line_endings_do_not_hide_reader_envelope(tmp_path):
    root, item, body = write_copy(tmp_path)
    file = root / item['file']
    file.write_bytes(file.read_bytes().replace(b'\n', b'\r\n'))
    item['sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
    save_manifest(root, [item])
    assert read_reference_copy(tmp_path, URL)['body'] == body


def test_collector_uses_copy_only_after_failure_and_runs_real_review_pipeline(web_client, monkeypatch):
    c = web_client
    _, item, body = write_copy(c.app.state.store.directory)
    def blocked(url, *a, **k):
        if url.endswith('robots.txt'):
            return url, '', b'', 'text/plain'
        raise web.HttpStatus(403)
    calls = []
    async def model(settings, payload, system=None):
        calls.append(payload)
        return {'items': [{'id': p['id'], 'relevant': True, 'reason': 'Exact reference.',
                           'quote': 'TikTok acquisition notification facts and administrative obligations.'} for p in payload['pages']]}, {'total_tokens': 20}
    monkeypatch.setattr(web, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(web, 'fetch_page', blocked)
    monkeypatch.setattr(web.model, 'call_model', model)
    run = process(c, add_source(c, url=URL, max_pages=1))
    assert run['status'] == 'completed' and len(calls) == 1
    page = c.get('/api/web/pages/' + str(run['items'][0]['id'])).json()
    assert page['method'] == 'reader_copy' and page['body'] == body
    assert page['date'] == '2025-09-29' and page['date_source'] == 'document_text'
    assert page['url'] == URL and page['fetched_at'] == item['retrieved_at']
    assert run['items'][0]['quote'] in body and run['items'][0]['relevant'] == 1
    assert run['errors'] and not c.get('/api/documents').json()['items']


def test_robots_disallow_blocks_copy_too(web_client, monkeypatch):
    c = web_client
    write_copy(c.app.state.store.directory)
    def disallow(url, *a, **k):
        if url.endswith('robots.txt'):
            text = 'User-agent: *\nDisallow: /\n'
            return url, text, text.encode(), 'text/plain'
        raise AssertionError('Must not fetch a disallowed URL')
    monkeypatch.setattr(web, 'fetch_page', disallow)
    run = process(c, add_source(c, url=URL, max_pages=1))
    assert run['status'] == 'failed' and not run['items']


def test_live_body_has_priority_over_copy(web_client, monkeypatch):
    c = web_client
    write_copy(c.app.state.store.directory)
    from test_websearch import fake_fetch, fake_model
    monkeypatch.setattr(web, 'fetch_page', fake_fetch)
    monkeypatch.setattr(web.model, 'call_model', fake_model)
    run = process(c, add_source(c, url=URL, max_pages=1))
    assert run['status'] == 'completed' and run['items'][0]['method'] == 'direct'
