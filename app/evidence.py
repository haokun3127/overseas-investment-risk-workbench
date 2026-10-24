"""Supplemental evidence is scoped to one source document, never public knowledge."""
import json
import secrets
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import companies
from .access import company_of, session_company
from .ingest import insert_document, parse_file
from .store import now
from . import checklist

MAX_SUPPLEMENT_TEXT = 24000
MAX_SUPPLEMENTS = 10


class Supplement(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=MAX_SUPPLEMENT_TEXT)
    source: str = Field(default='', max_length=300)
    url: str = Field(default='', max_length=2000)
    allow_external: bool = False


def reasons(result):
    parts = result.get('parts') or [result]
    return list(dict.fromkeys(p['reason'] for p in parts if p.get('decision') == 'insufficient' and p.get('reason'))) or ['请查看原分析说明，并核实原文和适用业务背景。']


def router(store, settings):
    api = APIRouter(prefix='/api/evidence')

    def case(analysis_id, request, db=None, editable=False):
        sql = '''SELECT a.id,a.document_id,a.version,a.decision,a.result_json,a.rules_json,a.created_at,
            d.title,d.company_id,d.allow_external,d.quarantined_at,d.demo,
            (SELECT id FROM analyses WHERE document_id=d.id ORDER BY version DESC,id DESC LIMIT 1) latest_analysis_id
            FROM analyses a JOIN documents d ON d.id=a.document_id WHERE a.id=? AND d.kind='event'
            AND EXISTS(SELECT 1 FROM analyses x WHERE x.document_id=d.id AND x.decision='insufficient')'''
        row = db.execute(sql,(analysis_id,)).fetchone() if db else store.one(sql,(analysis_id,))
        row = dict(row) if row else None
        if not row or (company_of(request) is not None and row['company_id'] != company_of(request)) or row['quarantined_at'] or row['demo']:
            raise HTTPException(404,'补证记录不存在。')
        if editable and (row['id'] != row['latest_analysis_id'] or row['decision'] != 'insufficient'):
            raise HTTPException(409,'分析版本已更新，请刷新后查看最新结论。')
        return row

    def ensure_idle(db, document_id):
        if db.execute("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(document_id,)).fetchone():
            raise HTTPException(409,'资料正在分析，请等待任务结束后再调整补充材料。')

    def attach(analysis_id, request, record, allow_external, content=None, filename=''):
        owner = case(analysis_id,request,editable=True)
        stored_name = secrets.token_hex(16)+Path(filename).suffix.lower() if content is not None else ''
        path = store.directory/'uploads'/stored_name if stored_name else None
        created = False
        if path:
            path.write_bytes(content)
        try:
            record = {**record,'title':str(record.get('title') or '').strip(),'body':str(record.get('body') or '').strip()}
            doc_id,created = insert_document(store,record,'supplement',allow_external,
                file_path=stored_name,filename=filename,company_id=owner['company_id'])
            with store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                current = case(analysis_id,request,db,editable=True)
                ensure_idle(db,current['document_id'])
                existing = db.execute('SELECT 1 FROM document_evidence WHERE document_id=? AND supplement_id=?',(current['document_id'],doc_id)).fetchone()
                if not existing:
                    totals = db.execute('SELECT count(*) n,coalesce(sum(length(d.body)),0) chars FROM document_evidence e JOIN documents d ON d.id=e.supplement_id WHERE e.document_id=?',(current['document_id'],)).fetchone()
                    if totals['n'] >= MAX_SUPPLEMENTS or totals['chars']+len(record['body'].strip()) > MAX_SUPPLEMENT_TEXT:
                        raise HTTPException(409,'每条资料最多关联10份补充材料，合计不超过24000字符，请精简后保存。')
                    db.execute('INSERT INTO document_evidence VALUES (?,?,?,?)',(current['document_id'],doc_id,analysis_id,now()))
            store.audit('evidence_added',f'document={owner["document_id"]}, analysis={analysis_id}, supplement={doc_id}',company_id=owner['company_id'])
            return {'id':doc_id,'created':created}
        except Exception:
            if created:
                store.delete_documents([doc_id])
            raise
        finally:
            if path and not created:
                path.unlink(missing_ok=True)

    @api.get('')
    def queue(request:Request,status:str='pending',q:str='',page:int=1):
        if status not in ('pending','resolved'):
            raise ValueError('补证状态无效。')
        scope = "d.kind='event' AND d.demo=0 AND d.quarantined_at IS NULL AND EXISTS(SELECT 1 FROM analyses x WHERE x.document_id=d.id AND x.decision='insufficient')"
        args = []
        if company_of(request) is not None:
            scope += ' AND d.company_id=?'
            args.append(company_of(request))
        base = ' FROM documents d JOIN analyses a ON a.id=(SELECT id FROM analyses WHERE document_id=d.id ORDER BY version DESC,id DESC LIMIT 1) WHERE '+scope
        counts = store.one("SELECT coalesce(sum(a.decision='insufficient'),0) pending,coalesce(sum(a.decision!='insufficient'),0) resolved"+base,args)
        where = " AND a.decision"+('=' if status=='pending' else '!=')+"'insufficient' AND (d.title LIKE ? OR d.source LIKE ?)"
        values = args+['%'+q+'%']*2
        total = store.one('SELECT count(*) n'+base+where,values)['n']
        page = max(page,1)
        rows = store.rows('''SELECT a.id,a.version,a.decision,a.created_at,a.result_json,d.id document_id,d.title,d.source,d.company_id,
            (SELECT name FROM (SELECT id,json_extract(profile_json,'$.name') name FROM companies) c WHERE c.id=d.company_id) company_name,
            (SELECT count(*) FROM document_evidence e WHERE e.document_id=d.id) supplements,
            (SELECT status FROM jobs WHERE document_id=d.id ORDER BY id DESC LIMIT 1) job_status'''+base+where+' ORDER BY a.id DESC LIMIT 20 OFFSET ?',values+[(page-1)*20])
        for row in rows:
            row['reasons'] = reasons(json.loads(row.pop('result_json'))) if row['decision']=='insufficient' else []
            row['checklist']=store.one("SELECT count(*) total,coalesce(sum(status='open'),0) remaining FROM evidence_checklist WHERE analysis_id=?",(row['id'],))
        return {'items':rows,'total':total,'page':page,'page_size':20,'counts':counts}

    @api.get('/{analysis_id}')
    def detail(analysis_id:int,request:Request):
        row = case(analysis_id,request)
        row['result'] = json.loads(row.pop('result_json'))
        row['rules'] = json.loads(row.pop('rules_json'))
        row['reasons'] = reasons(row['result']) if row['decision']=='insufficient' else []
        row['supplements'] = store.rows('''SELECT d.id,d.title,d.source,d.url,d.allow_external,d.quarantined_at,d.filename,length(d.body) characters,e.created_at
            FROM document_evidence e JOIN documents d ON d.id=e.supplement_id WHERE e.document_id=? ORDER BY e.created_at,d.id''',(row['document_id'],))
        row['history'] = store.rows('SELECT id,version,decision,created_at FROM analyses WHERE document_id=? ORDER BY version DESC,id DESC',(row['document_id'],))
        row['active_job'] = store.one("SELECT id,status FROM jobs WHERE document_id=? AND status IN ('queued','running')",(row['document_id'],))
        row['editable'] = row['id']==row['latest_analysis_id'] and row['decision']=='insufficient' and not row['active_job']
        row['characters'] = sum(d['characters'] for d in row['supplements'])
        row['checklist']=checklist.items(store,analysis_id)
        row['checklist_suggestions']=checklist.suggestions(row['result']) if row['decision']=='insufficient' and not row['checklist'] else []
        return row

    @api.post('/{analysis_id}/supplements')
    def add(analysis_id:int,data:Supplement,request:Request):
        return attach(analysis_id,request,data.model_dump(),data.allow_external)

    @api.post('/{analysis_id}/upload')
    async def upload(analysis_id:int,request:Request,file:UploadFile=File(...),allow_external:bool=Form(False)):
        case(analysis_id,request,editable=True)
        content = await file.read(settings.max_upload+1)
        if len(content)>settings.max_upload:
            raise HTTPException(413,'文件超过10MB限制。')
        filename = Path((file.filename or 'upload').replace('\\','/')).name
        try:
            records = await run_in_threadpool(parse_file,filename,content)
        except ValueError:
            raise
        except Exception:
            raise ValueError('无法解析附件，请检查格式或先对扫描件进行 OCR。')
        if len(records)!=1:
            raise ValueError('每次请上传一份补充材料；多行表格请拆分后上传。')
        record = records[0]['record']
        if len(record.get('body',''))>MAX_SUPPLEMENT_TEXT:
            raise ValueError('补充材料超过24000字符，请按相关章节拆分。')
        return await run_in_threadpool(attach,analysis_id,request,record,allow_external,content,filename)

    @api.delete('/{analysis_id}/supplements/{doc_id}')
    def unlink(analysis_id:int,doc_id:int,request:Request):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = case(analysis_id,request,db,editable=True)
            ensure_idle(db,row['document_id'])
            if not db.execute('DELETE FROM document_evidence WHERE document_id=? AND supplement_id=?',(row['document_id'],doc_id)).rowcount:
                raise HTTPException(404,'补充材料不存在。')
            db.execute('DELETE FROM checklist_materials WHERE supplement_id=? AND item_id IN (SELECT id FROM evidence_checklist WHERE analysis_id=?)',(doc_id,analysis_id))
            db.execute("UPDATE evidence_checklist SET status='open',revision=revision+1,updated_at=?,updated_by=? WHERE analysis_id=? AND status='provided' AND NOT EXISTS(SELECT 1 FROM checklist_materials m WHERE m.item_id=evidence_checklist.id)",(now(),request.state.username,analysis_id))
        store.audit('evidence_unlinked',f'document={row["document_id"]}, supplement={doc_id}',company_id=row['company_id'])
        return {'ok':True}

    @api.post('/{analysis_id}/reanalyze')
    def reanalyze(analysis_id:int,request:Request):
        if not settings.configured:
            raise HTTPException(409,'请先配置模型服务。')
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = case(analysis_id,request,db,editable=True)
            active = db.execute("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(row['document_id'],)).fetchone()
            if active:
                return {'id':active['id'],'existing':True}
            if not row['allow_external']:
                raise HTTPException(409,'原资料尚未授权外部分析，请先在原文页调整授权。')
            docs = db.execute('SELECT d.* FROM document_evidence e JOIN documents d ON d.id=e.supplement_id WHERE e.document_id=? ORDER BY d.id',(row['document_id'],)).fetchall()
            if not docs:
                raise HTTPException(409,'请先保存至少一份补充材料。')
            try:
                chunks = store.supplement_snapshot(db,row['document_id'])
            except ValueError as error:
                raise HTTPException(409,str(error))
            snap = companies.snapshot(store,row['company_id'] or session_company(request))
            job_id = store.enqueue_job(db,row['document_id'],snap,chunks,analysis_id)
        store.audit('evidence_reanalysis',f'document={row["document_id"]}, analysis={analysis_id}, job={job_id}',company_id=row['company_id'])
        return {'id':job_id,'existing':False}

    checklist.routes(api,store,case,ensure_idle)
    return api
