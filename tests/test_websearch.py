import asyncio
import json
import socket
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app import websearch

HEADERS={'X-Requested-With':'risk-workbench'}

@pytest.fixture(autouse=True)
def no_archive(monkeypatch):
    monkeypatch.setattr(websearch,'ARCHIVE_FALLBACK',False)

@pytest.fixture
def web_client(tmp_path):
    settings=Settings(data_dir=tmp_path,model_base_url='https://model.example/v1',model_name='test-model',model_api_key='test',model_mode='external')
    app=create_app(settings,run_worker=False)
    with TestClient(app,headers=HEADERS) as c:
        c.post('/api/auth/setup',json={'password':'test-password-2026'})
        rules=app.state.store.setting('rules');rules['confirmed']=True;app.state.store.set_setting('rules',rules)
        yield c

def add_source(c,**extra):
    data={'name':'指定网站测试','url':'https://source.example/news/','keywords':'港口 原料','max_pages':3,'allow_external':True,**extra}
    r=c.post('/api/web/sources',json=data)
    assert r.status_code==200,r.text
    return r.json()['id']

def fake_fetch(url,base,robots=None,relaxed=False):
    if url.endswith('robots.txt'):
        return url,'User-agent: *\nDisallow: /private/\n',b'','text/plain'
    if url.endswith('/news/'):
        html='<html><title>原料供应通报</title><article>港口设备故障导致原料延迟七天，库存仅能维持三天生产，第四天生产线可能停工。</article><a href="/news/training">培训</a><a href="https://other.example/">站外</a><a href="/private/">路径外</a></html>'
    else:
        html='<html><title>培训公告</title><article>本周例行培训已按计划完成，没有停工、纠纷或安全事故，也没有原料供应问题。</article></html>'
    return url,html,html.encode(),'text/html; charset=utf-8'

async def fake_model(settings,payload,system=None):
    assert system==websearch.SEARCH_SYSTEM
    return {'items':[{'id':p['id'],'relevant':p['title']=='原料供应通报','reason':'有供应中断信号' if p['title']=='原料供应通报' else '例行培训无关','quote':p['body'][:25] if p['title']=='原料供应通报' else ''} for p in payload['pages']]},{'total_tokens':42}

def process(c,source_id):
    run_id=c.post('/api/web/runs',json={'source_id':source_id}).json()['id']
    run=c.app.state.store.one('SELECT * FROM web_runs WHERE id=?',(run_id,))
    asyncio.run(c.app.state.collector.process(run))
    return c.get('/api/web/runs/'+str(run_id)).json()

def test_retrieval_preview_dedup_import_and_risk_queue(web_client,monkeypatch):
    monkeypatch.setattr(websearch,'fetch_page',fake_fetch);monkeypatch.setattr(websearch.model,'call_model',fake_model)
    c=web_client;sid=add_source(c);run=process(c,sid)
    assert run['status']=='completed' and run['model']=='test-model'
    assert len(run['items'])==2
    assert not c.get('/api/documents').json()['items']
    relevant=next(p for p in run['items'] if p['relevant'])
    unrelated=next(p for p in run['items'] if not p['relevant'])
    original=c.get('/api/web/pages/'+str(relevant['id'])).json()
    assert relevant['quote'] in original['body'] and original['url'].startswith('https://source.example/news/')
    assert c.post('/api/web/import',json={'page_ids':[relevant['id'],unrelated['id']],'kind':'both'}).status_code==400
    assert not c.get('/api/documents').json()['items']
    result=c.post('/api/web/import',json={'page_ids':[relevant['id']],'kind':'both','analyze':True}).json()
    assert len(result['items'])==2 and all(i['created'] for i in result['items'])
    assert next(i for i in result['items'] if i['kind']=='event')['job_id']
    assert c.get('/api/knowledge/search?q=港口原料').json()['items']
    doc=c.get('/api/documents/'+str(result['items'][0]['id'])).json()
    assert doc['url']==original['url'] and doc['demo']==0
    snapshot=c.get('/api/documents/'+str(doc['id'])+'/file')
    assert snapshot.status_code==200 and 'attachment' in snapshot.headers['content-disposition']
    second=c.post('/api/web/import',json={'page_ids':[relevant['id']],'kind':'both','analyze':True}).json()
    assert not any(i['created'] for i in second['items'])
    assert c.get('/api/jobs').json()['total']==1

def test_search_failure_does_not_auto_import(web_client,monkeypatch):
    monkeypatch.setattr(websearch,'fetch_page',fake_fetch)
    async def wrong(settings,payload,system=None):
        return {'items':[{'id':p['id'],'relevant':True,'reason':'假引用','quote':'这是不存在于任何页面的伪造原文'} for p in payload['pages']]},{}
    monkeypatch.setattr(websearch.model,'call_model',wrong)
    run=process(web_client,add_source(web_client,auto_import='both',auto_analyze=True))
    # Fabricated quotes are never accepted: pages stay unjudged, the run still completes, nothing is imported.
    assert run['status']=='completed' and 'AI 未给出可核验的判定' in run['error']
    assert run['items'] and all(p['relevant'] is None and p['reason']==websearch.UNJUDGED for p in run['items'])
    assert not web_client.get('/api/documents').json()['items']
    assert not web_client.get('/api/documents?kind=knowledge').json()['items']

def test_robots_and_scope_stop_fetching(web_client,monkeypatch):
    calls=[]
    def blocked(url,base,robots=None,relaxed=False):
        calls.append(url)
        return url,'User-agent: *\nDisallow: /news/\n',b'','text/plain'
    monkeypatch.setattr(websearch,'fetch_page',blocked)
    run=process(web_client,add_source(web_client))
    assert run['status']=='failed' and len(calls)==1 and 'robots.txt' in run['errors'][0]['error']
    assert not websearch.in_scope('https://source.example/elsewhere','https://source.example/news/')
    assert not websearch.in_scope('https://source.example/news-evil','https://source.example/news/')
    assert not websearch.in_scope('https://attacker.example/news/','https://source.example/news/')
    assert not websearch.in_scope('https://source.example/news/%2e%2e/private/','https://source.example/news/')

def test_public_dns_and_address_validation(monkeypatch):
    for bad in ('file:///etc/passwd','https://user:password@example.com/','http://example.com:8780/','https://example.com/\n'):
        with pytest.raises(ValueError):websearch.clean_url(bad)
    for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','::1','192.168.1.1'):
        monkeypatch.setattr(socket,'getaddrinfo',lambda *a,ip=ip,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))])
        with pytest.raises(ValueError):websearch.public_address('example.com',443)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))])
    assert websearch.public_address('example.com',443)=='8.8.8.8'

def test_authorization_cancel_edit_pause(web_client):
    c=web_client;sid=add_source(c,allow_external=False)
    assert c.post('/api/web/runs',json={'source_id':sid}).status_code==400
    assert c.post('/api/web/sources',json={'name':'定时','url':'https://example.com/','keywords':'政策','interval_hours':24}).status_code==400
    sid=add_source(c,interval_hours=24)
    rid=c.post('/api/web/runs',json={'source_id':sid}).json()['id']
    assert c.post('/api/web/runs',json={'source_id':sid}).json()['id']==rid
    data={'name':'更新网站','url':'https://source.example/news/','keywords':'原料','allow_external':True}
    assert c.put('/api/web/sources/'+str(sid),json=data).status_code==400
    assert c.post('/api/web/runs/'+str(rid)+'/cancel').status_code==200
    assert c.put('/api/web/sources/'+str(sid),json=data).status_code==200
    assert c.post('/api/web/sources/'+str(sid)+'/pause').status_code==200
    assert next(s for s in c.get('/api/web/sources').json()['items'] if s['id']==sid)['interval_hours']==0
    c.post('/api/auth/logout')
    assert c.get('/api/web/sources').status_code==401

def test_automatic_ingest_keeps_knowledge_and_analysis_separate(web_client,monkeypatch):
    monkeypatch.setattr(websearch,'fetch_page',fake_fetch);monkeypatch.setattr(websearch.model,'call_model',fake_model)
    run=process(web_client,add_source(web_client,auto_import='both',auto_analyze=True))
    assert run['status']=='completed'
    assert web_client.get('/api/documents?kind=knowledge').json()['total']==1
    assert web_client.get('/api/documents?kind=event').json()['total']==1
    assert web_client.get('/api/jobs').json()['total']==1

def test_redirect_and_size_limits(monkeypatch):
    connected=[]
    monkeypatch.setattr(websearch,'public_address',lambda host,port:'8.8.8.8')
    class Response:
        status=302
        def getheader(self,name,default=None):return 'https://evil.example/' if name=='Location' else default
    class Connection:
        def __init__(self,host,port,ip,tls,proxy=None):connected.append((host,ip,tls))
        def request(self,*args,**kwargs):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(websearch,'PinnedConnection',Connection)
    with pytest.raises(ValueError,match='超出指定网站'):
        websearch.fetch_page('https://source.example/news/','https://source.example/news/')
    assert connected==[('source.example','8.8.8.8',True)]
    Response.status=200
    Response.getheader=lambda self,name,default=None: 'text/html' if name=='Content-Type' else default
    Response.read=lambda self,size:b'x'*min(size,websearch.MAX_BYTES+1)
    assert len(websearch.fetch_page('https://source.example/news/','https://source.example/news/')[2])==websearch.MAX_BYTES

def test_scheduler_runs_due_source_and_recovers_interrupted_run(web_client,monkeypatch):
    c=web_client;sid=add_source(c,interval_hours=24)
    with c.app.state.store.db() as db:db.execute('UPDATE web_sources SET next_run=0 WHERE id=?',(sid,))
    processed=[]
    async def one_run(run):
        processed.append(run['source_id'])
        raise asyncio.CancelledError()
    monkeypatch.setattr(c.app.state.collector,'process',one_run)
    with pytest.raises(asyncio.CancelledError):asyncio.run(c.app.state.collector.loop())
    assert processed==[sid]
    with c.app.state.store.db() as db:db.execute("UPDATE web_runs SET status='running'")
    websearch.initialize(c.app.state.store)
    run=c.get('/api/web/runs').json()['items'][0]
    assert run['status']=='failed' and '服务重启' in run['error']

def test_snapshots_do_not_overwrite_when_redirected_page_changes(web_client,monkeypatch):
    raws=[]
    def changing(url,base,robots=None,relaxed=False):
        if url.endswith('robots.txt'):return fake_fetch(url,base,robots)
        html='<title>原料供应通报</title><p>港口设备故障导致生产原料供应中断，库存只够三天。这是第'+str(len(raws)+1)+'版。</p><a href="/news/alias">其他入口</a>'
        raws.append(html.encode())
        return base,html,raws[-1],'text/html'
    monkeypatch.setattr(websearch,'fetch_page',changing);monkeypatch.setattr(websearch.model,'call_model',fake_model)
    run=process(web_client,add_source(web_client,max_pages=2))
    assert run['status']=='completed'
    pages=web_client.app.state.store.rows('SELECT snapshot FROM web_pages WHERE run_id=? ORDER BY id',(run['id'],))
    assert len(pages)==2 and pages[0]['snapshot']!=pages[1]['snapshot']
    assert [(web_client.app.state.store.directory/'uploads'/p['snapshot']).read_bytes() for p in pages]==raws

def test_fallback_proxy_validation():
    assert websearch.loopback_proxy('')is None
    assert websearch.loopback_proxy('http://127.0.0.1:7890')==('127.0.0.1',7890)
    for bad in ('http://10.0.0.5:7890','socks5://127.0.0.1:7890','http://127.0.0.1','http://u:p@127.0.0.1:7890'):
        with pytest.raises(ValueError):websearch.loopback_proxy(bad)

def fallback_harness(monkeypatch,direct):
    calls=[]
    class Response:
        def __init__(self,status):self.status=status
        def getheader(self,name,default=None):return 'text/html' if name=='Content-Type' else default
        def read(self,size):return b'<title>ok</title>hello'
    class Connection:
        def __init__(self,host,port,ip,tls,proxy=None):self.ip,self.proxy=ip,proxy
        def request(self,*a,**kw):
            calls.append((self.ip,self.proxy))
            if not self.proxy and direct=='refused':raise ConnectionRefusedError()
        def getresponse(self):return Response(403 if (not self.proxy and direct==403) else 200)
        def close(self):pass
    monkeypatch.setattr(websearch,'PinnedConnection',Connection)
    return calls

def test_fallback_proxy_only_after_direct_failure(monkeypatch):
    url='https://source.example/news/'
    monkeypatch.setattr(websearch,'public_address',lambda host,port:'8.8.8.8')
    monkeypatch.setattr(websearch,'FETCH_PROXY',None)
    calls=fallback_harness(monkeypatch,'refused')
    with pytest.raises(ValueError,match='网页连接失败'):websearch.fetch_page(url,url)
    assert calls==[('8.8.8.8',None)]
    monkeypatch.setattr(websearch,'FETCH_PROXY',('127.0.0.1',7890))
    calls=fallback_harness(monkeypatch,'refused')
    assert websearch.fetch_page(url,url)[1].endswith('hello')
    assert calls==[('8.8.8.8',None),('8.8.8.8',('127.0.0.1',7890))]
    # 403: once more directly with the browser-compatible UA, then via the proxy.
    calls=fallback_harness(monkeypatch,403)
    assert websearch.fetch_page(url,url)[1].endswith('hello')
    assert calls==[('8.8.8.8',None),('8.8.8.8',None),('8.8.8.8',('127.0.0.1',7890))]
    calls=fallback_harness(monkeypatch,200)
    websearch.fetch_page(url,url)
    assert calls==[('8.8.8.8',None)]

def test_fallback_proxy_keeps_private_address_block(monkeypatch):
    url='https://source.example/news/'
    monkeypatch.setattr(websearch,'FETCH_PROXY',('127.0.0.1',7890))
    calls=fallback_harness(monkeypatch,200)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.8',443))])
    with pytest.raises(ValueError,match='公网地址'):websearch.fetch_page(url,url)
    assert calls==[]
    def nxdomain(*a,**kw):raise socket.gaierror('nx')
    monkeypatch.setattr(socket,'getaddrinfo',nxdomain)
    websearch.fetch_page(url,url)
    assert calls==[(None,('127.0.0.1',7890))]

def test_robots_follow_rfc9309_longest_match():
    text="User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\nDisallow: /cari\nDisallow: /peraturan/*/gated\nDisallow: /*.json$\nCrawl-delay: 2\n"
    r=websearch.Robots(text)
    assert r.can_fetch('https://pasal.id/peraturan/uu/uu-no-13-tahun-2003')
    assert not r.can_fetch('https://pasal.id/cari?q=upah')
    assert not r.can_fetch('https://pasal.id/peraturan/uu/gated')
    assert not r.can_fetch('https://pasal.id/data/a.json') and r.can_fetch('https://pasal.id/data/a.json?x=1')
    assert r.crawl_delay()==2
    mine=websearch.Robots("User-agent: *\nDisallow: /\n\nUser-agent: RiskWorkbenchBot\nDisallow: /private/\n")
    assert mine.can_fetch('https://x.example/news/') and not mine.can_fetch('https://x.example/private/a')
    assert websearch.Robots("User-agent: *\nDisallow: /news\nAllow: /news/open\n").can_fetch('https://x.example/news/open/1')

def test_robots_4xx_is_unrestricted_but_5xx_stops(monkeypatch):
    def status(code):
        def fetch(url,base,robots=None,relaxed=False):raise websearch.HttpStatus(code)
        return fetch
    monkeypatch.setattr(websearch,'fetch_page',status(403))
    assert websearch.load_robots('https://x.example/').can_fetch('https://x.example/anything')
    monkeypatch.setattr(websearch,'fetch_page',status(503))
    with pytest.raises(ValueError,match='robots.txt'):websearch.load_robots('https://x.example/')

def test_long_pages_are_truncated_and_entry_redirect_becomes_scope(web_client,monkeypatch):
    calls=[]
    def moved(url,base,robots=None,relaxed=False):
        calls.append((url,base))
        if url.endswith('robots.txt'):return url,'User-agent: *\nDisallow: /private/\n',b'','text/plain'
        if url=='https://source.example/news/':raise websearch.OutOfScope('https://source.example/id/berita/')
        html='<title>原料供应通报</title><p>港口设备故障导致原料延迟。'+'详细内容'*20000+'</p>'
        return url,html,html.encode(),'text/html'
    monkeypatch.setattr(websearch,'fetch_page',moved);monkeypatch.setattr(websearch.model,'call_model',fake_model)
    run=process(web_client,add_source(web_client,max_pages=2))
    assert run['status']=='completed' and len(run['items'])==1
    assert ('https://source.example/id/berita/','https://source.example/id/berita/') in calls
    body=web_client.get('/api/web/pages/'+str(run['items'][0]['id'])).json()['body']
    assert len(body)==websearch.MAX_BODY and body.endswith(websearch.TRUNCATED)
    result=web_client.post('/api/web/import',json={'page_ids':[run['items'][0]['id']],'kind':'knowledge'})
    assert result.status_code==200,result.text

def test_unreachable_page_falls_back_to_internet_archive(web_client,monkeypatch):
    monkeypatch.setattr(websearch,'ARCHIVE_FALLBACK',True)
    def blocked(url,base,robots=None,relaxed=False):
        if url.endswith('robots.txt'):raise websearch.HttpStatus(403)
        raise websearch.HttpStatus(403)
    def archive(url):
        html='<title>原料供应通报</title><p>港口设备故障导致原料延迟七天，库存仅能维持三天。</p>'
        return '2026-05-01',html,html.encode(),'text/html'
    monkeypatch.setattr(websearch,'fetch_page',blocked);monkeypatch.setattr(websearch,'archived_page',archive)
    monkeypatch.setattr(websearch.model,'call_model',fake_model)
    run=process(web_client,add_source(web_client,max_pages=1))
    assert run['status']=='completed' and run['items'][0]['title'].startswith('［网页存档 2026-05-01］')
    def challenge(url):
        html='<title>Just a moment...</title><p>Checking your browser before accessing the site, please wait.</p>'
        return '2026-05-01',html,html.encode(),'text/html'
    monkeypatch.setattr(websearch,'archived_page',challenge)
    run=process(web_client,add_source(web_client,max_pages=1))
    assert run['status']=='failed' and '人机验证' in run['errors'][0]['error']

def test_pdf_pages_are_extracted(monkeypatch):
    from pypdf import PdfWriter
    import io
    writer=PdfWriter();writer.add_blank_page(200,200);buf=io.BytesIO();writer.write(buf)
    with pytest.raises(ValueError,match='扫描件'):websearch.pdf_text(buf.getvalue())
    monkeypatch.setattr(websearch,'public_address',lambda host,port:'8.8.8.8')
    monkeypatch.setattr(websearch,'pdf_text',lambda raw:'[第1页]\nPeraturan tentang tenaga kerja asing')
    class Response:
        status=200
        def getheader(self,name,default=None):return 'application/pdf' if name=='Content-Type' else default
        def read(self,size):return b'%PDF-1.4'
    class Connection:
        def __init__(self,*a,**kw):pass
        def request(self,*a,**kw):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(websearch,'PinnedConnection',Connection)
    url,text,raw,ctype=websearch.fetch_page('https://source.example/news/a.pdf','https://source.example/news/')
    assert ctype=='application/pdf' and 'tenaga kerja' in text

def test_link_ranking_prefers_detail_pages_and_skips_login():
    terms=['upah','pengupahan']
    assert websearch.SKIP_LINK.search('https://ojk.go.id/_layouts/15/Authenticate.aspx?Source=x')
    assert websearch.SKIP_LINK.search('https://x.go.id/masuk')
    assert websearch.link_score('https://x.go.id/peraturan/pp-36-2021.pdf','PP Pengupahan',terms)>websearch.link_score('https://x.go.id/kontak','Kontak',terms)

def test_compressed_bodies_and_archive_hosts_skip_local_dns(monkeypatch):
    import gzip
    class Response:
        status=200
        def __init__(self):self.data=gzip.compress(b'<title>t</title>'+b'x'*5000)
        def getheader(self,name,default=None):return {'Content-Type':'text/html','Content-Encoding':'gzip'}.get(name,default)
        def read(self,size):return self.data[:size]
    assert websearch.read_body(Response(),100)==b'<title>t</title>'+b'x'*84
    seen=[]
    class Connection:
        def __init__(self,host,port,ip,tls,proxy=None):seen.append((host,ip,proxy))
        def request(self,*a,**kw):pass
        def getresponse(self):
            r=Response();r.data=gzip.compress(b'{"archived_snapshots":{}}');return r
        def close(self):pass
    def poisoned(*a,**kw):raise AssertionError('archive hosts must not use local DNS')
    monkeypatch.setattr(websearch,'PinnedConnection',Connection);monkeypatch.setattr(socket,'getaddrinfo',poisoned)
    monkeypatch.setattr(websearch,'FETCH_PROXY',('127.0.0.1',7890))
    with pytest.raises(ValueError,match='没有可用快照'):websearch.archived_page('https://kppu.go.id/')
    assert seen==[('archive.org',None,('127.0.0.1',7890))]

def test_unreachable_robots_uses_archive_and_rebase_keeps_page_budget(web_client,monkeypatch):
    monkeypatch.setattr(websearch,'ARCHIVE_FALLBACK',True)
    def down(url,base,robots=None,relaxed=False):raise ValueError('网页连接失败：SSLEOFError')
    def archive(url):
        html='<title>原料供应通报</title><p>港口设备故障导致原料延迟七天，库存仅能维持三天。</p>'
        return '2026-04-15',html,html.encode(),'text/html'
    monkeypatch.setattr(websearch,'fetch_page',down);monkeypatch.setattr(websearch,'archived_page',archive)
    monkeypatch.setattr(websearch.model,'call_model',fake_model)
    run=process(web_client,add_source(web_client,max_pages=1))
    assert run['status']=='completed' and run['items'][0]['title'].startswith('［网页存档 2026-04-15］')
    def moved(url,base,robots=None,relaxed=False):
        if url.endswith('robots.txt'):raise websearch.HttpStatus(404)
        if url=='https://source.example/news/':raise websearch.OutOfScope('https://source.example/id/news/')
        return fake_fetch(url,base)
    monkeypatch.setattr(websearch,'fetch_page',moved)
    run=process(web_client,add_source(web_client,max_pages=1))
    assert run['status']=='completed' and run['items'][0]['url']=='https://source.example/id/news/'

def test_model_proxy_accepts_only_loopback_http():
    from app import model
    assert model.loopback_proxy('') is None and model.loopback_proxy('http://127.0.0.1:7890')=='http://127.0.0.1:7890'
    for bad in ('http://10.0.0.2:7890','https://127.0.0.1:7890','socks5://127.0.0.1:7890','http://127.0.0.1'):
        with pytest.raises(ValueError):model.loopback_proxy(bad)
