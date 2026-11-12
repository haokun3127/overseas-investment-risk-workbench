"""Import official Indonesian legal texts locally, index them, then re-analyse the 19 reference documents.

Runs only on a local copy of production data; production is updated later by a separate sync step.
"""
import asyncio
import html
import json
import os
import re
import sys
import time
from dataclasses import replace
from pathlib import Path

from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'qa/legal-import-20261112'
LEGAL=ROOT/'qa/requirements-audit-20261112/legal'
ENV=os.environ.get('RAG_REPLAY_ENV')
SERVER_ONLY={'DATA_DIR','SSL_CERT_FILE','BACKUP_DIR','WEB_FETCH_PROXY','RENDER_URL','RENDER_TOKEN','COOKIE_PATH','SECURE_COOKIE'}
if ENV:os.environ.update({k:v for k,v in dotenv_values(ENV).items() if v is not None and k not in SERVER_ONLY})
if os.environ.get('RAG_REPLAY_PROXY'):os.environ['MODEL_PROXY']=os.environ['RAG_REPLAY_PROXY']
os.environ.setdefault('FASTEMBED_CACHE_PATH',str(WORK/'replica/models'))
sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.store import Store
from app.jobs import Worker
from app.ingest import insert_document
from app import companies,vectors
from app.meeting import current_rules
from app.enrich import Enricher

VERIFIED='2026-11-12'
LAWS=[
    {'file':'permendag31-a.pdf','title':'印尼贸易部长条例2023年第31号（电子系统交易的经营许可、广告、指导与监督）',
     'date':'2023-09-25','source':'印尼贸易部法律文献信息网（JDIH Kemendag）',
     'url':'https://jdih.kemendag.go.id/peraturan/peraturan-menteri-perdagangan-nomor-31-tahun-2023-tentang-perizinan-berusaha-periklanan-pembinaan-dan-pengawasan-pelaku-usaha-dalam-perdagangan-melalui-sistem-elektronik-1',
     'meta':{'document_no':'Permendag No. 31 Tahun 2023','issuer':'印尼贸易部','effective_from':'2023-09-26',
             'verification_note':'官方法规库页面标注状态为“Berlaku”（有效）；原文自印尼贸易部法规库下载。'}},
    {'file':'pp36-2023.pdf','title':'印尼政府条例2023年第36号（自然资源开发、管理及加工活动的出口外汇收入）',
     'date':'2023-07-12','source':'印尼财政部法律文献信息网（JDIH Kemenkeu）',
     'url':'https://jdih.kemenkeu.go.id/dok/pp-36-tahun-2023',
     'meta':{'document_no':'PP No. 36 Tahun 2023','issuer':'印尼政府','effective_from':'2023-08-01',
             'verification_note':'官方法规库标注2023-08-01起施行；部分条款已由2025年第8号政府条例修订，适用2025-03-01以前的事实或未修订条款。'}},
    {'file':'pp8-2025.pdf','title':'印尼政府条例2025年第8号（关于修订2023年第36号政府条例的出口外汇收入规定）',
     'date':'2025-02-17','source':'印尼财政部法律文献信息网（JDIH Kemenkeu）',
     'url':'https://jdih.kemenkeu.go.id/dok/pp-8-tahun-2025',
     'meta':{'document_no':'PP No. 8 Tahun 2025','issuer':'印尼政府','effective_from':'2025-03-01',
             'verification_note':'官方法规库标注2025-03-01起施行，为2023年第36号政府条例的最新修订。'}},
    {'file':'uu5-1999.htm','title':'印尼1999年第5号法律（禁止垄断行为和不正当商业竞争法）',
     'date':'1999-03-05','source':'印尼财政部法律文献信息网（JDIH Kemenkeu）',
     'url':'https://jdih.kemenkeu.go.id/dok/uu-5-tahun-1999',
     'meta':{'document_no':'UU No. 5 Tahun 1999','issuer':'印尼国会与总统','effective_from':'2000-03-05',
             'verification_note':'官方法规库收录原始文本；该法部分条款后经2023年第6号法律（创造就业法）修订，引用罚则条款前应核对修订文本。'}},
]


def text_of(path):
    if path.suffix=='.htm':
        raw=path.read_bytes().decode('cp1252','replace')
        raw=re.sub(r'(?is)<(script|style).*?</\1>',' ',raw)
        raw=re.sub(r'(?i)<br\s*/?>|</p>|</div>|</tr>','\n',raw)
        text=html.unescape(re.sub(r'<[^>]+>',' ',raw))
    else:
        import pypdf
        text='\n'.join((p.extract_text() or '') for p in pypdf.PdfReader(str(path)).pages)
    text=re.sub(r'[ \t\u00a0]+',' ',text)
    return re.sub(r'\n\s*\n+','\n\n',text).strip()


def parts_of(body,limit=55000):
    """Split at chapter (BAB) headings so each stored part stays within the import limit."""
    if len(body)<=limit:return [body]
    marks=[m.start() for m in re.finditer(r'(?m)^\s*BAB\s+[IVXLC]+\b',body)]
    parts,start=[],0
    for i,mark in enumerate(marks+[len(body)]):
        if mark-start>limit and i:
            cut=marks[i-1] if marks[i-1]>start else start+limit
            parts.append(body[start:cut]);start=cut
    parts.append(body[start:])
    final=[]
    for p in parts:
        while len(p)>limit:final.append(p[:limit]);p=p[limit:]
        final.append(p)
    return [p for p in final if p.strip()]


def import_laws(store):
    ids=[]
    for law in LAWS:
        body=text_of(LEGAL/law['file'])
        assert len(body)>5000,law['file']
        meta={**law['meta'],'category':'id_law','jurisdiction':'印度尼西亚','validity':'in_force',
              'verified_on':VERIFIED,'verification_urls':[law['url']],'corroboration':'single'}
        parts=parts_of(body)
        for index,part in enumerate(parts,1):
            title=law['title']+(f'（第{index}部分，共{len(parts)}部分）' if len(parts)>1 else '')
            doc_id,created=insert_document(store,{'title':title,'date':law['date'],'source':law['source'],'url':law['url'],
                'body':part,'legal_metadata':meta},'knowledge',allow_external=True,meta={'date_source':'provided'})
            ids.append({'id':doc_id,'created':created,'title':title,'characters':len(part)})
            print('law',doc_id,created,len(part),flush=True)
    return ids


async def reanalyse(store,settings,doc_ids):
    results=[]
    for doc_id in doc_ids:
        doc=store.one('SELECT * FROM documents WHERE id=?',(doc_id,))
        snap=companies.snapshot(store,doc['company_id'])
        tick=time.monotonic()
        for attempt in range(2):
            with store.db() as db:jid=store.enqueue_job(db,doc_id,snap)
            await asyncio.wait_for(Worker(store,settings).process(store.one('SELECT * FROM jobs WHERE id=?',(jid,))),timeout=420)
            job=store.one('SELECT status,error FROM jobs WHERE id=?',(jid,))
            if job['status']=='done' or 'HTTP 402' in (job.get('error') or ''):break
        analysis=store.one('SELECT id,decision FROM analyses WHERE job_id=?',(jid,))
        events=store.rows('SELECT id,title,category,level,actions_json,evidence_json FROM events WHERE analysis_id=?',(analysis['id'],)) if analysis else []
        row={'document_id':doc_id,'job_id':jid,**job,'seconds':round(time.monotonic()-tick,1),
             'analysis_id':analysis and analysis['id'],'decision':analysis and analysis['decision'],
             'events':[{'id':e['id'],'title':e['title'],'category':e['category'],'level':e['level'],
                        'actions':len(json.loads(e['actions_json'])),
                        'actions_with_basis':sum(1 for a in json.loads(e['actions_json']) if a.get('basis')),
                        'law_evidence':sum(1 for r in json.loads(e['evidence_json']) if r.get('kind')=='knowledge')} for e in events]}
        results.append(row)
        (WORK/'replay-progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'doc':doc_id,'status':job['status'],'decision':row['decision'],'s':row['seconds'],
                          'basis':[e['actions_with_basis'] for e in row['events']]},ensure_ascii=False),flush=True)
        if job['status']!='done' and 'HTTP 402' in (job.get('error') or ''):break
    return results


async def main():
    store=Store(WORK/'replica');companies.initialize(store)
    settings=replace(Settings(),data_dir=store.directory)
    rules=current_rules(store.setting('rules'));rules['confirmed']=True;store.set_setting('rules',rules)
    step=os.environ.get('RAG_STEP','all')
    if step in ('all','import'):
        laws=import_laws(store)
        while vectors.index_once(store):pass
        status=vectors.status(store)
        (WORK/'import.json').write_text(json.dumps({'laws':laws,'vector_status':status},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print('index',status,flush=True)
    if step in ('all','enrich'):
        # Chinese summaries and keywords let Chinese queries reach the Indonesian legal text.
        enricher=Enricher(store,settings)
        while await enricher.run_once():pass
        print('enriched',store.rows("SELECT id,zh_state,substr(zh_keywords,1,80) k FROM documents WHERE id>=109 AND kind='knowledge'"),flush=True)
    if step in ('all','replay'):
        plan=json.loads((ROOT/'qa/requirements-audit-20261112/date-plan.json').read_text())
        only=os.environ.get('RAG_DOCS')
        ids=[int(x) for x in only.split(',')] if only else [d for d,_ in plan]
        await reanalyse(store,settings,ids)


if __name__=='__main__':
    asyncio.run(main())
