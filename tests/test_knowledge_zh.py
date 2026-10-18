import asyncio
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ingest import insert_document
from app.retrieval import retrieve
from app import enrich

HEADERS={'X-Requested-With':'risk-workbench'}

@pytest.fixture
def client(tmp_path):
    settings=Settings(data_dir=tmp_path,model_base_url='https://model.example/v1',model_name='test-model',model_api_key='test',model_mode='external')
    app=create_app(settings,run_worker=False)
    with TestClient(app,headers=HEADERS) as c:
        c.post('/api/auth/setup',json={'password':'test-password-2026'})
        yield c

def add(store,title,body,allow=True):
    doc_id,_=insert_document(store,{'title':title,'body':body,'source':'测试','url':'','date':''},'knowledge',allow)
    return doc_id

LAW='Peraturan Menteri Ketenagakerjaan tentang bantuan subsidi upah bagi pekerja. '*30

def test_chinese_summary_makes_foreign_documents_searchable_in_chinese(client,monkeypatch):
    store=client.app.state.store
    law=add(store,'Permenaker Nomor 5 Tahun 2025',LAW)
    secret=add(store,'Dokumen internal',LAW,allow=False)
    async def fake(settings,payload,system=None):
        assert system==enrich.SUMMARY_SYSTEM and payload['title']=='Permenaker Nomor 5 Tahun 2025'
        return {'summary':'印尼劳工部2025年第5号部长条例，规定向劳动者发放工资补贴。','keywords':['外籍劳工','工资补贴','劳工部']},{}
    monkeypatch.setattr(enrich.model,'call_model',fake)
    assert not retrieve(store,'工资补贴')
    assert asyncio.run(client.app.state.enricher.run_once()) is True
    assert asyncio.run(client.app.state.enricher.run_once()) is False  # the unauthorised document is never sent
    assert store.one('SELECT zh_state FROM documents WHERE id=?',(secret,))['zh_state']==''
    items=client.get('/api/knowledge/search?q=工资补贴').json()['items']
    assert [i['document_id'] for i in items]==[law]  # one hit per document, with its summary
    assert items[0]['zh_summary'].startswith('印尼劳工部') and items[0]['text'] in LAW
    hits=retrieve(store,'工资补贴',limit=4)
    assert hits and all(h['document_id']==law and 'zh_summary' not in h for h in hits)  # analysis gets original text only

def test_model_outage_leaves_documents_pending_and_bad_output_marks_failed(client,monkeypatch):
    store=client.app.state.store
    doc=add(store,'Treaty','ASEAN Treaty on Extradition. '*40)
    async def down(settings,payload,system=None):raise ValueError('模型服务返回 HTTP 503，请检查服务地址、权限或配额。')
    monkeypatch.setattr(enrich.model,'call_model',down)
    assert asyncio.run(client.app.state.enricher.run_once()) is False
    assert store.one('SELECT zh_state FROM documents WHERE id=?',(doc,))['zh_state']==''
    async def junk(settings,payload,system=None):return {'items':[]},{}
    monkeypatch.setattr(enrich.model,'call_model',junk)
    assert asyncio.run(client.app.state.enricher.run_once()) is True
    assert store.one('SELECT zh_state FROM documents WHERE id=?',(doc,))['zh_state']=='failed'
