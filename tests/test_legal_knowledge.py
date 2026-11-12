import json
import secrets

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ingest import insert_document
from app.legal_knowledge import structured_chunks, section_spans, validate_metadata
from app.retrieval import retrieve
from app.store import Store
from app import consultation

HEADERS = {'X-Requested-With': 'risk-workbench'}
BODY = '合同争议判决\n事实认定\n企业支付了合同货款但未收到设备。\n法院认为\n应当依据合同约定判断履行责任。\n判决如下\n被告返还货款。'


def test_exact_section_offsets_and_no_narrative_false_heading():
    pieces = list(structured_chunks(BODY, size=12))
    assert ''.join(text for _, text, _ in pieces) == BODY
    assert {tag for _,_,tag in pieces} == {'general','facts','reasoning','disposition'}
    assert section_spans('新闻提到法院认为合同有效，但不是判决正文。')[0][2] == 'general'
    for locator,text,tag in pieces:
        a,b = locator.replace('正文字符 ','').split('–')
        assert BODY[int(a)-1:int(b)] == text


@pytest.mark.parametrize('heading,tag', [('PERTIMBANGAN HUKUM','reasoning'), ('MENGADILI','disposition'),
    ('Statement of Facts','facts'), ('Applicable Law','law'), ('仲裁庭认为','reasoning')])
def test_multilingual_headings(heading, tag):
    assert list(structured_chunks(heading+'\n合同当事人应承担履行责任。'))[0][2] == tag


@pytest.mark.parametrize('values', [ {'category':'made_up'}, {'validity':'in_force'},
    {'verification_urls':['javascript:alert(1)']}, {'effective_from':'2026-99-12'},
    {'effective_from':'2026-02-01','effective_to':'2026-01-01'}, []])
def test_metadata_rejects_unfounded_validity_and_invalid_inputs(values):
    with pytest.raises(ValueError): validate_metadata(values)


def test_filtered_search_does_not_allow_vector_hits_to_bypass_sections(tmp_path, monkeypatch):
    store = Store(tmp_path)
    doc = insert_document(store, {'title':'合同履行判决','body':BODY,'legal_metadata':{'category':'judgment'}}, 'knowledge')[0]
    other = insert_document(store, {'title':'合同履行新闻','body':'合同履行出现争议。'}, 'knowledge')[0]
    candidates = store.rows('SELECT c.*,d.title,d.source,d.date FROM chunks c JOIN documents d ON d.id=c.document_id ORDER BY c.id DESC')
    monkeypatch.setattr('app.retrieval.fuse_hits', lambda *args: candidates)
    result = retrieve(store,'合同履行',category='judgment',section='reasoning',limit=20)
    assert result and all(r['document_id']==doc and r['section_type']=='reasoning' for r in result)
    assert all(r['document_id'] != other for r in result)


def test_migration_preserves_original_chunks_and_adds_exact_section_fragments(tmp_path):
    store = Store(tmp_path)
    doc = insert_document(store, {'title':'历史判决','body':BODY}, 'knowledge')[0]
    with store.db() as db:
        db.execute('DELETE FROM chunks WHERE document_id=?',(doc,))
        original = db.execute('INSERT INTO chunks(document_id,locator,text) VALUES (?,?,?)',(doc,f'正文字符 1–{len(BODY)}',BODY)).lastrowid
        db.execute("DELETE FROM settings WHERE key='legal_section_migration_v1'")
    migrated = Store(tmp_path)
    assert migrated.one('SELECT text FROM chunks WHERE id=?',(original,))['text'] == BODY
    assert migrated.one("SELECT count(*) n FROM chunks WHERE document_id=? AND section_type='reasoning'",(doc,))['n'] == 1
    before = migrated.rows('SELECT * FROM chunks')
    assert Store(tmp_path).rows('SELECT * FROM chunks') == before


def test_api_metadata_import_filters_permissions_and_stale_revision(tmp_path):
    app = create_app(Settings(data_dir=tmp_path),run_worker=False)
    with TestClient(app,headers=HEADERS) as admin, TestClient(app,headers=HEADERS) as tenant:
        assert admin.post('/api/auth/setup',json={'password':secrets.token_urlsafe(20)}).status_code == 200
        schema = admin.get('/api/knowledge/schema').json()
        assert len(schema['categories']) == 15
        doc = admin.post('/api/documents',json={'title':'合同履行判决','body':BODY,'kind':'knowledge','legal_metadata':{'category':'judgment','jurisdiction':'印度尼西亚'}}).json()['id']
        imported = admin.post('/api/import',files={'file':('合成法规.txt','合成法规要求企业保存记录。'.encode())},data={'kind':'knowledge','legal_metadata':json.dumps({'category':'id_law'})})
        assert imported.status_code==200 and imported.json()['created']==1
        assert admin.get('/api/documents?kind=knowledge&category=judgment').json()['total'] == 1
        assert admin.get('/api/documents?kind=knowledge&validity=in_force').json()['total'] == 0
        detail = admin.get(f'/api/documents/{doc}').json()
        assert detail['legal_metadata']['category']=='judgment'
        result = admin.get('/api/knowledge/search',params={'q':'合同履行','category':'judgment','section':'reasoning'}).json()
        assert result['items'] and all(r['section_type']=='reasoning' for r in result['items'])
        assert all('事实认定' not in w['text'] and '判决如下' not in w['text'] for r in result['items'] for w in r['hit_windows'])
        update = {'revision':0,'metadata':{'category':'case'}}
        assert admin.put(f'/api/documents/{doc}/legal-metadata',json=update).status_code==200
        assert admin.put(f'/api/documents/{doc}/legal-metadata',json=update).status_code==409
        tenant.cookies.update(admin.cookies)
        assert tenant.post('/api/auth/register',json={'username':'legal_tenant','password':secrets.token_urlsafe(20),'name':'合成企业'}).status_code==200
        assert tenant.put(f'/api/documents/{doc}/legal-metadata',json={'revision':1,'metadata':{}}).status_code==403
        assert tenant.post('/api/documents',json={'title':'企业合同','body':BODY,'kind':'knowledge'}).status_code==403
        assert tenant.get('/api/knowledge/search?q=合同').status_code==403
        assert admin.get('/api/knowledge/search?section=unknown&q=合同').status_code==400


def test_report_enforces_source_category_and_preserves_citations(tmp_path):
    source = {'document_id':1,'title':'合成法规','source':'测试机构','date':'2026-01-01','locator':'正文字符 1–20',
              'text':'合成法规要求企业保存经营记录。','section_type':'law','legal_metadata':{'category':'id_law','validity':'in_force'}}
    candidate = {'status':'answered','blocks':[{'section':'basis','text':'企业应保存经营记录。','citations':[{'ref':'S1','quote':source['text']}]}]}
    answer = consultation.verify_answer(candidate,{'S1':source},report=True)
    assert answer['blocks'][0]['heading']=='法律依据' and len(answer['missing_sections'])==3
    source['legal_metadata']['validity']='unknown'
    with pytest.raises(ValueError): consultation.verify_answer(candidate,{'S1':source},report=True)
    candidate['blocks'][0]['section']='cases'
    with pytest.raises(ValueError): consultation.verify_answer(candidate,{'S1':source},report=True)


def test_report_endpoint_explains_gaps_and_passes_original_section_context(tmp_path, monkeypatch):
    app = create_app(Settings(data_dir=tmp_path,model_base_url='https://example.test/v1',model_name='test',model_api_key='test'),run_worker=False)
    with TestClient(app,headers=HEADERS) as client:
        client.post('/api/auth/setup',json={'password':secrets.token_urlsafe(20)})
        client.post('/api/documents',json={'title':'合同履行判决','body':BODY,'kind':'knowledge','legal_metadata':{'category':'judgment'}})
        async def answer(settings,payload,system):
            assert '不输出数值评分' in system
            ref = next(row['ref'] for row in payload['evidence'] if row['section_type']=='reasoning')
            unit = next(u for u in payload['quote_units'] if u['ref']==ref and '依据合同' in u['text'])
            return {'status':'answered','blocks':[{'section':'cases','text':'本案裁判理由依据合同约定判断责任。','citations':[{'ref':ref,'unit_id':unit['unit_id']}]}]},{}
        monkeypatch.setattr(consultation.model,'call_model',answer)
        result=client.post('/api/consultation',json={'question':'合同履行责任','mode':'report'})
        assert result.status_code==200, result.text
        assert result.json()['mode']=='report' and '法律依据' in result.json()['missing_sections']
        exported=client.get(f"/api/consultation/reports/{result.json()['report_id']}/docx")
        assert exported.status_code==200 and exported.content.startswith(b'PK')
        from docx import Document
        import io
        doc=Document(io.BytesIO(exported.content))
        assert any(p.text=='类似案例分析' for p in doc.paragraphs)
        (tmp_path/'report.docx').write_bytes(exported.content)
        assert client.get('/api/consultation/reports/999/docx').status_code==404


def test_report_export_is_scoped_to_current_company(tmp_path):
    app=create_app(Settings(data_dir=tmp_path),run_worker=False)
    with TestClient(app,headers=HEADERS) as admin, TestClient(app,headers=HEADERS) as a, TestClient(app,headers=HEADERS) as b:
        admin.post('/api/auth/setup',json={'password':secrets.token_urlsafe(20)})
        ids=[]
        for index, client in enumerate((a,b)):
            client.cookies.update(admin.cookies)
            ids.append(client.post('/api/auth/register',json={'username':f'export_tenant_{index}','password':secrets.token_urlsafe(20),'name':f'合成企业{index}'}).json()['company_id'])
        with app.state.store.db() as db:
            rid=db.execute('INSERT INTO consultation_reports(company_id,question,result_json,created_at) VALUES (?,?,?,?)',
                (ids[0],'合同问题',json.dumps({'blocks':[],'sources':[]}), '2026-11-11')).lastrowid
        assert a.get(f'/api/consultation/reports/{rid}/docx').status_code==403
        assert b.get(f'/api/consultation/reports/{rid}/docx').status_code==403
        assert admin.get(f'/api/consultation/reports/{rid}/docx').status_code==200
        admin.post(f'/api/companies/{ids[0]}/activate')
        assert admin.get(f'/api/consultation/reports/{rid}/docx').status_code==200


def test_manual_cross_verification_requires_recorded_independent_sources():
    with pytest.raises(ValueError): validate_metadata({'corroboration':'confirmed','verification_urls':['https://one.test/a','https://one.test/b']})
    valid=validate_metadata({'corroboration':'confirmed','verified_on':'2026-11-11','verification_note':'人工核对两个独立发布机构，事实一致。','verification_urls':['https://one.test/a','https://two.test/b']})
    assert valid['corroboration']=='confirmed'
