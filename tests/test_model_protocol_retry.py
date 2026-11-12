import asyncio
from dataclasses import replace
import httpx
import pytest
from app import model
from app.config import Settings

def client(monkeypatch,replies):
    original=httpx.AsyncClient;seen=[]
    def handle(request):
        seen.append(request)
        return httpx.Response(200,json=replies[min(len(seen)-1,len(replies)-1)])
    monkeypatch.setattr(model.httpx,'AsyncClient',lambda **kw:original(**kw,transport=httpx.MockTransport(handle)))
    async def sleep(_):pass
    monkeypatch.setattr(model.asyncio,'sleep',sleep)
    return seen

def settings():
    return replace(Settings(),model_base_url='https://example.com/v1',model_name='test',model_mode='external',
                   model_wire_api='chat_completions',model_proxy='',model_api_key='test')

def test_invalid_json_recovers_with_bounded_retry(monkeypatch):
    seen=client(monkeypatch,[{'choices':[{'message':{'content':'{broken'}}]},
                             {'choices':[{'message':{'content':'{"decision":"non_risk"}'}}]}])
    result,_=asyncio.run(model.call_model(settings(),{'fact':'example'}))
    assert result=={'decision':'non_risk'} and len(seen)==2
    assert seen[0].content==seen[1].content

def test_repeated_invalid_json_stops_at_three_requests(monkeypatch):
    seen=client(monkeypatch,[{'choices':[{'message':{'content':'{broken'}}]}])
    with pytest.raises(ValueError,match='JSON'):
        asyncio.run(model.call_model(settings(),{}))
    assert len(seen)==3

def test_missing_choices_is_not_treated_as_success(monkeypatch):
    seen=client(monkeypatch,[{'choices':[]}])
    with pytest.raises(ValueError,match='JSON'):
        asyncio.run(model.call_model(settings(),{}))
    assert len(seen)==3
