"""Small recovery check: no embeddings, business writes or case replay."""
import datetime
import json
import os
from pathlib import Path
import sqlite3
import httpx
from dotenv import dotenv_values

os.environ.update({k:v for k,v in dotenv_values('/etc/rag-workbench/workbench.env').items() if v is not None})
result={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'production_writes':False,'embedding_loaded':False}
root=Path(os.getenv('DATA_DIR','/var/lib/rag-workbench'))
with sqlite3.connect(root.joinpath('risk.db').as_uri()+'?mode=ro',uri=True) as db:
    result['database_quick_check']=db.execute('PRAGMA quick_check').fetchone()[0]
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result['counts']={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0]
                      for t in ('companies','documents','chunks','analyses','events','jobs') if t in tables}
base=os.getenv('MODEL_BASE_URL','').rstrip('/')
model=os.getenv('MODEL_NAME','')
if 'api.deepseek.com' in base and model.lower() in ('v4.1-flash-1017','deepseek-v4.1-flash','deepseek-v4.1-flash-1017'):
    model='deepseek-flash'
responses=os.getenv('MODEL_WIRE_API','chat_completions')=='responses'
messages=[{'role':'system','content':'Return only this JSON object: {"ok":true}.'},
          {'role':'user','content':'Connectivity check. Return JSON.'}]
payload={'model':model,'store':False}
if responses:
    payload.update(input=messages,max_output_tokens=128)
else:
    payload.update(messages=messages,max_tokens=64)
try:
    with httpx.Client(timeout=20,trust_env=False,follow_redirects=False,
                      proxy=os.getenv('MODEL_PROXY') or None) as client:
        response=client.post(base+('/responses' if responses else '/chat/completions'),json=payload,
                             headers={'Authorization':'Bearer '+os.getenv('MODEL_API_KEY','')})
    result['model_probe']={'http_status':response.status_code,'full_analysis_test':False}
except Exception as error:
    result['model_probe']={'error_type':type(error).__name__,'full_analysis_test':False}
print(json.dumps(result,ensure_ascii=False),flush=True)
