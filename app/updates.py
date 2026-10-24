"""Persistent review inbox for saved website changes, scoped to administrators."""
import json
import secrets
from datetime import date

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .store import now
from .webcompare import previous_page, summary, comparison


def initialize(store):
    with store.db() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS web_updates(
            page_id INTEGER PRIMARY KEY REFERENCES web_pages(id) ON DELETE CASCADE,
            previous_page_id INTEGER REFERENCES web_pages(id) ON DELETE SET NULL,
            change_status TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            note TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1,
            reviewed_by TEXT NOT NULL DEFAULT '', reviewed_at TEXT,
            document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
            action_token TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS update_review_queue ON web_updates(change_status,status,page_id);
            CREATE TABLE IF NOT EXISTS web_update_history(
                id INTEGER PRIMARY KEY,page_id INTEGER NOT NULL REFERENCES web_pages(id) ON DELETE CASCADE,
                status TEXT NOT NULL,note TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,
                document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL);''')
        db.execute("UPDATE web_updates SET action_token='' WHERE action_token!=''")
    index_runs(store)


def index_runs(store,run_id=None):
    with store.db() as db:
        sql="SELECT p.*,r.source_id FROM web_pages p JOIN web_runs r ON r.id=p.run_id WHERE r.status='completed' AND NOT EXISTS(SELECT 1 FROM web_updates u WHERE u.page_id=p.id)"
        args=[]
        if run_id is not None:sql+=' AND r.id=?';args.append(run_id)
        pages=db.execute(sql+' ORDER BY r.id,p.id',args).fetchall()
        for row in pages:
            page=dict(row);change=summary(page,previous_page(db,page,page['source_id']))
            db.execute('INSERT OR IGNORE INTO web_updates(page_id,previous_page_id,change_status,created_at) VALUES (?,?,?,?)',
                (page['id'],change['previous_id'],change['status'],page['fetched_at']))


class UpdateReview(BaseModel):
    revision: int = Field(ge=1)
    status: str
    note: str = Field(default='',max_length=2000)


class UpdateTransfer(BaseModel):
    revision: int = Field(ge=1)
    company_id: int = Field(ge=1)
    analyze: bool = False
    note: str = Field(default='',max_length=2000)


def routes(api,store,settings,transfer):
    def get(page_id,db=None):
        sql="""SELECT u.*,p.run_id,p.title,p.url,p.relevant,p.reason,p.fetched_at,p.imports_json,
            s.name source,s.category FROM web_updates u JOIN web_pages p ON p.id=u.page_id
            JOIN web_runs r ON r.id=p.run_id JOIN web_sources s ON s.id=r.source_id
            WHERE u.page_id=? AND r.status='completed' AND s.deleted_at IS NULL AND u.change_status!='unchanged'"""
        row=db.execute(sql,(page_id,)).fetchone() if db else store.one(sql,(page_id,))
        if not row:raise HTTPException(404,'更新记录不存在。')
        return dict(row)

    def check_revision(row,revision):
        if row['action_token']:raise HTTPException(409,'该更新正在转存，请稍后刷新状态。')
        if row['revision']!=revision:raise HTTPException(409,'该更新已被处理，请刷新后重新核验。')

    @api.get('/updates')
    def inbox(status:str='pending',change:str='changed',q:str='',category:str='',date_from:str='',date_to:str='',page:int=1):
        if status not in ('pending','reviewed','ignored','all'):raise ValueError('更新处理状态无效。')
        if change not in ('changed','added','incomparable','all'):raise ValueError('正文变化类型无效。')
        for d in (date_from,date_to):
            if d:
                try:date.fromisoformat(d)
                except ValueError:raise ValueError('采集日期须为 YYYY-MM-DD。')
        if date_from and date_to and date_from>date_to:raise ValueError('开始日期不能晚于结束日期。')
        conditions=["r.status='completed'","s.deleted_at IS NULL","u.change_status!='unchanged'"]
        args=[]
        if change!='all':conditions.append('u.change_status=?');args.append(change)
        if q.strip():conditions.append('(p.title LIKE ? OR s.name LIKE ? OR p.url LIKE ?)');args+=['%'+q.strip()+'%']*3
        if category:conditions.append('s.category=?');args.append(category)
        if date_from:conditions.append('substr(p.fetched_at,1,10)>=?');args.append(date_from)
        if date_to:conditions.append('substr(p.fetched_at,1,10)<=?');args.append(date_to)
        base=' FROM web_updates u JOIN web_pages p ON p.id=u.page_id JOIN web_runs r ON r.id=p.run_id JOIN web_sources s ON s.id=r.source_id WHERE '+' AND '.join(conditions)
        counts={s:0 for s in ('pending','reviewed','ignored')}
        counts.update({r['status']:r['n'] for r in store.rows('SELECT u.status,count(*) n'+base+' GROUP BY u.status',args)})
        if status!='all':base+=' AND u.status=?';args.append(status)
        total=store.one('SELECT count(*) n'+base,args)['n'];page=max(1,page)
        rows=store.rows('''SELECT u.page_id,u.previous_page_id,u.change_status,u.status,u.note,u.revision,u.reviewed_by,u.reviewed_at,u.document_id,u.action_token!='' busy,
            p.title,p.url,p.relevant,p.reason,p.fetched_at,p.run_id,s.name source,s.category,c.profile_json company_json
            '''+base.replace(' WHERE ',' LEFT JOIN documents d ON d.id=u.document_id LEFT JOIN companies c ON c.id=d.company_id WHERE ',1)+
            ' ORDER BY p.id DESC LIMIT 20 OFFSET ?',args+[(page-1)*20])
        for row in rows:row['company_name']=json.loads(row.pop('company_json') or '{}').get('name','')
        categories=[r['category'] for r in store.rows("SELECT DISTINCT category FROM web_sources WHERE deleted_at IS NULL ORDER BY category")]
        return {'items':rows,'counts':counts,'total':total,'page':page,'page_size':20,'categories':categories}

    @api.patch('/updates/{page_id}')
    def review(page_id:int,data:UpdateReview,request:Request):
        if data.status not in ('pending','reviewed','ignored'):raise ValueError('更新处理状态无效。')
        if data.status=='ignored' and not data.note.strip():raise ValueError('忽略更新时，请填写原因。')
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=get(page_id,db);check_revision(row,data.revision)
            db.execute('UPDATE web_updates SET status=?,note=?,revision=revision+1,reviewed_by=?,reviewed_at=? WHERE page_id=?',
                (data.status,data.note,request.state.username,now(),page_id))
            db.execute('INSERT INTO web_update_history(page_id,status,note,actor,created_at) VALUES (?,?,?,?,?)',
                (page_id,data.status,data.note,request.state.username,now()))
        store.audit('website_update_reviewed',f'page={page_id}, status={data.status}')
        return {'ok':True,'revision':data.revision+1}

    @api.get('/updates/{page_id}/history')
    def history(page_id:int):
        get(page_id)
        return {'items':store.rows('SELECT status,note,actor,created_at,document_id FROM web_update_history WHERE page_id=? ORDER BY id DESC',(page_id,))}

    @api.get('/updates/{page_id}/comparison')
    def saved_comparison(page_id:int):
        row=get(page_id)
        current=store.one('SELECT * FROM web_pages WHERE id=?',(page_id,))
        previous=store.one('SELECT * FROM web_pages WHERE id=?',(row['previous_page_id'],)) if row['previous_page_id'] else None
        return comparison(current,previous)

    @api.post('/updates/{page_id}/transfer')
    def transfer_update(page_id:int,data:UpdateTransfer,request:Request):
        token=secrets.token_hex(16)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=get(page_id,db);check_revision(row,data.revision)
            if row['relevant']!=1:raise HTTPException(409,'仅相关命中页可转存，请先回网站检索核验或重新筛选。')
            db.execute('UPDATE web_updates SET action_token=? WHERE page_id=?',(token,page_id))
        try:
            result=transfer(store,settings,[page_id],'event',data.analyze,company_id=data.company_id)
            doc_id=result['items'][0]['id']
            with store.db() as db:
                db.execute("UPDATE web_updates SET status='reviewed',note=?,document_id=?,revision=revision+1,reviewed_by=?,reviewed_at=?,action_token='' WHERE page_id=? AND action_token=?",
                    (data.note,doc_id,request.state.username,now(),page_id,token))
                db.execute("INSERT INTO web_update_history(page_id,status,note,actor,created_at,document_id) VALUES (?,'reviewed',?,?,?,?)",
                    (page_id,data.note,request.state.username,now(),doc_id))
            store.audit('website_update_transferred',f'page={page_id}, document={doc_id}',company_id=data.company_id)
            return {**result,'revision':data.revision+1}
        finally:
            with store.db() as db:db.execute("UPDATE web_updates SET action_token='' WHERE page_id=? AND action_token=?",(page_id,token))
