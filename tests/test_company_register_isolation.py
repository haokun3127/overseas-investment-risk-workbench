import asyncio
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

HEADERS = {"X-Requested-With": "risk-workbench"}

def test_company_registration_and_strict_tenant_isolation(tmp_path, monkeypatch):
    import json
    from app.store import now
    app=create_app(Settings(data_dir=tmp_path),run_worker=False)
    with TestClient(app,headers=HEADERS) as admin, TestClient(app,headers=HEADERS) as a, TestClient(app,headers=HEADERS) as b:
        assert admin.post('/api/auth/setup',json={'password':'test-password-12345'}).status_code==200
        ids=[]
        for index,c in enumerate((a,b)):
            c.cookies.update(admin.cookies)
            ids.append(c.post('/api/auth/register',json={'username':f'company_{index}','password':f'pass-{index}-123456','name':f'企业{index}'}).json()['company_id'])
        event_ids=[]
        for cid in ids:
            assert admin.post(f'/api/companies/{cid}/activate').status_code==200
            created=admin.post('/api/events',json={'company_id':cid,'revision':0,'title':'已核实风险','category':'其他','level':'lv2','summary':'企业合同被终止，项目停产。','reason':'录入核实事实'})
            assert created.status_code==200,created.text
            event_ids.append(created.json()['id'])
        for c,cid,eid,foreign in ((a,ids[0],event_ids[0],event_ids[1]),(b,ids[1],event_ids[1],event_ids[0])):
            assert c.get('/api/events').json()['total']==1
            assert c.get('/api/overview').json()['total']==1
            assert c.get(f'/api/events/{eid}').status_code==200
            assert c.get(f'/api/events/{foreign}').status_code==404
            assert [row['id'] for row in c.get('/api/companies').json()['items']]==[cid]
            assert c.post('/api/documents',json={'title':'无权上传','body':'任何资料'}).status_code==403
            assert c.get('/api/documents?kind=knowledge').status_code==403
            assert c.put(f'/api/companies/{cid}',json={'name':'修改'}).status_code==403
            assert c.put(f'/api/events/{eid}/review',json={'status':'accepted','note':'x'}).status_code==403
        assert admin.delete('/api/companies/active').status_code==200
        assert admin.get('/api/events').json()['total']==2
        assert admin.post(f'/api/companies/{ids[0]}/activate').status_code==200
        assert admin.get('/api/events').json()['total']==1

