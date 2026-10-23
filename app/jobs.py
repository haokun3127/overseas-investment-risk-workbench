import asyncio
import json
import time
from . import model
from .retrieval import retrieve
from .store import now

class Worker:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self.loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def loop(self):
        while True:
            job = self.store.one("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1")
            if not job:
                await asyncio.sleep(0.5)
                continue
            await self.process(job)

    async def process(self, job):
        started = time.monotonic()
        with self.store.db() as db:
            claimed=db.execute("UPDATE jobs SET status='running',started_at=? WHERE id=? AND status='queued'",(now(),job['id'])).rowcount
            if not claimed: return
            job = dict(db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone())
        doc = None
        try:
            doc = self.store.one('SELECT * FROM documents WHERE id=?',(job['document_id'],))
            company=json.loads(job.get('company_json') or '{}')
            if not job.get('rules_json'):
                raise ValueError('任务缺少规则快照，请重新提交分析。')
            rules = json.loads(job['rules_json'])
            supplements = json.loads(job.get('supplements_json') or '[]')
            if not doc:
                raise ValueError('资料已删除，任务无法继续。')
            if doc.get('quarantined_at'):
                raise ValueError('资料已隔离，不能进入分析。')
            if not self.settings.configured:
                raise ValueError('尚未配置模型服务，请填写 .env 后重启。')
            if not rules['confirmed']:
                raise ValueError('风险规则尚未确认。')
            external = True
            if not doc['allow_external']:
                raise ValueError('该资料未获准发送到外部模型。')
            context=company if company.get('allow_external') else {}
            job_company_id = doc.get('company_id') or company.get('id') or 0
            for item in supplements:
                supplemental_doc = self.store.one('SELECT * FROM documents WHERE id=?',(item['document_id'],))
                if not supplemental_doc or supplemental_doc['quarantined_at'] or not supplemental_doc['allow_external']:
                    raise ValueError('补充资料已删除、隔离或撤销外发授权，请核对后重新提交。')
                if supplemental_doc.get('company_id') != doc.get('company_id'):
                    raise ValueError('补充资料归属与原资料不一致。')
            chunks = self.store.rows('SELECT * FROM chunks WHERE document_id=? ORDER BY id',(doc['id'],))
            with self.store.db() as db:
                db.execute('UPDATE jobs SET total=? WHERE id=?',(len(chunks),job['id']))
            results, events, usage, knowledge = [], [], [], {}
            for index, chunk in enumerate(chunks):
                hits = retrieve(self.store,chunk['text'],external=external,company_id=job_company_id,per_document=True)
                for h in hits:
                    h.pop('zh_summary', None)
                    h.pop('zh_keywords', None)
                references = {f'S{chunk["id"]}':{'text':chunk['text'],'kind':'source','document_id':doc['id'],'locator':chunk['locator'],'title':doc['title']}}
                for item in supplements:
                    references[f'S{item["id"]}'] = {**item,'kind':'source','role':'supplement'}
                for hit in hits:
                    references[f'K{hit["id"]}'] = {**hit,'kind':'knowledge'}
                    knowledge[str(hit['id'])] = hit
                payload = {'scope':{'country':'印度尼西亚','industry':context.get('industry') or '未指定行业'},'rules':rules,
                    'document':{'title':doc['title'],'date':doc['date'],'source':doc['source']},
                    'company':context,
                    'part':f'{index+1}/{len(chunks)}','references':[{'reference':key,**value} for key,value in references.items()]}
                raw, used = await model.call_model(self.settings,payload)
                result = model.validate_result(raw,references,rules)
                results.append(result)
                usage.append(used)
                events.extend(result['events'])
                with self.store.db() as db:
                    db.execute('UPDATE jobs SET progress=? WHERE id=?',(index+1,job['id']))
            # Only exact duplicate titles/quotes are collapsed; all remaining events stay reviewable.
            unique = {}
            for event in events:
                key = (event['title'], event['evidence'][0]['quote'])
                unique.setdefault(key,event)
            events = list(unique.values())
            decision = 'risk' if events else ('insufficient' if any(r['decision']=='insufficient' for r in results) else 'non_risk')
            result_blob = {'decision':decision,'parts':results,'prompt_version':model.PROMPT_VERSION,
                           'company_context':context,
                           'partial_context':len(chunks)>1,'review_required':True,
                           'parent_analysis_id':job.get('parent_analysis_id'),
                           'supplement_document_ids':list(dict.fromkeys(i['document_id'] for i in supplements)),
                           'rules_snapshot_origin':job.get('rules_snapshot_origin'),
                           'model_config':{'wire_api':self.settings.model_wire_api,'reasoning_effort':self.settings.model_reasoning_effort,'store':self.settings.model_store}}
            with self.store.db() as db:
                version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM analyses WHERE document_id=?',(doc['id'],)).fetchone()[0]
                analysis_id = db.execute('''INSERT INTO analyses(document_id,job_id,version,decision,model,mode,rules_json,knowledge_json,result_json,created_at,duration_ms,usage_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(doc['id'],job['id'],version,decision,self.settings.model_name,self.settings.model_mode,
                    json.dumps(rules,ensure_ascii=False),json.dumps(knowledge,ensure_ascii=False),json.dumps(result_blob,ensure_ascii=False),now(),int((time.monotonic()-started)*1000),json.dumps(usage))).lastrowid
                for event in events:
                    db.execute('''INSERT INTO events(analysis_id,title,category,level,summary,impact,recommendation,evidence_json)
                        VALUES (?,?,?,?,?,?,?,?)''',(analysis_id,event['title'],event['category'],event['level'],event['summary'],event['impact'],event['recommendation'],json.dumps(event['evidence'],ensure_ascii=False)))
                db.execute("UPDATE jobs SET status='completed',finished_at=? WHERE id=?",(now(),job['id']))
            self.store.audit('analysis_completed',f'job={job["id"]}, analysis={analysis_id}',company_id=doc.get('company_id'))
        except asyncio.CancelledError:
            with self.store.db() as db:
                db.execute("UPDATE jobs SET status='failed',error='服务停止，任务中断，请重试。',finished_at=? WHERE id=?",(now(),job['id']))
            raise
        except Exception as error:
            message = str(error) if isinstance(error,ValueError) else '处理失败，请检查资料格式及服务配置后重试。'
            with self.store.db() as db:
                db.execute("UPDATE jobs SET status='failed',error=?,finished_at=? WHERE id=?",(message[:500],now(),job['id']))
            self.store.audit('analysis_failed',f'job={job["id"]}, type={type(error).__name__}',company_id=doc.get('company_id') if doc else None)
