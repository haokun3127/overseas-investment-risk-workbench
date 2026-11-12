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
        assert system==enrich.SUMMARY_SYSTEM and payload['title'] in ('Permenaker Nomor 5 Tahun 2025','Dokumen internal')
        return {'summary':'印尼劳工部2025年第5号部长条例，规定向劳动者发放工资补贴。','keywords':['外籍劳工','工资补贴','劳工部']},{}
    monkeypatch.setattr(enrich.model,'call_model',fake)
    assert not retrieve(store,'工资补贴')
    assert law == secret  # identical body is reused despite a different title
    assert asyncio.run(client.app.state.enricher.run_once()) is True
    assert asyncio.run(client.app.state.enricher.run_once()) is False
    assert store.one('SELECT zh_state FROM documents WHERE id=?',(secret,))['zh_state']=='done'
    items=client.get('/api/knowledge/search?q=工资补贴').json()['items']
    assert {i['document_id'] for i in items}=={law,secret}  # both records are usable without an authorization toggle
    assert items[0]['zh_summary'].startswith('印尼劳工部') and items[0]['text'] in LAW
    hits=retrieve(store,'工资补贴',limit=4)
    assert hits and all(h['document_id'] in (law,secret) and 'zh_summary' not in h for h in hits)  # analysis gets original text only

def test_synonym_and_foreign_body_still_find_the_document(client):
    store=client.app.state.store
    stated=add(store,'Wage rule','English text without the wage term. '*20)
    buried=add(store,'Permenaker wage chapter','Bab tentang pengupahan dan upah minimum pekerja. '*20)
    with store.db() as db:
        db.execute('UPDATE documents SET zh_summary=?,zh_keywords=? WHERE id=?',('规定劳动者工资支付标准。','工资',stated))
        db.execute('UPDATE documents SET zh_summary=?,zh_keywords=? WHERE id=?',('印尼劳工部条例，调整补贴发放地区。','劳工部,补贴',buried))
    assert any(hit['document_id']==stated for hit in retrieve(store,'薪酬'))
    body_hits=retrieve(store,'工资')
    assert any(hit['document_id']==buried for hit in body_hits)
    assert any(hit['document_id']==stated for hit in body_hits)
    stated_score=next(hit['score'] for hit in body_hits if hit['document_id']==stated)
    buried_score=next(hit['score'] for hit in body_hits if hit['document_id']==buried)
    assert stated_score >= buried_score

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

def test_automatic_category_does_not_overwrite_manual_classification(client,monkeypatch):
    import json
    store=client.app.state.store
    doc=add(store,'合同法条','合同成立后双方应当依约履行义务。')
    async def classified(settings,payload,system=None):
        return {'summary':'合同履行法律条文。','keywords':['合同履行'],'category':'id_law'},{}
    monkeypatch.setattr(enrich.model,'call_model',classified)
    assert asyncio.run(client.app.state.enricher.run_once())
    row=store.one('SELECT legal_meta,legal_revision FROM documents WHERE id=?',(doc,))
    assert json.loads(row['legal_meta'])['category']=='id_law' and row['legal_revision']==1
    other=add(store,'争议新闻','双方当事人就设备交付产生争议，尚未提起诉讼。')
    async def changed_during_call(settings,payload,system=None):
        metadata=json.loads(store.one('SELECT legal_meta FROM documents WHERE id=?',(other,))['legal_meta'])
        metadata['category']='incident'
        with store.db() as db:
            db.execute('UPDATE documents SET legal_meta=?,legal_revision=legal_revision+1 WHERE id=?',(json.dumps(metadata),other))
        return {'summary':'合同争议资料。','keywords':['合同争议'],'category':'judgment'},{}
    monkeypatch.setattr(enrich.model,'call_model',changed_during_call)
    assert asyncio.run(client.app.state.enricher.run_once())
    row=store.one('SELECT legal_meta,legal_revision FROM documents WHERE id=?',(other,))
    assert json.loads(row['legal_meta'])['category']=='incident' and row['legal_revision']==1

