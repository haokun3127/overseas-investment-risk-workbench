import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import model
from app.ingest import insert_document
from app.store import Store
from test_tenant_authz import app, admin, companies, add_event


def insufficient(app,client,monkeypatch):
    doc=add_event(client)
    job=client.post('/api/jobs',json={'document_ids':[doc]}).json()['items'][0]['id']
    async def fake(*args,**kwargs):
        return {'decision':'insufficient','reason':'缺少通知的完整正文及具体适用对象。','events':[]},{}
    monkeypatch.setattr(model,'call_model',fake)
    asyncio.run(app.state.worker.process(app.state.store.one('SELECT * FROM jobs WHERE id=?',(job,))))
    row=app.state.store.one('SELECT * FROM analyses WHERE document_id=?',(doc,))
    assert row is not None
    return doc,row['id']


def supplement(client,aid,**extra):
    return client.post(f'/api/evidence/{aid}/supplements',json={
        'title':'补充通知原文','body':'通知明确要求园区全部企业按期申报，未申报将暂停原料采购。','allow_external':True,**extra})


def test_complete_supplement_flow_preserves_history_and_citations(app,admin,monkeypatch):
    doc,aid=insufficient(app,admin,monkeypatch)
    assert admin.get('/api/evidence').json()['counts']=={'pending':1,'resolved':0}
    assert admin.get('/api/workspace').json()['needs_evidence']==1
    assert admin.get('/api/documents').json()['items'][0]['analysis_id']==aid
    assert admin.post(f'/api/evidence/{aid}/reanalyze').status_code==409
    saved=supplement(admin,aid)
    assert saved.status_code==200,saved.text
    sid=saved.json()['id']
    assert admin.get('/api/documents?kind=knowledge').json()['total']==0
    assert admin.get('/api/documents').json()['total']==1
    assert supplement(admin,aid).json()['created'] is False
    detail=admin.get(f'/api/evidence/{aid}').json()
    assert len(detail['supplements'])==1 and detail['editable']
    queued=admin.post(f'/api/evidence/{aid}/reanalyze').json()['id']
    assert admin.post(f'/api/evidence/{aid}/reanalyze').json()=={'id':queued,'existing':True}
    assert admin.delete(f'/api/evidence/{aid}/supplements/{sid}').status_code==409
    assert admin.patch(f'/api/documents/{sid}/policy',json={'allow_external':False}).status_code==409
    assert admin.delete(f'/api/documents/{sid}').status_code==400
    rules=app.state.store.setting('rules');rules['version']='changed-after-submit';rules['confirmed']=False
    app.state.store.set_setting('rules',rules)
    captured=[]
    async def fake(settings,payload):
        captured.append(payload)
        ref=next(r for r in payload['references'] if r.get('role')=='supplement')
        return {'decision':'risk','reason':'补充正文提供了直接证据。','events':[{
            'title':'原料采购暂停风险','category':'准入审批限制风险','level':'orange','summary':'申报义务明确',
            'impact':'可能影响生产','recommendation':'核对并完成申报',
            'evidence':[{'reference':ref['reference'],'quote':'未申报将暂停原料采购','reason':'补充原文直接规定后果'}]}]},{}
    monkeypatch.setattr(model,'call_model',fake)
    asyncio.run(app.state.worker.process(app.state.store.one('SELECT * FROM jobs WHERE id=?',(queued,))))
    assert captured[0]['rules']['version']!='changed-after-submit'
    latest=app.state.store.one('SELECT * FROM analyses WHERE document_id=? ORDER BY version DESC',(doc,))
    assert latest['decision']=='risk' and latest['version']==2
    result=json.loads(latest['result_json'])
    assert result['parent_analysis_id']==aid and result['supplement_document_ids']==[sid]
    event=admin.get('/api/events').json()['items'][0]
    evidence=admin.get(f'/api/events/{event["id"]}').json()['evidence'][0]
    assert evidence['document_id']==sid
    assert admin.get(f'/api/documents/{sid}').json()['body'].find(evidence['quote'])>=0
    assert admin.get('/api/evidence').json()['counts']=={'pending':0,'resolved':1}
    assert len(admin.get('/api/evidence?status=resolved').json()['items'])==1
    assert len(admin.get(f'/api/evidence/{aid}').json()['history'])==2
    assert supplement(admin,aid).status_code==409
    assert admin.get(f'/api/evidence/{latest["id"]}').json()['editable'] is False


def test_supplements_respect_tenant_scope_and_auth(app,companies,admin,monkeypatch):
    a,b=companies
    doc,aid=insufficient(app,a,monkeypatch)
    sid=supplement(a,aid,allow_external=False).json()['id']
    assert a.get(f'/api/documents/{sid}').status_code==200
    assert b.get('/api/evidence').json()['total']==0
    for method,path,kwargs in [
        ('get',f'/api/evidence/{aid}',{}),
        ('get',f'/api/documents/{sid}',{}),
        ('post',f'/api/evidence/{aid}/supplements',{'json':{'title':'越权','body':'不得越权'}}),
        ('post',f'/api/evidence/{aid}/reanalyze',{}),
        ('delete',f'/api/evidence/{aid}/supplements/{sid}',{}),
        ('post',f'/api/evidence/{aid}/upload',{'files':{'file':('test.txt',b'hello')}}),
    ]:
        assert getattr(b,method)(path,**kwargs).status_code==404
    assert a.post(f'/api/evidence/{aid}/reanalyze').status_code==409
    assert a.patch(f'/api/documents/{sid}/policy',json={'allow_external':True}).status_code==200
    assert a.post(f'/api/evidence/{aid}/reanalyze').status_code==200
    assert admin.get('/api/evidence').json()['total']==1
    with TestClient(app) as anon:
        assert anon.get('/api/evidence').status_code==401


def test_attachment_validation_limits_unlink_and_cleanup(app,admin,monkeypatch):
    doc,aid=insufficient(app,admin,monkeypatch)
    endpoint=f'/api/evidence/{aid}/upload'
    uploaded=admin.post(endpoint,files={'file':('补充正文.txt','这是可核验的补充通知正文内容。'.encode())},data={'allow_external':'true'})
    assert uploaded.status_code==200,uploaded.text
    sid=uploaded.json()['id']
    assert admin.get(f'/api/documents/{sid}/file').status_code==200
    assert admin.post(endpoint,files={'file':('huge.txt',b'a'*24001)}).status_code==400
    assert admin.post(endpoint,files={'file':('bad.exe',b'bad')}).status_code==400
    assert admin.post(endpoint,files={'file':('multi.csv','标题,正文\n甲,正文甲\n乙,正文乙'.encode())}).status_code==400
    for i in range(9):assert supplement(admin,aid,title=f'补充{i}').status_code==200
    before=app.state.store.one('SELECT count(*) n FROM documents')['n']
    assert supplement(admin,aid,title='超过数量限制').status_code==409
    assert app.state.store.one('SELECT count(*) n FROM documents')['n']==before
    assert admin.delete(f'/api/evidence/{aid}/supplements/{sid}').status_code==200
    assert admin.get(f'/api/documents/{sid}').status_code==200  # historical source remains readable
    assert admin.delete(f'/api/documents/{doc}').status_code==200
    assert not app.state.store.rows('SELECT * FROM document_evidence')


def test_queue_uses_latest_analysis_and_excludes_quarantine_and_demo(app,admin,monkeypatch):
    doc,aid=insufficient(app,admin,monkeypatch)
    store=app.state.store
    assert admin.get('/api/evidence?q=不存在').json()['total']==0
    assert admin.get('/api/evidence?status=invalid').status_code==400
    with store.db() as db:db.execute("UPDATE documents SET quarantined_at='test' WHERE id=?",(doc,))
    assert admin.get('/api/evidence').json()['total']==0
    assert admin.get(f'/api/evidence/{aid}').status_code==404
    with store.db() as db:db.execute("UPDATE documents SET quarantined_at=NULL,demo=1 WHERE id=?",(doc,))
    assert admin.get('/api/evidence').json()['total']==0
    assert admin.get(f'/api/evidence/{aid}').status_code==404


def test_queued_manual_rules_are_frozen_and_upgrade_is_idempotent(app,admin,monkeypatch):
    doc=add_event(admin)
    store=app.state.store
    old=store.setting('rules')
    jid=admin.post('/api/jobs',json={'document_ids':[doc]}).json()['items'][0]['id']
    changed={**old,'version':'later','confirmed':False};store.set_setting('rules',changed)
    captured=[]
    async def fake(settings,payload):
        captured.append(payload['rules'])
        return {'decision':'non_risk','reason':'未发现明确风险','events':[]},{}
    monkeypatch.setattr(model,'call_model',fake)
    asyncio.run(app.state.worker.process(store.one('SELECT * FROM jobs WHERE id=?',(jid,))))
    assert captured==[old]
    saved=store.one('SELECT * FROM jobs WHERE id=?',(jid,))
    assert json.loads(saved['rules_json'])==old and saved['rules_snapshot_origin']=='submission'
    assert admin.post('/api/jobs',json={'document_ids':[doc]}).status_code==409
    with store.db() as db:
        legacy=db.execute("INSERT INTO jobs(document_id,status,created_at,company_json) VALUES (?,'queued','test','{}')",(doc,)).lastrowid
    Store(store.directory)
    row=store.one('SELECT * FROM jobs WHERE id=?',(legacy,))
    assert json.loads(row['rules_json'])==changed and row['rules_snapshot_origin']=='upgrade'
    store.set_setting('rules',old)
    Store(store.directory)
    assert store.one('SELECT rules_json FROM jobs WHERE id=?',(legacy,))['rules_json']==row['rules_json']


def test_normal_retry_keeps_linked_supplements_and_checks_policy(app,admin,monkeypatch):
    doc,aid=insufficient(app,admin,monkeypatch)
    sid=supplement(admin,aid,allow_external=False).json()['id']
    assert not admin.post('/api/jobs/preflight',json={'document_ids':[doc]}).json()['ready']
    assert admin.post('/api/jobs',json={'document_ids':[doc]}).status_code==400
    admin.patch(f'/api/documents/{sid}/policy',json={'allow_external':True})
    assert admin.post('/api/jobs/preflight',json={'document_ids':[doc]}).json()['ready']
    job=admin.post('/api/jobs',json={'document_ids':[doc]}).json()['items'][0]['id']
    queued=app.state.store.one('SELECT * FROM jobs WHERE id=?',(job,))
    assert queued['parent_analysis_id']==aid and json.loads(queued['supplements_json'])[0]['document_id']==sid
    listed=admin.get('/api/jobs').json()['items'][0]
    assert listed['rule_version'] and listed['supplement_document_ids']==[sid]
    assert 'supplements_json' not in listed and 'rules_json' not in listed


def test_supplement_limit_and_worker_rechecks_revoked_evidence(app,admin,monkeypatch):
    doc,aid=insufficient(app,admin,monkeypatch)
    sid=supplement(admin,aid,body='补充事实。'*4000).json()['id']
    assert supplement(admin,aid,title='超限材料',body='补充。'*2000).status_code==409
    queued=admin.post(f'/api/evidence/{aid}/reanalyze').json()['id']
    with app.state.store.db() as db:db.execute('UPDATE documents SET allow_external=0 WHERE id=?',(sid,))
    called=[]
    async def must_not_call(*args,**kwargs):called.append(True);raise AssertionError('no unauthorized calls')
    monkeypatch.setattr(model,'call_model',must_not_call)
    asyncio.run(app.state.worker.process(app.state.store.one('SELECT * FROM jobs WHERE id=?',(queued,))))
    assert not called
    assert app.state.store.one('SELECT status FROM jobs WHERE id=?',(queued,))['status']=='failed'
    assert app.state.store.one('SELECT count(*) n FROM analyses WHERE document_id=?',(doc,))['n']==1
