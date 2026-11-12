"""One real consultation, locally isolated, secrets stay in process memory."""
import json
import secrets
import subprocess
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ingest import insert_document

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT/'qa/requirements-completion-20261112'


def run():
    code = """import json
from dotenv import dotenv_values
values=dotenv_values('/etc/rag-workbench/workbench.env')
print(json.dumps({k:v for k,v in values.items() if k.startswith('MODEL_')}))
"""
    config = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',
        'root@47.108.51.138','/opt/rag-workbench/venv/bin/python -'],
        input=code.encode(), capture_output=True, timeout=30)
    config.check_returncode()
    env = json.loads(config.stdout)
    snapshot = json.loads((ROOT/'qa/presentation-audit-20261112/business-snapshot.json').read_text(encoding='utf-8'))
    source = next(d for d in snapshot['documents'] if d['kind']=='knowledge' and
        'TikTok' in d['body'] and ('15 miliar' in d['body'] or '15.000.000.000' in d['body']))
    with tempfile.TemporaryDirectory(prefix='rag-requirements-model-') as directory:
        settings = Settings(data_dir=Path(directory), model_base_url=env['MODEL_BASE_URL'],
            model_name=env['MODEL_NAME'],model_api_key=env['MODEL_API_KEY'],
            model_wire_api=env.get('MODEL_WIRE_API','chat_completions'),
            model_reasoning_effort=env.get('MODEL_REASONING_EFFORT',''),
            model_proxy='http://127.0.0.1:7897',model_store=False,
            secure_cookie=False,cookie_path='/')
        app=create_app(settings,run_worker=False)
        insert_document(app.state.store,{**source,'legal_metadata':{'category':'administrative','jurisdiction':'印度尼西亚'}},'knowledge')
        with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
            assert client.post('/api/auth/setup',json={'password':secrets.token_urlsafe(20)}).status_code==200
            r=client.post('/api/consultation',json={'question':
                '资料中TikTok因收购Tokopedia申报问题的罚款是多少？仅依据原文，并说明这些资料是否足以确认该案具体付款截止日期。'})
            result={'http_status':r.status_code,'source_document_id':source['id'],
                    'execution':'local_isolated_real_model','production_writes':False,
                    'embedding_or_batch_jobs':False}
            if r.status_code==200:
                answer=r.json()
                assert answer['status'] in ('answered','insufficient')
                if answer['status']=='answered':assert answer['sources']
                else:assert answer.get('explanation',{}).get('needed')
                result.update(passed=True,answer=answer)
            else:
                result.update(passed=False,error=r.json().get('detail','调用失败'))
            (QA/'real-model-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in result.items() if k not in ('answer','error')}))
            if not result['passed']:raise RuntimeError('Real model smoke failed; see sanitized QA result.')


if __name__=='__main__':
    run()
