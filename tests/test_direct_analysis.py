"""Regression proof that no import, job or knowledge path needs per-item consent."""
import asyncio
import json
from app import enrich
from app.retrieval import retrieve
from test_companies import client


def test_legacy_false_flags_do_not_block_worker_or_company_context(client,monkeypatch):
    store=client.app.state.store
    company=client.post('/api/companies',json={'name':'业务公司','industry':'设备制造','allow_external':False}).json()['id']
    document=client.post('/api/documents',json={'title':'业务事项','body':'设备供应中断，需要核实停产影响和恢复计划。','allow_external':False}).json()['id']
    with store.db() as db:
        db.execute('UPDATE documents SET allow_external=0 WHERE id=?',(document,))
        profile=json.loads(db.execute('SELECT profile_json FROM companies WHERE id=?',(company,)).fetchone()[0])
        profile['allow_external']=False
        db.execute('UPDATE companies SET profile_json=? WHERE id=?',(json.dumps(profile),company))
    assert client.post('/api/jobs/preflight',json={'document_ids':[document]}).json()['ready']
    queued=client.post('/api/jobs',json={'document_ids':[document]})
    assert queued.status_code==200
    job=store.one('SELECT * FROM jobs WHERE id=?',(queued.json()['items'][0]['id'],))
    seen=[]
    async def model(settings,payload,**kwargs):
        seen.append(payload)
        return {'decision':'non_risk','reason':'需进一步监测，当前未形成实质风险。','events':[]},{}
    monkeypatch.setattr('app.jobs.model.call_model',model)
    asyncio.run(client.app.state.worker.process(job))
    assert seen and seen[0]['company']['name']=='业务公司'
    assert seen[0]['scope']['industry']=='设备制造'
    assert store.one('SELECT status FROM jobs WHERE id=?',(job['id'],))['status']=='completed'
    assert store.one('SELECT count(*) n FROM analyses WHERE document_id=?',(document,))['n']==1


def test_upload_and_knowledge_work_without_consent_fields(client,monkeypatch):
    response=client.post('/api/import',files={'file':('事项.txt','进口设备到货延期，需核实供应链影响。'.encode())})
    assert response.status_code==200
    document=response.json()['results'][0]['id']
    assert client.post('/api/jobs/preflight',json={'document_ids':[document]}).json()['ready']
    assert client.post('/api/jobs',json={'document_ids':[document]}).status_code==200
    knowledge=client.post('/api/documents',json={'kind':'knowledge','title':'设备进口管理','body':'设备进口需要核实申报材料、进口许可及通关安排。'}).json()['id']
    with client.app.state.store.db() as db:db.execute('UPDATE documents SET allow_external=0 WHERE id=?',(knowledge,))
    assert knowledge in {h['document_id'] for h in retrieve(client.app.state.store,'设备进口',external=True)}
    async def summarize(settings,payload,**kwargs):
        return {'summary':'规定设备进口申报、许可和通关安排。','keywords':['设备进口','许可','通关']},{}
    monkeypatch.setattr(enrich.model,'call_model',summarize)
    assert asyncio.run(client.app.state.enricher.run_once())
    assert client.app.state.store.one('SELECT zh_state FROM documents WHERE id=?',(knowledge,))['zh_state']=='done'
