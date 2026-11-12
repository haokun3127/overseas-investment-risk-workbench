"""One real local draft using existing reference facts, followed by a real revision."""
import json
import secrets
import subprocess
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.presentation import clean_preparation_markers

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/drafting-workspace-20261112'
TEMPLATE='''风险事项说明
一 事件摘要
根据提供的事项经过填写发生时间、地点、主体和已经发生的事实，缺失信息保留待补充。
二 风险判断
依据提供的原文说明事实支持的风险和不确定性，不预设风险等级。
三 处理建议
写明可以采取的核实或处理措施及适用条件，法律依据不足时明确待核实。
四 依据与来源
列出本次引用的原文及来源，不编造法律或判决。'''


def run():
    code="""import json
from dotenv import dotenv_values
values=dotenv_values('/etc/rag-workbench/workbench.env')
print(json.dumps({k:v for k,v in values.items() if k.startswith('MODEL_')}))
"""
    config=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',
        'root@47.108.51.138','/opt/rag-workbench/venv/bin/python -'],
        input=code.encode(),capture_output=True,timeout=30)
    config.check_returncode();env=json.loads(config.stdout)
    case=json.loads((ROOT/'qa/local-replay-20261112/model-inputs.json').read_text(encoding='utf-8'))[0]
    facts=clean_preparation_markers(case['body'])
    with tempfile.TemporaryDirectory(prefix='rag-draft-real-') as directory:
        settings=Settings(data_dir=Path(directory),model_base_url=env['MODEL_BASE_URL'],
            model_name=env['MODEL_NAME'],model_api_key=env['MODEL_API_KEY'],
            model_wire_api=env.get('MODEL_WIRE_API','chat_completions'),
            model_reasoning_effort=env.get('MODEL_REASONING_EFFORT',''),
            model_proxy='http://127.0.0.1:7897',model_store=False,model_timeout=170,
            secure_cookie=False,cookie_path='/')
        app=create_app(settings,run_worker=False)
        with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
            assert client.post('/api/auth/setup',json={'password':secrets.token_urlsafe(24)}).status_code==200
            tid=client.post('/api/drafting/templates',json={'name':'风险事项说明','category':'事项说明','body':TEMPLATE}).json()['id']
            response=client.post('/api/drafting',json={'template_id':tid,'facts':facts,
                'instruction':'围绕2023年10月印尼电商交易暂停撰写完整的内部事项说明。区分后续2024年交易，不把后续事实放到2023年。未提供法律原文，不要编造法条。'})
            report={'http_status':response.status_code,'execution':'local_isolated_real_model',
                'server_model_execution':False,'production_writes':False,'reference_answers_in_prompt':False}
            QA.mkdir(parents=True,exist_ok=True)
            if response.status_code!=200:
                report['error']=response.json();(QA/'real-model.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                raise RuntimeError('Draft failed; see sanitized real-model.json')
            first=response.json();assert len(first['blocks'])==4 and first['sources']
            (QA/'real-draft.json').write_text(json.dumps(first,ensure_ascii=False,indent=2),encoding='utf-8')
            (QA/'real-draft.docx').write_bytes(client.get(f"/api/drafting/{first['id']}/docx").content)
            response=client.post('/api/drafting',json={'template_id':tid,'facts':facts,'previous_draft_id':first['id'],
                'instruction':'保留四个章节和已知事实，简化表达，处理建议只保留核实与跟进事项，不增设法定义务。'})
            report.update(sections=len(first['blocks']),characters=first['checks']['characters'],sources=len(first['sources']),
                          refinement_http_status=response.status_code)
            if response.status_code==200:
                second=response.json()
                assert second['id']!=first['id'] and second['context']['previous_draft_id']==first['id']
                assert client.get(f"/api/drafting/results/{first['id']}").json()['blocks']==first['blocks']
                (QA/'real-refined.json').write_text(json.dumps(second,ensure_ascii=False,indent=2),encoding='utf-8')
                report['passed']=True
            else:report.update(passed=False,refinement_error=response.json())
            (QA/'real-model.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in report.items() if 'error' not in k}))
            assert report['passed']


if __name__=='__main__':run()
