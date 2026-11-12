"""Audited metadata corrections; stored source text and citation offsets are immutable."""
import json
from datetime import date
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .access import require_admin
from .presentation import clean_name
from .store import now


class MetadataEdit(BaseModel):
    revision: int = Field(ge=0)
    title: str = Field(min_length=1,max_length=240)
    date: str = Field(default='',max_length=10)
    source: str = Field(default='',max_length=300)
    url: str = Field(default='',max_length=2000)
    reason: str = Field(min_length=1,max_length=2000)


def router(store):
    with store.db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS document_metadata_changes(
            id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES documents(id),
            actor TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,
            reason TEXT NOT NULL,created_at TEXT NOT NULL)''')
    api=APIRouter()

    def editable(db,doc_id):
        doc=db.execute("SELECT * FROM documents WHERE id=? AND kind='knowledge'",(doc_id,)).fetchone()
        if not doc:raise HTTPException(404,'知识资料不存在。')
        if doc['quarantined_at']:raise HTTPException(409,'资料已隔离，请先完成核实。')
        if db.execute('SELECT id FROM companies WHERE document_id=?',(doc_id,)).fetchone():
            raise HTTPException(409,'公司档案请在企业信息中维护，不能在这里单独修改。')
        return doc

    @api.put('/api/documents/{doc_id}/metadata')
    def update(doc_id:int,data:MetadataEdit,request:Request):
        require_admin(request)
        title=clean_name(data.title);source=clean_name(data.source);url=data.url.strip()
        if not title or not data.reason.strip():raise ValueError('请填写资料标题和修改原因。')
        if data.date:
            try:
                if date.fromisoformat(data.date).isoformat()!=data.date:raise ValueError()
            except ValueError:raise ValueError('资料日期须为 YYYY-MM-DD，未取得发布日期时请留空。') from None
        if url and (urlsplit(url).scheme not in ('http','https') or not urlsplit(url).hostname or urlsplit(url).username):
            raise ValueError('原文网址须为完整的 http 或 https 地址，不能包含登录凭证。')
        fields=('title','date','date_source','source','url')
        with store.db() as db:
            doc=editable(db,doc_id)
            before={key:doc[key] for key in fields}
            after={'title':title,'date':data.date,'source':source,'url':url,
                   'date_source':doc['date_source'] if data.date==doc['date'] else ('provided' if data.date else 'removed')}
            changed=db.execute('''UPDATE documents SET title=?,date=?,date_source=?,source=?,url=?,
                date_legacy=CASE WHEN ?='' AND date!='' THEN date ELSE date_legacy END,
                legal_revision=legal_revision+1 WHERE id=? AND legal_revision=?''',
                (title,data.date,after['date_source'],source,url,data.date,doc_id,data.revision)).rowcount
            if not changed:raise HTTPException(409,'资料已被其他操作修改，请重新打开后再保存。')
            db.execute('''INSERT INTO document_metadata_changes(document_id,actor,before_json,after_json,reason,created_at)
                VALUES (?,?,?,?,?,?)''',(doc_id,request.state.username,json.dumps(before,ensure_ascii=False),
                  json.dumps(after,ensure_ascii=False),data.reason.strip(),now()))
        return {'ok':True,'revision':data.revision+1}

    @api.get('/api/documents/{doc_id}/metadata-history')
    def history(doc_id:int,request:Request):
        require_admin(request)
        if not store.one("SELECT id FROM documents WHERE id=? AND kind='knowledge'",(doc_id,)):
            raise HTTPException(404,'知识资料不存在。')
        items=store.rows('SELECT * FROM document_metadata_changes WHERE document_id=? ORDER BY id DESC',(doc_id,))
        for item in items:
            item['before']=json.loads(item.pop('before_json'));item['after']=json.loads(item.pop('after_json'))
        return {'items':items}
    return api
