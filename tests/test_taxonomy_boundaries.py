import asyncio
import copy

import pytest

from app import model
from app.store import DEFAULT_RULES
from app.jobs import Worker
from app import jobs
from test_workbench import client, add, valid_result


def references():
    return {'S1': {'text': '这是用于测试的风险证据原文。', 'kind': 'source',
                   'document_id': 1, 'locator': '正文', 'title': '合成资料'}}


def test_risk_can_be_explicitly_unmapped_without_changing_taxonomy():
    rules = copy.deepcopy(DEFAULT_RULES)
    value = valid_result()
    value['events'][0]['category'] = model.UNMAPPED_CATEGORY
    value['events'][0]['summary'] = '存在直接风险事实，但现有三级定义没有覆盖，待人工归类。'
    result = model.validate_result(value, references(), rules)
    assert result['decision'] == 'risk'
    assert result['events'][0]['category'] == '对不上'
    assert rules == DEFAULT_RULES


def test_unmapped_is_not_permission_to_invent_labels_or_skip_citations():
    value = valid_result()
    value['events'][0]['category'] = '任意新增类别'
    with pytest.raises(ValueError, match='规则之外'):
        model.validate_result(value, references(), DEFAULT_RULES)
    value['events'][0]['category'] = model.UNMAPPED_CATEGORY
    value['events'][0]['evidence'] = []
    with pytest.raises(ValueError, match='可验证的引用'):
        model.validate_result(value, references(), DEFAULT_RULES)


def test_vector_focus_never_removes_other_valid_indicators():
    rules=copy.deepcopy(DEFAULT_RULES)
    chosen=['劳工组织维权风险','环境行政审查风险','法律政策变动']
    narrowed=Worker(None,None)._narrow_rules(rules,chosen)
    assert narrowed['categories']==rules['categories']
    assert narrowed['focus_categories']==chosen
    assert '汇兑限制' in narrowed['categories'] and '汇兑限制' not in chosen
    assert rules==DEFAULT_RULES


def test_vector_group_preparation_retains_all_allowed_categories(monkeypatch):
    chosen=['劳工组织维权风险','环境行政审查风险','法律政策变动']
    chunk={'id':8,'text':'工人抗议和环境监管属于不同事实。','locator':'正文'}
    plan={'categories':chosen,'sources':[chunk],'category_chunks':{c:[8] for c in chosen},
          'top_similarity':0.6,'floor':0.3,'model':'synthetic-embedding'}
    monkeypatch.setattr(jobs,'plan_sources',lambda *a,**k:plan)
    queries=[]
    def fake_retrieve(store,query,**kwargs):
        queries.append(query)
        return []
    monkeypatch.setattr(jobs,'retrieve',fake_retrieve)
    prepared=Worker(None,None)._prepare_grouped({'id':4,'title':'合成资料','date':'','source':'合成'},
        [chunk],copy.deepcopy(DEFAULT_RULES),{'industry':'合成行业','location':'印尼'},[],True,1)
    payload,refs,knowledge,coverage=prepared
    assert payload['rules']['categories']==DEFAULT_RULES['categories']
    assert coverage['categories']==chosen
    assert coverage['category_chunks']=={c:[8] for c in chosen}
    assert coverage['allowed_category_count']==len(DEFAULT_RULES['categories'])
    assert queries[0].startswith(' '.join(chosen))
    assert refs['S8']['document_id']==4


def test_distinct_indicators_survive_same_title_and_quote(client, monkeypatch):
    app = client.app
    app.state.settings.model_base_url = 'https://example.test/v1'
    app.state.settings.model_name = 'synthetic-only'
    app.state.settings.model_api_key = 'not-a-real-key'
    rules = copy.deepcopy(DEFAULT_RULES)
    rules['confirmed'] = True
    app.state.store.set_setting('rules', rules)
    doc = add(client, allow_external=True, body='工人就劳动条件提出集体抗议；监管机关另要求对废水处理落实整改。')

    async def fake(settings, payload):
        ref = next(r for r in payload['references'] if r['kind'] == 'source')
        def event(category):
            return {'title': '同一合成企业的两项独立事项', 'category': category, 'level': 'lv3',
                    'summary': '合成测试摘要', 'impact': '影响待核实', 'recommendation': '人工核实',
                    'evidence': [{'reference': ref['reference'], 'quote': ref['text'], 'reason': '直接事实'}]}
        labor = event('劳工组织维权风险')
        environment = event('环境行政审查风险')
        return {'decision': 'risk', 'reason': '独立事实分别归类',
                'events': [labor, environment, copy.deepcopy(labor)]}, {}

    monkeypatch.setattr(model, 'call_model', fake)
    response = client.post('/api/jobs', json={'document_ids': [doc]})
    assert response.status_code == 200, response.text
    job_id = response.json()['items'][0]['id']
    job = app.state.store.one('SELECT * FROM jobs WHERE id=?', (job_id,))
    asyncio.run(app.state.worker.process(job))
    assert app.state.store.one('SELECT status FROM jobs WHERE id=?', (job_id,))['status'] == 'completed'
    rows = app.state.store.rows('SELECT category FROM events')
    assert sorted(r['category'] for r in rows) == ['劳工组织维权风险', '环境行政审查风险']
