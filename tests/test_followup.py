import asyncio
import copy
import io
import json
from docx import Document
import pytest
from app.ingest import insert_document
from app.model import citation_units,validate_result
from app.meeting import current_rules
from app.presentation import clean_name,clean_reference
from app.store import DEFAULT_RULES
from scripts.apply_meeting_materials import apply
from test_tenant_authz import app,admin,companies


def test_internal_name_markers_removed_without_changing_quotes():
    assert clean_name('L5 S1 仲裁裁决 [原文分卷2/3]')=='仲裁裁决'
    assert clean_name('［网页存档 2026-06-29］网页原标题')=='网页原标题'
    assert clean_name('［PDF文本副本］行政处罚决定')=='行政处罚决定'
    assert clean_name('L2 收购申报处罚')=='收购申报处罚'
    assert clean_name('［PDF文本副本］L5 S1 仲裁裁决')=='仲裁裁决'
    assert clean_name('事件事实摘录')=='事项资料'
    item=clean_reference({'title':'L1 S2 原文','quote':'L1 S2 是原文中的字符，不能删除。'})
    assert item['title']=='原文' and item['quote'].startswith('L1 S2')


def test_canonical_citation_units_cannot_invent_evidence():
    from test_workbench import valid_result
    result=valid_result();rules=current_rules(DEFAULT_RULES)
    refs={'S1':{'text':'这是用于测试的风险证据原文。','kind':'source','document_id':1,'locator':'正文','title':'事实'}}
    result['events'][0]['evidence']=[{'reference':'S1','unit_id':'S1:1','reason':'直接事实'}]
    assert validate_result(copy.deepcopy(result),refs,rules)['events'][0]['evidence'][0]['quote']==refs['S1']['text']
    result['events'][0]['evidence'][0]['unit_id']='S1:999'
    with pytest.raises(ValueError,match='原文匹配'):validate_result(result,refs,rules)


def test_reviewed_material_plan_preserves_body_and_concurrent_edit(app):
    import hashlib
    store=app.state.store
    did,_=insert_document(store,{'title':'L5 S1 仲裁裁决 [原文分卷1/1]','body':'仲裁裁决原文。','source':'公开参考资料'},'knowledge')
    old=store.one('SELECT title,source,legal_meta,legal_revision,body FROM documents WHERE id=?',(did,))
    plan={'changes':[{'id':did,'body_sha256':hashlib.sha256(old['body'].encode()).hexdigest(),'before':{k:old[k] for k in ('title','source','legal_meta','legal_revision')},'title':'仲裁裁决','source':'公开参考资料','category':'arbitration','reason':'已核对原文'}]}
    assert apply(store,plan)['changed']==[did]
    row=store.one('SELECT * FROM documents WHERE id=?',(did,));assert row['body']==old['body'] and json.loads(row['legal_meta'])['category']=='arbitration'
    assert apply(store,plan)['skipped_concurrent_edits']==[did]
    assert store.one('SELECT count(*) n FROM material_changes')['n']==1


def test_draft_edit_cas_audit_word_and_company_denial(admin,companies,monkeypatch):
    a,_=companies
    tid=admin.post('/api/drafting/templates',json={'name':'事项说明','category':'事项说明','body':'事项说明\n根据已经提供的原文整理事项，未知信息保留待补充。'}).json()['id']
    async def fake(settings,payload,system):
        unit=next(u for u in payload['quote_units'] if u['ref']=='F1')
        return {'status':'answered','blocks':[{'heading':'事项事实','text':'设备尚未交付。','citations':[{'ref':'F1','unit_id':unit['unit_id']}]}]},{}
    monkeypatch.setattr('app.drafting.model.call_model',fake)
    draft=admin.post('/api/drafting',json={'template_id':tid,'facts':'买方已经支付设备货款，但设备尚未交付。'}).json()
    path=f"/api/drafting/results/{draft['id']}"
    assert a.get(path).status_code==403 and a.put(path,json={}).status_code==403
    body={'revision':0,'blocks':[{'heading':'核实事项','text':'设备尚未交付，具体时间待补充。','citations':[1]}],'reason':'核实后补充说明'}
    assert admin.put(path,json=body).status_code==200
    assert admin.put(path,json=body).status_code==409
    current=admin.get(path).json();assert current['revision']==1 and current['manually_edited']
    assert len(admin.get('/api/drafting/results').json()['items'])==1
    word=admin.get(f"/api/drafting/{draft['id']}/docx")
    assert '设备尚未交付，具体时间待补充。' in '\n'.join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
    assert admin.app.state.store.one('SELECT actor,reason FROM drafting_changes')['actor']=='admin'
    body['revision']=1;body['blocks'][0]['citations']=[999]
    assert admin.put(path,json=body).status_code==400


def test_manual_event_basis_exact_source_and_scope(admin,companies):
    from test_meeting import data
    a,b=companies;store=admin.app.state.store
    eid=admin.post('/api/events',json=data(a.company_id)).json()['id']
    doc,_=insert_document(store,{'title':'合同原文','body':'双方确认设备尚未交付，付款已经完成。'},'knowledge')
    payload={'revision':0,'document_id':doc,'quote':'双方确认设备尚未交付，付款已经完成。','reason':'支持合同履行事实'}
    endpoint=f'/api/events/{eid}/evidence'
    assert a.post(endpoint,json=payload).status_code==403
    assert admin.post(endpoint,json={**payload,'quote':'不存在的原文句段。'}).status_code==400
    private,_=insert_document(store,{'title':'其他企业合同','body':payload['quote']},'knowledge',company_id=b.company_id)
    assert admin.post(endpoint,json={**payload,'document_id':private}).status_code==400
    assert admin.post(endpoint,json=payload).status_code==200
    event=admin.get(f'/api/events/{eid}').json()
    assert event['revision']==1 and event['evidence'][0]['manual']
    assert admin.post(endpoint,json={**payload,'revision':1}).status_code==400
