import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import countermeasures
from app.store import DEFAULT_RULES, now
from test_workbench import client, add
from test_tenant_authz import app, admin, companies, add_event


def write_bank(directory):
    folder=directory/'reference-data'/'grading-1027'
    folder.mkdir(parents=True)
    raw=b'Synthetic document for reference API tests only'
    data={'schema_version':1,'source':{'title':'合成分级规则','version':'2026-10-27',
        'section':'合成第二表','sha256':hashlib.sha256(raw).hexdigest()},'levels':{}}
    for i,level in enumerate(countermeasures.LEVEL_ORDER,1):
        data['levels'][level]={'level':level,'label':f'合成等级{i}','threshold':'合成区间',
            'standard':f'合成等级{i}的标准','standard_locator':f'合成表第{i}行',
            'enterprise':[{'id':f'enterprise-r{i}','text':f'企业合成对策{i}','locator':f'表2第{i}行第5列'}],
            'state':[{'id':f'state-r{i}','text':f'国家合成对策{i}','locator':f'表2第{i}行第6列'}]}
    (folder/'bank.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    (folder/'source.doc').write_bytes(raw)
    return folder,data,raw


def make_event(c,level,category='对不上'):
    store=c.app.state.store
    number=store.one('SELECT COUNT(*) n FROM events')['n']
    doc=add_event(c,title=f'合成风险资料 {number}',body=f'合成事项{number}，用于独立事件和分级对策的接口核查。')
    with store.db() as db:
        analysis=db.execute('''INSERT INTO analyses(document_id,version,decision,model,mode,rules_json,
            knowledge_json,result_json,created_at,duration_ms,usage_json) VALUES (?,1,'risk','synthetic','external',?,'{}','{}',?,1,'{}')''',
            (doc,json.dumps(DEFAULT_RULES,ensure_ascii=False),now())).lastrowid
        event=db.execute('''INSERT INTO events(analysis_id,title,category,level,summary,impact,recommendation,evidence_json)
            VALUES (?,'合成风险',?,?,'合成摘要','合成影响','独立的模型建议','[]')''',(analysis,category,level)).lastrowid
    return event


def test_library_and_original_document_require_login(client):
    write_bank(client.app.state.store.directory)
    assert client.get('/api/countermeasures').status_code==410
    assert client.get('/api/countermeasures/source').status_code==410
    assert countermeasures.load_library(client.app.state.store.directory)['status']=='available'
    with TestClient(client.app) as anonymous:
        assert anonymous.get('/api/countermeasures').status_code==401
        assert anonymous.get('/api/countermeasures/source').status_code==401


def test_unmapped_risk_uses_grade_without_changing_model_output(client):
    write_bank(client.app.state.store.directory)
    event_id=make_event(client,'lv3')
    store=client.app.state.store
    before=store.one('SELECT * FROM events WHERE id=?',(event_id,))
    event=client.get(f'/api/events/{event_id}').json()
    assert event['category']=='其他' and event['level']=='lv3'
    assert event['recommendation']=='独立的模型建议'
    assert 'countermeasures' not in event
    reference=countermeasures.for_level(countermeasures.load_library(store.directory),event['level'])
    assert reference['status']=='available' and reference['level']=='lv3'
    assert reference['enterprise'][0]['text']=='企业合成对策3'
    assert reference['state'][0]['text']=='国家合成对策3'
    assert store.one('SELECT * FROM events WHERE id=?',(event_id,))==before
    assert store.one('SELECT COUNT(*) n FROM jobs')['n']==0


def test_report_aggregates_filtered_grades_once_and_does_not_map_legacy(client):
    write_bank(client.app.state.store.directory)
    for grade in ('lv3','lv3','lv1','red'):make_event(client,grade)
    report=client.get('/api/report').json()
    assert [entry['level'] for entry in report['countermeasures']['groups']]==['lv1','lv3']
    assert report['countermeasures']['unsupported_levels']==['red']
    narrowed=client.get('/api/report?level=lv3').json()
    assert narrowed['total']==2
    assert [entry['level'] for entry in narrowed['countermeasures']['groups']]==['lv3']
    legacy=client.get('/api/report?level=red').json()
    assert legacy['countermeasures']['groups']==[]


def test_missing_or_tampered_source_does_not_break_existing_event(client):
    event=make_event(client,'lv2')
    assert 'countermeasures' not in client.get(f'/api/events/{event}').json()
    assert client.get('/api/countermeasures/source').status_code==410
    folder,data,raw=write_bank(client.app.state.store.directory)
    (folder/'source.doc').write_bytes(b'Tampered reference')
    assert countermeasures.load_library(client.app.state.store.directory)['status']=='unavailable'
    assert client.get('/api/countermeasures/source').status_code==410
    result=client.get(f'/api/events/{event}')
    assert result.status_code==200 and result.json()['recommendation']=='独立的模型建议'


def test_malformed_roles_and_untrusted_extra_fields(client):
    folder,data,raw=write_bank(client.app.state.store.directory)
    data['source']['server_path']='private configuration location'
    data['levels']['lv1']['status']='fabricated'
    (folder/'bank.json').write_text(json.dumps(data),encoding='utf-8')
    loaded=countermeasures.load_library(client.app.state.store.directory)
    assert loaded['status']=='available'
    assert 'server_path' not in loaded['source'] and 'status' not in loaded['levels'][0]
    data['levels']['lv1']['state']=[]
    (folder/'bank.json').write_text(json.dumps(data),encoding='utf-8')
    assert countermeasures.load_library(client.app.state.store.directory)['status']=='unavailable'


def test_common_reference_does_not_unlock_another_company_event(app,admin,companies):
    first,second=companies
    write_bank(app.state.store.directory)
    event=make_event(first,'lv2')
    assert 'countermeasures' not in first.get(f'/api/events/{event}').json()
    assert second.get(f'/api/events/{event}').status_code==404
    assert second.get('/api/report').status_code==403
    assert second.get('/api/countermeasures').status_code==403


def test_source_symlink_cannot_leave_data_directory(client,tmp_path_factory):
    folder,data,raw=write_bank(client.app.state.store.directory)
    outside=tmp_path_factory.mktemp('outside-reference')/'source.doc'
    outside.write_bytes(raw)
    (folder/'source.doc').unlink()
    try:
        (folder/'source.doc').symlink_to(outside)
    except OSError:
        pytest.skip('This Windows user cannot create symlinks')
    assert countermeasures.load_library(client.app.state.store.directory)['status']=='unavailable'
    assert client.get('/api/countermeasures/source').status_code==410


def test_reference_script_loads_before_application_boot():
    html=(Path(__file__).resolve().parents[1]/'web/index.html').read_text(encoding='utf-8')
    assert html.index('static/countermeasures.js')<html.index('static/app.js')
