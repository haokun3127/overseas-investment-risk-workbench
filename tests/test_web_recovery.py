import pytest

from app import websearch as web
from test_websearch import add_source, fake_model, process, web_client


def test_template_detection_does_not_reject_normal_article():
    shell = '\n'.join('{{placeholder_' + str(i) + '}}' for i in range(25))
    assert len(shell) > 200 and web.unrendered_template(shell)
    assert not web.unrendered_template('Actual article text. ' * 30 + shell)
    assert not web.unrendered_template('Report uses {{oneExample}} in a quoted template.')


def test_long_template_is_rendered_before_review(web_client, monkeypatch):
    shell = '\n'.join('{{placeholder_' + str(i) + '}}' for i in range(25))
    html = '<title>JS</title><div id="app">' + shell + '</div><script src="app.js"></script>'

    def fetch(url, *args, **kwargs):
        if url.endswith('robots.txt'):
            return url, '', b'', 'text/plain'
        return url, html, html.encode(), 'text/html'

    monkeypatch.setattr(web, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(web, 'fetch_page', fetch)
    monkeypatch.setattr(web, 'RENDERER', ('127.0.0.1', 8791, '/render'))
    monkeypatch.setattr(web.model, 'call_model', fake_model)
    monkeypatch.setattr(web, 'render_page', lambda url: (url, '<title>原料供应通报</title><article>' + '港口设备故障导致原料延迟七天。' * 30 + '</article>'))
    run = process(web_client, add_source(web_client, max_pages=1))
    assert run['status'] == 'completed'
    assert run['items'][0]['method'] == 'render'
    original = web_client.get('/api/web/pages/' + str(run['items'][0]['id'])).json()
    assert '{{placeholder' not in original['body']


def test_render_failure_does_not_save_template_as_success(web_client, monkeypatch):
    shell = '\n'.join('{{placeholder_' + str(i) + '}}' for i in range(25))

    def fetch(url, *args, **kwargs):
        if url.endswith('robots.txt'):
            return url, '', b'', 'text/plain'
        return url, shell, shell.encode(), 'text/html'

    def unavailable(url):
        raise ValueError('浏览器渲染服务不可用：ConnectionRefusedError')

    monkeypatch.setattr(web, 'ARCHIVE_FALLBACK', False)
    monkeypatch.setattr(web, 'fetch_page', fetch)
    monkeypatch.setattr(web, 'RENDERER', ('127.0.0.1', 8791, '/render'))
    monkeypatch.setattr(web, 'render_page', unavailable)
    run = process(web_client, add_source(web_client, max_pages=1))
    assert run['status'] == 'failed' and not run['items']
    assert any('ConnectionRefusedError' in error['error'] for error in run['errors'])


def test_pdf_size_is_bounded_and_error_is_specific(monkeypatch):
    class Response:
        status = 200

        def getheader(self, name, default=None):
            return 'application/pdf' if name == 'Content-Type' else default

        def read(self, size):
            return b'x' * min(size, 25)

    class Connection:
        def close(self):
            pass

    monkeypatch.setattr(web, 'open_response', lambda *args: (Connection(), Response()))
    monkeypatch.setattr(web, 'pdf_text', lambda raw: 'Source PDF text')
    monkeypatch.setattr(web, 'MAX_PDF_BYTES', 24)
    url = 'https://example.com/source.pdf'
    with pytest.raises(ValueError, match='MB采集限制') as error:
        web.fetch_page(url, url)
    assert '超过采集大小上限' in web.error_hint(str(error.value))
    monkeypatch.setattr(web, 'MAX_PDF_BYTES', 32)
    assert web.fetch_page(url, url)[1] == 'Source PDF text'


def test_disclosure_pdf_uses_actual_allowed_link_and_exact_id(monkeypatch):
    base = 'https://www.cninfo.com.cn/new/disclosure/detail?announcementId=60864150'
    target = 'https://static.cninfo.com.cn/finalpage/2012-04-20/60864150.PDF'
    called = []
    monkeypatch.setattr(web, 'load_robots', lambda url: web.Robots())

    def fetch(url, base, robots):
        called.append(url)
        return url, 'Actual annual report body', b'%PDF', 'application/pdf'

    monkeypatch.setattr(web, 'fetch_page', fetch)
    assert web.disclosure_attachment(base, [target])[1] == 'Actual annual report body'
    assert called == [target]
    for invalid in [target.replace('60864150.PDF', '999.PDF'), target.replace('static.cninfo.com.cn', 'evil.example'), target.replace('https:', 'http:'), target + '?redirect=http://127.0.0.1']:
        assert web.disclosure_attachment(base, [invalid]) is None
    assert web.disclosure_attachment(base.replace('www.cninfo.com.cn', 'evil.example'), [target]) is None
    assert called == [target]


def test_empty_dynamic_page_uses_archive_without_faking_live_content(web_client, monkeypatch):
    def fetch(url, *args, **kwargs):
        if url.endswith('robots.txt'):
            return url, '', b'', 'text/plain'
        return url, '<div id="app"></div>', b'<div id="app"></div>', 'text/html'

    saved = '<title>原料供应通报</title><article>港口设备故障导致原料延迟七天，库存仅能维持三天生产。</article>'
    monkeypatch.setattr(web, 'fetch_page', fetch)
    monkeypatch.setattr(web, 'ARCHIVE_FALLBACK', True)
    monkeypatch.setattr(web, 'RENDERER', None)
    monkeypatch.setattr(web, 'archived_page', lambda url: ('2026-10-01', saved, saved.encode(), 'text/html'))
    monkeypatch.setattr(web.model, 'call_model', fake_model)
    run = process(web_client, add_source(web_client, max_pages=1))
    assert run['status'] == 'completed'
    item = run['items'][0]
    assert item['method'] == 'archive' and item['archived_at'] == '2026-10-01'
    assert item['url'] == 'https://source.example/news/'
    assert item['title'].startswith('［网页存档 2026-10-01］')


def test_archive_rate_limit_pauses_following_requests(monkeypatch):
    calls = []

    def limited(*args, **kwargs):
        calls.append(1)
        raise web.HttpStatus(429, '120')

    monkeypatch.setattr(web, 'ARCHIVE_RETRY_AT', 0)
    monkeypatch.setattr(web.time, 'monotonic', lambda: 1000)
    monkeypatch.setattr(web, 'fetch_page', limited)
    with pytest.raises(ValueError, match='HTTP 429'):
        web.archive_get('https://archive.org/wayback/available', 'https://archive.org/')
    assert web.ARCHIVE_RETRY_AT == 1120
    with pytest.raises(ValueError, match='秒后重试'):
        web.archive_get('https://archive.org/wayback/available', 'https://archive.org/')
    assert calls == [1]
