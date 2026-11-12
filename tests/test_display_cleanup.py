from app.presentation import clean_model_text, clean_result, rule_label


def test_model_text_hides_internal_references():
    text = clean_model_text('但S540未载明；K394所述；故填“对不上”；本次source直接；按lv2审视；S369、S370显示')
    assert 'S540' not in text and 'K394' not in text and '对不上' not in text and 'lv2' not in text
    assert '原文未载明' in text and '“其他”' in text and '黄色' in text


def test_standard_names_are_not_rewritten():
    assert clean_model_text('参考ISSB IFRS S1/S2') == '参考ISSB IFRS S1/S2'
    assert clean_model_text('MiniLM-L12-v2') == 'MiniLM-L12-v2'


def test_result_display_copy_drops_preparation_metadata():
    raw = {'customer_test_provenance': {'case_id': 'S1'}, 'company_context': {'name': 'TikTok 〔S2〕'},
           'parts': [{'reason': 'S1显示', 'events': [{'category': '对不上', 'evidence_json': '[]',
                                                     'evidence': [{'reference': 'S1', 'quote': '原文〔S2〕', 'reason': 'S1说明'}]}]}]}
    shown = clean_result(raw)
    assert 'customer_test_provenance' not in shown and shown['company_context']['name'] == 'TikTok'
    event = shown['parts'][0]['events'][0]
    assert event['category'] == '其他' and 'evidence_json' not in event
    assert event['evidence'][0]['quote'] == '原文〔S2〕'  # quoted source text is never rewritten
    assert raw['parts'][0]['events'][0]['category'] == '对不上'
    assert rule_label('client-risk-taxonomy-20261101-evidence') == '风险规则 2026-11-01'
