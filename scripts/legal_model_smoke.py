"""Real model smoke test against an isolated copy of one existing reference, never production writes."""
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
from dataclasses import replace

from dotenv import dotenv_values
os.environ.update({k:v for k,v in dotenv_values('/etc/rag-workbench/workbench.env').items() if v is not None})

from app.config import Settings
from app.main import create_app
from app.ingest import insert_document
from fastapi.testclient import TestClient
from docx import Document

def run():
    with sqlite3.connect('file:/var/lib/rag-workbench/risk.db?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=[dict(row) for row in db.execute("SELECT id,title,body,date,source,url FROM documents WHERE kind='knowledge' AND quarantined_at IS NULL AND (body LIKE '%TikTok%' OR body LIKE '%TikTok%') AND (body LIKE '%15 miliar%' OR body LIKE '%15.000.000.000%') LIMIT 1")]
    assert rows, 'No matching existing fine reference'
    with tempfile.TemporaryDirectory(prefix='rag-legal-smoke-') as directory:
        app=create_app(replace(Settings(),data_dir=Path(directory),secure_cookie=False,cookie_path='/'),run_worker=False)
        material=rows[0]
        insert_document(app.state.store,{**material,'legal_metadata':{'category':'administrative','jurisdiction':'印度尼西亚'}},'knowledge')
        with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
            client.post('/api/auth/setup',json={'password':secrets.token_urlsafe(20)})
            reports=[]
            for mode in ('answer','report'):
                response=client.post('/api/consultation',json={'question':'这份资料中TikTok因收购Tokopedia申报问题受到多少罚款？请保留原币种并说明依据。','mode':mode})
                assert response.status_code==200, (mode,response.status_code,response.text[:300])
                answer=response.json()
                assert answer['status']=='answered' and answer['sources'], (mode,answer)
                if mode=='report':
                    assert '法律依据' in answer['missing_sections'] and '类似案例分析' in answer['missing_sections']
                    word=client.get(f"/api/consultation/reports/{answer['report_id']}/docx")
                    assert word.status_code==200
                    paragraphs=[p.text for p in Document(io.BytesIO(word.content)).paragraphs]
                    assert '法律咨询报告' in paragraphs and any('引用原文' in p for p in paragraphs)
                reports.append({'mode':mode,'status':answer['status'],'blocks':answer['blocks'],'sources':answer['sources'],'missing_sections':answer.get('missing_sections',[])})
        print(json.dumps({'source_document_id':material['id'],'results':reports,'production_writes':False},ensure_ascii=False))

if __name__=='__main__': run()
