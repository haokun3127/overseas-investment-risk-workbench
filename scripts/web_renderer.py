"""Isolated page renderer for website retrieval: loads one public page in headless Chromium and returns the
rendered HTML, for sites whose text only appears after JavaScript runs.

Security model (see scripts/web-renderer.service):
- listens on 127.0.0.1 only and every request must carry RENDER_TOKEN;
- runs as its own unprivileged user; systemd IPAddressDeny=any + IPAddressAllow=localhost means the browser
  can reach nothing but the local egress proxy, and Chromium is told to send even loopback traffic through
  that proxy, so page scripts cannot touch this server's internal network;
- images, media, fonts, downloads and service workers are blocked; one page at a time, hard timeouts.
It does not solve bot challenges (CAPTCHA, Cloudflare): those pages come back as they are.
"""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

TOKEN = os.environ['RENDER_TOKEN']
PROXY = os.environ.get('RENDER_PROXY', 'http://127.0.0.1:7890')
PORT = int(os.environ.get('RENDER_PORT', '8791'))
USER_AGENT = 'Mozilla/5.0 (compatible; RiskWorkbenchBot/1.1)'
MAX_HTML = 2 * 1024 * 1024
SKIPPED = ('image', 'media', 'font')

def render(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(proxy={'server': PROXY, 'bypass': '<-loopback>'},
                                    args=['--disable-dev-shm-usage', '--no-first-run', '--disable-extensions',
                                          '--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
        try:
            context = browser.new_context(user_agent=USER_AGENT, accept_downloads=False, service_workers='block',
                                          locale='id-ID', extra_http_headers={'Accept-Language': 'id,en;q=0.9'})
            page = context.new_page()
            page.route('**/*', lambda route: route.abort() if route.request.resource_type in SKIPPED else route.continue_())
            response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
            try: page.wait_for_load_state('networkidle', timeout=12000)
            except Exception: pass
            return {'url': page.url, 'status': response.status if response else 0, 'html': page.content()[:MAX_HTML]}
        finally:
            browser.close()

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if self.path != '/render' or not hmac.compare_digest(self.headers.get('X-Render-Token', ''), TOKEN):
            return self.reply(403, {'error': 'forbidden'})
        try:
            url = json.loads(self.rfile.read(min(int(self.headers.get('Content-Length', 0)), 8192)))['url']
            if urlsplit(url).scheme not in ('http', 'https'): raise ValueError('bad url')
        except Exception:
            return self.reply(400, {'error': 'bad request'})
        try: self.reply(200, render(url))
        except Exception as error: self.reply(502, {'error': type(error).__name__ + ': ' + str(error)[:300]})
    def log_message(self, fmt, *args): pass  # URLs are business data; keep them out of the journal

if __name__ == '__main__':
    HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()  # single-threaded: one browser at a time
