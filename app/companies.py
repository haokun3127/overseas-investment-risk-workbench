"""Editable company profiles and synchronized knowledge documents."""
import hashlib
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .store import now
from .ingest import chunks_for

LABELS = {'name':'公司名称','industry':'所属行业','business':'主营业务与产品','location':'印尼投资地区','stage':'投资阶段','investment':'投资规模','entity':'当地实体与股权结构','workforce':'员工与用工情况','supply_chain':'供应链与进出口','licenses':'许可与合规情况','concerns':'重点关注风险','notes':'补充说明'}
class Profile(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    industry: str = Field(default='',max_length=200)
    business: str = Field(default='',max_length=3000)
    location: str = Field(default='',max_length=500)
    stage: str = Field(default='',max_length=200)
    investment: str = Field(default='',max_length=500)
    entity: str = Field(default='',max_length=2000)
    workforce: str = Field(default='',max_length=2000)
    supply_chain: str = Field(default='',max_length=3000)
    licenses: str = Field(default='',max_length=3000)
    concerns: str = Field(default='',max_length=3000)
    notes: str = Field(default='',max_length=3000)
    allow_external: bool = False

def initialize(store):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY,profile_json TEXT NOT NULL,document_id INTEGER UNIQUE REFERENCES documents(id),updated_at TEXT NOT NULL)")
        columns={r['name'] for r in db.execute('PRAGMA table_info(jobs)')}
        if 'company_json' not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN company_json TEXT NOT NULL DEFAULT '{}'")

def unpack(row):
    return {**json.loads(row['profile_json']),'id':row['id'],'document_id':row['document_id'],'updated_at':row['updated_at']}

def current(store):
    company_id=store.setting('active_company')
    row=store.one('SELECT * FROM companies WHERE id=?',(company_id,)) if company_id else None
    return unpack(row) if row else None

def snapshot(store):
    return json.dumps(current(store) or {},ensure_ascii=False)

def sync(db,company_id,profile,document_id):
    title='公司档案 · '+profile['name']
    body='国家：印度尼西亚\n'+'\n'.join(label+'：'+profile[key] for key,label in LABELS.items() if profile.get(key))
    digest=hashlib.sha256(('company:'+str(company_id)+':'+body).encode()).hexdigest()
    values=(title,body,int(profile['allow_external']),digest,now())
    if document_id:
        db.execute('UPDATE documents SET title=?,body=?,allow_external=?,digest=?,created_at=? WHERE id=?',values+(document_id,))
        db.execute('DELETE FROM chunks WHERE document_id=?',(document_id,))
    else:
        document_id=db.execute("INSERT INTO documents(title,body,allow_external,digest,created_at,kind,source) VALUES (?,?,?,?,?,'knowledge','公司信息档案')",values).lastrowid
    for locator,text in chunks_for(body):
        db.execute('INSERT INTO chunks(document_id,locator,text) VALUES (?,?,?)',(document_id,locator,text))
    db.execute('UPDATE companies SET document_id=? WHERE id=?',(document_id,company_id))
    return document_id

def router(store):
    api=APIRouter(prefix='/api/companies')
    @api.get('')
    def listing():
        return {'items':[unpack(r) for r in store.rows('SELECT * FROM companies ORDER BY id')], 'active_id':store.setting('active_company')}
    @api.post('')
    def create(data:Profile):
        return save(data)
    @api.put('/{company_id}')
    def edit(company_id:int,data:Profile):
        return save(data,company_id)
    def save(data,company_id=None):
        profile={k:v.strip() if isinstance(v,str) else v for k,v in data.model_dump().items()}
        if not profile['name']: raise ValueError('请填写公司名称。')
        with store.db() as db:
            if company_id is None:
                company_id=db.execute('INSERT INTO companies(profile_json,updated_at) VALUES (?,?)',(json.dumps(profile,ensure_ascii=False),now())).lastrowid
            else:
                row=db.execute('SELECT * FROM companies WHERE id=?',(company_id,)).fetchone()
                if not row: raise HTTPException(404,'公司档案不存在。')
                db.execute('UPDATE companies SET profile_json=?,updated_at=? WHERE id=?',(json.dumps(profile,ensure_ascii=False),now(),company_id))
                if row['document_id']: sync(db,company_id,profile,row['document_id'])
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('active_company',json.dumps(company_id)))
        store.audit('company_saved',f'id={company_id}')
        return {'id':company_id}
    @api.post('/{company_id}/activate')
    def activate(company_id:int):
        if not store.one('SELECT id FROM companies WHERE id=?',(company_id,)): raise HTTPException(404,'公司档案不存在。')
        store.set_setting('active_company',company_id)
        return {'ok':True}
    @api.post('/{company_id}/knowledge')
    def knowledge(company_id:int):
        with store.db() as db:
            row=db.execute('SELECT * FROM companies WHERE id=?',(company_id,)).fetchone()
            if not row: raise HTTPException(404,'公司档案不存在。')
            document_id=sync(db,company_id,json.loads(row['profile_json']),row['document_id'])
        store.audit('company_knowledge_synced',f'id={company_id}, document={document_id}')
        return {'id':document_id}
    return api
