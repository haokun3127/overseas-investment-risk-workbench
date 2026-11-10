import hashlib
import io
import json
from datetime import datetime, timezone

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.retained_pdf import read_retained_pdf
from app import websearch as web
from test_websearch import add_source, process, web_client

URL = 'https://links.sgx.com/FileOpen/Announcement.ashx?AnncID=ABC123&App=ArchiveAnnouncement&FileID=123'


def write_copy(directory):
    root = directory / 'reference-copies'
    root.mkdir(exist_ok=True)
    writer, stream = PdfWriter(), io.BytesIO()
    page = writer.add_blank_page(600, 800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    lines = ['ANNOUNCEMENT', 'Project conditional joint venture terms and power supply agreement.'] + ['The transaction remains conditional on regulatory approval and project financing.'] * 20 + ['By Order of the Board', 'Chief Executive Officer', '12 June 2017']
    content = DecodedStreamObject()
    content.set_data(('BT /F1 12 Tf 30 750 Td ' + ' 0 -20 Td '.join('(' + line + ') Tj' for line in lines) + ' ET').encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(content)
    writer.write(stream)
    raw = stream.getvalue()
    (root / 'announcement.pdf').write_bytes(raw)
    item = {'url': URL, 'file': 'announcement.pdf', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'pages': 1, 'title': 'Project announcement', 'date': '2017-06-12', 'provider': 'original_download', 'retrieval_url': URL, 'retrieved_at': datetime.now(timezone.utc).isoformat()}
    save(root, [item])
    return root, item


def save(root, items):
    (root / 'pdf-manifest.json').write_text(json.dumps({'version': 1, 'items': items}))


def test_original_binary_and_signature_date_are_preserved(tmp_path):
    root, item = write_copy(tmp_path)
    result = read_retained_pdf(tmp_path, URL)
    assert result['raw'] == (root / item['file']).read_bytes()
    assert result['date'] == '2017-06-12' and result['date_source'] == 'document_signature'
    assert result['title'].startswith('［PDF原件留存］')


@pytest.mark.parametrize('change', [{'file': '../other.pdf'}, {'sha256': '0'*64}, {'bytes': 1}, {'pages': 2}, {'date': '2018-01-01'}, {'retrieval_url': 'https://other.test'}, {'retrieved_at': '2026-01-01'}])
def test_unverified_original_is_rejected(tmp_path, change):
    root, item = write_copy(tmp_path)
    save(root, [dict(item, **change)])
    with pytest.raises(ValueError):
        read_retained_pdf(tmp_path, URL)


def test_unknown_or_modified_url_and_duplicate_are_rejected(tmp_path):
    root, item = write_copy(tmp_path)
    assert read_retained_pdf(tmp_path, URL.replace('links.sgx.com', 'links.sgx.com.evil.test')) is None
    assert read_retained_pdf(tmp_path, URL.replace('FileID=123', 'FileID=456')) is None
    save(root, [item, item])
    with pytest.raises(ValueError):read_retained_pdf(tmp_path, URL)


def test_collector_fallback_reviews_original_and_preserves_pdf(web_client, monkeypatch):
    client = web_client
    _, item = write_copy(client.app.state.store.directory)
    def blocked(url, *a, **kw):
        if url.endswith('robots.txt'):return url, '', b'', 'text/plain'
        raise web.HttpStatus(403)
    async def model(settings, payload, **kw):
        return {'items': [{'id': p['id'], 'relevant': True, 'reason': 'Project terms', 'quote': 'Project conditional joint venture terms and power supply agreement.'} for p in payload['pages']]}, {}
    monkeypatch.setattr(web, 'fetch_page', blocked)
    monkeypatch.setattr(web, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(web.model, 'call_model', model)
    run = process(client, add_source(client, url=URL, max_pages=1))
    assert run['status'] == 'completed' and run['items'][0]['relevant'] == 1
    page = client.get('/api/web/pages/' + str(run['items'][0]['id'])).json()
    assert page['method'] == 'original_copy' and page['date_source'] == 'document_signature'
    snapshot = client.app.state.store.one('SELECT snapshot FROM web_pages WHERE id=?', (page['id'],))['snapshot']
    assert snapshot.endswith('.pdf') and page['fetched_at'] == item['retrieved_at']
    assert run['errors'] and not client.get('/api/documents').json()['items']


def test_robots_exclusion_also_blocks_original_fallback(web_client, monkeypatch):
    client = web_client
    write_copy(client.app.state.store.directory)
    def blocked(url, *a, **kw):
        if url.endswith('robots.txt'):
            raw = b'User-agent: *\nDisallow: /\n'
            return url, raw.decode(), raw, 'text/plain'
        raise AssertionError('must obey exclusions')
    monkeypatch.setattr(web, 'fetch_page', blocked)
    run = process(client, add_source(client, url=URL, max_pages=1))
    assert run['status'] == 'failed' and not run['items']
