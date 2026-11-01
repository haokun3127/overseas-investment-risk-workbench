"""Editable company profiles, per-company user accounts, and synchronized knowledge documents."""
import hashlib
import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .store import now
from .ingest import chunks_for

from .profile_fields import LABELS
class Profile(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    industry: str = Field(default="",max_length=200)
    business: str = Field(default="",max_length=3000)
    location: str = Field(default="",max_length=500)
    stage: str = Field(default="",max_length=200)
    investment: str = Field(default="",max_length=500)
    entity: str = Field(default="",max_length=2000)
    workforce: str = Field(default="",max_length=2000)
    supply_chain: str = Field(default="",max_length=3000)
    licenses: str = Field(default="",max_length=3000)
    concerns: str = Field(default="",max_length=3000)
    notes: str = Field(default="",max_length=3000)
    allow_external: bool = False

def initialize(store):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY,profile_json TEXT NOT NULL,document_id INTEGER UNIQUE REFERENCES documents(id),updated_at TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS company_users(
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            created_at TEXT NOT NULL
        )""")
        columns={r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
        if "company_json" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN company_json TEXT NOT NULL DEFAULT \x27{}\x27")
        # Ensure existing company knowledge documents have their company_id populated
        for row in db.execute("SELECT id, document_id FROM companies WHERE document_id IS NOT NULL").fetchall():
            db.execute("UPDATE documents SET company_id=? WHERE id=? AND company_id IS NULL", (row["id"], row["document_id"]))

def unpack(row):
    return {**json.loads(row["profile_json"]),"id":row["id"],"document_id":row["document_id"],"updated_at":row["updated_at"]}

def current(store, company_id=None):
    row = store.one("SELECT * FROM companies WHERE id=?", (company_id,)) if company_id else None
    return unpack(row) if row else None

def snapshot(store, company_id=None):
    return json.dumps(current(store, company_id) or {}, ensure_ascii=False)

def sync(db,company_id,profile,document_id):
    title="公司档案 · "+profile["name"]
    body="国家：印度尼西亚\n"+"\n".join(label+"："+profile[key] for key,label in LABELS.items() if profile.get(key))
    digest=hashlib.sha256(("company:"+str(company_id)+":"+body).encode()).hexdigest()
    values=(title,body,int(profile["allow_external"]),digest,now(),company_id)
    if document_id:
        db.execute("UPDATE documents SET title=?,body=?,allow_external=?,digest=?,created_at=?,company_id=? WHERE id=?",values+(document_id,))
        db.execute("DELETE FROM chunks WHERE document_id=?",(document_id,))
    else:
        document_id=db.execute("INSERT INTO documents(title,body,allow_external,digest,created_at,company_id,kind,source) VALUES (?,?,?,?,?,?,\x27knowledge\x27,\x27公司信息档案\x27)",values).lastrowid
    for locator,text in chunks_for(body):
        db.execute("INSERT INTO chunks(document_id,locator,text) VALUES (?,?,?)",(document_id,locator,text))
    db.execute("UPDATE companies SET document_id=? WHERE id=?",(document_id,company_id))
    return document_id

def router(store):
    api=APIRouter(prefix="/api/companies")
    @api.get("")
    def listing(request:Request):
        scoped_id=getattr(request.state,"company_id",None)
        if scoped_id is not None:
            rows=store.rows("SELECT * FROM companies WHERE id=?",(scoped_id,))
            return {"items":[unpack(r) for r in rows],"active_id":scoped_id,"scoped":True}
        active_id = getattr(request.state, "active_company", None)
        return {"items":[unpack(r) for r in store.rows("SELECT * FROM companies ORDER BY id")],"active_id":active_id,"scoped":False}
    @api.post("")
    def create(data:Profile,request:Request):
        if getattr(request.state,"company_id",None) is not None:
            raise HTTPException(403,"当前企业账号仅能维护本公司档案，不能新增其他公司。")
        return save(data,request=request)
    @api.put("/{company_id}")
    def edit(company_id:int,data:Profile,request:Request):
        scoped_id=getattr(request.state,"company_id",None)
        if scoped_id is not None and scoped_id!=company_id:
            raise HTTPException(403,"无权修改其他公司的档案。")
        return save(data,company_id,request=request)
    def save(data,company_id=None,request=None):
        scoped_id=getattr(request.state,"company_id",None) if request else None
        profile={k:v.strip() if isinstance(v,str) else v for k,v in data.model_dump().items()}
        if not profile["name"]: raise ValueError("请填写公司名称。")
        created = company_id is None
        with store.db() as db:
            if company_id is None:
                company_id=db.execute("INSERT INTO companies(profile_json,updated_at) VALUES (?,?)",(json.dumps(profile,ensure_ascii=False),now())).lastrowid
            else:
                row=db.execute("SELECT * FROM companies WHERE id=?",(company_id,)).fetchone()
                if not row: raise HTTPException(404,"公司档案不存在。")
                db.execute("UPDATE companies SET profile_json=?,updated_at=? WHERE id=?",(json.dumps(profile,ensure_ascii=False),now(),company_id))
                if row["document_id"]: sync(db,company_id,profile,row["document_id"])
            if created and scoped_id is None and request:
                db.execute(
                    "UPDATE sessions SET active_company=? WHERE token=?",
                    (company_id, request.state.session_key),
                )
        store.audit("company_saved",f"id={company_id}",company_id=company_id)
        return {"id":company_id}
    @api.post("/{company_id}/activate")
    def activate(company_id:int,request:Request):
        scoped_id=getattr(request.state,"company_id",None)
        if scoped_id is not None:
            if scoped_id!=company_id: raise HTTPException(403,"当前企业账号不能切换到其他公司。")
            return {"ok":True}
        if not store.one("SELECT id FROM companies WHERE id=?",(company_id,)): raise HTTPException(404,"公司档案不存在。")
        with store.db() as db:
            db.execute(
                "UPDATE sessions SET active_company=? WHERE token=?",
                (company_id, request.state.session_key),
            )
        return {"ok":True}
    @api.post("/{company_id}/knowledge")
    def knowledge(company_id:int,request:Request):
        scoped_id=getattr(request.state,"company_id",None)
        if scoped_id is not None and scoped_id!=company_id:
            raise HTTPException(403,"无权操作其他公司的知识库档案。")
        with store.db() as db:
            row=db.execute("SELECT * FROM companies WHERE id=?",(company_id,)).fetchone()
            if not row: raise HTTPException(404,"公司档案不存在。")
            document_id=sync(db,company_id,json.loads(row["profile_json"]),row["document_id"])
        store.audit("company_knowledge_synced",f"id={company_id}, document={document_id}",company_id=company_id)
        return {"id":document_id}
    return api
