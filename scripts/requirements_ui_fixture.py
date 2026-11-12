"""Local isolated flow checks. Synthetic model replies, no external calls or vectors."""
import json
import secrets
import tempfile
from pathlib import Path
import uvicorn
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ingest import insert_document
from app.store import now
from app import consultation

directory = Path(tempfile.mkdtemp(prefix='rag-requirements-ui-'))
app = create_app(Settings(data_dir=directory, model_base_url='https://example.com/v1',
    model_name='isolated-test', model_api_key='isolated-test'), run_worker=False)
store = app.state.store
rules = store.setting('rules'); rules['confirmed'] = True; store.set_setting('rules', rules)
with TestClient(app, headers={'X-Requested-With': 'risk-workbench'}) as client:
    client.post('/api/auth/setup', json={'password': 'local-ui-test-only'})
    company = client.post('/api/companies', json={'name': '界面验证企业', 'industry': '设备制造'}).json()['id']
    client.post('/api/auth/register', json={'username': 'company_ui', 'password': 'local-ui-test-only',
        'name': '隔离企业账号'})
    account_company = client.get('/api/auth/status').json()['company_id']
    client.post('/api/auth/login', json={'username': 'admin', 'password': 'local-ui-test-only'})
    client.delete('/api/companies/active')
    event = client.post('/api/events', json={'company_id': account_company, 'revision': 0,
        'title': '合同履行风险', 'category': '其他', 'level': 'lv2', 'summary': '合同设备尚未交付。',
        'impact': '生产可能受到影响。', 'recommendation': '核实合同并协商履行。',
        'reason': '本地隔离验证'}).json()['id']
    client.put(f'/api/events/{event}/review', json={'status': 'accepted', 'note': '已核对合同原文。'})
law, _ = insert_document(store, {'title': '合同履行法律依据', 'body': '当事人应当依照合同约定履行义务。',
    'date': '2025-01-02', 'source': '发布机关', 'legal_metadata': {
        'category': 'id_law', 'validity': 'in_force', 'verified_on': '2026-11-01',
        'verification_note': '隔离流程验证', 'verification_urls': ['https://example.com/law']}}, 'knowledge')
did, _ = insert_document(store, {'title': '待补充合同', 'body': '已收到合同但缺少签署日期和争议解决条款。'}, company_id=account_company)
with store.db() as db:
    db.execute('''INSERT INTO analyses(document_id,version,decision,model,mode,rules_json,knowledge_json,
        result_json,created_at,duration_ms,usage_json) VALUES (?,1,'insufficient','test','external',
        '{}','[]',?,?,0,'{}')''', (did, json.dumps({'reason':
        '已取得付款事实；缺少签署日期和争议解决条款，暂不能判断适用版本，请补充签字合同。'}), now()))
async def local_model(settings, payload, **kwargs):
    unit = payload['quote_units'][0]
    return {'status': 'insufficient', 'gaps': {'missing_facts': ['缺少签署日期。'],
        'affected': ['不能判断适用版本。'], 'needed': ['请补充签字合同。']},
        'blocks': [{'text': '当事人应依照合同约定履行义务。',
            'citations': [{'ref': unit['ref'], 'unit_id': unit['unit_id']}]}]}, {}
consultation.model.call_model = local_model
print(json.dumps({'directory': str(directory), 'company_id': account_company, 'event_id': event, 'law_id': law}), flush=True)
uvicorn.run(app, host='127.0.0.1', port=8898, log_level='warning')
