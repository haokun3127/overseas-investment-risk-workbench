"""Deterministic isolated UI fixture for draft editing; no model-generation claim."""
import json
import os
from pathlib import Path
from app.config import Settings
from app.main import create_app,password_hash
from app.ingest import insert_document
from app.store import now
from fastapi.testclient import TestClient
import secrets
import uvicorn

directory=Path(__file__).resolve().parents[1]/'qa/followup-20261111/ui-data'
assert not directory.exists(),'Use a fresh fixture directory'
app=create_app(Settings(data_dir=directory,model_base_url='',model_name='',model_api_key=''),run_worker=False)
store=app.state.store;salt=secrets.token_hex(16)
store.set_setting('admin',{'salt':salt,'hash':password_hash(os.environ['RAG_UI_PASSWORD'],salt)})
did,_=insert_document(store,{'title':'合同履行情况','body':'双方确认已经支付货款，设备尚未交付。','legal_metadata':{'category':'case'}},'knowledge')
with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
    assert client.post('/api/auth/login',json={'username':'admin','password':os.environ['RAG_UI_PASSWORD']}).status_code==200
    cid=client.post('/api/companies',json={'name':'界面验证企业','industry':'设备制造'}).json()['id']
    assert client.post('/api/events',json={'company_id':cid,'revision':0,'title':'合同履行风险','category':'合同执行风险','level':'lv3','summary':'买方已经付款，设备尚未交付。','impact':'生产安排可能受影响。','recommendation':'核对合同条款与履行情况。','reason':'隔离界面测试'}).status_code==200
    tid=client.post('/api/drafting/templates',json={'name':'事项说明','category':'事项说明','body':'事项说明\n依据已提供事实整理经过，缺少的信息明确标注待补充。'}).json()['id']
    client.delete('/api/companies/active')
template=store.one('SELECT * FROM drafting_templates WHERE id=?',(tid,))
result={'status':'answered','blocks':[{'heading':'事项经过','text':'双方已经支付货款，设备尚未交付。','citations':[1]}],
        'sources':[{'number':1,'document_id':did,'title':'合同履行情况','quote':'双方确认已经支付货款，设备尚未交付。','url':''}]}
with store.db() as db:
    db.execute('INSERT INTO drafting_results(template_id,template_json,facts,result_json,created_at) VALUES (?,?,?,?,?)',
               (tid,json.dumps(template,ensure_ascii=False),'双方已经支付货款，设备尚未交付。',json.dumps(result,ensure_ascii=False),now()))
uvicorn.run(app,host='127.0.0.1',port=8899,log_level='warning')
