import asyncio
from app import websearch
from tests.test_websearch import web_client, add_source, fake_fetch, fake_model, process, no_archive  # noqa: F401

def test_pages_carry_method_and_knowledge_state_and_discoveries(web_client,monkeypatch):
    monkeypatch.setattr(websearch,'fetch_page',fake_fetch);monkeypatch.setattr(websearch.model,'call_model',fake_model)
    c=web_client;run=process(c,add_source(c))
    assert {p['method'] for p in run['items']}=={'direct'} and run['judged']==2
    assert c.get('/api/web/runs').json()['items'][0]['stage']=='review'
    relevant=next(p for p in run['items'] if p['relevant'])
    assert not relevant['in_knowledge']
    found=c.get('/api/web/discoveries').json()['items']
    assert [p['id'] for p in found]==[relevant['id']] and found[0]['source']=='指定网站测试'
    c.post('/api/web/import',json={'page_ids':[relevant['id']],'kind':'knowledge'})
    # A later run that finds the same text sees it is already in the knowledge base.
    again=process(c,add_source(c,url='https://source.example/news/',name='同一网站另一入口'))
    assert next(p for p in again['items'] if p['relevant'])['in_knowledge']

def test_failed_source_card_names_the_main_page_error(web_client,monkeypatch):
    def blocked(url,base,robots=None,relaxed=False,**kw):
        if url.endswith('robots.txt'): return url,'',b'','text/plain'
        raise websearch.HttpStatus(403)
    monkeypatch.setattr(websearch,'fetch_page',blocked);monkeypatch.setattr(websearch,'feed_pages',lambda *a:[])
    c=web_client;run=process(c,add_source(c,max_pages=1))
    assert run['status']=='failed' and '防火墙' in run['hint']
    card=c.get('/api/web/sources').json()['items'][0]
    assert card['last_run_id']==run['id'] and '防火墙' in card['last_hint']

def test_group_batch_progress_and_cancel_rest(web_client):
    c=web_client
    c.post('/api/web/sources/import',json={'items':[{'name':f'站点{i}','url':f'https://s{i}.example/','keywords':'x','category':'二、测试'} for i in range(3)],'allow_external':True})
    assert c.post('/api/web/runs/group',json={'category':'二、测试'}).json()['queued']==3
    with c.app.state.store.db() as db: db.execute("UPDATE web_runs SET status='completed' WHERE id=(SELECT min(id) FROM web_runs)")
    batch=c.get('/api/web/runs').json()['batches'][0]
    assert batch['category']=='二、测试' and (batch['total'],batch['done'],batch['queued'])==(3,1,2)
    assert c.post('/api/web/runs/batch/cancel',json={'batch':batch['batch']}).json()['cancelled']==2
    assert c.get('/api/web/runs').json()['batches']==[]

def test_documents_sort_by_date_and_runtime_extras(web_client):
    c=web_client;store=c.app.state.store
    from app.ingest import insert_document
    old,_=insert_document(store,{'title':'旧资料','body':'旧资料正文内容。','source':'s','url':'','date':'2020-01-01'},'knowledge',True)
    new,_=insert_document(store,{'title':'新资料','body':'新资料正文内容。','source':'s','url':'','date':'2026-01-01'},'knowledge',False)
    undated,_=insert_document(store,{'title':'无日期','body':'无日期正文内容。','source':'s','url':'','date':''},'knowledge',True)
    assert [d['id'] for d in c.get('/api/documents?kind=knowledge').json()['items']]==[undated,new,old]
    items=c.get('/api/documents?kind=knowledge&sort=date').json()['items']
    assert [d['id'] for d in items]==[new,old,undated] and items[0]['zh_state']==''
    r=c.get('/api/runtime').json()
    assert r['enrich_pending']==2 and r['model_error'] is None and r['fetch_proxy'] in (True,False)
