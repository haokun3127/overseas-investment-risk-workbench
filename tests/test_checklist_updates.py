import asyncio
import json

from app import checklist, model, updates
from test_tenant_authz import app, admin, companies
from test_evidence import insufficient, supplement
from test_websearch import web_client, add_source, make_company, fake_fetch, fake_model, process
from app import websearch


def test_checklist_suggestions_are_local_traceable_and_deduplicated():
    result={'parts':[{'decision':'insufficient','reason':'缺少法规全文，未说明适用条件。未提供供应商与交易对手清单。'}]*2}
    items=checklist.suggestions(result)
    assert len({i['category'] for i in items})==len(items)
    assert {'original','applicability','counterparty'}<={i['category'] for i in items}
    assert all(i['excerpt'] in result['parts'][0]['reason'] for i in items)
    assert len(checklist.suggestions({'decision':'insufficient','reason':'无法判断。'}))==1


def test_checklist_generate_update_snapshot_and_version_lock(app,admin,monkeypatch):
    doc,aid=insufficient(app,admin,monkeypatch)
    before=admin.get(f'/api/evidence/{aid}').json()
    assert before['checklist']==[] and before['checklist_suggestions']
    generated=admin.post(f'/api/evidence/{aid}/checklist/generate').json()['items']
    assert generated and generated==admin.post(f'/api/evidence/{aid}/checklist/generate').json()['items']
    item=generated[0];sid=supplement(admin,aid).json()['id']
    payload={'title':'通知完整正文','revision':item['revision'],'status':'provided','note':'已取得通知附件','supplement_ids':[sid]}
    endpoint=f'/api/evidence/{aid}/checklist/{item["id"]}'
    assert admin.patch(endpoint,json=payload).status_code==200
    assert admin.patch(endpoint,json=payload).status_code==409
    current=admin.get(f'/api/evidence/{aid}').json()['checklist'][0]
    assert current['materials'][0]['id']==sid and current['updated_by']=='admin'
    job=admin.post(f'/api/evidence/{aid}/reanalyze').json()['id']
    frozen=json.loads(app.state.store.one('SELECT checklist_json FROM jobs WHERE id=?',(job,))['checklist_json'])
    assert frozen[0]['status']=='provided' and frozen[0]['supplement_ids']==[sid]
    assert admin.patch(endpoint,json={**payload,'revision':2}).status_code==409
    async def fake(*a,**kw):return {'decision':'non_risk','reason':'补充材料未显示明确风险','events':[]},{}
    monkeypatch.setattr(model,'call_model',fake)
    asyncio.run(app.state.worker.process(app.state.store.one('SELECT * FROM jobs WHERE id=?',(job,))))
    latest=app.state.store.one('SELECT result_json FROM analyses WHERE document_id=? ORDER BY version DESC',(doc,))
    assert json.loads(latest['result_json'])['evidence_checklist']==frozen
    assert admin.patch(endpoint,json={**payload,'revision':2}).status_code==409
    assert admin.get(f'/api/evidence/{aid}').json()['checklist'][0]['status']=='provided'


def test_checklist_requires_materials_notes_and_same_case(app,admin,companies,monkeypatch):
    a,b=companies
    _,aid=insufficient(app,a,monkeypatch)
    _,bid=insufficient(app,b,monkeypatch)
    item=a.post(f'/api/evidence/{aid}/checklist',json={'title':'补齐适用范围'}).json()['id']
    endpoint=f'/api/evidence/{aid}/checklist/{item}'
    data={'title':'补齐适用范围','revision':1,'status':'provided'}
    assert a.patch(endpoint,json=data).status_code==400
    assert a.patch(endpoint,json={**data,'status':'not_needed'}).status_code==400
    assert a.patch(endpoint,json={**data,'status':'bad'}).status_code==400
    foreign=supplement(b,bid).json()['id']
    assert a.patch(endpoint,json={**data,'supplement_ids':[foreign]}).status_code==400
    assert b.patch(endpoint,json=data).status_code==404
    assert b.post(f'/api/evidence/{aid}/checklist/generate').status_code==404
    assert b.post(f'/api/evidence/{aid}/checklist',json={'title':'越权'}).status_code==404
    assert a.patch(endpoint,json={**data,'status':'not_needed','note':'此事项不适用，已核对业务范围'}).status_code==200
    assert a.post(f'/api/evidence/{aid}/checklist',json={'title':'   '}).status_code==400


def test_unlink_last_material_reopens_checklist(app,admin,monkeypatch):
    _,aid=insufficient(app,admin,monkeypatch);sid=supplement(admin,aid).json()['id']
    item=admin.post(f'/api/evidence/{aid}/checklist',json={'title':'补充原文'}).json()['id']
    admin.patch(f'/api/evidence/{aid}/checklist/{item}',json={'title':'补充原文','revision':1,'status':'provided','supplement_ids':[sid]})
    assert admin.delete(f'/api/evidence/{aid}/supplements/{sid}').status_code==200
    item=admin.get(f'/api/evidence/{aid}').json()['checklist'][0]
    assert item['status']=='open' and item['revision']==3 and not item['materials']


def version(c,sid,body,*,url='https://source.example/news/notice',status='completed',relevant=1):
    store=c.app.state.store;config=store.one('SELECT * FROM web_sources WHERE id=?',(sid,))
    with store.db() as db:
        rid=db.execute("INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (?,?,?,'2026-10-24T00:00:00+00:00')",(sid,json.dumps(config),status)).lastrowid
        pid=db.execute("INSERT INTO web_pages(run_id,url,title,body,fetched_at,digest,snapshot,relevant,reason,method) VALUES (?,?,'官方通知',?,'2026-10-24T00:00:00+00:00',?,'',?,'包含申报要求','direct')",(rid,url,body,str(rid),relevant)).lastrowid
    updates.index_runs(store,rid)
    return pid


def test_update_inbox_keeps_unread_change_after_unchanged_run(web_client):
    c=web_client;sid=add_source(c,category='监管机构')
    one=version(c,sid,'三十日内申报。')
    two=version(c,sid,'十五日内申报。')
    version(c,sid,'十五日内申报。')
    version(c,sid,'失败的正文。',status='failed')
    inbox=c.get('/api/web/updates').json()
    assert inbox['total']==1 and inbox['items'][0]['page_id']==two
    assert inbox['items'][0]['previous_page_id']==one
    assert c.get('/api/web/updates?change=added').json()['total']==1
    assert c.get('/api/web/updates?q=不存在').json()['total']==0
    assert c.get('/api/web/updates?category=监管机构').json()['total']==1
    assert c.get('/api/web/updates?date_from=2026-10-25').json()['total']==0
    before=c.app.state.store.rows('SELECT * FROM web_updates')
    updates.initialize(c.app.state.store)
    assert c.app.state.store.rows('SELECT * FROM web_updates')==before
    assert c.get('/api/web/updates?change=unchanged').status_code==400
    assert c.get('/api/web/updates?date_from=bad').status_code==400
    assert c.get('/api/web/updates?date_from=2026-10-25&date_to=2026-10-24').status_code==400


def test_update_review_history_and_conflicting_edits(web_client):
    c=web_client;sid=add_source(c);version(c,sid,'旧正文。');pid=version(c,sid,'新正文。')
    endpoint=f'/api/web/updates/{pid}'
    assert c.patch(endpoint,json={'revision':1,'status':'ignored'}).status_code==400
    assert c.patch(endpoint,json={'revision':1,'status':'ignored','note':'与当前业务无关'}).status_code==200
    assert c.get('/api/web/updates').json()['total']==0
    assert c.get('/api/web/updates?status=ignored').json()['items'][0]['reviewed_by']=='admin'
    assert c.patch(endpoint,json={'revision':1,'status':'reviewed'}).status_code==409
    assert c.patch(endpoint,json={'revision':2,'status':'pending'}).status_code==200
    history=c.get(endpoint+'/history').json()['items']
    assert [h['status'] for h in history]==['pending','ignored']
    assert history[1]['note']=='与当前业务无关'
    with c.app.state.store.db() as db:db.execute("UPDATE web_sources SET deleted_at='test' WHERE id=?",(sid,))
    assert c.get('/api/web/updates').json()['total']==0
    assert c.patch(endpoint,json={'revision':3,'status':'reviewed'}).status_code==404


def test_update_transfer_scope_dedup_rules_and_lock_cleanup(web_client):
    c=web_client;store=c.app.state.store;sid=add_source(c)
    version(c,sid,'旧申报要求。');pid=version(c,sid,'新申报要求：十五日内完成申报。')
    owner=make_company(c);path=f'/api/web/updates/{pid}/transfer'
    assert c.post(path,json={'revision':1,'company_id':999999}).status_code==400
    assert not store.one('SELECT action_token FROM web_updates WHERE page_id=?',(pid,))['action_token']
    response=c.post(path,json={'revision':1,'company_id':owner,'analyze':True})
    assert response.status_code==200,response.text
    doc=response.json()['items'][0]['id'];job=response.json()['items'][0]['job_id']
    assert store.one('SELECT company_id FROM documents WHERE id=?',(doc,))['company_id']==owner
    assert json.loads(store.one('SELECT rules_json FROM jobs WHERE id=?',(job,))['rules_json'])==store.setting('rules')
    assert c.get('/api/web/updates?status=reviewed').json()['items'][0]['document_id']==doc
    assert c.post(path,json={'revision':1,'company_id':owner}).status_code==409
    repeated=c.post(path,json={'revision':2,'company_id':owner,'analyze':True})
    assert repeated.status_code==200 and repeated.json()['items'][0]['id']==doc
    assert store.one('SELECT count(*) n FROM jobs')['n']==1
    with store.db() as db:db.execute("UPDATE web_updates SET action_token='busy' WHERE page_id=?",(pid,))
    assert c.post(path,json={'revision':3,'company_id':owner}).status_code==409
    assert c.patch(f'/api/web/updates/{pid}',json={'revision':3,'status':'pending'}).status_code==409


def test_update_non_hits_cannot_transfer_and_collector_indexes(web_client,monkeypatch):
    c=web_client;sid=add_source(c)
    version(c,sid,'旧正文。');pid=version(c,sid,'不相关正文。',relevant=0)
    assert c.post(f'/api/web/updates/{pid}/transfer',json={'revision':1,'company_id':make_company(c)}).status_code==409
    monkeypatch.setattr(websearch,'fetch_page',fake_fetch);monkeypatch.setattr(websearch.model,'call_model',fake_model)
    run=process(c,sid)
    assert run['status']=='completed'
    assert c.app.state.store.one('SELECT count(*) n FROM web_updates WHERE page_id IN (SELECT id FROM web_pages WHERE run_id=?)',(run['id'],))['n']==len(run['items'])


def test_update_comparison_baseline_stays_frozen_when_old_run_recovers(web_client):
    c=web_client;sid=add_source(c)
    old=version(c,sid,'早期失败快照。',status='failed')
    current=version(c,sid,'本次成功快照。')
    store=c.app.state.store
    with store.db() as db:db.execute("UPDATE web_runs SET status='completed' WHERE id=(SELECT run_id FROM web_pages WHERE id=?)",(old,))
    updates.index_runs(store)
    assert c.get(f'/api/web/pages/{current}/compare').json()['status']=='changed'
    assert c.get(f'/api/web/updates/{current}/comparison').json()['status']=='added'
