import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.retrieval import retrieve

@pytest.fixture
def client(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,model_mode='external',model_base_url='https://example.com/v1',model_name='test',model_api_key='test'),run_worker=False)
    with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as c:
        c.post('/api/auth/setup',json={'password':'test-password-2026'})
        rules=app.state.store.setting('rules');rules['confirmed']=True;app.state.store.set_setting('rules',rules)
        yield c

def test_profile_update_sync_and_company_retrieval(client):
    c=client
    a={'name':'测试甲公司','industry':'纺织','business':'印尼纺织制造','allow_external':True}
    aid=c.post('/api/companies',json=a).json()['id']
    doc=c.post(f'/api/companies/{aid}/knowledge').json()['id']
    assert c.post(f'/api/companies/{aid}/knowledge').json()['id']==doc
    a['business']='纺织生产与棉花进口'
    assert c.put(f'/api/companies/{aid}',json=a).status_code==200
    assert '棉花进口' in c.get(f'/api/documents/{doc}').json()['body']
    bid=c.post('/api/companies',json={'name':'测试乙公司','business':'棉花贸易'}).json()['id']
    bdoc=c.post(f'/api/companies/{bid}/knowledge').json()['id']
    assert {h['document_id'] for h in retrieve(c.app.state.store,'棉花')}=={bdoc}
    c.post(f'/api/companies/{aid}/activate')
    assert {h['document_id'] for h in retrieve(c.app.state.store,'棉花',external=True)}=={doc}
    assert c.get('/api/documents?kind=knowledge').json()['total']==2
    assert c.put('/api/companies/999',json=a).status_code==404
    assert c.post('/api/companies',json={'name':'   '}).status_code==400

def test_job_keeps_company_snapshot_and_external_consent(client,monkeypatch):
    c=client;store=c.app.state.store
    a=c.post('/api/companies',json={'name':'甲公司私密','industry':'私密行业','allow_external':True}).json()['id']
    doc=c.post('/api/documents',json={'title':'资料测试','body':'公开正文用于风险分析测试，包含供应链相关信息。','allow_external':True}).json()['id']
    jid=c.post('/api/jobs',json={'document_ids':[doc]}).json()['items'][0]['id']
    c.post('/api/companies',json={'name':'乙公司','industry':'电子'})
    captured=[]
    async def fake(settings,payload,**kwargs):
        captured.append(payload)
        return {'decision':'non_risk','reason':'无风险','events':[]},{}
    monkeypatch.setattr('app.jobs.model.call_model',fake)
    asyncio.run(c.app.state.worker.process(store.one('SELECT * FROM jobs WHERE id=?',(jid,))))
    assert captured[0]['company']['name']=='甲公司私密'
    assert captured[0]['scope']['industry']=='私密行业'
    jid=c.post('/api/jobs',json={'document_ids':[doc]}).json()['items'][0]['id']
    asyncio.run(c.app.state.worker.process(store.one('SELECT * FROM jobs WHERE id=?',(jid,))))
    assert captured[-1]['company']=={}
    assert captured[-1]['scope']['industry']=='未指定行业'
    assert store.one('SELECT status FROM jobs WHERE id=?',(jid,))['status']=='completed'
