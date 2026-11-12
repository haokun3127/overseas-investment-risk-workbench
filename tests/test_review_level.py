import json
from test_tenant_authz import app, admin, companies
from test_meeting import data


def test_review_adjusts_level_atomically_with_history_and_scope(app, admin, companies):
    company, outsider = companies
    eid = admin.post('/api/events', json=data(company.company_id)).json()['id']
    url = f'/api/events/{eid}/review'
    original = admin.get(f'/api/events/{eid}').json()['result']
    change = {'status': 'accepted', 'level': 'lv1', 'revision': 0, 'note': '已核对原文，重大影响'}
    assert outsider.put(url, json=change).status_code == 403
    assert admin.put(url, json={**change, 'level': 'lv5'}).status_code == 400
    assert admin.put(url, json={**change, 'note': ''}).status_code == 400
    assert admin.put(url, json={k:v for k,v in change.items() if k!='revision'}).status_code == 400
    saved = admin.put(url, json=change)
    assert saved.status_code == 200
    assert saved.json()['level'] == 'lv1' and saved.json()['revision'] == 1
    assert admin.put(url, json=change).status_code == 409
    detail = admin.get(f'/api/events/{eid}').json()
    assert detail['result'] == original
    history = app.state.store.one("SELECT * FROM event_changes WHERE event_id=? AND action='review_level'", (eid,))
    assert json.loads(history['before_json'])['level'] == 'lv2'
    assert json.loads(history['after_json'])['level'] == 'lv1'
    assert history['reason'] == change['note']
    assert admin.put(url, json={**change, 'revision': 1, 'level': 'non_risk', 'note': '已核实不构成风险'}).status_code == 200
    assert admin.get('/api/overview').json()['total'] == 0
    assert admin.get('/api/events').json()['total'] == 0
    assert admin.get(f'/api/events/{eid}').json()['level'] == 'non_risk'
    # Status-only clients remain compatible and must preserve the adjusted grade.
    assert admin.put(url, json={'status': 'needs_change', 'note': '继续核实'}).status_code == 200
    assert admin.get(f'/api/events/{eid}').json()['level'] == 'non_risk'
