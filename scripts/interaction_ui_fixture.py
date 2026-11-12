"""Isolated representative data; no model execution or vector loading."""
import json
import tempfile
from pathlib import Path
import uvicorn
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

directory = Path(tempfile.mkdtemp(prefix='rag-interaction-ui-'))
app = create_app(Settings(data_dir=directory, model_mode='external',
    model_base_url='https://example.com/v1', model_name='test',model_api_key='test',
    secure_cookie=False,cookie_path='/'), run_worker=False)
with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
    client.post('/api/auth/setup',json={'password':'local-ui-test-only'})
    company=client.post('/api/companies',json={'name':'设备制造企业','industry':'设备制造'}).json()['id']
    client.delete('/api/companies/active')
    for i,category in enumerate(['法律政策变动','劳工组织维权风险','环境行政审查风险','汇兑限制','其他','其他','其他','其他']):
        response=client.post('/api/events',json={'company_id':company,'revision':0,
            'title':f'{category}事项核查{i+1}','category':category,'level':['lv1','lv2','lv3'][i%3],
            'summary':'企业设备尚未交付，应当核对约定履行期限与现有付款记录。',
            'impact':'可能影响生产安排，具体影响需进一步核实。',
            'recommendation':'查阅签署合同、核对履行条件，并保留沟通记录。',
            'reason':'隔离界面验证'})
        assert response.status_code==200,response.text
    response=client.post('/api/drafting/templates',json={'name':'设备交付履行函','category':'商务函件',
        'body':'设备交付履行函\n收件人：{{收件人}}\n一、事项事实\n说明已付款和未交付的事实。\n二、履行请求\n按合同约定履行，日期【待补充：日期】。\n三、联系与落款\n保留联系人和日期。'})
    assert response.status_code==200,response.text
print(json.dumps({'directory':str(directory),'external_calls':False}),flush=True)
uvicorn.run(app,host='127.0.0.1',port=8898,log_level='warning')
