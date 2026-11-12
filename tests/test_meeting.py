import copy
import io
import json
from docx import Document
import pytest
from app.ingest import insert_document
from app.meeting import current_rules, TARGET_LEVELS
from app.model import validate_result
from app.retrieval import retrieve
from app.store import DEFAULT_RULES
from app.store import Store
from test_tenant_authz import app, admin, companies

def data(cid, **extra):
    return {'company_id':cid,'revision':0,'title':'已核实合同风险','category':'其他','level':'lv2',
            'summary':'设备合同已被终止，企业生产受到影响。','impact':'生产受阻。','recommendation':'核实合同并协商。','reason':'已核对合同及业务记录',**extra}

def test_admin_crud_revision_audit_soft_delete_and_no_supersession(app,admin,companies):
    a,_=companies;store=app.state.store
    first=admin.post('/api/events',json=data(a.company_id)).json()['id']
    second=admin.post('/api/events',json=data(a.company_id)).json()['id']
    assert first!=second
    assert admin.get('/api/events').json()['total']==2
    original=copy.deepcopy(admin.get(f'/api/events/{first}').json()['result'])
    changed=data(a.company_id,level='lv1',reason='新增资料证明重大影响')
    assert admin.put(f'/api/events/{first}',json=changed).status_code==200
    assert admin.put(f'/api/events/{first}',json=changed).status_code==409
    detail=admin.get(f'/api/events/{first}').json()
    assert detail['level']=='lv1' and detail['revision']==1 and detail['result']==original
    assert len(detail['changes'])==2 and detail['changes'][0]['actor']=='admin'
    assert admin.request('DELETE',f'/api/events/{first}',json={'revision':0,'reason':'重复'}).status_code==409
    assert admin.request('DELETE',f'/api/events/{first}',json={'revision':1,'reason':'重复资料核实后撤销'}).status_code==200
    assert admin.get(f'/api/events/{first}').status_code==404
    assert admin.get('/api/overview').json()['total']==1
    assert store.one('SELECT deleted_at FROM events WHERE id=?',(first,))['deleted_at']
    assert store.one('SELECT COUNT(*) n FROM event_changes WHERE event_id=?',(first,))['n']==3

def test_green_is_non_risk_not_insufficient_and_company_cannot_adjust(app,admin,companies):
    a,b=companies
    eid=admin.post('/api/events',json=data(a.company_id)).json()['id']
    assert a.put(f'/api/events/{eid}',json=data(a.company_id,level='non_risk')).status_code==403
    assert b.get(f'/api/events/{eid}').status_code==404
    assert admin.put(f'/api/events/{eid}',json=data(a.company_id,level='non_risk',reason='原事项不构成风险，已核实')).status_code==200
    assert admin.get('/api/overview').json()['total']==0
    assert {'decision':'non_risk','count':1} in a.get('/api/overview').json()['decisions']
    assert admin.get('/api/documents').json()['items'][0]['decision']=='non_risk'
    assert admin.post('/api/events',json=data(a.company_id,level='non_risk')).status_code==400
    assert admin.post('/api/events',json=data(a.company_id,level='lv5')).status_code==400

def test_selected_company_really_filters_import_and_stats(admin,companies):
    a,b=companies
    for cid in (a.company_id,b.company_id):assert admin.post('/api/events',json=data(cid)).status_code==200
    assert admin.post(f'/api/companies/{a.company_id}/activate').status_code==200
    assert admin.get('/api/events').json()['total']==1
    assert admin.get('/api/overview').json()['scope']['company_id']==a.company_id
    uploaded=admin.post('/api/import',files={'file':('contract.txt','合同明确约定履行期限及设备交付地点。'.encode())}).json()['results'][0]['id']
    assert admin.app.state.store.one('SELECT company_id FROM documents WHERE id=?',(uploaded,))['company_id']==a.company_id
    assert admin.delete('/api/companies/active').status_code==200
    assert admin.get('/api/events').json()['total']==2

def test_new_rules_snapshots_are_three_levels_historical_rules_untouched(admin):
    stored=copy.deepcopy(admin.app.state.store.setting('rules'))
    current=admin.get('/api/settings').json()['rules']
    assert set(current['levels'])==set(TARGET_LEVELS)
    assert all('%' not in v for v in current['levels'].values())
    assert admin.app.state.store.setting('rules')==stored
    assert current_rules(current)==current
    current['levels']['lv2']='黄色风险：经业务确认的较大影响。'
    assert admin.put('/api/rules',json=current).status_code==200
    assert admin.get('/api/settings').json()['rules']['levels']['lv2']==current['levels']['lv2']

def test_knowledge_dedupe_preserves_origins_scope_and_versions(app):
    store=app.state.store
    law={'title':'法规原本','body':'合同成立后双方应当按约履行义务。','date':'2025-01-01','legal_metadata':{'category':'id_law','document_no':'A-2025','effective_from':'2025-01-01'}}
    original,_=insert_document(store,law,'knowledge')
    same,new=insert_document(store,{**law,'title':'另一标题','url':'https://law.test/same','body':'合同成立后双方应当按约履行义务。\n'},'knowledge')
    assert same==original and not new
    assert store.one('SELECT url FROM document_origins WHERE document_id=?',(original,))['url']=='https://law.test/same'
    revised,new=insert_document(store,{**law,'date':'2026-01-01','legal_metadata':{**law['legal_metadata'],'document_no':'A-2026','effective_from':'2026-01-01'}},'knowledge')
    assert new and revised!=original
    assert insert_document(store,{**law,'date':'2026-01-01','legal_metadata':{**law['legal_metadata'],'document_no':'A-2026','effective_from':'2026-01-01'}},'knowledge')==(revised,False)
    private,_=insert_document(store,law,'knowledge',company_id=123)
    assert private not in (original,revised)

def test_old_grades_migrate_once_with_audit_and_original_model_preserved(app,admin,companies):
    a,_=companies;store=app.state.store
    expected={'lv4':'lv3','lv5':'non_risk','red':'lv1','orange':'lv2','yellow':'lv3'}
    ids=[]
    for old,new in expected.items():
        eid=admin.post('/api/events',json=data(a.company_id,title='旧等级'+old)).json()['id']
        with store.db() as db:db.execute('UPDATE events SET level=? WHERE id=?',(old,eid))
        ids.append((eid,old,new))
    originals=store.rows('SELECT id,result_json,rules_json FROM analyses ORDER BY id')
    Store(store.directory)
    count=store.one('SELECT COUNT(*) n FROM event_changes')['n']
    for eid,old,new in ids:
        assert store.one('SELECT level,revision FROM events WHERE id=?',(eid,))=={'level':new,'revision':1}
        change=store.one("SELECT * FROM event_changes WHERE event_id=? AND action='standard_migration'",(eid,))
        assert json.loads(change['before_json'])['level']==old and json.loads(change['after_json'])['level']==new
    Store(store.directory)
    assert store.one('SELECT COUNT(*) n FROM event_changes')['n']==count
    assert store.rows('SELECT id,result_json,rules_json FROM analyses ORDER BY id')==originals

def test_retrieval_law_priority_no_irrelevant_elevation_and_fragment_duplicates(app):
    store=app.state.store
    news,_=insert_document(store,{'title':'合同履行新闻','body':'合同履行双方需要协商处理。'},'knowledge')
    verified={'category':'id_law','validity':'in_force','verified_on':'2026-11-11','verification_note':'合成测试核验记录','verification_urls':['https://law.test/original']}
    law,_=insert_document(store,{'title':'合同履行法规','body':'合同履行应当依照双方约定。','legal_metadata':verified},'knowledge')
    irrelevant,_=insert_document(store,{'title':'海洋气候','body':'海洋气候与季风环境说明。','legal_metadata':verified},'knowledge')
    hits=retrieve(store,'合同履行',limit=10)
    assert hits[0]['document_id']==law and news in {h['document_id'] for h in hits}
    assert irrelevant not in {h['document_id'] for h in hits}
    assert len({h['text'] for h in hits})==len(hits)

def test_countermeasure_basis_must_be_a_real_verified_law():
    from test_workbench import valid_result
    value=valid_result();rules=current_rules(DEFAULT_RULES)
    references={'S1':{'text':'这是用于测试的风险证据原文。','kind':'source','document_id':1,'locator':'正文','title':'事实'},
                'K2':{'text':'合同履行应当依照双方约定。','kind':'knowledge','document_id':2,'locator':'第一条','title':'法规','legal_metadata':{'category':'id_law','validity':'in_force'}}}
    value['events'][0]['actions']=[{'text':'核对约定并协商履行','conditions':'合同有效且适用本法','basis':[{'reference':'K2','quote':'合同履行应当依照双方约定。','reason':'履约义务'}]}]
    result=validate_result(copy.deepcopy(value),references,rules)
    assert result['events'][0]['actions'][0]['basis'][0]['document_id']==2
    references['K2']['legal_metadata']['validity']='unknown'
    withheld=validate_result(copy.deepcopy(value),references,rules)['events'][0]['actions'][0]
    assert withheld['basis']==[] and withheld['basis_withheld']==1
    references['K2']['legal_metadata']['category']='incident'
    withheld=validate_result(copy.deepcopy(value),references,rules)['events'][0]['actions'][0]
    assert withheld['basis']==[] and withheld['basis_withheld']==1
    value['events'][0]['actions'][0]['basis'][0]['quote']='原文中不存在的法条内容。'
    references['K2']['legal_metadata']={'category':'id_law','validity':'in_force'}
    assert validate_result(copy.deepcopy(value),references,rules)['events'][0]['actions'][0]['basis']==[]

def test_drafting_template_required_verified_generation_and_download(admin,companies,monkeypatch):
    a,_=companies
    assert admin.post('/api/drafting',json={'template_id':999,'facts':'当事双方已签订设备采购合同，设备尚未交付。'}).status_code==409
    body='合同履行函\n收件人：【待补充】\n我方已按合同支付货款，请按照约定履行设备交付义务。'
    tid=admin.post('/api/drafting/templates',json={'name':'合成函件模板','category':'合成测试分类','body':body}).json()['id']
    assert a.get('/api/drafting/templates').status_code==403
    async def fake(settings,payload,system):
        assert '不猜当事人' in system
        unit=next(u for u in payload['quote_units'] if u['ref']=='F1')
        return {'status':'answered','blocks':[{'heading':'履行事项','text':'设备尚未交付，请核对合同约定。','citations':[{'ref':'F1','unit_id':unit['unit_id']}]}]},{}
    monkeypatch.setattr('app.drafting.model.call_model',fake)
    response=admin.post('/api/drafting',json={'template_id':tid,'facts':'当事双方已签订设备采购合同，设备尚未交付。'})
    assert response.status_code==200,response.text
    result=response.json();assert result['status']=='answered' and result['blocks'][0]['heading']=='履行事项'
    word=admin.get(f"/api/drafting/{result['id']}/docx")
    assert word.status_code==200
    paragraphs=[p.text for p in Document(io.BytesIO(word.content)).paragraphs]
    assert '履行事项' in paragraphs and any('草稿' in p for p in paragraphs)
    assert a.get(f"/api/drafting/{result['id']}/docx").status_code==403
    assert admin.delete(f'/api/drafting/templates/{tid}').status_code==200
    assert admin.post('/api/drafting',json={'template_id':tid,'facts':'当事双方已签订设备采购合同，设备尚未交付。'}).status_code==409
    assert admin.get(f"/api/drafting/{result['id']}/docx").status_code==200

def test_review_invalidates_stale_edit_and_cannot_review_deleted(admin,companies):
    a,_=companies
    eid=admin.post('/api/events',json=data(a.company_id)).json()['id']
    assert admin.put(f'/api/events/{eid}/review',json={'status':'accepted','note':'已复核'}).status_code==200
    assert admin.put(f'/api/events/{eid}',json=data(a.company_id)).status_code==409
    assert admin.request('DELETE',f'/api/events/{eid}',json={'revision':1,'reason':'核实重复记录'}).status_code==200
    assert admin.put(f'/api/events/{eid}/review',json={'status':'pending','note':''}).status_code==404

