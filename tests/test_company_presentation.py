import json
import pytest
from app.presentation import clean_company_profile, clean_reference, match_company
from scripts.clean_company_presentation import apply
from test_companies import client


def test_metadata_markers_removed_but_evidence_and_business_names_preserved():
    assert clean_company_profile({'name':'PT Example（S1业务部） 〔S2〕','business':'经营资料〔S1〕','id':7}) == {
        'name':'PT Example（S1业务部）','business':'经营资料','id':7}
    quote='原文明确包含〔S1〕，必须原样留存。'
    assert clean_reference({'title':'项目〔S2〕','quote':quote})=={'title':'项目','quote':quote}
    rows=[{'id':7,'profile_json':json.dumps({'name':'PT Example'})}]
    assert match_company(rows,{'name':'PT Example 〔S2〕'})['id']==7
    with pytest.raises(ValueError):
        match_company(rows,{'name':'未找到'})
    with pytest.raises(ValueError):
        match_company(rows+rows,{'name':'PT Example'})


def test_company_cleanup_is_audited_idempotent_and_preserves_source(client):
    store=client.app.state.store
    cid=client.post('/api/companies',json={'name':'公司甲 〔S1〕'}).json()['id']
    assert client.get('/api/companies').json()['items'][0]['name']=='公司甲'
    did=client.post(f'/api/companies/{cid}/knowledge').json()['id']
    with store.db() as db:
        db.execute('UPDATE companies SET profile_json=? WHERE id=?',
                   (json.dumps({'name':'公司甲 〔S1〕','business':'业务说明〔S2〕'}),cid))
        db.execute('UPDATE documents SET title=? WHERE id=?',('公司档案 · 公司甲 〔S1〕',did))
    original=store.one('SELECT body,digest FROM documents WHERE id=?',(did,))
    chunks=store.rows('SELECT * FROM chunks WHERE document_id=?',(did,))
    assert apply(store)=={'company_profiles_cleaned':1,'company_document_titles_cleaned':1}
    assert apply(store)=={'company_profiles_cleaned':0,'company_document_titles_cleaned':0}
    assert store.one('SELECT body,digest FROM documents WHERE id=?',(did,))==original
    assert store.rows('SELECT * FROM chunks WHERE document_id=?',(did,))==chunks
    assert store.one('SELECT count(*) n FROM presentation_changes')['n']==2
    assert client.get('/api/companies').json()['items'][0]['business']=='业务说明'


def test_admin_login_does_not_inherit_global_company_and_scope_is_session_local(client):
    from fastapi.testclient import TestClient
    cid=client.post('/api/companies',json={'name':'公司甲'}).json()['id']
    client.app.state.store.set_setting('active_company',cid)
    with TestClient(client.app,headers={'X-Requested-With':'risk-workbench'}) as other:
        assert other.post('/api/auth/login',json={'username':'admin','password':'test-password-2026'}).status_code==200
        assert other.get('/api/companies').json()['active_id'] is None
        assert other.get('/api/overview').json()['scope']['all_companies']
        assert client.get('/api/companies').json()['active_id']==cid
        assert other.post(f'/api/companies/{cid}/activate').status_code==200
        assert not other.get('/api/overview').json()['scope']['all_companies']
        assert other.delete('/api/companies/active').status_code==200
        assert other.get('/api/overview').json()['scope']['all_companies']


def test_document_metadata_and_summary_cleanup_keeps_original_source_and_evidence(client):
    from app.ingest import insert_document
    from app.presentation import clean_summary
    from scripts.clean_remaining_presentation import apply as clean_remaining
    store=client.app.state.store
    body='这是合同原文〔S1〕。合同法令〔2025〕42号应予保留，引用[1]。'
    did,_=insert_document(store,{'title':'L1 S2 合同资料','source':'机构〔S2〕','body':body},'knowledge')
    detail=client.get(f'/api/documents/{did}').json()
    assert detail['title']=='合同资料' and detail['source']=='机构'
    assert detail['body']==body and detail['chunks'][0]['text']==body
    with store.db() as db:
        db.execute("UPDATE documents SET zh_summary=? WHERE id=?",('合同资料〔S2〕原文分卷1/3，依据法令〔2025〕42号。',did))
    source=store.one('SELECT body,digest FROM documents WHERE id=?',(did,))
    chunks=store.rows('SELECT * FROM chunks WHERE document_id=?',(did,))
    assert clean_remaining(store)['fields_cleaned']==1
    assert clean_remaining(store)['fields_cleaned']==0
    assert store.one('SELECT body,digest FROM documents WHERE id=?',(did,))==source
    assert store.rows('SELECT * FROM chunks WHERE document_id=?',(did,))==chunks
    summary=client.get(f'/api/documents/{did}').json()['zh_summary']
    assert summary=='合同资料，依据法令〔2025〕42号。'
    assert clean_summary('资料含标号〔S1〕，不是法令〔2025〕42号。')=='资料含标号，不是法令〔2025〕42号。'


def test_word_exports_omit_preparation_labels_without_rewriting_saved_sources(client):
    import io
    from docx import Document
    from app.store import now
    store=client.app.state.store
    result={'blocks':[{'heading':'事项说明','text':'依据现有资料进行核查。','citations':[1]}],
      'sources':[{'number':1,'title':'L1 S2 合同资料〔S1〕','quote':'合同法令〔2025〕42号规定履约义务。〔S2〕',
                  'source':'发布机构〔S1〕','date':'2025-01-01','locator':'正文第1段','url':''}]}
    encoded=json.dumps(result,ensure_ascii=False)
    with store.db() as db:
        tid=db.execute('INSERT INTO drafting_templates(name,category,body,created_at) VALUES (?,?,?,?)',
                       ('事项说明','说明','事项说明模板正文，用于本地导出校验。',now())).lastrowid
        did=db.execute('INSERT INTO drafting_results(template_id,template_json,facts,result_json,created_at) VALUES (?,?,?,?,?)',
                       (tid,json.dumps({'name':'事项说明'}),'事实',encoded,now())).lastrowid
        rid=db.execute('INSERT INTO consultation_reports(company_id,question,result_json,created_at) VALUES (NULL,?,?,?)',
                       ('需要核查哪些义务？',encoded,now())).lastrowid
    for url in (f'/api/drafting/{did}/docx',f'/api/consultation/reports/{rid}/docx'):
        response=client.get(url)
        assert response.status_code==200
        text='\n'.join(p.text for p in Document(io.BytesIO(response.content)).paragraphs)
        assert '〔S1〕' not in text and '〔S2〕' not in text and 'L1 S2' not in text
        assert '〔2025〕42号' in text and '[1]' in text
    assert store.one('SELECT result_json FROM drafting_results WHERE id=?',(did,))['result_json']==encoded
    assert store.one('SELECT result_json FROM consultation_reports WHERE id=?',(rid,))['result_json']==encoded


def test_historic_website_run_display_omits_labels_but_keeps_saved_config(client):
    from app.store import now
    store=client.app.state.store
    config=json.dumps({'name':'L4 S3 发布机构〔S2〕','max_pages':1,'keywords':'合同 履约'},ensure_ascii=False)
    with store.db() as db:
        sid=db.execute("""INSERT INTO web_sources(name,url,keywords,max_pages,interval_hours,
            allow_external,auto_import,auto_analyze,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            ('发布机构','https://example.com/','合同 履约',1,0,1,'none',0,now())).lastrowid
        rid=db.execute('INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (?,?,?,?)',
                       (sid,config,'completed',now())).lastrowid
    result=client.get(f'/api/web/runs/{rid}')
    assert result.status_code==200
    assert result.json()['config']['name']=='发布机构'
    assert result.json()['config']['keywords']=='合同 履约'
    assert store.one('SELECT config_json FROM web_runs WHERE id=?',(rid,))['config_json']==config
