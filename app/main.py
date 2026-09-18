import hashlib
import csv
import io
import shutil
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from .config import Settings, ROOT
from .store import Store, now, DEFAULT_RULES
from .ingest import parse_file, insert_document
from .jobs import Worker
from .retrieval import retrieve
from .demo import seed
from . import model

class Credentials(BaseModel):
    password: str = Field(min_length=10,max_length=128)

class Record(BaseModel):
    title: str
    body: str
    date: str = ''
    source: str = ''
    url: str = ''
    kind: str = 'event'
    allow_external: bool = False

class JobRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1,max_length=100)

class Review(BaseModel):
    status: str
    note: str = Field(default='',max_length=2000)

class DocumentPolicy(BaseModel):
    allow_external: bool

def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),300000).hex()

def create_app(settings=None, run_worker=True):
    settings=settings or Settings()
    store=Store(settings.data_dir)
    worker=Worker(store,settings)
    login_attempts={}
    @asynccontextmanager
    async def lifespan(app):
        if run_worker: worker.start()
        yield
        await worker.stop()
    app=FastAPI(title='海外投资风险工作台',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=store; app.state.worker=worker; app.state.settings=settings

    @app.middleware('http')
    async def guard(request,call_next):
        path=request.url.path
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail':'请求来源不被允许。'},status_code=403)
            # Browsers cannot forge custom headers cross-origin without a preflight.
            if path.startswith('/api/') and request.headers.get('x-requested-with')!='risk-workbench':
                return JSONResponse({'detail':'缺少请求校验标记。'},status_code=403)
            try:
                if int(request.headers.get('content-length','0')) > settings.max_upload+65536:
                    return JSONResponse({'detail':'上传内容超过10MB限制。'},status_code=413)
            except ValueError:
                return JSONResponse({'detail':'无效请求长度。'},status_code=400)
        public={'/api/auth/status','/api/auth/setup','/api/auth/login','/api/health'}
        if path.startswith('/api/') and path not in public:
            token=request.cookies.get('risk_session','')
            key=hashlib.sha256(token.encode()).hexdigest()
            if not token or not store.one('SELECT token FROM sessions WHERE token=? AND expires>?',(key,time.time())):
                return JSONResponse({'detail':'请先登录。'},status_code=401)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if path.startswith('/api/'): response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(ValueError)
    async def value_error(request,error):
        return JSONResponse({'detail':str(error)},status_code=400)

    @app.get('/api/health')
    def health(): return {'status':'ok'}

    @app.get('/api/auth/status')
    def auth_status(request:Request):
        token=request.cookies.get('risk_session','')
        logged=bool(token and store.one('SELECT token FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())))
        return {'initialized':bool(store.setting('admin')),'authenticated':logged}

    def set_session():
        token=secrets.token_urlsafe(32)
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+8*3600))
        response=JSONResponse({'ok':True})
        response.set_cookie('risk_session',token,httponly=True,secure=settings.secure_cookie,samesite='strict',max_age=8*3600)
        return response

    @app.post('/api/auth/setup')
    def setup(data:Credentials,request:Request):
        if request.client.host not in ('127.0.0.1','::1','testclient'):
            raise HTTPException(403,'首次管理员设置请在服务器本机完成。')
        salt=secrets.token_hex(16)
        with store.db() as db:
            try:
                db.execute('INSERT INTO settings VALUES (?,?)',('admin',json.dumps({'salt':salt,'hash':password_hash(data.password,salt)})))
            except sqlite3.IntegrityError:
                raise HTTPException(409,'管理员已经初始化，请登录。')
        return set_session()

    @app.post('/api/auth/login')
    def login(data:Credentials,request:Request):
        key=request.client.host
        tries=[t for t in login_attempts.get(key,[]) if t>time.time()-300]
        if len(tries)>=10:
            raise HTTPException(429,'登录尝试过多，请5分钟后重试。')
        admin=store.setting('admin')
        if not admin or not hmac.compare_digest(password_hash(data.password,admin['salt']),admin['hash']):
            login_attempts[key]=tries+[time.time()]
            raise HTTPException(401,'密码不正确。')
        login_attempts.pop(key,None)
        return set_session()

    @app.post('/api/auth/logout')
    def logout(request:Request):
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('risk_session','').encode()).hexdigest(),))
        response=JSONResponse({'ok':True}); response.delete_cookie('risk_session'); return response

    @app.get('/api/settings')
    def config():
        return {'configured':settings.configured,'mode':settings.model_mode,'model':settings.model_name,
                'base_url':settings.model_base_url,'rules':store.setting('rules'),
                'retrieval':'本地 BM25 文本检索（中文双字词）','prompt_version':'risk-evidence-v1'}

    @app.put('/api/rules')
    async def rules(request:Request):
        value=await request.json()
        if not isinstance(value,dict) or set(value)!= {'version','confirmed','categories','levels','notes'}:
            raise ValueError('规则字段须包含 version、confirmed、categories、levels、notes。')
        cats=value['categories']
        if not isinstance(cats,list) or not 1<=len(cats)<=30 or any(not isinstance(c,str) or not c.strip() or len(c)>80 for c in cats) or len(set(cats))!=len(cats):
            raise ValueError('分类须为1至30个不重复的名称。')
        if not isinstance(value['levels'],dict) or set(value['levels'])!={'red','orange','yellow'} or any(not isinstance(v,str) or not v.strip() or len(v)>2000 for v in value['levels'].values()):
            raise ValueError('请提供 red、orange、yellow 三个等级的判断标准。')
        if type(value['confirmed']) is not bool or not isinstance(value['version'],str) or not 1<=len(value['version'])<=60 or not isinstance(value['notes'],str) or len(value['notes'])>5000:
            raise ValueError('规则版本、确认状态或说明格式不正确。')
        store.set_setting('rules',value); store.audit('rules_updated',value['version'])
        return {'ok':True}

    @app.post('/api/model/check')
    async def model_check():
        if not settings.configured: raise HTTPException(409,'尚未配置模型服务，请填写 .env 并重启。')
        started=time.monotonic()
        payload={'scope':{'country':'印度尼西亚','industry':'制造业'},'rules':DEFAULT_RULES,
                 'document':{'title':'连接检查（合成测试）'},'references':[],
                 'instruction':'本次仅检查连接，没有业务资料，请返回 insufficient、说明及空 events 数组。'}
        result,_=await model.call_model(settings,payload)
        model.validate_result(result,{},DEFAULT_RULES)
        store.audit('model_checked','connection and JSON protocol verified')
        return {'ok':True,'duration_ms':int((time.monotonic()-started)*1000),'checked_at':now(),
                'message':'已验证连接及基础 JSON 协议；业务识别质量仍需真实样本评估。'}

    @app.post('/api/documents')
    def manual(data:Record):
        if data.kind not in ('event','knowledge'): raise ValueError('资料用途无效。')
        doc_id,created=insert_document(store,data.model_dump(),data.kind,data.allow_external)
        store.audit('document_imported',f'id={doc_id}, created={created}')
        return {'id':doc_id,'created':created}

    @app.post('/api/import')
    async def upload(file:UploadFile=File(...),kind:str=Form('event'),allow_external:bool=Form(False)):
        if kind not in ('event','knowledge'): raise ValueError('资料用途无效。')
        content=await file.read(settings.max_upload+1)
        if len(content)>settings.max_upload: raise HTTPException(413,'文件超过10MB限制。')
        filename=Path((file.filename or 'upload').replace('\\','/')).name
        try:
            records=await run_in_threadpool(parse_file,filename,content)
        except ValueError: raise
        except Exception: raise ValueError('无法解析文件，请检查文件是否损坏、加密或与扩展名不符。')
        stored_name=secrets.token_hex(16)+Path(filename).suffix.lower()
        results=[]; created_count=0
        # Save original first so any committed record always has its source file.
        target=store.directory/'uploads'/stored_name
        target.write_bytes(content)
        for item in records:
            try:
                doc_id,created=insert_document(store,item['record'],kind,allow_external,file_path=stored_name,filename=filename)
                created_count+=int(created)
                results.append({'row':item['row'],'id':doc_id,'status':'created' if created else 'duplicate'})
            except ValueError as error:
                results.append({'row':item['row'],'status':'failed','error':str(error)})
        if not created_count: target.unlink(missing_ok=True)
        store.audit('file_imported',f'created={created_count}, rows={len(results)}')
        return {'created':created_count,'results':results}

    @app.get('/api/template')
    def template():
        return Response('\ufeff标题,时间,来源,正文,原始链接\r\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="import-template.csv"'})

    @app.get('/api/documents')
    def documents(kind:str='event',q:str='',page:int=1,status:str='',policy:str=''):
        page=max(1,page)
        if kind not in ('event','knowledge'): raise ValueError('资料用途无效。')
        args=[kind,'%'+q+'%','%'+q+'%']
        where='d.kind=? AND (d.title LIKE ? OR d.source LIKE ?)'
        if policy in ('local','external'):
            where+=' AND d.allow_external=?'; args.append(int(policy=='external'))
        if status=='unanalysed':
            where+=' AND NOT EXISTS(SELECT 1 FROM analyses a WHERE a.document_id=d.id)'
        elif status in ('queued','running','failed','completed'):
            where+=' AND (SELECT status FROM jobs j WHERE j.document_id=d.id ORDER BY j.id DESC LIMIT 1)=?'; args.append(status)
        count=store.one('SELECT COUNT(*) n FROM documents d WHERE '+where,args)['n']
        rows=store.rows('''SELECT d.id,d.title,d.date,d.source,d.kind,d.allow_external,d.demo,d.created_at,length(d.body) characters,
            (SELECT status FROM jobs WHERE document_id=d.id ORDER BY id DESC LIMIT 1) job_status,
            (SELECT decision FROM analyses WHERE document_id=d.id ORDER BY version DESC LIMIT 1) decision
            FROM documents d WHERE '''+where+' ORDER BY d.id DESC LIMIT 30 OFFSET ?',args+[(page-1)*30])
        return {'items':rows,'total':count,'page':page,'page_size':30}

    @app.get('/api/documents/{doc_id}')
    def document(doc_id:int):
        doc=store.one('SELECT * FROM documents WHERE id=?',(doc_id,))
        if not doc: raise HTTPException(404,'资料不存在。')
        doc.pop('file_path'); doc.pop('digest')
        doc['chunks']=store.rows('SELECT id,locator,text FROM chunks WHERE document_id=? ORDER BY id',(doc_id,))
        doc['analyses']=store.rows('SELECT id,version,decision,model,mode,created_at,result_json FROM analyses WHERE document_id=? ORDER BY version DESC',(doc_id,))
        for row in doc['analyses']:
            row['result']=json.loads(row.pop('result_json'))
            row['events']=store.rows('SELECT id,title FROM events WHERE analysis_id=?',(row['id'],))
        return doc

    @app.patch('/api/documents/{doc_id}/policy')
    def document_policy(doc_id:int,data:DocumentPolicy):
        with store.db() as db:
            if db.execute("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(doc_id,)).fetchone():
                raise HTTPException(409,'资料有待处理任务，请等待任务结束后修改授权范围。')
            if db.execute('UPDATE documents SET allow_external=? WHERE id=? AND demo=0',(int(data.allow_external),doc_id)).rowcount==0:
                raise HTTPException(404,'资料不存在或属于不可修改的演示资料。')
        store.audit('document_policy_changed',f'document={doc_id}, allow_external={data.allow_external}')
        return {'ok':True}

    @app.get('/api/documents/{doc_id}/file')
    def original(doc_id:int):
        doc=store.one('SELECT file_path,filename FROM documents WHERE id=?',(doc_id,))
        if not doc or not doc['file_path']: raise HTTPException(404,'该资料没有原始附件。')
        return FileResponse(store.directory/'uploads'/doc['file_path'],filename=doc['filename'],media_type='application/octet-stream')

    @app.get('/api/knowledge/search')
    def knowledge_search(q:str=''):
        if not q.strip(): return {'items':[]}
        return {'items':retrieve(store,q,limit=8)}

    @app.post('/api/jobs')
    def enqueue(data:JobRequest):
        if not settings.configured: raise HTTPException(409,'尚未配置模型服务，请按模型设置页说明填写 .env 并重启。')
        if not store.setting('rules')['confirmed']: raise HTTPException(409,'请先确认甲方风险分类分级规则。')
        ids=list(dict.fromkeys(data.document_ids))
        with store.db() as db:
            for doc_id in ids:
                doc=db.execute('SELECT * FROM documents WHERE id=?',(doc_id,)).fetchone()
                if not doc or doc['kind']!='event': raise ValueError(f'资料 {doc_id} 不是待分析资料。')
                if doc['demo']: raise ValueError('内置演示资料不进入真实分析，请导入新的测试资料。')
                if settings.model_mode=='external' and not doc['allow_external']: raise ValueError(f'资料 {doc_id} 未获准发送外部模型，请在原文页核实并修改授权范围。')
            result=[]
            for doc_id in ids:
                active=db.execute("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(doc_id,)).fetchone()
                if active: result.append({'id':active['id'],'existing':True}); continue
                job_id=db.execute("INSERT INTO jobs(document_id,status,created_at) VALUES (?,'queued',?)",(doc_id,now())).lastrowid
                result.append({'id':job_id,'existing':False})
        return {'items':result}

    @app.get('/api/jobs')
    def jobs(q:str='',status:str='',page:int=1):
        conditions=['(d.title LIKE ? OR CAST(j.id AS TEXT)=?)'];args=['%'+q+'%',q]
        if status:
            if status not in ('queued','running','completed','failed','cancelled'): raise ValueError('任务状态无效。')
            conditions.append('j.status=?');args.append(status)
        base=' FROM jobs j JOIN documents d ON d.id=j.document_id WHERE '+' AND '.join(conditions)
        total=store.one('SELECT COUNT(*) n'+base,args)['n'];page=max(1,page)
        return {'items':store.rows('SELECT j.*,d.title'+base+' ORDER BY j.id DESC LIMIT 100 OFFSET ?',args+[(page-1)*100]),'total':total,'page':page,'page_size':100,
                'active':store.one("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')")['n']}

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id:int):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row: raise HTTPException(404,'任务不存在。')
            if row['status']!='queued': raise HTTPException(409,'仅能取消尚未开始的排队任务，请刷新任务状态。')
            if not db.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=? AND status='queued'",(now(),job_id)).rowcount:
                raise HTTPException(409,'任务已开始，请刷新任务状态。')
        store.audit('job_cancelled',f'job={job_id}')
        return {'ok':True}

    @app.post('/api/jobs/preflight')
    def preflight(data:JobRequest):
        items=[]
        for doc_id in dict.fromkeys(data.document_ids):
            doc=store.one('SELECT id,title,kind,demo,allow_external FROM documents WHERE id=?',(doc_id,))
            reasons=[]
            if not doc: reasons.append('资料不存在')
            else:
                if doc['kind']!='event': reasons.append('参考资料不能直接启动风险分析')
                if doc['demo']: reasons.append('虚构演示资料不能进入真实分析')
                if settings.model_mode=='external' and not doc['allow_external']: reasons.append('尚未授权外部分析')
            active=store.one("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(doc_id,))
            items.append({'id':doc_id,'title':doc['title'] if doc else f'资料 #{doc_id}','issues':reasons,'existing_job':active['id'] if active else None})
        blockers=[]
        if not settings.configured: blockers.append('尚未配置模型服务')
        if not store.setting('rules')['confirmed']: blockers.append('风险分类分级规则尚未确认')
        return {'items':items,'blockers':blockers,'ready':not blockers and all(not i['issues'] for i in items),'mode':settings.model_mode}

    def events_query(demo='all',q='',level='',category='',review='',date_from='',date_to=''):
        from datetime import date
        for value in (date_from,date_to):
            if value:
                try: date.fromisoformat(value)
                except ValueError: raise ValueError('筛选日期须为 YYYY-MM-DD。')
        if date_from and date_to and date_from>date_to: raise ValueError('开始日期不能晚于结束日期。')
        if demo not in ('all','real','demo'): raise ValueError('数据范围无效。')
        if level and level not in ('red','orange','yellow'): raise ValueError('风险等级无效。')
        if review and review not in ('pending','accepted','needs_change'): raise ValueError('复核状态无效。')
        conditions=['a.id=(SELECT a2.id FROM analyses a2 WHERE a2.document_id=a.document_id ORDER BY version DESC LIMIT 1)']
        args=[]
        for value,sql in [(q,'(e.title LIKE ? OR e.summary LIKE ?)'),(level,'e.level=?'),(category,'e.category=?'),(review,'e.review_status=?'),(date_from,'d.date>=?'),(date_to,'d.date<=?')]:
            if value:
                conditions.append(sql)
                args.extend(['%'+value+'%']*2 if sql.startswith('(') else [value])
        if demo in ('real','demo'): conditions.append('d.demo=?'); args.append(int(demo=='demo'))
        base=' FROM events e JOIN analyses a ON a.id=e.analysis_id JOIN documents d ON d.id=a.document_id WHERE '+' AND '.join(conditions)
        return base,args

    @app.get('/api/events')
    def events(q:str='',level:str='',category:str='',review:str='',demo:str='all',page:int=1,date_from:str='',date_to:str=''):
        base,args=events_query(demo,q,level,category,review,date_from,date_to)
        total=store.one('SELECT COUNT(*) n'+base,args)['n']
        rows=store.rows('SELECT e.id,e.title,e.category,e.level,e.summary,e.review_status,d.date,d.source,d.demo,d.id document_id,a.model,a.mode'+base+' ORDER BY d.date DESC,e.id DESC LIMIT 20 OFFSET ?',args+[(max(page,1)-1)*20])
        return {'items':rows,'total':total,'page':max(page,1),'page_size':20}

    @app.get('/api/events/{event_id}')
    def event(event_id:int):
        row=store.one('''SELECT e.*,a.document_id,a.version,a.model,a.mode,a.created_at,a.duration_ms,a.rules_json,a.usage_json,a.result_json,
            d.date,d.source,d.url,d.demo FROM events e JOIN analyses a ON a.id=e.analysis_id JOIN documents d ON d.id=a.document_id WHERE e.id=?''',(event_id,))
        if not row: raise HTTPException(404,'事件不存在。')
        for name in ('evidence','rules','usage','result'): row[name]=json.loads(row.pop(name+'_json'))
        row['is_latest']=store.one('SELECT id FROM analyses WHERE document_id=? ORDER BY version DESC LIMIT 1',(row['document_id'],))['id']==row['analysis_id']
        row['review_history']=store.rows('SELECT status,note,created_at FROM review_history WHERE event_id=? ORDER BY id DESC',(event_id,))
        return row

    @app.put('/api/events/{event_id}/review')
    def review(event_id:int,data:Review):
        if data.status not in ('pending','accepted','needs_change'): raise ValueError('复核状态无效。')
        with store.db() as db:
            previous=db.execute('SELECT review_status,review_note,reviewed_at FROM events WHERE id=?',(event_id,)).fetchone()
            if previous and previous['reviewed_at'] and not db.execute('SELECT id FROM review_history WHERE event_id=?',(event_id,)).fetchone():
                db.execute('INSERT INTO review_history(event_id,status,note,created_at) VALUES (?,?,?,?)',(event_id,previous['review_status'],previous['review_note'],previous['reviewed_at']))
            changed=db.execute('UPDATE events SET review_status=?,review_note=?,reviewed_at=? WHERE id=?',(data.status,data.note,now(),event_id)).rowcount
            if not changed: raise HTTPException(404,'事件不存在。')
            db.execute('INSERT INTO review_history(event_id,status,note,created_at) VALUES (?,?,?,?)',(event_id,data.status,data.note,now()))
        store.audit('event_reviewed',f'event={event_id}, status={data.status}')
        return {'ok':True}

    @app.get('/api/overview')
    def overview(demo:str='all'):
        base,args=events_query(demo)
        return {'total':store.one('SELECT COUNT(*) n'+base,args)['n'],
            'levels':store.rows('SELECT e.level,COUNT(*) count'+base+' GROUP BY e.level',args),
            'categories':store.rows('SELECT e.category,COUNT(*) count'+base+' GROUP BY e.category ORDER BY count DESC',args),
            'pending':store.one('SELECT COUNT(*) n'+base+" AND e.review_status='pending'",args)['n'],
            'documents':store.one("SELECT COUNT(*) n FROM documents WHERE kind='event'"+(" AND demo=?" if demo in ('real','demo') else ''),([int(demo=='demo')] if demo in ('real','demo') else []))['n'],
            'active_jobs':store.one("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')")['n']}

    @app.post('/api/demo')
    def demo(): return {'added':seed(store)}

    @app.get('/api/export/events')
    def export_events(q:str='',level:str='',category:str='',review:str='',demo:str='all',date_from:str='',date_to:str=''):
        base,args=events_query(demo,q,level,category,review,date_from,date_to)
        rows=store.rows('SELECT e.*,d.date,d.source,d.demo,d.url,a.version'+base+' ORDER BY d.date DESC,e.id DESC',args)
        output=io.StringIO(newline=''); writer=csv.writer(output)
        writer.writerow(['事件编号','标题','风险等级','类型','摘要','潜在影响','建议','复核状态','复核意见','资料日期','来源','链接','分析版本','数据性质','引用依据'])
        def safe(value):
            value=str(value or '')
            return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
        for row in rows:
            writer.writerow([safe(v) for v in [row['id'],row['title'],{'red':'高风险','orange':'中风险','yellow':'一般关注'}.get(row['level'],row['level']),row['category'],row['summary'],row['impact'],row['recommendation'],{'pending':'待复核','accepted':'已认可','needs_change':'需修正'}[row['review_status']],row['review_note'],row['date'],row['source'],row['url'],row['version'],'虚构演示' if row['demo'] else '真实资料', '\n'.join(r.get('quote','') for r in json.loads(row['evidence_json']))]])
        store.audit('events_exported',f'count={len(rows)}, scope={demo}')
        return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="risk-events.csv"'})

    @app.get('/api/workspace')
    def workspace():
        docs=store.rows('SELECT kind,COUNT(*) count,SUM(allow_external) authorized,SUM(length(body)) characters FROM documents WHERE demo=0 GROUP BY kind')
        counts={r['kind']:r for r in docs}
        return {'documents':counts,'jobs':store.rows('SELECT status,COUNT(*) count FROM jobs GROUP BY status'),
            'unanalyzed':store.one("SELECT COUNT(*) n FROM documents d WHERE kind='event' AND demo=0 AND NOT EXISTS(SELECT 1 FROM analyses a WHERE a.document_id=d.id)")['n'],
            'recent_activity':store.rows('SELECT action,detail,created_at FROM audit ORDER BY id DESC LIMIT 15'),
            'checks':[{'label':'模型服务配置','ready':settings.configured,'href':'#settings'},
                      {'label':'业务规则确认','ready':bool(store.setting('rules')['confirmed']),'href':'#settings'},
                      {'label':'真实待分析资料','ready':bool(counts.get('event',{}).get('count')),'href':'#documents'},
                      {'label':'知识库参考资料（可选）','ready':bool(counts.get('knowledge',{}).get('count')),'href':'#knowledge'}]}

    @app.get('/api/report')
    def report(q:str='',level:str='',category:str='',review:str='',demo:str='all',date_from:str='',date_to:str=''):
        base,args=events_query(demo,q,level,category,review,date_from,date_to)
        total=store.one('SELECT COUNT(*) n'+base,args)['n']
        if total>500: raise HTTPException(400,'当前匹配超过500条，请缩小日期或分类范围后生成简报；完整台账可使用 CSV 导出。')
        items=store.rows('SELECT e.*,d.date,d.source,d.url,d.demo,a.version,a.model,a.mode,a.rules_json'+base+' ORDER BY CASE e.level WHEN \'red\' THEN 0 WHEN \'orange\' THEN 1 ELSE 2 END,d.date DESC,e.id DESC',args)
        for item in items:
            item['evidence']=json.loads(item.pop('evidence_json'))
            item['rule_version']=json.loads(item.pop('rules_json'))['version']
        return {'generated_at':now(),'total':total,'items':items,'scope':{'q':q,'level':level,'category':category,'review':review,'demo':demo,'date_from':date_from,'date_to':date_to}}

    @app.get('/api/runtime')
    def runtime():
        disk=shutil.disk_usage(store.directory)
        return {'checked_at':now(),'database_bytes':store.path.stat().st_size,'disk_free_bytes':disk.free,
                'documents':store.one('SELECT COUNT(*) n FROM documents')['n'],
                'chunks':store.one('SELECT COUNT(*) n FROM chunks')['n'],
                'analyses':store.one('SELECT COUNT(*) n FROM analyses')['n'],
                'queue':store.rows('SELECT status,COUNT(*) count FROM jobs GROUP BY status'),
                'worker_enabled':run_worker,'last_analysis':store.one('SELECT created_at,model,mode FROM analyses ORDER BY id DESC LIMIT 1')}

    app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
    @app.get('/')
    def home(): return FileResponse(ROOT/'web'/'index.html')
    return app
