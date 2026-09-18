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
        try:
            doc = self.store.one('SELECT * FROM documents WHERE id=?',(job['document_id'],))
            rules = self.store.setting('rules')
            if not self.settings.configured:
                raise ValueError('尚未配置模型服务，请填写 .env 后重启。')
            if not rules['confirmed']:
                raise ValueError('风险规则尚未确认。')
            external = self.settings.model_mode=='external'
            if external and not doc['allow_external']:
                raise ValueError('该资料未获准发送到外部模型。')
            chunks = self.store.rows('SELECT * FROM chunks WHERE document_id=? ORDER BY id',(doc['id'],))
            with self.store.db() as db:
                db.execute('UPDATE jobs SET total=? WHERE id=?',(len(chunks),job['id']))
            results, events, usage, knowledge = [], [], [], {}
            for index, chunk in enumerate(chunks):
                hits = retrieve(self.store,chunk['text'],external=external)
                references = {f'S{chunk["id"]}':{'text':chunk['text'],'kind':'source','document_id':doc['id'],'locator':chunk['locator'],'title':doc['title']}}
                for hit in hits:
                    references[f'K{hit["id"]}'] = {**hit,'kind':'knowledge'}
                    knowledge[str(hit['id'])] = hit
                payload = {'scope':{'country':'印度尼西亚','industry':'制造业'},'rules':rules,
                    'document':{'title':doc['title'],'date':doc['date'],'source':doc['source']},
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
                           'partial_context':len(chunks)>1,'review_required':True}
            with self.store.db() as db:
                version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM analyses WHERE document_id=?',(doc['id'],)).fetchone()[0]
                analysis_id = db.execute('''INSERT INTO analyses(document_id,job_id,version,decision,model,mode,rules_json,knowledge_json,result_json,created_at,duration_ms,usage_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(doc['id'],job['id'],version,decision,self.settings.model_name,self.settings.model_mode,
                    json.dumps(rules,ensure_ascii=False),json.dumps(knowledge,ensure_ascii=False),json.dumps(result_blob,ensure_ascii=False),now(),int((time.monotonic()-started)*1000),json.dumps(usage))).lastrowid
                for event in events:
                    db.execute('''INSERT INTO events(analysis_id,title,category,level,summary,impact,recommendation,evidence_json)
                        VALUES (?,?,?,?,?,?,?,?)''',(analysis_id,event['title'],event['category'],event['level'],event['summary'],event['impact'],event['recommendation'],json.dumps(event['evidence'],ensure_ascii=False)))
                db.execute("UPDATE jobs SET status='completed',finished_at=? WHERE id=?",(now(),job['id']))
            self.store.audit('analysis_completed',f'job={job["id"]}, analysis={analysis_id}')
        except asyncio.CancelledError:
            with self.store.db() as db:
                db.execute("UPDATE jobs SET status='failed',error='服务停止，任务中断，请重试。',finished_at=? WHERE id=?",(now(),job['id']))
            raise
        except Exception as error:
            message = str(error) if isinstance(error,ValueError) else '处理失败，请检查资料格式及服务配置后重试。'
            with self.store.db() as db:
                db.execute("UPDATE jobs SET status='failed',error=?,finished_at=? WHERE id=?",(message[:500],now(),job['id']))
            self.store.audit('analysis_failed',f'job={job["id"]}, type={type(error).__name__}')
