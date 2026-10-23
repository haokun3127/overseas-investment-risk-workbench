from contextlib import asynccontextmanager
import csv
import hashlib
import hmac
import io
import json
import secrets
import shutil
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .access import company_of, is_admin, require_admin, session_company
from .config import ROOT, Settings
from . import companies, model
from .demo import seed
from .enrich import Enricher
from .ingest import insert_document, parse_file
from .jobs import Worker
from .retrieval import annotate_hits, kind_label, retrieve
from .store import DEFAULT_RULES, Store, now
from .websearch import Collector, initialize as initialize_websearch, router as websearch_router
from . import websearch

class Credentials(BaseModel):
    password: str = Field(min_length=10,max_length=128)

class LoginCredentials(BaseModel):
    username: str = Field(default='',max_length=60)
    password: str = Field(min_length=8,max_length=128)

class CompanyRegister(BaseModel):
    username: str = Field(min_length=3,max_length=60)
    password: str = Field(min_length=8,max_length=128)
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
    allow_external: bool = True

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
    if settings.model_mode != 'external':
        raise ValueError('工作台仅支持外部模型 API，请配置 MODEL_MODE=external。')
    store=Store(settings.data_dir)
    companies.initialize(store)
    worker=Worker(store,settings)
    initialize_websearch(store)
    collector=Collector(store,settings)
    enricher=Enricher(store,settings)
    login_attempts={}
    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            worker.start()
            collector.start()
            enricher.start()
        yield
        await worker.stop()
        await collector.stop()
        await enricher.stop()
    app=FastAPI(title='海外投资风险工作台',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=store; app.state.worker=worker; app.state.settings=settings
    app.state.collector=collector
    app.state.enricher=enricher
    app.include_router(websearch_router(store,settings))
    app.include_router(companies.router(store))

    @app.middleware('http')
    async def guard(request,call_next):
        request.state.company_id=None
        request.state.username=''
        request.state.active_company=None
        request.state.session_key=''
        path=request.url.path
        root_path=request.scope.get('root_path','').rstrip('/')
        if root_path and path.startswith(root_path+'/'):
            path=path[len(root_path):]
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail':'请求来源不被允许。'},status_code=403)
            if path.startswith('/api/') and request.headers.get('x-requested-with')!='risk-workbench':
                return JSONResponse({'detail':'缺少请求校验标记。'},status_code=403)
            try:
                if int(request.headers.get('content-length','0')) > settings.max_upload+65536:
                    return JSONResponse({'detail':'上传内容超过10MB限制。'},status_code=413)
            except ValueError:
                return JSONResponse({'detail':'无效请求长度。'},status_code=400)
        public={'/api/auth/status','/api/auth/setup','/api/auth/login','/api/auth/register','/api/health'}
        if path.startswith('/api/') and path not in public:
            token=request.cookies.get(settings.session_cookie_name,'')
            key=hashlib.sha256(token.encode()).hexdigest()
            sess=store.one('SELECT token,company_id,username,active_company FROM sessions WHERE token=? AND expires>?',(key,time.time())) if token else None
            if not sess:
                return JSONResponse({'detail':'请先登录。'},status_code=401)
            if sess.get('company_id') is None and sess.get('username')!='admin':
                # Sessions from before roles were recorded carry no proof of admin identity.
                with store.db() as db: db.execute('DELETE FROM sessions WHERE token=?',(key,))
                return JSONResponse({'detail':'登录状态已失效，请重新登录。'},status_code=401)
            request.state.company_id=sess.get('company_id')
            request.state.username=sess.get('username') or ''
            request.state.session_key=key
            active_id = sess.get('active_company')
            if active_id and store.one('SELECT id FROM companies WHERE id=?',(active_id,)):
                request.state.active_company=active_id
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
        token=request.cookies.get(settings.session_cookie_name,'')
        sess=store.one('SELECT token,company_id,username,active_company FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())) if token else None
        if sess and sess.get('company_id') is None and sess.get('username')!='admin': sess=None
        logged=bool(sess)
        cid=sess.get('company_id') if sess else None
        cname=''
        if cid:
            crow=store.one('SELECT profile_json FROM companies WHERE id=?',(cid,))
            if crow: cname=json.loads(crow['profile_json']).get('name','')
        has_users=bool(store.one('SELECT 1 FROM company_users LIMIT 1'))
        return {
            'initialized':bool(store.setting('admin')) or has_users,
            'authenticated':logged,
            'company_id':cid,
            'company_name':cname,
            'active_company_id':sess.get('active_company') if sess else None,
            'username':(sess.get('username') or '') if sess else '',
            'role':'company' if cid else ('admin' if logged else ''),
        }

    def set_session(company_id=None,username='',extra=None):
        token=secrets.token_urlsafe(32)
        active_company=None
        if company_id is None:
            selected=store.setting('active_company')
            if selected and store.one('SELECT id FROM companies WHERE id=?',(selected,)):
                active_company=selected
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute(
                'INSERT INTO sessions(token,expires,company_id,username,active_company) VALUES (?,?,?,?,?)',
                (hashlib.sha256(token.encode()).hexdigest(),time.time()+8*3600,company_id,username,active_company),
            )
        body={'ok':True,'company_id':company_id,'username':username}
        if extra: body.update(extra)
        response=JSONResponse(body)
        response.set_cookie(settings.session_cookie_name,token,path=settings.cookie_path,httponly=True,secure=settings.secure_cookie,samesite='strict',max_age=8*3600)
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
        return set_session(username='admin')

    @app.post('/api/auth/register')
    def register(data:CompanyRegister,request:Request):
        uname=data.username.strip()
        if len(uname)<3 or uname.lower()=='admin':
            raise ValueError('登录账号须为3至60个字符，且不能使用保留名称 admin。')
        profile={k:getattr(data,k).strip() if isinstance(getattr(data,k),str) else getattr(data,k) for k in companies.LABELS}
        profile['allow_external']=bool(data.allow_external)
        if not profile['name']:
            raise ValueError('请填写公司名称。')
        salt=secrets.token_hex(16)
        phash=password_hash(data.password,salt)
        with store.db() as db:
            if db.execute('SELECT id FROM company_users WHERE lower(username)=lower(?)',(uname,)).fetchone():
                raise HTTPException(409,'该登录账号已被注册，请直接登录或更换账号。')
            company_id=db.execute('INSERT INTO companies(profile_json,updated_at) VALUES (?,?)',(json.dumps(profile,ensure_ascii=False),now())).lastrowid
            companies.sync(db,company_id,profile,None)
            db.execute('INSERT INTO company_users(username,salt,password_hash,company_id,created_at) VALUES (?,?,?,?,?)',(uname,salt,phash,company_id,now()))
        store.audit('company_registered',f'username={uname}, company={company_id}',company_id=company_id)
        return set_session(company_id=company_id,username=uname,extra={'company_name':profile['name']})

    @app.post('/api/auth/login')
    def login(data:LoginCredentials,request:Request):
        key=request.client.host
        tries=[t for t in login_attempts.get(key,[]) if t>time.time()-300]
        if len(tries)>=10:
            raise HTTPException(429,'登录尝试过多，请5分钟后重试。')
        uname=data.username.strip()
        if uname and uname.lower()!='admin':
            user=store.one('SELECT * FROM company_users WHERE lower(username)=lower(?)',(uname,))
            if not user or not hmac.compare_digest(password_hash(data.password,user['salt']),user['password_hash']):
                login_attempts[key]=tries+[time.time()]
                raise HTTPException(401,'账号或密码不正确。')
            login_attempts.pop(key,None)
            return set_session(company_id=user['company_id'],username=user['username'])
        admin=store.setting('admin')
        if not admin or not hmac.compare_digest(password_hash(data.password,admin['salt']),admin['hash']):
            # If user omitted username or typed password only, also check if it matches a single company user when username not supplied? No, keep strict.
            login_attempts[key]=tries+[time.time()]
            raise HTTPException(401,'密码不正确。')
        login_attempts.pop(key,None)
        return set_session(company_id=None,username='admin')

    @app.post('/api/auth/logout')
    def logout(request:Request):
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get(settings.session_cookie_name,'').encode()).hexdigest(),))
        response=JSONResponse({'ok':True}); response.delete_cookie(settings.session_cookie_name,path=settings.cookie_path); return response

    @app.get('/api/settings')
    def config(request:Request):
        cid=company_of(request)
        can_manage=is_admin(request)
        if cid is not None:
            latest=store.one('SELECT a.created_at,a.model FROM analyses a JOIN documents d ON d.id=a.document_id WHERE a.model=? AND a.mode=? AND d.company_id=? ORDER BY a.id DESC LIMIT 1',(settings.model_name,settings.model_mode,cid))
        else:
            latest=store.one('SELECT created_at,model FROM analyses WHERE model=? AND mode=? ORDER BY id DESC LIMIT 1',(settings.model_name,settings.model_mode))
        return {'configured':settings.configured,'mode':settings.model_mode,'model':settings.model_name,
                'last_success':latest,
                'base_url':settings.model_base_url if can_manage else None,
                'wire_api':settings.model_wire_api if can_manage else None,
                'reasoning_effort':settings.model_reasoning_effort if can_manage else None,
                'store_responses':settings.model_store if can_manage else None,
                'role':'admin' if can_manage else 'company','can_manage':can_manage,
                'rules':store.setting('rules'),
                'retrieval':'服务端 BM25 文本检索：原文加入库时生成的中文摘要和关键词 + 中印英跨语言法规术语扩展','prompt_version':'risk-evidence-v1'}

    @app.put('/api/rules')
    async def rules(request:Request):
        require_admin(request)
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
    async def model_check(request:Request):
        require_admin(request)
        if not settings.configured: raise HTTPException(409,'尚未配置模型服务，请填写 .env 并重启。')
        started=time.monotonic()
        payload={'scope':{'country':'印度尼西亚','industry':'连接测试'},'rules':DEFAULT_RULES,
                 'document':{'title':'连接检查（合成测试）'},'references':[],
                 'instruction':'本次仅检查连接，没有业务资料，请返回 insufficient、说明及空 events 数组。'}
        result,_=await model.call_model(settings,payload)
        model.validate_result(result,{},DEFAULT_RULES)
        store.audit('model_checked','connection and JSON protocol verified')
        return {'ok':True,'duration_ms':int((time.monotonic()-started)*1000),'checked_at':now(),
                'message':'已验证连接及基础 JSON 协议；业务识别质量仍需真实样本评估。'}

    @app.post('/api/documents')
    def manual(data:Record,request:Request):
        if data.kind not in ('event','knowledge'): raise ValueError('资料用途无效。')
        cid=getattr(request.state,'company_id',None)
        doc_id,created=insert_document(store,data.model_dump(),data.kind,data.allow_external,company_id=cid)
        store.audit('document_imported',f'id={doc_id}, created={created}, company={cid}',company_id=cid)
        return {'id':doc_id,'created':created}

    @app.post('/api/import')
    async def upload(request:Request,file:UploadFile=File(...),kind:str=Form('event'),allow_external:bool=Form(False)):
        if kind not in ('event','knowledge'): raise ValueError('资料用途无效。')
        cid=getattr(request.state,'company_id',None)
        content=await file.read(settings.max_upload+1)
        if len(content)>settings.max_upload: raise HTTPException(413,'文件超过10MB限制。')
        filename=Path((file.filename or 'upload').replace('\\','/')).name
        try:
            records=await run_in_threadpool(parse_file,filename,content)
        except ValueError: raise
        except Exception: raise ValueError('无法解析文件，请检查文件是否损坏、加密或与扩展名不符。')
        stored_name=secrets.token_hex(16)+Path(filename).suffix.lower()
        results=[]; created_count=0
        target=store.directory/'uploads'/stored_name
        target.write_bytes(content)
        for item in records:
            try:
                doc_id,created=insert_document(store,item['record'],kind,allow_external,file_path=stored_name,filename=filename,company_id=cid)
                created_count+=int(created)
                results.append({'row':item['row'],'id':doc_id,'status':'created' if created else 'duplicate'})
            except ValueError as error:
                results.append({'row':item['row'],'status':'failed','error':str(error)})
        if not created_count: target.unlink(missing_ok=True)
        store.audit('file_imported',f'created={created_count}, rows={len(results)}, company={cid}',company_id=cid)
        return {'created':created_count,'results':results}

    @app.get('/api/template')
    def template():
        return Response('﻿标题,时间,来源,正文,原始链接\r\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="import-template.csv"'})

    def _can_read_doc(doc, cid):
        if cid is None: return True
        if doc.get('company_id') == cid: return True
        if doc.get('kind') == 'knowledge' and doc.get('company_id') is None:
            owner = store.one('SELECT id FROM companies WHERE document_id=?', (doc['id'],))
            return not owner or owner['id'] == cid
        return False

    @app.get('/api/documents')
    def documents(request:Request,kind:str='event',q:str='',page:int=1,status:str='',policy:str='',sort:str=''):
        page=max(1,page)
        if kind not in ('event','knowledge'): raise ValueError('资料用途无效。')
        cid=getattr(request.state,'company_id',None)
        args=[kind]+['%'+q+'%']*4
        where='d.kind=? AND (d.title LIKE ? OR d.source LIKE ? OR d.zh_keywords LIKE ? OR d.zh_summary LIKE ?)'
        if cid is not None:
            if kind=='event':
                where+=' AND d.company_id=?'; args.append(cid)
            else:
                where+=' AND (d.company_id=? OR (d.company_id IS NULL AND d.id NOT IN (SELECT document_id FROM companies WHERE document_id IS NOT NULL)))'
                args.append(cid)
        if policy in ('local','external'):
            where+=' AND d.allow_external=?'; args.append(int(policy=='external'))
        if status=='unanalysed':
            where+=' AND NOT EXISTS(SELECT 1 FROM analyses a WHERE a.document_id=d.id)'
        elif status in ('queued','running','failed','completed'):
            where+=' AND (SELECT status FROM jobs j WHERE j.document_id=d.id ORDER BY j.id DESC LIMIT 1)=?'; args.append(status)
        count=store.one('SELECT COUNT(*) n FROM documents d WHERE '+where,args)['n']
        order="d.date='',d.date DESC,d.id DESC" if sort=='date' else 'd.id DESC'
        rows=store.rows("""SELECT d.id,d.title,d.date,d.date_source,d.archived_at,d.fetched_at,d.source,d.url,d.kind,d.allow_external,d.demo,d.created_at,length(d.body) characters,d.zh_summary,d.zh_keywords,d.zh_state,d.company_id,d.filename,d.file_path!='' has_file,d.quarantined_at,d.quarantine_reason,
            (SELECT id FROM jobs WHERE document_id=d.id ORDER BY id DESC LIMIT 1) job_id,
            (SELECT status FROM jobs WHERE document_id=d.id ORDER BY id DESC LIMIT 1) job_status,
            (SELECT progress FROM jobs WHERE document_id=d.id ORDER BY id DESC LIMIT 1) job_progress,
            (SELECT total FROM jobs WHERE document_id=d.id ORDER BY id DESC LIMIT 1) job_total,
            (SELECT error FROM jobs WHERE document_id=d.id ORDER BY id DESC LIMIT 1) job_error,
            (SELECT decision FROM analyses WHERE document_id=d.id ORDER BY version DESC LIMIT 1) decision
            FROM documents d WHERE """+where+' ORDER BY '+order+' LIMIT 30 OFFSET ?',args+[(page-1)*30])
        for row in rows:
            row['editable']=cid is None or row['company_id']==cid
            row['kind_label']=kind_label(store,row)
            row.pop('has_file')
        return {'items':rows,'total':count,'page':page,'page_size':30}

    @app.get('/api/documents/{doc_id}')
    def document(doc_id:int,request:Request):
        cid=getattr(request.state,'company_id',None)
        doc=store.one('SELECT * FROM documents WHERE id=?',(doc_id,))
        if not doc or not _can_read_doc(doc,cid): raise HTTPException(404,'资料不存在。')
        doc['kind_label']=kind_label(store,doc)
        doc.pop('file_path'); doc.pop('digest')
        doc['editable']=cid is None or doc.get('company_id')==cid
        doc['chunks']=store.rows('SELECT id,locator,text FROM chunks WHERE document_id=? ORDER BY id',(doc_id,))
        doc['analyses']=store.rows('SELECT id,version,decision,model,mode,created_at,result_json FROM analyses WHERE document_id=? ORDER BY version DESC',(doc_id,))
        for row in doc['analyses']:
            row['result']=json.loads(row.pop('result_json'))
            row['events']=store.rows('SELECT id,title FROM events WHERE analysis_id=?',(row['id'],))
        return doc

    @app.patch('/api/documents/{doc_id}/policy')
    def document_policy(doc_id:int,data:DocumentPolicy,request:Request):
        cid=getattr(request.state,'company_id',None)
        doc=store.one('SELECT id,company_id,quarantined_at FROM documents WHERE id=?',(doc_id,))
        if not doc or (cid is not None and doc.get('company_id')!=cid):
            raise HTTPException(404,'资料不存在或无权修改。')
        if doc['quarantined_at']:
            raise HTTPException(409,'资料已隔离待核实，不能修改外发授权。')
        with store.db() as db:
            if db.execute("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(doc_id,)).fetchone():
                raise HTTPException(409,'资料有待处理任务，请等待任务结束后修改授权范围。')
            if db.execute('UPDATE documents SET allow_external=? WHERE id=? AND demo=0',(int(data.allow_external),doc_id)).rowcount==0:
                raise HTTPException(404,'资料不存在或属于不可修改的演示资料。')
        store.audit('document_policy_changed',f'document={doc_id}, allow_external={data.allow_external}',company_id=doc['company_id'])
        return {'ok':True}

    @app.get('/api/documents/{doc_id}/file')
    def original(doc_id:int,request:Request):
        cid=getattr(request.state,'company_id',None)
        doc=store.one('SELECT id,kind,company_id,file_path,filename FROM documents WHERE id=?',(doc_id,))
        if not doc or not _can_read_doc(doc,cid) or not doc['file_path']: raise HTTPException(404,'该资料没有原始附件。')
        return FileResponse(store.directory/'uploads'/doc['file_path'],filename=doc['filename'],media_type='application/octet-stream')

    @app.get('/api/knowledge/search')
    def knowledge_search(request:Request,q:str=''):
        if not q.strip(): return {'items':[],'total_documents':0,'limit':8,'query':q}
        cid=company_of(request)
        scope_cid=cid if cid is not None else (getattr(request.state,'active_company',None) or 0)
        full=retrieve(store,q,limit=200,company_id=scope_cid,per_document=True)
        items=annotate_hits(store,q,full[:8],viewer_company_id=cid)
        return {'items':items,'total_documents':len(full),'limit':8,'query':q}

    @app.post('/api/jobs')
    def enqueue(data:JobRequest,request:Request):
        if not settings.configured: raise HTTPException(409,'尚未配置模型服务，请按模型设置页说明填写 .env 并重启。')
        if not store.setting('rules')['confirmed']: raise HTTPException(409,'请先确认甲方风险分类分级规则。')
        cid=company_of(request)
        selected_company=session_company(request)
        ids=list(dict.fromkeys(data.document_ids))
        with store.db() as db:
            checked={}
            for doc_id in ids:
                doc=db.execute('SELECT * FROM documents WHERE id=?',(doc_id,)).fetchone()
                if not doc or doc['kind']!='event' or (cid is not None and doc['company_id']!=cid):
                    raise ValueError(f'资料 {doc_id} 不是当前公司的待分析资料。')
                if doc['demo']: raise ValueError('内置演示资料不进入真实分析，请导入新的测试资料。')
                if doc['quarantined_at']: raise ValueError(f'资料 {doc_id} 已隔离，不能进入分析。')
                if not doc['allow_external']: raise ValueError(f'资料 {doc_id} 未获准发送外部模型，请在原文页核实并修改授权范围。')
                checked[doc_id]=doc
            result=[]
            for doc_id in ids:
                owner=checked[doc_id]['company_id'] or selected_company
                snap=companies.snapshot(store,owner)
                active=db.execute("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(doc_id,)).fetchone()
                if active: result.append({'id':active['id'],'existing':True}); continue
                job_id=db.execute("INSERT INTO jobs(document_id,status,created_at,company_json) VALUES (?,'queued',?,?)",(doc_id,now(),snap)).lastrowid
                result.append({'id':job_id,'existing':False})
        return {'items':result}

    @app.get('/api/jobs')
    def jobs(request:Request,q:str='',status:str='',page:int=1):
        cid=getattr(request.state,'company_id',None)
        conditions=['(d.title LIKE ? OR CAST(j.id AS TEXT)=?)'];args=['%'+q+'%',q]
        if cid is not None:
            conditions.append('d.company_id=?');args.append(cid)
        if status:
            if status not in ('queued','running','completed','failed','cancelled'): raise ValueError('任务状态无效。')
            conditions.append('j.status=?');args.append(status)
        base=' FROM jobs j JOIN documents d ON d.id=j.document_id WHERE '+' AND '.join(conditions)
        total=store.one('SELECT COUNT(*) n'+base,args)['n'];page=max(1,page)
        active_sql="SELECT COUNT(*) n FROM jobs j JOIN documents d ON d.id=j.document_id WHERE j.status IN ('queued','running')"+(' AND d.company_id=?' if cid is not None else '')
        active_args=(cid,) if cid is not None else ()
        return {'items':store.rows('SELECT j.*,d.title'+base+' ORDER BY j.id DESC LIMIT 100 OFFSET ?',args+[(page-1)*100]),'total':total,'page':page,'page_size':100,
                'active':store.one(active_sql,active_args)['n']}

    @app.get('/api/jobs/active')
    def active_jobs(request:Request):
        cid=company_of(request)
        sql="SELECT COUNT(*) n FROM jobs j JOIN documents d ON d.id=j.document_id WHERE j.status IN ('queued','running')"
        args=()
        if cid is not None:
            sql+=' AND d.company_id=?';args=(cid,)
        return {'active':store.one(sql,args)['n']}

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id:int,request:Request):
        cid=getattr(request.state,'company_id',None)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT j.status,d.company_id FROM jobs j JOIN documents d ON d.id=j.document_id WHERE j.id=?',(job_id,)).fetchone()
            if not row or (cid is not None and row['company_id']!=cid): raise HTTPException(404,'任务不存在。')
            if row['status']!='queued': raise HTTPException(409,'仅能取消尚未开始的排队任务，请刷新任务状态。')
            if not db.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=? AND status='queued'",(now(),job_id)).rowcount:
                raise HTTPException(409,'任务已开始，请刷新任务状态。')
        store.audit('job_cancelled',f'job={job_id}',company_id=row['company_id'])
        return {'ok':True}

    @app.post('/api/jobs/preflight')
    def preflight(data:JobRequest,request:Request):
        cid=company_of(request)
        items=[]
        for doc_id in dict.fromkeys(data.document_ids):
            doc=store.one('SELECT id,title,kind,demo,allow_external,company_id,quarantined_at FROM documents WHERE id=?',(doc_id,))
            if doc and cid is not None and doc.get('company_id')!=cid:
                doc=None
            reasons=[]
            if not doc: reasons.append('资料不存在')
            else:
                if doc['kind']!='event': reasons.append('参考资料不能直接启动风险分析')
                if doc['demo']: reasons.append('虚构演示资料不能进入真实分析')
                if doc['quarantined_at']: reasons.append('资料已隔离（待核实）')
                if not doc['allow_external']: reasons.append('尚未授权外部分析')
            active=store.one("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','running')",(doc_id,)) if doc else None
            owner=doc.get('company_id') if doc else None
            company=companies.current(store,owner) if owner else None
            items.append({'id':doc_id,'title':doc['title'] if doc else f'资料 #{doc_id}','issues':reasons,'existing_job':active['id'] if active else None,
                          'company':{'id':company['id'],'name':company['name']} if company else None})
        blockers=[]
        if not settings.configured: blockers.append('尚未配置模型服务')
        if not store.setting('rules')['confirmed']: blockers.append('风险分类分级规则尚未确认')
        current=companies.current(store,session_company(request))
        return {'items':items,'blockers':blockers,'ready':not blockers and all(not i['issues'] for i in items),'mode':settings.model_mode,
                'session_company':{'id':current['id'],'name':current['name']} if current else None}

    def events_query(demo='all',q='',level='',category='',review='',date_from='',date_to='',company_id=None):
        from datetime import date
        for value in (date_from,date_to):
            if value:
                try: date.fromisoformat(value)
                except ValueError: raise ValueError('筛选日期须为 YYYY-MM-DD。')
        if date_from and date_to and date_from>date_to: raise ValueError('开始日期不能晚于结束日期。')
        if demo not in ('all','real','demo'): raise ValueError('数据范围无效。')
        if level and level not in ('red','orange','yellow'): raise ValueError('风险等级无效。')
        if review and review not in ('pending','accepted','needs_change'): raise ValueError('复核状态无效。')
        conditions=[
            'a.id=(SELECT a2.id FROM analyses a2 WHERE a2.document_id=a.document_id ORDER BY version DESC LIMIT 1)',
            'd.quarantined_at IS NULL',
        ]
        args=[]
        if company_id is not None:
            conditions.append('d.company_id=?')
            args.append(company_id)
        for value,sql in [(q,'(e.title LIKE ? OR e.summary LIKE ?)'),(level,'e.level=?'),(category,'e.category=?'),(review,'e.review_status=?'),(date_from,'d.date>=?'),(date_to,'d.date<=?')]:
            if value:
                conditions.append(sql)
                args.extend(['%'+value+'%']*2 if sql.startswith('(') else [value])
        if demo in ('real','demo'): conditions.append('d.demo=?'); args.append(int(demo=='demo'))
        base=' FROM events e JOIN analyses a ON a.id=e.analysis_id JOIN documents d ON d.id=a.document_id LEFT JOIN companies c ON c.id=d.company_id WHERE '+' AND '.join(conditions)
        return base,args

    @app.get('/api/events')
    def events(request:Request,q:str='',level:str='',category:str='',review:str='',demo:str='all',page:int=1,date_from:str='',date_to:str=''):
        cid=getattr(request.state,'company_id',None)
        base,args=events_query(demo,q,level,category,review,date_from,date_to,company_id=cid)
        total=store.one('SELECT COUNT(*) n'+base,args)['n']
        rows=store.rows('SELECT e.id,e.title,e.category,e.level,e.summary,e.review_status,d.date,d.date_source,d.source,d.demo,d.id document_id,a.model,a.mode'+base+' ORDER BY d.date DESC,e.id DESC LIMIT 20 OFFSET ?',args+[(max(page,1)-1)*20])
        return {'items':rows,'total':total,'page':max(page,1),'page_size':20}

    @app.get('/api/events/{event_id}')
    def event(event_id:int,request:Request):
        cid=getattr(request.state,'company_id',None)
        row=store.one("""SELECT e.*,a.document_id,a.version,a.model,a.mode,a.created_at,a.duration_ms,a.rules_json,a.usage_json,a.result_json,
            d.date,d.date_source,d.source,d.url,d.demo,d.company_id,d.quarantined_at,d.quarantine_reason
            FROM events e JOIN analyses a ON a.id=e.analysis_id JOIN documents d ON d.id=a.document_id WHERE e.id=?""",(event_id,))
        if not row or (cid is not None and row.get('company_id')!=cid): raise HTTPException(404,'事件不存在。')
        for name in ('evidence','rules','usage','result'): row[name]=json.loads(row.pop(name+'_json'))
        row['is_latest']=store.one('SELECT id FROM analyses WHERE document_id=? ORDER BY version DESC LIMIT 1',(row['document_id'],))['id']==row['analysis_id']
        row['review_history']=store.rows('SELECT status,note,created_at FROM review_history WHERE event_id=? ORDER BY id DESC',(event_id,))
        return row

    @app.put('/api/events/{event_id}/review')
    def review(event_id:int,data:Review,request:Request):
        if data.status not in ('pending','accepted','needs_change'): raise ValueError('复核状态无效。')
        cid=getattr(request.state,'company_id',None)
        with store.db() as db:
            previous=db.execute('SELECT e.review_status,e.review_note,e.reviewed_at,d.company_id FROM events e JOIN analyses a ON a.id=e.analysis_id JOIN documents d ON d.id=a.document_id WHERE e.id=?',(event_id,)).fetchone()
            if not previous or (cid is not None and previous['company_id']!=cid):
                raise HTTPException(404,'事件不存在。')
            if previous['reviewed_at'] and not db.execute('SELECT id FROM review_history WHERE event_id=?',(event_id,)).fetchone():
                db.execute('INSERT INTO review_history(event_id,status,note,created_at) VALUES (?,?,?,?)',(event_id,previous['review_status'],previous['review_note'],previous['reviewed_at']))
            changed=db.execute('UPDATE events SET review_status=?,review_note=?,reviewed_at=? WHERE id=?',(data.status,data.note,now(),event_id)).rowcount
            if not changed: raise HTTPException(404,'事件不存在。')
            db.execute('INSERT INTO review_history(event_id,status,note,created_at) VALUES (?,?,?,?)',(event_id,data.status,data.note,now()))
        store.audit('event_reviewed',f'event={event_id}, status={data.status}',company_id=previous['company_id'])
        return {'ok':True}

    @app.get('/api/overview')
    def overview(request:Request,demo:str='all'):
        cid=getattr(request.state,'company_id',None)
        base,args=events_query(demo,company_id=cid)
        doc_where="WHERE kind='event' AND quarantined_at IS NULL"
        doc_args=[]
        if cid is not None:
            doc_where+=' AND company_id=?'; doc_args.append(cid)
        if demo in ('real','demo'):
            doc_where+=' AND demo=?'; doc_args.append(int(demo=='demo'))
        job_where="WHERE j.status IN ('queued','running') AND d.quarantined_at IS NULL"
        job_args=[]
        if cid is not None:
            job_where+=' AND d.company_id=?'; job_args.append(cid)
        company_count=store.one('SELECT COUNT(*) n FROM companies')['n'] if cid is None else 1
        return {'total':store.one('SELECT COUNT(*) n'+base,args)['n'],
            'levels':store.rows('SELECT e.level,COUNT(*) count'+base+' GROUP BY e.level',args),
            'categories':store.rows('SELECT e.category,COUNT(*) count'+base+' GROUP BY e.category ORDER BY count DESC',args),
            'pending':store.one('SELECT COUNT(*) n'+base+" AND e.review_status='pending'",args)['n'],
            'documents':store.one('SELECT COUNT(*) n FROM documents '+doc_where,doc_args)['n'],
            'active_jobs':store.one('SELECT COUNT(*) n FROM jobs j JOIN documents d ON d.id=j.document_id '+job_where,job_args)['n'],
            'scope':{'all_companies':cid is None,'company_id':cid,'company_count':company_count}}

    @app.post('/api/demo')
    def demo(request:Request):
        require_admin(request)
        return {'added':seed(store)}

    @app.delete('/api/demo')
    def clear_demo(request:Request):
        require_admin(request)
        ids=[r['id'] for r in store.rows('SELECT id FROM documents WHERE demo=1')]
        result=store.delete_documents(ids)
        store.audit('demo_cleared',f"count={result['documents']}, events={result['events']}")
        return result

    @app.delete('/api/documents/{doc_id}')
    def delete_document(doc_id:int,request:Request):
        cid=getattr(request.state,'company_id',None)
        doc=store.one('SELECT id,title,kind,company_id,quarantined_at FROM documents WHERE id=?',(doc_id,))
        if not doc or (cid is not None and doc.get('company_id')!=cid):
            raise HTTPException(404,'资料不存在或无权删除。')
        if doc['quarantined_at']:
            raise HTTPException(409,'资料已隔离待核实，需先由管理员撤销隔离后才能删除。')
        result=store.delete_documents([doc_id])
        store.audit('document_deleted',f"id={doc_id}, kind={doc['kind']}, events={result['events']}",company_id=doc['company_id'])
        return result

    @app.get('/api/export/events')
    def export_events(request:Request,q:str='',level:str='',category:str='',review:str='',demo:str='all',date_from:str='',date_to:str=''):
        cid=getattr(request.state,'company_id',None)
        base,args=events_query(demo,q,level,category,review,date_from,date_to,company_id=cid)
        rows=store.rows('SELECT e.*,d.date,d.date_source,d.source,d.demo,d.url,a.version'+base+' ORDER BY d.date DESC,e.id DESC',args)
        output=io.StringIO(newline=''); writer=csv.writer(output)
        writer.writerow(['事件编号','标题','风险等级','类型','摘要','潜在影响','建议','复核状态','复核意见','资料日期','来源','链接','分析版本','数据性质','引用依据','日期来源'])
        def safe(value):
            value=str(value or '')
            return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
        for row in rows:
            writer.writerow([safe(v) for v in [row['id'],row['title'],{'red':'高风险','orange':'中风险','yellow':'一般关注'}.get(row['level'],row['level']),row['category'],row['summary'],row['impact'],row['recommendation'],{'pending':'待复核','accepted':'已认可','needs_change':'需修正'}[row['review_status']],row['review_note'],row['date'],row['source'],row['url'],row['version'],'虚构演示' if row['demo'] else '非演示数据', '\n'.join(r.get('quote','') for r in json.loads(row['evidence_json'])),row['date_source']]])
        store.audit('events_exported',f'count={len(rows)}, scope={demo}, company={cid}',company_id=cid)
        return Response('﻿'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="risk-events.csv"'})

    @app.get('/api/workspace')
    def workspace(request:Request):
        cid=getattr(request.state,'company_id',None)
        if cid is not None:
            ev_row=store.one("SELECT 'event' kind,COUNT(*) count,COALESCE(SUM(allow_external),0) authorized,COALESCE(SUM(length(body)),0) characters FROM documents WHERE demo=0 AND kind='event' AND quarantined_at IS NULL AND company_id=?",(cid,))
            kn_row=store.one("SELECT 'knowledge' kind,COUNT(*) count,COALESCE(SUM(allow_external),0) authorized,COALESCE(SUM(length(body)),0) characters FROM documents WHERE demo=0 AND kind='knowledge' AND quarantined_at IS NULL AND (company_id=? OR (company_id IS NULL AND id NOT IN (SELECT document_id FROM companies WHERE document_id IS NOT NULL)))",(cid,))
            counts={'event':ev_row,'knowledge':kn_row}
            jobs_rows=store.rows('SELECT j.status,COUNT(*) count FROM jobs j JOIN documents d ON d.id=j.document_id WHERE d.company_id=? GROUP BY j.status',(cid,))
            unanalysed=store.one("SELECT COUNT(*) n FROM documents d WHERE kind='event' AND demo=0 AND quarantined_at IS NULL AND company_id=? AND NOT EXISTS(SELECT 1 FROM analyses a WHERE a.document_id=d.id)",(cid,))['n']
            recent=store.rows('SELECT action,detail,created_at FROM audit WHERE company_id=? ORDER BY id DESC LIMIT 15',(cid,))
        else:
            docs=store.rows('SELECT kind,COUNT(*) count,SUM(allow_external) authorized,SUM(length(body)) characters FROM documents WHERE demo=0 AND quarantined_at IS NULL GROUP BY kind')
            counts={r['kind']:r for r in docs}
            jobs_rows=store.rows('SELECT status,COUNT(*) count FROM jobs GROUP BY status')
            unanalysed=store.one("SELECT COUNT(*) n FROM documents d WHERE kind='event' AND demo=0 AND quarantined_at IS NULL AND NOT EXISTS(SELECT 1 FROM analyses a WHERE a.document_id=d.id)")['n']
            recent=store.rows('SELECT action,detail,created_at FROM audit ORDER BY id DESC LIMIT 15')
        return {'documents':counts,'jobs':jobs_rows,
            'unanalyzed':unanalysed,
            'recent_activity':recent,
            'checks':[{'label':'模型服务配置','ready':settings.configured,'href':'#settings'},
                      {'label':'业务规则确认','ready':bool(store.setting('rules')['confirmed']),'href':'#settings'},
                      {'label':'待分析资料（非演示）','ready':bool(counts.get('event',{}).get('count')),'href':'#documents'},
                      {'label':'知识库参考资料（可选）','ready':bool(counts.get('knowledge',{}).get('count')),'href':'#knowledge'}]}

    @app.get('/api/report')
    def report(request:Request,q:str='',level:str='',category:str='',review:str='',demo:str='all',date_from:str='',date_to:str=''):
        cid=getattr(request.state,'company_id',None)
        base,args=events_query(demo,q,level,category,review,date_from,date_to,company_id=cid)
        total=store.one('SELECT COUNT(*) n'+base,args)['n']
        if total>500: raise HTTPException(400,'当前匹配超过500条，请缩小日期或分类范围后生成简报；完整台账可使用 CSV 导出。')
        items=store.rows("SELECT e.*,d.date,d.date_source,d.source,d.url,d.demo,a.version,a.model,a.mode,a.rules_json,json_extract(c.profile_json,'$.name') company_name"+base+" ORDER BY CASE e.level WHEN 'red' THEN 0 WHEN 'orange' THEN 1 ELSE 2 END,d.date DESC,e.id DESC",args)
        for item in items:
            item['evidence']=json.loads(item.pop('evidence_json'))
            item['rule_version']=json.loads(item.pop('rules_json'))['version']
        company=companies.current(store,cid) if cid is not None else None
        return {'generated_at':now(),'total':total,'items':items,'scope':{
            'q':q,'level':level,'category':category,'review':review,'demo':demo,'date_from':date_from,'date_to':date_to,
            'company':{'all':cid is None,'name':company['name'] if company else '','count':store.one('SELECT COUNT(*) n FROM companies')['n'] if cid is None else 1},
        }}

    def last_backup():
        if not settings.backup_dir:return None
        marks=sorted(Path(settings.backup_dir).glob('*/backup.json'),key=lambda p:p.parent.name)
        if not marks:return {'created_at':None,'count':0}
        try:created=json.loads(marks[-1].read_text(encoding='utf-8'))['created_at']
        except (OSError,ValueError,KeyError):created=None
        return {'created_at':created,'count':len(marks)}

    def model_error():
        rows=[r for r in (store.one("SELECT error,finished_at at FROM jobs WHERE status='failed' AND error!='' ORDER BY id DESC LIMIT 1"),
                          store.one("SELECT error,finished_at at FROM web_runs WHERE error LIKE '%模型服务%' ORDER BY id DESC LIMIT 1")) if r and r['at']]
        return max(rows,key=lambda r:r['at']) if rows else None

    @app.get('/api/runtime')
    def runtime(request:Request):
        require_admin(request)
        disk=shutil.disk_usage(store.directory)
        return {'checked_at':now(),'database_bytes':store.path.stat().st_size,'disk_free_bytes':disk.free,
                'documents':store.one('SELECT COUNT(*) n FROM documents')['n'],
                'chunks':store.one('SELECT COUNT(*) n FROM chunks')['n'],
                'analyses':store.one('SELECT COUNT(*) n FROM analyses')['n'],
                'queue':store.rows('SELECT status,COUNT(*) count FROM jobs GROUP BY status'),
                'worker_enabled':run_worker,'backup':last_backup(),
                'fetch_proxy':bool(websearch.FETCH_PROXY),'renderer':bool(websearch.RENDERER),
                'enrich_pending':store.one("SELECT COUNT(*) n FROM documents WHERE kind='knowledge' AND demo=0 AND quarantined_at IS NULL AND allow_external=1 AND zh_state=''")['n'],
                'enrich_failed':store.one("SELECT COUNT(*) n FROM documents WHERE kind='knowledge' AND quarantined_at IS NULL AND zh_state='failed'")['n'],
                'model_error':model_error(),'last_analysis':store.one('SELECT created_at,model,mode FROM analyses ORDER BY id DESC LIMIT 1')}

    app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
    @app.get('/')
    def home(): return FileResponse(ROOT/'web'/'index.html')
    return app
