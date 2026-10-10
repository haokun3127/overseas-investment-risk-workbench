"""Website search with provider snapshots, durable tasks and explicit review.

Search summaries are never substituted for source text. This module does not
fetch arbitrary result URLs; source text is a snapshot supplied by the provider.
"""
import asyncio
import hashlib
import ipaddress
import json
import socket
import sqlite3
from datetime import date, datetime
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict

from .ingest import insert_document, MAX_TEXT
from .store import now


class SourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    enabled: bool = True


class SearchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_ids: list[int] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=1, max_length=500)
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=10, ge=1, le=20)


class ImportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str = 'knowledge'
    allow_external: bool = False


def public_url(value):
    """Normalize public HTTPS links without touching the network."""
    try:
        u = urlsplit(value.strip())
        host = (u.hostname or '').encode('idna').decode('ascii').lower()
        if (len(value) > 2000 or u.scheme != 'https' or not host or u.username or u.password
                or u.port not in (None, 443) or '\\' in value
                or any(ord(c) < 32 for c in value)):
            raise ValueError
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host:
            raise ValueError
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError
        except ValueError as error:
            # Non-address hostnames are allowed; numeric private addresses are not.
            if ':' in host or all(c in '0123456789.' for c in host):
                raise ValueError from error
        path = u.path or '/'
        for _ in range(4):
            decoded = unquote(path)
            if decoded == path:
                break
            path = decoded
        if unquote(path) != path:
            raise ValueError
        if '\\' in path or any(segment in ('.', '..') for segment in path.split('/')):
            raise ValueError
        if any(not label or len(label) > 63 or not all(c.isalnum() or c == '-' for c in label)
               or label.startswith('-') or label.endswith('-') for label in host.split('.')):
            raise ValueError
        return urlunsplit(('https', host, u.path or '/', u.query, ''))
    except (ValueError, UnicodeError):
        raise ValueError('请填写不含凭据的公开 HTTPS 地址，不允许本机或内网地址。')


def source_url(value):
    url = public_url(value)
    if urlsplit(url).query:
        raise ValueError('网站来源使用域名或栏目路径，不包含查询参数。')
    return url


def in_scope(url, sources):
    try:
        u = urlsplit(public_url(url))
    except ValueError:
        return False
    path = u.path
    for _ in range(4):
        path = unquote(path)
    path = path.rstrip('/') or '/'
    for source in sources:
        s = urlsplit(source['url'])
        prefix = s.path
        for _ in range(4):
            prefix = unquote(prefix)
        prefix = prefix.rstrip('/') or '/'
        if u.hostname == s.hostname and (prefix == '/' or path == prefix or path.startswith(prefix + '/')):
            return True
    return False


async def tavily_search(settings, request):
    base = public_url(settings.search_base_url)
    if urlsplit(base).query:
        raise ValueError('检索服务基础地址不允许查询参数。')
    # Validate configured endpoints as well as static addresses. No redirects.
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, urlsplit(base).hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('检索服务地址须解析到公开地址。')
    except OSError:
        raise ValueError('检索服务地址无法解析。')
    payload = {
        'query': request['query'],
        'include_domains': sorted({urlsplit(s['url']).hostname for s in request['sources']}),
        'max_results': request['limit'], 'search_depth': 'advanced',
        'include_raw_content': 'text', 'include_answer': False,
    }
    if request.get('date_from'):
        payload['start_date'] = request['date_from']
    if request.get('date_to'):
        payload['end_date'] = request['date_to']
    try:
        async with httpx.AsyncClient(timeout=settings.search_timeout, follow_redirects=False) as client:
            async with client.stream('POST', base.rstrip('/') + '/search', json=payload,
                                     headers={'Authorization': 'Bearer ' + settings.search_api_key}) as response:
                if response.status_code >= 300:
                    raise ValueError(f'检索服务返回 HTTP {response.status_code}，请检查配置、额度或稍后重试。')
                content = bytearray()
                async for block in response.aiter_bytes():
                    content.extend(block)
                    if len(content) > 5 * 1024 * 1024:
                        raise ValueError('检索服务响应超过5MB限制，请减少结果数量。')
                data = json.loads(content)
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            raise ValueError('检索服务返回格式错误。')
        return data['results'][:request['limit']]
    except (httpx.HTTPError, TimeoutError):
        raise ValueError('检索服务超时或网络不可达，请检查连接后重试。')
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError('检索服务返回内容不是有效 JSON。')


# A provider adapter returns source results, never fabricated demonstration data.
PROVIDERS = {'tavily': tavily_search}


def initialize(store):
    with store.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS website_sources(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS website_searches(
            id INTEGER PRIMARY KEY, status TEXT NOT NULL, request_json TEXT NOT NULL,
            provider TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT,
            error TEXT NOT NULL DEFAULT '', rejected INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS website_versions(
            id INTEGER PRIMARY KEY, url TEXT NOT NULL, digest TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL, published_date TEXT NOT NULL,
            acquired_at TEXT NOT NULL, provider TEXT NOT NULL,
            UNIQUE(url,digest));
        CREATE TABLE IF NOT EXISTS website_results(
            id INTEGER PRIMARY KEY, search_id INTEGER NOT NULL REFERENCES website_searches(id),
            url TEXT NOT NULL, original_url TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, summary TEXT NOT NULL,
            published_date TEXT NOT NULL, fetched_at TEXT NOT NULL,
            content_status TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending',
            version_id INTEGER REFERENCES website_versions(id), duplicate INTEGER NOT NULL DEFAULT 0,
            UNIQUE(search_id,url));
        CREATE TABLE IF NOT EXISTS website_documents(
            version_id INTEGER NOT NULL REFERENCES website_versions(id),
            kind TEXT NOT NULL, document_id INTEGER NOT NULL REFERENCES documents(id),
            PRIMARY KEY(version_id,kind));
        CREATE INDEX IF NOT EXISTS website_results_search ON website_results(search_id);
        CREATE INDEX IF NOT EXISTS website_documents_document ON website_documents(document_id);
        ''')
        if 'original_url' not in {row['name'] for row in db.execute('PRAGMA table_info(website_results)')}:
            db.execute("ALTER TABLE website_results ADD COLUMN original_url TEXT NOT NULL DEFAULT ''")
        db.execute("UPDATE website_searches SET status='failed',error='服务重启中断了检索，请重试。',finished_at=? WHERE status='running'", (now(),))


def save_results(store, task, rows):
    request = json.loads(task['request_json'])
    rejected = 0
    accepted = 0
    acquired = now()
    with store.db() as db:
        for row in rows[:request['limit']]:
            if not isinstance(row, dict) or not isinstance(row.get('url'), str) or not in_scope(row['url'], request['sources']):
                rejected += 1
                continue
            # If the adapter supplies a redirect target, require it to remain in scope.
            if row.get('final_url') and (not isinstance(row['final_url'], str) or not in_scope(row['final_url'], request['sources'])):
                rejected += 1
                continue
            url = public_url(row.get('final_url') or row['url'])
            title = str(row.get('title') or '').strip()[:240]
            if not title:
                rejected += 1
                continue
            published = str(row.get('published_date') or '')
            try:
                published = (date.fromisoformat(published) if len(published) == 10 else datetime.fromisoformat(published).date()).isoformat()
            except ValueError:
                published = ''
            if published and ((request.get('date_from') and published < request['date_from'])
                              or (request.get('date_to') and published > request['date_to'])):
                rejected += 1
                continue
            body = row.get('raw_content')
            body = body.strip() if isinstance(body, str) else ''
            status = 'ready' if body else 'summary_only'
            if len(body) > MAX_TEXT:
                status = 'too_long'
            version_id = None
            duplicate = False
            if status == 'ready':
                digest = hashlib.sha256((title + '\0' + published + '\0' + body).encode()).hexdigest()
                old = db.execute('SELECT id FROM website_versions WHERE url=? AND digest=?', (url, digest)).fetchone()
                duplicate = bool(old)
                if old:
                    version_id = old['id']
                else:
                    version_id = db.execute('INSERT INTO website_versions(url,digest,title,body,published_date,acquired_at,provider) VALUES (?,?,?,?,?,?,?)',
                        (url, digest, title, body, published, acquired, task['provider'])).lastrowid
            summary = row.get('content')
            summary = summary[:5000] if isinstance(summary, str) else ''
            inserted = db.execute('INSERT OR IGNORE INTO website_results(search_id,url,original_url,title,summary,published_date,fetched_at,content_status,version_id,duplicate) VALUES (?,?,?,?,?,?,?,?,?,?)',
                (task['id'], url, public_url(row['url']), title, summary, published, acquired, status, version_id, int(duplicate))).rowcount
            accepted += inserted
        incomplete = any(r['content_status'] != 'ready' or (
            (request.get('date_from') or request.get('date_to')) and not r['published_date'])
            for r in db.execute('SELECT content_status,published_date FROM website_results WHERE search_id=?', (task['id'],)))
        db.execute('UPDATE website_searches SET status=?,finished_at=?,rejected=? WHERE id=?',
                   ('partial' if rejected or incomplete else 'completed', acquired, rejected, task['id']))
    return accepted


class SearchWorker:
    def __init__(self, store, settings):
        self.store, self.settings, self.task = store, settings, None

    def start(self):
        self.task = asyncio.create_task(self.loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def loop(self):
        while True:
            task = self.store.one("SELECT * FROM website_searches WHERE status='queued' ORDER BY id LIMIT 1")
            if task:
                await self.process(task)
            else:
                await asyncio.sleep(.5)

    async def process(self, task):
        with self.store.db() as db:
            if not db.execute("UPDATE website_searches SET status='running' WHERE id=? AND status='queued'", (task['id'],)).rowcount:
                return
        try:
            if not self.settings.search_api_key:
                raise ValueError('尚未配置 SEARCH_API_KEY。')
            adapter = PROVIDERS.get(task['provider'])
            if not adapter:
                raise ValueError('当前检索服务不受支持。')
            rows = await adapter(self.settings, json.loads(task['request_json']))
            if not isinstance(rows, list):
                raise ValueError('检索服务返回格式错误。')
            save_results(self.store, task, rows)
            self.store.audit('website_searched', f'search={task["id"]}')
        except asyncio.CancelledError:
            self.fail(task['id'], '服务停止，检索中断，请重试。')
            raise
        except Exception as error:
            # Never persist provider response bodies, credentials or arbitrary exceptions.
            self.fail(task['id'], str(error) if isinstance(error, ValueError) else '检索处理失败，请检查服务配置后重试。')

    def fail(self, task_id, message):
        with self.store.db() as db:
            db.execute("UPDATE website_searches SET status='failed',error=?,finished_at=? WHERE id=?", (message[:500], now(), task_id))


def register(app, store, settings):
    @app.get('/api/websites/config')
    def config():
        return {'provider': settings.search_provider,
                'configured': bool(settings.search_api_key and settings.search_provider in PROVIDERS),
                'providers': list(PROVIDERS), 'worker_enabled': bool(app.state.website_worker.task)}

    @app.get('/api/websites/sources')
    def sources():
        return {'items': store.rows('SELECT * FROM website_sources ORDER BY id DESC')}

    def write_source(data, source_id=None):
        if not data.name.strip():
            raise ValueError('来源名称不能为空。')
        url = source_url(data.url)
        with store.db() as db:
            try:
                if source_id is None:
                    source_id = db.execute('INSERT INTO website_sources(name,url,enabled,created_at) VALUES (?,?,?,?)',
                        (data.name.strip(), url, int(data.enabled), now())).lastrowid
                elif not db.execute('UPDATE website_sources SET name=?,url=?,enabled=? WHERE id=?',
                                     (data.name.strip(), url, int(data.enabled), source_id)).rowcount:
                    raise HTTPException(404, '网站来源不存在。')
            except sqlite3.IntegrityError:
                raise HTTPException(409, '该网站或栏目已配置。')
        store.audit('website_source_updated', f'source={source_id}')
        return {'id': source_id}

    @app.post('/api/websites/sources')
    def add_source(data: SourceInput):
        return write_source(data)

    @app.put('/api/websites/sources/{source_id}')
    def update_source(source_id: int, data: SourceInput):
        return write_source(data, source_id)

    @app.get('/api/websites/searches')
    def searches():
        rows = store.rows('SELECT s.*, (SELECT COUNT(*) FROM website_results r WHERE r.search_id=s.id) result_count FROM website_searches s ORDER BY id DESC LIMIT 30')
        for row in rows:
            row['request'] = json.loads(row.pop('request_json'))
        return {'items': rows}

    @app.post('/api/websites/searches')
    def search(data: SearchInput):
        if not settings.search_api_key or settings.search_provider not in PROVIDERS:
            raise HTTPException(409, '请先配置支持的检索服务和 SEARCH_API_KEY，然后重启服务。')
        if not data.query.strip():
            raise ValueError('检索关键词不能为空。')
        if data.date_from and data.date_to and data.date_from > data.date_to:
            raise ValueError('开始日期不能晚于结束日期。')
        selected = []
        for source_id in sorted(set(data.source_ids)):
            source = store.one('SELECT * FROM website_sources WHERE id=? AND enabled=1', (source_id,))
            if not source:
                raise ValueError('所选网站不存在或已停用。')
            selected.append(source)
        request = data.model_dump(mode='json', exclude={'source_ids'})
        request['query'] = data.query.strip()
        request['sources'] = selected
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # Repeated clicks while a matching request is active share one task.
            encoded = json.dumps(request, ensure_ascii=False, sort_keys=True)
            existing = db.execute("SELECT id FROM website_searches WHERE request_json=? AND status IN ('queued','running') AND provider=?", (encoded, settings.search_provider)).fetchone()
            if existing:
                return {'id': existing['id'], 'created': False}
            task_id = db.execute("INSERT INTO website_searches(status,request_json,provider,created_at) VALUES ('queued',?,?,?)",
                                 (encoded, settings.search_provider, now())).lastrowid
        return {'id': task_id, 'created': True}

    @app.get('/api/websites/searches/{task_id}')
    def detail(task_id: int):
        task = store.one('SELECT * FROM website_searches WHERE id=?', (task_id,))
        if not task:
            raise HTTPException(404, '检索任务不存在。')
        task['request'] = json.loads(task.pop('request_json'))
        rows = store.rows('SELECT r.*,v.body,v.provider FROM website_results r LEFT JOIN website_versions v ON v.id=r.version_id WHERE r.search_id=? ORDER BY r.id', (task_id,))
        for row in rows:
            row['documents'] = store.rows('SELECT kind,document_id FROM website_documents WHERE version_id=?', (row['version_id'],)) if row['version_id'] else []
        return {'task': task, 'items': rows}

    @app.post('/api/websites/results/{result_id}/import')
    def import_result(result_id: int, data: ImportInput):
        if data.kind not in ('event', 'knowledge'):
            raise ValueError('资料用途无效。')
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            result = db.execute('SELECT r.*,v.body,v.published_date AS date FROM website_results r LEFT JOIN website_versions v ON v.id=r.version_id WHERE r.id=?', (result_id,)).fetchone()
            if not result:
                raise HTTPException(404, '检索结果不存在。')
            if result['content_status'] != 'ready' or result['review_status'] == 'ignored':
                raise HTTPException(409, '该结果缺少可用正文或已忽略，不能入库。')
            # A bounded search with unknown publication date remains a lead only.
            request = json.loads(db.execute('SELECT request_json FROM website_searches WHERE id=?', (result['search_id'],)).fetchone()[0])
            if (request.get('date_from') or request.get('date_to')) and not result['date']:
                raise HTTPException(409, '发布时间未知，无法核实时间范围；请去掉时间限制后重新检索再确认。')
            existing = db.execute('SELECT document_id FROM website_documents WHERE version_id=? AND kind=?', (result['version_id'], data.kind)).fetchone()
            created = False
            if existing:
                doc_id = existing['document_id']
            else:
                doc_id, created = insert_document(store, {'title': result['title'], 'body': result['body'],
                    'date': result['date'], 'url': result['url'], 'source': urlsplit(result['url']).hostname},
                    data.kind, data.allow_external, connection=db, source_identity=f'website-version:{result["version_id"]}')
                db.execute('INSERT INTO website_documents(version_id,kind,document_id) VALUES (?,?,?)', (result['version_id'], data.kind, doc_id))
            db.execute("UPDATE website_results SET review_status='imported' WHERE id=?", (result_id,))
        store.audit('website_imported', f'document={doc_id}, kind={data.kind}')
        return {'id': doc_id, 'created': created, 'kind': data.kind}

    @app.post('/api/websites/results/{result_id}/ignore')
    def ignore(result_id: int):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM website_results WHERE id=?', (result_id,)).fetchone()
            if not row:
                raise HTTPException(404, '检索结果不存在。')
            if row['review_status'] == 'imported':
                raise HTTPException(409, '该结果已入库，不能忽略；请在资料页面管理使用范围。')
            db.execute("UPDATE website_results SET review_status='ignored' WHERE id=?", (result_id,))
        return {'ok': True}
