import json
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ingest import insert_document

HEADERS={'X-Requested-With':'risk-workbench'}

@pytest.fixture
def client(tmp_path):
    settings=Settings(data_dir=tmp_path,model_base_url='https://model.example/v1',model_name='test-model',model_api_key='test',model_mode='external')
    app=create_app(settings,run_worker=False)
    with TestClient(app,headers=HEADERS) as c:
        c.post('/api/auth/setup',json={'password':'test-password-2026'})
        yield c

def count(store,table,where='1=1',args=()):
    return store.one(f'SELECT COUNT(*) n FROM {table} WHERE {where}',args)['n']

def test_clear_demo_removes_only_demo_records(client):
    store=client.app.state.store
    assert client.post('/api/demo').json()['added']==4
    real,_=insert_document(store,{'title':'真实资料','body':'港口设备故障导致原料延迟七天。','source':'业务部门','url':'','date':''},'event',True)
    event_id=store.one('SELECT id FROM events LIMIT 1')['id']
    assert client.put(f'/api/events/{event_id}/review',json={'status':'accepted','note':'演示复核'}).status_code==200
    assert count(store,'review_history')==1
    result=client.delete('/api/demo').json()
    assert result=={'documents':4,'events':4}
    assert count(store,'documents','demo=1')==0 and count(store,'events')==0 and count(store,'analyses')==0 and count(store,'review_history')==0
    assert count(store,'documents','id=?',(real,))==1 and count(store,'chunks','document_id=?',(real,))==1
    assert client.delete('/api/demo').json()=={'documents':0,'events':0}

def test_delete_document_cascades_and_unlinks(client):
    store=client.app.state.store
    client.post('/api/demo')
    doc=store.one('SELECT id,file_path FROM documents WHERE demo=1 LIMIT 1')
    (store.directory/'uploads'/'shared.html').write_text('x');(store.directory/'uploads'/'own.pdf').write_text('y')
    other,_=insert_document(store,{'title':'另一份','body':'另一份正文内容足够长。','source':'s','url':'','date':''},'knowledge',True,file_path='shared.html',filename='a.html')
    mine,_=insert_document(store,{'title':'待删','body':'待删除资料正文内容。','source':'s','url':'','date':''},'knowledge',True,file_path='own.pdf',filename='b.pdf')
    with store.db() as db:
        db.execute("UPDATE documents SET file_path='shared.html' WHERE id=?",(doc['id'],))
        db.execute("INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (1,'{}','completed','now')")
        db.execute("INSERT INTO web_pages(run_id,url,title,body,fetched_at,digest,snapshot,relevant,imports_json) VALUES (1,'u','t','b','now','d','s.html',1,?)",(json.dumps({'knowledge':mine,'event':other}),))
    r=client.delete(f"/api/documents/{doc['id']}").json()
    assert r=={'documents':1,'events':1} and count(store,'chunks','document_id=?',(doc['id'],))==0
    assert (store.directory/'uploads'/'shared.html').exists()  # still used by another document
    assert client.delete(f'/api/documents/{mine}').json()['documents']==1
    assert not (store.directory/'uploads'/'own.pdf').exists()
    assert json.loads(store.one('SELECT imports_json FROM web_pages')['imports_json'])=={'event':other}
    assert client.delete(f'/api/documents/{mine}').status_code==404

def test_delete_refused_while_analysis_is_queued(client):
    store=client.app.state.store
    doc,_=insert_document(store,{'title':'分析中','body':'正在分析的资料正文。','source':'s','url':'','date':''},'event',True)
    with store.db() as db: db.execute("INSERT INTO jobs(document_id,status,created_at) VALUES (?,'queued','now')",(doc,))
    r=client.delete(f'/api/documents/{doc}')
    assert r.status_code==400 and '正在分析' in r.json()['detail']
    assert count(store,'documents','id=?',(doc,))==1
