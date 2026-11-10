import pytest
from app.quantities import AmountMismatch, amounts, verify_amounts
from app.consultation import verify_answer


@pytest.mark.parametrize('original,translated', [
    ('Rp15 miliar', '150亿印尼盾'),
    ('Rp1,5 miliar', '15亿印尼盾'),
    ('Rp15.000.000.000', '150亿印尼盾'),
    ('15 billion rupiah', '150亿印尼盾'),
    ('USD 1.5 billion', '15亿美元'),
    ('US$ 5 million', '500万美元'),
    ('Rp1.234,5 juta', '12.345亿印尼盾'),
])
def test_equivalent_amounts(original, translated):
    assert amounts(original) and amounts(translated)
    verify_amounts(translated, original)


@pytest.mark.parametrize('wrong,original', [
    ('15亿印尼盾', 'Rp15 miliar'),
    ('150亿美元', 'Rp15 miliar'),
    ('150亿印尼盾', 'Rp15 juta'),
    ('罚款150亿印尼盾', '正文没有罚款金额'),
])
def test_wrong_magnitude_currency_and_unsupported_amount_are_rejected(wrong, original):
    with pytest.raises(AmountMismatch):
        verify_amounts(wrong, original)


def test_dates_counts_and_no_currency_are_not_misidentified_as_money():
    assert amounts('2025年9月29日，迟报88个工作日。') == []


def test_exact_quote_does_not_let_wrong_translation_pass():
    quote='KPPU menjatuhkan sanksi denda sebesar Rp15 miliar kepada TikTok.'
    source={'S1':{'text':quote,'document_id':1,'title':'KPPU','source':'KPPU','date':'2025-09-29','locator':'正文'}}
    answer={'status':'answered','blocks':[{'text':'罚款15亿印尼盾。','citations':[{'ref':'S1','quote':quote}]}]}
    with pytest.raises(AmountMismatch):
        verify_answer(answer,source)
    answer['blocks'][0]['text']='罚款150亿印尼盾。'
    assert verify_answer(answer,source)['status']=='answered'


@pytest.mark.parametrize('repair_ok',[True,False])
def test_consultation_corrects_once_or_blocks_wrong_amount(tmp_path,monkeypatch,repair_ok):
    import secrets
    from fastapi.testclient import TestClient
    from app import consultation
    from app.config import Settings
    from app.main import create_app
    from app.ingest import insert_document
    app=create_app(Settings(data_dir=tmp_path,model_base_url='https://example.com/v1',model_name='test',model_api_key='test'),run_worker=False)
    quote='KPPU menjatuhkan sanksi denda sebesar Rp15 miliar kepada TikTok.'
    insert_document(app.state.store,{'title':'TikTok KPPU','body':quote},kind='knowledge')
    calls=[]
    async def answer(settings,payload,**kwargs):
        calls.append(payload)
        text='罚款150亿印尼盾。' if len(calls)==2 and repair_ok else '罚款15亿印尼盾。'
        return {'status':'answered','blocks':[{'text':text,'citations':[{'ref':payload['evidence'][0]['ref'],'quote':quote}]}]},{}
    monkeypatch.setattr(consultation.model,'call_model',answer)
    with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
        assert client.post('/api/auth/setup',json={'password':secrets.token_urlsafe(18)}).status_code==200
        result=client.post('/api/consultation',json={'question':'TikTok KPPU 罚款多少？'})
        assert len(calls)==2 and 'candidate_answer' in calls[1]
        if repair_ok:
            assert result.status_code==200 and result.json()['blocks'][0]['text']=='罚款150亿印尼盾。'
        else:
            assert result.status_code==502 and '金额未通过' in result.json()['detail']


def test_connection_failure_is_not_reported_as_citation_failure(tmp_path,monkeypatch):
    import secrets
    from fastapi.testclient import TestClient
    from app import consultation
    from app.config import Settings
    from app.main import create_app
    from app.ingest import insert_document
    app=create_app(Settings(data_dir=tmp_path,model_base_url='https://example.com/v1',model_name='test',model_api_key='test'),run_worker=False)
    insert_document(app.state.store,{'title':'TikTok KPPU','body':'TikTok KPPU公开资料内容。'},kind='knowledge')
    async def unavailable(*args,**kwargs):raise ValueError('network failure')
    monkeypatch.setattr(consultation.model,'call_model',unavailable)
    with TestClient(app,headers={'X-Requested-With':'risk-workbench'}) as client:
        client.post('/api/auth/setup',json={'password':secrets.token_urlsafe(18)})
        response=client.post('/api/consultation',json={'question':'TikTok KPPU'})
        assert response.status_code==502 and '模型暂时不可用' in response.json()['detail']


def test_citation_unit_uses_original_text_and_rejects_unknown_or_wrong_source():
    from app.consultation import quote_units
    quote='KPPU menjatuhkan sanksi denda sebesar Rp15 miliar kepada TikTok.'
    source={'S1':{'text':quote,'document_id':1,'title':'KPPU','source':'KPPU','date':'2025-09-29','locator':'正文'}}
    unit=next(iter(quote_units(source)))
    citation={'ref':'S1','unit_id':unit}
    value={'status':'answered','blocks':[{'text':'罚款150亿印尼盾。','citations':[citation]}]}
    assert verify_answer(value,source)['sources'][0]['quote']==quote
    citation['unit_id']='S1:999'
    with pytest.raises(ValueError):verify_answer(value,source)
    citation.update(unit_id=unit,ref='S2')
    with pytest.raises(ValueError):verify_answer(value,source)
    citation.update(ref='S1',quote='模型伪造的引文')
    with pytest.raises(ValueError):verify_answer(value,source)
