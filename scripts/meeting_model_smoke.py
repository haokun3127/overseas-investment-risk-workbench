"""One existing reference, real model, isolated temporary database only."""
import asyncio
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
from dotenv import dotenv_values

os.environ.update({k:v for k,v in dotenv_values('/etc/rag-workbench/workbench.env').items() if v is not None})
from app.config import Settings
from app.main import create_app
from app.ingest import insert_document
from app.meeting import TARGET_LEVELS
from fastapi.testclient import TestClient
from docx import Document


def run():
    with sqlite3.connect('file:/var/lib/rag-workbench/risk.db?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        source=db.execute("SELECT id,title,body,date,source,url FROM documents WHERE kind='knowledge' AND quarantined_at IS NULL AND body LIKE '%TikTok%' AND (body LIKE '%15 miliar%' OR body LIKE '%15.000.000.000%') LIMIT 1").fetchone()
        assert source,'Existing reference unavailable'
        source=dict(source)
    with tempfile.TemporaryDirectory(prefix='rag-meeting-model-') as directory:
        app=create_app(replace(Settings(),data_dir=Path(directory),secure_cookie=False,cookie_path='/'),run_worker=False)
        store=app.state.store
        insert_document(store,{**source,'legal_metadata':{'category':'administrative','jurisdiction':'印度尼西亚'}},'knowledge')
        with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
            assert client.post('/api/auth/setup',json={'password':secrets.token_urlsafe(20)}).status_code==200
            response=client.post('/api/consultation',json={'question':'这份资料中TikTok因收购Tokopedia申报问题受到多少罚款？请保留原币种并说明依据。','mode':'answer'})
            assert response.status_code==200,response.text[:500]
            consultation=response.json();assert consultation['status']=='answered' and consultation['sources']
            tid=client.post('/api/drafting/templates',json={'name':'隔离验证事实整理函','category':'隔离验证','body':'事项事实整理\n依据提供的原文，将已发生事项及金额整理成简短函件。未知收件人、签署方与日期填写【待补充】，不补造法律意见。'}).json()['id']
            response=client.post('/api/drafting',json={'template_id':tid,'facts':source['body'][:10000]})
            assert response.status_code==200,response.text[:500]
            draft=response.json();assert draft['sources']
            word=client.get(f"/api/drafting/{draft['id']}/docx");assert word.status_code==200
            assert any('草稿' in p.text for p in Document(io.BytesIO(word.content)).paragraphs)
            rules=store.setting('rules');rules['confirmed']=True;store.set_setting('rules',rules)
            doc_id,_=insert_document(store,source,'event')
            with store.db() as db:job_id=store.enqueue_job(db,doc_id,'{}')
            job=store.one('SELECT * FROM jobs WHERE id=?',(job_id,))
            asyncio.run(app.state.worker.process(job))
            job=store.one('SELECT status,error FROM jobs WHERE id=?',(job_id,));assert job['status']=='completed',job
            analysis=store.one('SELECT decision,rules_json FROM analyses WHERE document_id=?',(doc_id,))
            assert set(json.loads(analysis['rules_json'])['levels'])==set(TARGET_LEVELS)
            events=store.rows('SELECT level,actions_json FROM events')
            assert analysis['decision']=='risk' and events and all(e['level'] in TARGET_LEVELS for e in events)
            assert any(json.loads(e['actions_json']) for e in events),'Real model omitted per-action recommendations'
        print(json.dumps({'source_document_id':source['id'],'consultation':consultation['status'],'draft':'verified_and_word_exported','analysis':analysis['decision'],'levels':[e['level'] for e in events],'action_count':sum(len(json.loads(e['actions_json'])) for e in events),'production_writes':False},ensure_ascii=False))


if __name__=='__main__':run()
