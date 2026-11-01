import asyncio
import copy
import pytest
from app import model
from app.config import Settings
from app.store import DEFAULT_RULES
from test_workbench import valid_result

REFS={'S1':{'kind':'source','document_id':1,'locator':'正文','title':'合成事实','text':'这是用于测试的风险证据原文。'}}


def test_citation_only_repair_preserves_event_judgment(monkeypatch,tmp_path):
    initial=valid_result('被模型误改写的引用，不是给定原文。')
    original=copy.deepcopy(initial)
    calls=[]
    async def fake(settings,payload,system=model.SYSTEM):
        calls.append(payload)
        if len(calls)==1:
            return initial,{'total_tokens':10}
        assert 'expected' not in payload
        assert payload['citation_units'][0]['text']==REFS['S1']['text']
        return {'citations':[{'event_index':0,'items':[{'unit_id':'S1:1','reason':'支持同一事实'}]}]}, {'total_tokens':5}
    monkeypatch.setattr(model,'call_model',fake)
    result,usage=asyncio.run(model.call_validated(Settings(data_dir=tmp_path),{},REFS,DEFAULT_RULES))
    assert len(calls)==2 and usage['total_tokens']==15
    assert result['decision']==original['decision']
    for key in ['category','level','title','summary','impact','recommendation']:
        assert result['events'][0][key]==original['events'][0][key]
    assert result['events'][0]['evidence'][0]['quote']==REFS['S1']['text']
    assert usage['citation_repair']['applied'] is True
    assert initial==original


def test_citation_repair_cannot_bypass_exact_quote_check(monkeypatch,tmp_path):
    calls=[]
    async def fake(settings,payload,system=model.SYSTEM):
        calls.append(payload)
        if len(calls)==1:return valid_result('没有出现在来源中的伪造原文。'),{}
        return {'citations':[{'event_index':0,'items':[{'unit_id':'S1:999','reason':'声称支持'}]}]},{}
    monkeypatch.setattr(model,'call_model',fake)
    with pytest.raises(ValueError,match='原文匹配'):
        asyncio.run(model.call_validated(Settings(data_dir=tmp_path),{},REFS,DEFAULT_RULES))
    assert len(calls)==2


def test_citation_correction_cannot_smuggle_a_grade_change(monkeypatch,tmp_path):
    calls=[]
    async def fake(settings,payload,system=model.SYSTEM):
        calls.append(payload)
        if len(calls)==1:return valid_result('无效原文引用内容。'),{}
        return {'citations':[{'event_index':0,'items':[{'unit_id':'S1:1','reason':'事实'}]}],
                'level':'lv5'},{}
    monkeypatch.setattr(model,'call_model',fake)
    with pytest.raises(ValueError,match='原文匹配'):
        asyncio.run(model.call_validated(Settings(data_dir=tmp_path),{},REFS,DEFAULT_RULES))


def test_canonical_units_preserve_exact_foreign_and_long_source_text():
    text='This is an exact quotation.\n第二段保持原样！'+('长句完整原文'*200)
    units=model.citation_units({'S1':{**REFS['S1'],'text':text}})
    assert len(units)>3
    assert all(6<=len(unit['text'])<=800 and unit['text'] in text for unit in units.values())
    assert all(unit['reference']=='S1' and unit['kind']=='source' for unit in units.values())
