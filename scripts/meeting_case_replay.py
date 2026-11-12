"""Replay supplied facts against the deployed pipeline; answers are evaluation-only."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from dataclasses import replace
from dotenv import dotenv_values

REPLAY_ROOT=Path(os.environ.get('RAG_REPLAY_ROOT','/opt/rag-workbench/verification-followup-20261111')).resolve()
REPLAY_ENV=os.environ.get('RAG_REPLAY_ENV','/etc/rag-workbench/workbench.env')
os.environ.update({k:v for k,v in dotenv_values(REPLAY_ENV).items() if v is not None})
if 'RAG_REPLAY_PROXY' in os.environ:os.environ['MODEL_PROXY']=os.environ['RAG_REPLAY_PROXY']
sys.path.insert(0,str(REPLAY_ROOT))
from app.config import Settings
from app.store import Store
from app.jobs import Worker
from app.ingest import insert_document
from app import companies,vectors
from app.meeting import current_rules,LEGACY_MAPPING
from app.presentation import match_company

if os.environ.get('RAG_REPLAY_TRACE')=='1':
    import httpx
    _send=httpx.AsyncClient.send
    async def _traced_send(self,request,*args,**kwargs):
        response=await _send(self,request,*args,**kwargs)
        if request.url.path.endswith(('/chat/completions','/responses')):
            await response.aread()
            trace=REPLAY_ROOT/'model-trace';trace.mkdir(exist_ok=True)
            (trace/(os.environ.get('RAG_REPLAY_CURRENT','case')+'-'+str(time.time_ns())+'.json')).write_text(
                json.dumps({'status':response.status_code,'request':json.loads(request.content),
                    'response':response.text},ensure_ascii=False,indent=2),encoding='utf-8')
        return response
    httpx.AsyncClient.send=_traced_send


async def run():
    folder=REPLAY_ROOT
    inputs=json.loads((folder/'model-inputs.json').read_text(encoding='utf-8-sig'))
    answers=json.loads((folder/'extracted-cases.json').read_text(encoding='utf-8-sig'))
    from run_rag_customer_cases_20261101 import packet
    expected={c['id']:packet(c)['expected'] for c in answers}
    store=Store(folder/'replica');companies.initialize(store)
    settings=replace(Settings(),data_dir=store.directory)
    rules=current_rules(store.setting('rules'));rules['confirmed']=True;store.set_setting('rules',rules)
    results=[]
    selected=os.environ.get('RAG_REPLAY_CASES','').split(',')
    if selected!=['']:inputs=[item for item in inputs if item['id'] in selected]
    for item in inputs:
        os.environ['RAG_REPLAY_CURRENT']=item['id']
        tick=time.monotonic()
        owner=match_company(store.rows('SELECT id,profile_json FROM companies'),item['profile'])
        cid=owner['id']
        doc_id,_=insert_document(store,{'title':item['title'],'body':item['body'],'source':'事项资料'},'event',company_id=cid,identity='replay-'+item['id'])
        with store.db() as db:jid=store.enqueue_job(db,doc_id,json.dumps({**item['profile'],'id':cid},ensure_ascii=False))
        await asyncio.wait_for(Worker(store,settings).process(store.one('SELECT * FROM jobs WHERE id=?',(jid,))),timeout=360)
        job=store.one('SELECT status,error FROM jobs WHERE id=?',(jid,))
        analysis=store.one('SELECT * FROM analyses WHERE job_id=?',(jid,))
        result={'id':item['id'],'title':item['title'],'job_id':jid,'document_id':doc_id,**job,'seconds':round(time.monotonic()-tick,2)}
        if analysis:
            events=store.rows('SELECT title,category,level,summary,impact,recommendation,evidence_json,actions_json FROM events WHERE analysis_id=?',(analysis['id'],))
            wanted=expected[item['id']]
            old_level=wanted['level'];target_level=LEGACY_MAPPING.get(old_level,old_level)
            names={n for n in rules['categories'] if any(n in t for t in wanted['categories_text'])}
            if wanted['categories_text']==['对不上']:names={'其他'}
            decision='risk' if wanted['risk'] and target_level!='non_risk' else 'non_risk'
            actual=json.loads(analysis['result_json'])
            result.update(analysis_id=analysis['id'],decision=analysis['decision'],events=events,expected={'decision':decision,'categories':sorted(names),'level':target_level},
                decision_match=analysis['decision']==decision,
                category_match={e['category'] for e in events}==(names if decision=='risk' else set()),
                level_match=(bool(events) and all(e['level']==target_level for e in events)) if decision=='risk' else not events,
                source_coverage=actual['source_coverage'])
            result['all_match']=all(result[k] for k in ('decision_match','category_match','level_match'))
        results.append(result)
        (folder/'case-replay-progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ('events','expected','source_coverage')},ensure_ascii=False),flush=True)
        if job['status']=='failed' and 'HTTP 402' in (job.get('error') or ''):
            print('模型服务仍拒绝付费调用，停止后续案例，避免重复失败请求。',flush=True)
            break
    summary={'total':len(inputs),'attempted':len(results),'not_run':len(inputs)-len(results),'completed':sum(r['status']=='completed' for r in results),
             **{k:sum(bool(r.get(k)) for r in results) for k in ('decision_match','category_match','level_match','all_match')},
             'expected_labels_sent':False,'production_writes':False,'source':'current deployed pipeline with supplied facts and existing reference documents'}
    (folder/'case-replay.json').write_text(json.dumps({'summary':summary,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':asyncio.run(run())
