"""Local synthetic UI fixture; no external model, vector index or production writes."""
import json
import tempfile
from pathlib import Path
import uvicorn
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app import drafting

directory=Path(tempfile.mkdtemp(prefix='rag-drafting-ui-'))
app=create_app(Settings(data_dir=directory,model_mode='external',model_base_url='https://example.com/v1',
    model_name='test',model_api_key='test',secure_cookie=False,cookie_path='/'),run_worker=False)
with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
    client.post('/api/auth/setup',json={'password':'local-ui-test-only'})
    client.post('/api/drafting/templates',json={'name':'设备交付履行函','category':'商务函件',
        'body':'设备交付履行函\n收件人：{{收件人}}\n一、事项事实\n说明已付款和未交付的事实。\n二、履行请求\n按合同约定履行，日期【待补充：日期】。\n三、联系与落款\n保留联系人和日期。'})


async def fake(settings,payload,system):
    unit=next(u for u in payload['quote_units'] if u['ref']=='F1')
    return {'status':'answered','blocks':[{'heading':h,'kind':'fact',
        'text':['甲公司已按合同支付货款。设备尚未交付，双方正在核对交付安排。\n本次函件根据已提供的材料起草，具体交付条件以双方签署合同为准。',
                '请核对原合同约定的交付条件，并就尚未完成的事项协商确定后续履行安排。\n合同约定的交付日期：【待补充：日期】。',
                '联系人：【待补充：联系人】\n签署日期：【待补充：签署日期】'][i],
        'citations':[{'ref':'F1','unit_id':unit['unit_id']}]} for i,h in enumerate(payload['required_headings'])],
        'missing_fields':['日期','联系人','签署日期'],'warnings':['尚未提供完整签署合同，需核对交付条款。']},{}


drafting.model.call_model=fake
print(json.dumps({'directory':str(directory),'external_calls':False}),flush=True)
uvicorn.run(app,host='127.0.0.1',port=8898,log_level='warning')
