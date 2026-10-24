"""Conservative local suggestions; the user controls the evidence checklist."""
import json
import re

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .store import now

TOPICS = (
    ('original','政策或通知完整原文',r'全文|完整正文|具体条款|条文|原文|通知摘要|元数据|检索界面'),
    ('applicability','适用对象与触发条件',r'适用|适用性|适用对象|触发条件|行业|所在地区'),
    ('business','公司业务事实与经营记录',r'公司|企业|经营|业务|用工|劳动合同|外籍|许可证|实际状况'),
    ('counterparty','交易对手与供应链关联信息',r'交易对手|股权|供应商|客户|供应链|结算|银行|关联'),
    ('date','发布时间与有效性依据',r'生效|失效|有效期|发布日期|发布时间|修订日期'),
)


def suggestions(result):
    parts=result.get('parts') or [result]
    texts=[p.get('reason','') for p in parts if p.get('decision')=='insufficient']
    sentences=[s.strip() for t in texts for s in re.split(r'(?<=[。！？；])',t) if s.strip()]
    missing=re.compile(r'缺少|缺乏|不足|未提供|未包含|未提及|未涉及|未说明|未显示|尚不完整|不涉及|无法|需补充|待核实|不能|未建立|未描述|没有')
    candidates=[s for s in sentences if missing.search(s)]
    items=[]
    for category,title,pattern in TOPICS:
        evidence=next((s for s in candidates if re.search(pattern,s)),None)
        if evidence:items.append({'category':category,'title':title,'excerpt':evidence[:700]})
    if not items:
        items=[{'category':'other','title':'补充可核验的原文或业务依据','excerpt':(texts[0] if texts else '请结合原分析说明确认需补材料。')[:700]}]
    return items


class ChecklistInput(BaseModel):
    title: str = Field(min_length=1,max_length=160)
    note: str = Field(default='',max_length=2000)


class ChecklistUpdate(ChecklistInput):
    revision: int = Field(ge=1)
    status: str = 'open'
    supplement_ids: list[int] = Field(default_factory=list,max_length=10)


def items(store,analysis_id):
    rows=store.rows('SELECT * FROM evidence_checklist WHERE analysis_id=? ORDER BY id',(analysis_id,))
    for row in rows:
        row['materials']=store.rows('SELECT d.id,d.title,d.allow_external,d.quarantined_at FROM checklist_materials m JOIN documents d ON d.id=m.supplement_id WHERE m.item_id=? ORDER BY d.id',(row['id'],))
        row['supplement_ids']=[d['id'] for d in row['materials']]
    return rows


def routes(api,store,case,ensure_idle):
    @api.post('/{analysis_id}/checklist/generate')
    def generate(analysis_id:int,request:Request):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=case(analysis_id,request,db,editable=True)
            ensure_idle(db,row['document_id'])
            if not db.execute('SELECT id FROM evidence_checklist WHERE analysis_id=?',(analysis_id,)).fetchone():
                for item in suggestions(json.loads(row['result_json'])):
                    db.execute('INSERT INTO evidence_checklist(analysis_id,title,category,excerpt,created_at,updated_at,updated_by) VALUES (?,?,?,?,?,?,?)',
                        (analysis_id,item['title'],item['category'],item['excerpt'],now(),now(),request.state.username))
        store.audit('checklist_generated',f'analysis={analysis_id}',company_id=row['company_id'])
        return {'items':items(store,analysis_id)}

    @api.post('/{analysis_id}/checklist')
    def add(analysis_id:int,data:ChecklistInput,request:Request):
        if not data.title.strip():raise ValueError('补证事项不能为空。')
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=case(analysis_id,request,db,editable=True)
            ensure_idle(db,row['document_id'])
            if db.execute('SELECT count(*) FROM evidence_checklist WHERE analysis_id=?',(analysis_id,)).fetchone()[0]>=30:
                raise ValueError('每个分析版本最多30个补证事项。')
            item_id=db.execute('INSERT INTO evidence_checklist(analysis_id,title,note,created_at,updated_at,updated_by) VALUES (?,?,?,?,?,?)',
                (analysis_id,data.title.strip(),data.note,now(),now(),request.state.username)).lastrowid
        store.audit('checklist_added',f'analysis={analysis_id}, item={item_id}',company_id=row['company_id'])
        return {'id':item_id}

    @api.patch('/{analysis_id}/checklist/{item_id}')
    def update(analysis_id:int,item_id:int,data:ChecklistUpdate,request:Request):
        ids=list(dict.fromkeys(data.supplement_ids))
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=case(analysis_id,request,db,editable=True)
            if data.status not in ('open','provided','not_needed'):raise ValueError('补证事项状态无效。')
            if not data.title.strip():raise ValueError('补证事项不能为空。')
            if data.status=='not_needed' and not data.note.strip():raise ValueError('不需补充时，请填写原因。')
            if data.status=='provided' and not ids:raise ValueError('请关联至少一份材料，再标为已提供。')
            ensure_idle(db,row['document_id'])
            item=db.execute('SELECT * FROM evidence_checklist WHERE id=? AND analysis_id=?',(item_id,analysis_id)).fetchone()
            if not item:raise HTTPException(404,'补证事项不存在。')
            if item['revision']!=data.revision:raise HTTPException(409,'该事项已被更新，请刷新后重新编辑。')
            for doc_id in ids:
                if not db.execute('SELECT 1 FROM document_evidence e JOIN documents d ON d.id=e.supplement_id WHERE e.document_id=? AND e.supplement_id=? AND d.quarantined_at IS NULL',(row['document_id'],doc_id)).fetchone():
                    raise ValueError('只能关联当前资料下未隔离的补充材料。')
            db.execute('UPDATE evidence_checklist SET title=?,status=?,note=?,revision=revision+1,updated_at=?,updated_by=? WHERE id=?',
                (data.title.strip(),data.status,data.note,now(),request.state.username,item_id))
            db.execute('DELETE FROM checklist_materials WHERE item_id=?',(item_id,))
            db.executemany('INSERT INTO checklist_materials VALUES (?,?)',[(item_id,doc_id) for doc_id in ids])
        store.audit('checklist_updated',f'analysis={analysis_id}, item={item_id}, status={data.status}',company_id=row['company_id'])
        return {'ok':True,'revision':data.revision+1}
