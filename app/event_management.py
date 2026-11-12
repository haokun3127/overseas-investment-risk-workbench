import json
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .access import require_admin
from .ingest import insert_document
from .meeting import TARGET_LEVELS, current_rules
from .store import now


class EventEdit(BaseModel):
    revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=240)
    category: str = Field(min_length=1, max_length=200)
    level: str
    summary: str = Field(min_length=1, max_length=10000)
    impact: str = Field(default='', max_length=10000)
    recommendation: str = Field(default='', max_length=10000)
    reason: str = Field(min_length=1, max_length=2000)


class NewEvent(EventEdit):
    company_id: int = Field(gt=0)


class EvidenceEdit(BaseModel):
    revision: int = Field(ge=0)
    document_id: int = Field(gt=0)
    quote: str = Field(min_length=6,max_length=8000)
    reason: str = Field(min_length=1,max_length=2000)

class RemoveEvent(BaseModel):
    revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)


def router(store):
    api = APIRouter()

    def reference_for(db,event,data,action=False):
        doc=db.execute('''SELECT d.*,COALESCE(d.company_id,
            (SELECT id FROM companies WHERE document_id=d.id)) resolved_company
            FROM documents d WHERE d.id=? AND d.quarantined_at IS NULL''',(data.document_id,)).fetchone()
        if not doc or (doc['resolved_company'] is not None and doc['resolved_company']!=event['company_id']):
            raise ValueError('所选原文不属于公共资料或本事件企业。')
        if data.quote not in doc['body'] or not data.reason.strip():
            raise ValueError('引用必须与原文连续匹配，并说明支持哪项判断。')
        meta=json.loads(doc['legal_meta'] or '{}')
        if action:
            if doc['kind']!='knowledge' or meta.get('category') not in ('id_law','cn_law','treaty','regional','judgment','arbitration','case'):
                raise ValueError('对策依据请选择已分类的法律或裁判案例，不能以新闻或企业档案代替法律。')
            if meta['category'] in ('id_law','cn_law','treaty','regional') and meta.get('validity') not in ('in_force','historical'):
                raise ValueError('该法律效力尚未核实，请先在知识库记录效力依据。')
        return {'document_id':doc['id'],'title':doc['title'],'source':doc['source'],'url':doc['url'],'date':doc['date'],
                'locator':'原文引用','quote':data.quote,'reason':data.reason,
                'kind':'knowledge' if doc['kind']=='knowledge' else 'source','legal_metadata':meta,'manual':True}

    def validate(data):
        if data.level not in {*TARGET_LEVELS, 'non_risk'}:
            raise ValueError('风险事件只使用红、黄、蓝三级；无风险请通过分析结果记录，不能新增为风险事件。')
        if data.category not in store.setting('rules')['categories'] and data.category != '其他':
            raise ValueError('请选择有效风险类型，无法匹配时选择其他。')
        if not data.reason.strip() or not data.title.strip() or not data.summary.strip():
            raise ValueError('标题、摘要和修改原因不能为空。')

    def change(db, eid, actor, action, before, after, reason):
        db.execute('INSERT INTO event_changes(event_id,actor,action,before_json,after_json,reason,created_at) VALUES (?,?,?,?,?,?,?)',
                   (eid, actor, action, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), reason, now()))

    @api.post('/api/events')
    def create(data: NewEvent, request: Request):
        require_admin(request)
        validate(data)
        if data.level=='non_risk':
            raise ValueError('无风险不新增为风险事件。已有事件可在人工复核时调整为绿色无风险。')
        if not store.one('SELECT id FROM companies WHERE id=?', (data.company_id,)):
            raise ValueError('所属企业不存在。')
        # An independent manual record must never supersede an existing model analysis.
        doc_id, _ = insert_document(store, {'title': data.title, 'body': data.summary, 'source': '人工记录'}, company_id=data.company_id, identity=uuid.uuid4().hex)
        with store.db() as db:
            if db.execute("SELECT 1 FROM jobs WHERE document_id=? AND status IN ('queued','running')", (doc_id,)).fetchone():
                raise HTTPException(409, '该资料正在分析，请完成后再新增人工事件。')
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM analyses WHERE document_id=?', (doc_id,)).fetchone()[0]
            aid = db.execute('''INSERT INTO analyses(document_id,version,decision,model,mode,rules_json,knowledge_json,result_json,created_at,duration_ms,usage_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (doc_id, version, 'risk', '人工记录', 'manual', json.dumps(current_rules(store.setting('rules')), ensure_ascii=False), '[]', '{"decision":"risk","manual":true}', now(), 0, '{}')).lastrowid
            values = data.model_dump(exclude={'revision','reason','company_id'})
            eid = db.execute('INSERT INTO events(analysis_id,title,category,level,summary,impact,recommendation,evidence_json) VALUES (?,?,?,?,?,?,?,?)',
                (aid, values['title'], values['category'], values['level'], values['summary'], values['impact'], values['recommendation'], '[]')).lastrowid
            change(db, eid, request.state.username, 'create', {}, values, data.reason)
        return {'id': eid}

    @api.put('/api/events/{event_id}')
    def update(event_id: int, data: EventEdit, request: Request):
        require_admin(request)
        validate(data)
        with store.db() as db:
            before = db.execute('SELECT * FROM events WHERE id=? AND deleted_at IS NULL', (event_id,)).fetchone()
            if not before:
                raise HTTPException(404, '事件不存在。')
            values = data.model_dump(exclude={'revision','reason'})
            changed = db.execute('''UPDATE events SET title=?,category=?,level=?,summary=?,impact=?,recommendation=?,revision=revision+1,
                review_status='accepted',review_note=?,reviewed_at=? WHERE id=? AND revision=?''',
                (values['title'],values['category'],values['level'],values['summary'],values['impact'],values['recommendation'],data.reason,now(),event_id,data.revision)).rowcount
            if not changed:
                raise HTTPException(409, '事件已更新，请重新打开后再修改。')
            if values['recommendation'] != before['recommendation']:
                db.execute("UPDATE events SET actions_json='[]' WHERE id=?", (event_id,))
            change(db, event_id, request.state.username, 'update', dict(before), values, data.reason)
        return {'ok': True, 'revision': data.revision + 1}

    @api.post('/api/events/{event_id}/evidence')
    def add_evidence(event_id:int,data:EvidenceEdit,request:Request):
        require_admin(request)
        with store.db() as db:
            event=db.execute('''SELECT e.*,d.company_id FROM events e JOIN analyses a ON a.id=e.analysis_id
                JOIN documents d ON d.id=a.document_id WHERE e.id=? AND e.deleted_at IS NULL''',(event_id,)).fetchone()
            if not event:raise HTTPException(404,'事件不存在。')
            reference=reference_for(db,event,data)
            refs=json.loads(event['evidence_json'])
            if any(r.get('document_id')==data.document_id and r.get('quote')==data.quote for r in refs):
                raise ValueError('这段原文已经关联，无需重复添加。')
            if len(refs)>=30:raise ValueError('依据已达30条，请先核实已有依据。')
            refs.append(reference)
            if db.execute('UPDATE events SET evidence_json=?,revision=revision+1 WHERE id=? AND revision=?',
                          (json.dumps(refs,ensure_ascii=False),event_id,data.revision)).rowcount!=1:
                raise HTTPException(409,'事件已更新，请重新打开后补充依据。')
            change(db,event_id,request.state.username,'evidence',{'evidence_json':event['evidence_json']},{'evidence':refs},data.reason)
        return {'ok':True,'revision':data.revision+1}

    @api.post('/api/events/{event_id}/actions/{action_index}/basis')
    def add_action_basis(event_id:int,action_index:int,data:EvidenceEdit,request:Request):
        require_admin(request)
        with store.db() as db:
            event=db.execute('''SELECT e.*,d.company_id FROM events e JOIN analyses a ON a.id=e.analysis_id
                JOIN documents d ON d.id=a.document_id WHERE e.id=? AND e.deleted_at IS NULL''',(event_id,)).fetchone()
            if not event:raise HTTPException(404,'事件不存在。')
            if event['revision']!=data.revision:raise HTTPException(409,'事件已更新，请重新打开后补充对策依据。')
            reference=reference_for(db,event,data,action=True)
            actions=json.loads(event['actions_json'])
            if not actions and event['recommendation'].strip():
                actions=[{'text':event['recommendation'],'conditions':'请结合本事件事实及下方引用的适用范围核实后采用。','basis':[]}]
            if not 0<=action_index<len(actions):raise ValueError('所选对策不存在，请重新打开事件。')
            basis=actions[action_index].setdefault('basis',[])
            if any(r.get('document_id')==data.document_id and r.get('quote')==data.quote for r in basis):
                raise ValueError('该对策已关联这段原文，无需重复添加。')
            if len(basis)>=6:raise ValueError('单项对策依据已达6条，请先核实已有依据。')
            basis.append(reference)
            if db.execute('UPDATE events SET actions_json=?,revision=revision+1 WHERE id=? AND revision=?',
                          (json.dumps(actions,ensure_ascii=False),event_id,data.revision)).rowcount!=1:
                raise HTTPException(409,'事件已更新，请重新打开后补充对策依据。')
            change(db,event_id,request.state.username,'action_basis',
                   {'actions_json':event['actions_json']},{'action_index':action_index,'actions':actions},data.reason)
        return {'ok':True,'revision':data.revision+1}

    @api.delete('/api/events/{event_id}')
    def remove(event_id: int, data: RemoveEvent, request: Request):
        require_admin(request)
        if not data.reason.strip():
            raise ValueError('请填写删除原因。')
        with store.db() as db:
            before = db.execute('SELECT * FROM events WHERE id=? AND deleted_at IS NULL', (event_id,)).fetchone()
            if not before:
                raise HTTPException(404, '事件不存在。')
            if db.execute('UPDATE events SET deleted_at=?,revision=revision+1 WHERE id=? AND revision=?', (now(), event_id, data.revision)).rowcount != 1:
                raise HTTPException(409, '事件已更新，请刷新后再删除。')
            change(db, event_id, request.state.username, 'delete', dict(before), {}, data.reason)
        return {'ok': True}

    return api
