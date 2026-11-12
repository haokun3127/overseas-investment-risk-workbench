import copy
import io
import json
from docx import Document
import pytest
from app.drafting import verify_draft, template_fields, template_headings
from test_tenant_authz import app, admin, companies


def sources():
    return {'F1':{'text':'甲公司已支付100万元人民币，设备仍未交付。','title':'事项事实','document_id':0},
            'T1':{'text':'请根据已提供的合同约定，逐项说明履行请求与待补字段。','title':'函件模板','document_id':0},
            'K1':{'text':'当事人应当按照约定全面履行自己的义务。','title':'法律资料','document_id':3,
                  'legal_metadata':{'category':'id_law','validity':'in_force'}}}


def raw_blocks(n=7):
    return {'status':'answered','blocks':[{'heading':f'第{i+1}条 事项','kind':'fact',
        'text':'甲公司已支付100万元人民币，设备仍未交付。',
        'citations':[{'ref':'F1','unit_id':'F1:1'}]} for i in range(n)],
        'missing_fields':['送达地址'],'warnings':['需核对合同适用地区。']}


def test_full_length_document_and_template_structure():
    raw=raw_blocks();raw['blocks'][0]['text']='设备仍未交付。'*110
    result=verify_draft(raw,sources(),[b['heading'] for b in raw['blocks']])
    assert len(result['blocks'])==7 and len(result['blocks'][0]['text'])>700
    assert result['sources'][0]['role']=='facts'
    with pytest.raises(ValueError,match='章节缺失'):verify_draft(raw,sources(),['第一条 不存在'])
    raw['blocks'].reverse()
    with pytest.raises(ValueError,match='顺序变化'):verify_draft(raw,sources(),['第1条 事项','第2条 事项'])


@pytest.mark.parametrize('mutation',[
    lambda b:b.update(citations=[{'ref':'F1','unit_id':'F1:999'}]),
    lambda b:b.update(text='甲公司已支付200万元人民币。'),
    lambda b:b.update(citations=[{'ref':'T1','unit_id':'T1:1'}]),
    lambda b:b.update(kind='legal'),
])
def test_rejects_unverified_evidence_and_money(mutation):
    raw=raw_blocks(1);mutation(raw['blocks'][0])
    with pytest.raises(ValueError):verify_draft(raw,sources())


def test_legal_basis_metadata_required():
    raw=raw_blocks(1);raw['blocks'][0].update(kind='legal',text='当事人应按约定履行义务。',
        citations=[{'ref':'K1','unit_id':'K1:1'}])
    assert verify_draft(raw,sources())['blocks']
    for validity in ('unknown','repealed'):
        evidence=sources();evidence['K1']['legal_metadata']['validity']=validity
        with pytest.raises(ValueError,match='有效'):verify_draft(raw,evidence)


def test_template_field_extraction():
    assert template_fields('甲方：{{甲方}}\n{{甲方}}；【待补充：日期】')==['甲方','日期']
    assert template_headings('合同\n一、事项\n这是正文\n第二条 履行\n')==['一、事项','第二条 履行']


def test_upload_generate_revision_export_and_refine(admin,companies,monkeypatch):
    company,_=companies
    assert company.post('/api/drafting/materials/upload',files={'file':('x.txt',b'hello')}).status_code==403
    text='甲公司已支付100万元人民币，设备仍未交付。'
    uploaded=admin.post('/api/drafting/materials/upload',files={'file':('facts.txt',text.encode())})
    assert uploaded.status_code==200 and uploaded.json()['text']==text
    tid=admin.post('/api/drafting/templates',json={'name':'履行请求函','category':'函件',
        'body':'履行请求函\n收件人：{{收件人}}\n一、事实\n根据材料说明事实。\n二、请求\n按约定履行。'}).json()['id']
    templates=admin.get('/api/drafting/templates').json()['items']
    assert templates[0]['fields']==['收件人']
    async def fake(settings,payload,system):
        assert not settings.model_store and '1至60章' in system
        if payload['previous_draft']:assert '简化措辞'==payload['instruction']
        unit=next(u for u in payload['quote_units'] if u['ref']=='F1')
        return {'status':'answered','blocks':[{'heading':h,'kind':'fact','text':text,
             'citations':[{'ref':'F1','unit_id':unit['unit_id']}]} for h in payload['required_headings']],
             'missing_fields':[]},{}
    monkeypatch.setattr('app.drafting.model.call_model',fake)
    request={'template_id':tid,'facts':text,'field_values':{'收件人':'乙公司'}}
    r=admin.post('/api/drafting',json=request);assert r.status_code==200,r.text
    first=r.json();assert first['checks']['sections']==2
    assert first['context']['field_values']['收件人']=='乙公司'
    path=f"/api/drafting/results/{first['id']}"
    blocks=first['blocks'];blocks[0]['text']='送达地址：【待补充：地址】'
    edited=admin.put(path,json={'revision':0,'blocks':blocks,'reason':'补充送达地址'})
    assert edited.status_code==200 and edited.json()['checks']['missing_fields']==['地址']
    assert admin.put(path,json={'revision':0,'blocks':blocks,'reason':'过时修改'}).status_code==409
    word=Document(io.BytesIO(admin.get(f"/api/drafting/{first['id']}/docx").content))
    assert round(word.sections[0].page_width.cm)==21
    assert any('送达地址' in p.text for p in word.paragraphs)
    assert '宋体' in word.styles['Normal'].element.xml
    second=admin.post('/api/drafting',json={**request,'previous_draft_id':first['id'],'instruction':'简化措辞'})
    assert second.status_code==200 and second.json()['id']!=first['id']
    assert admin.get(path).json()['revision']==1
    assert len(admin.get('/api/drafting/results').json()['items'])==2
    assert company.get(path).status_code==403
    assert admin.post('/api/drafting',json={**request,'field_values':{'非法字段':'值'}}).status_code==400


def test_bad_generation_does_not_save(admin,monkeypatch):
    tid=admin.post('/api/drafting/templates',json={'name':'说明函','category':'函件','body':'说明函\n根据已经提供的事项事实起草说明，缺项保留。'}).json()['id']
    async def invalid(*args,**kwargs):return raw_blocks(1)|{'blocks':[]},{}
    monkeypatch.setattr('app.drafting.model.call_model',invalid)
    r=admin.post('/api/drafting',json={'template_id':tid,'facts':'已收到材料，但交付日期尚未确认。'})
    assert r.status_code==502
    assert not admin.get('/api/drafting/results').json()['items']
