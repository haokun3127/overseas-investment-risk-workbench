"""Remove internal preparation markers from names, never from quoted evidence."""
import re
import json


def clean_preparation_markers(value):
    """Remove reference-pack markers from display metadata, never quoted text."""
    return re.sub(r'[ \t]*[〔［【\[]\s*S\d+\s*[〕］】\]]', '', value).strip()


def clean_company_profile(profile):
    return {key:clean_preparation_markers(value) if isinstance(value,str) else value
            for key,value in profile.items()}


def clean_summary(value):
    value=str(value or '')
    value=re.sub(r'，含[“”"]?[〔［【\[]\s*S\d+[^。；，]*来源标注', '', value)
    value=clean_preparation_markers(value)
    value=re.sub(r'原文分卷\s*\d+\s*/\s*\d+', '', value)
    value=re.sub(r'客户(?:测试)?案例', '事项', value)
    value=re.sub(r'包含引用标记[“”"\s、]*(?:S\d+[、\s]*)+[”"]?', '', value)
    return value


def match_company(rows, profile):
    """Resolve trusted replay metadata without silently creating unowned data."""
    rows=list(rows)
    if profile.get('id') is not None:
        matches=[r for r in rows if r['id']==profile['id']]
    else:
        name=clean_preparation_markers(profile.get('name',''))
        matches=[r for r in rows if clean_company_profile(json.loads(r['profile_json'])).get('name')==name]
    if len(matches)!=1:
        raise ValueError('企业归属无法唯一确认，停止处理。')
    return matches[0]


def clean_name(value):
    value=clean_preparation_markers(str(value or ''))
    for _ in range(3):
        value=re.sub(r'^\s*[LPSN]\d+(?:\s+S\d+)?\s+', '', value)
        value=re.sub(r'^［(?:网页存档[^］]*|PDF文本副本)］\s*', '', value)
    value=re.sub(r'\s*\[原文分卷\d+/\d+\]\s*$', '', value)
    value=re.sub(r'^(?:客户测试案例事实摘录（已剔除参考答案）|客户测试案例事实摘录|客户案例事实摘录|客户测试资料|事件事实摘录)$', '事项资料', value)
    return value.strip()


def clean_reference(row):
    result=dict(row)
    for key in ('title','source'):
        if key in result:result[key]=clean_name(result[key])
    return result


_REF=r'(?<![A-Za-z0-9/])(?<!IFRS )'


def clean_model_text(value):
    """Model explanations may cite internal unit ids; show business wording instead."""
    if not isinstance(value,str):return value
    value=clean_preparation_markers(value)
    value=value.replace('“对不上”','“其他”').replace('"对不上"','"其他"').replace('对不上','其他')
    value=re.sub(_REF+r'S\d{1,6}(?:\s*[、和及与/]\s*S\d{1,6})*(?![A-Za-z0-9])','原文',value)
    value=re.sub(_REF+r'K\d{1,6}(?:\s*[、和及与/]\s*K\d{1,6})*(?![A-Za-z0-9])','知识库资料',value)
    value=re.sub(r'(?<![A-Za-z0-9_])document_id(?![A-Za-z0-9_])','资料',value)
    value=re.sub(r'本次\s*source','本次资料',value)
    value=re.sub(r'(?<![A-Za-z0-9_])source(?![A-Za-z0-9_])','资料',value)
    for code,label in (('lv1','红色'),('lv2','黄色'),('lv3','蓝色')):value=re.sub(r'(?<![A-Za-z0-9])'+code+r'(?![A-Za-z0-9])',label,value)
    return value


def rule_label(value):
    match=re.search(r'(20\d{2})(\d{2})(\d{2})',str(value or ''))
    return f'风险规则 {match.group(1)}-{match.group(2)}-{match.group(3)}' if match else '风险规则'


def clean_result(result):
    """Clean display copies of stored model results without touching quoted evidence."""
    if not isinstance(result,dict):return result
    result=dict(result)
    result.pop('customer_test_provenance',None)
    if isinstance(result.get('company_context'),dict):
        result['company_context']=clean_company_profile(result['company_context'])
    for key in ('reason','coverage','summary'):
        result[key]=clean_model_text(result.get(key)) if key in result else None
        if result[key] is None:result.pop(key)
    parts=[]
    for part in result.get('parts') or []:
        part=dict(part);part['reason']=clean_model_text(part.get('reason',''))
        events=[]
        for event in part.get('events') or []:
            event=dict(event)
            for key in ('title','category','summary','impact','recommendation'):
                if key in event:event[key]=clean_model_text(event[key])
            if isinstance(event.get('evidence'),list):
                event['evidence']=[clean_reference({**r,'reason':clean_model_text(r.get('reason',''))}) if isinstance(r,dict) else r for r in event['evidence']]
            event.pop('evidence_json',None)
            events.append(event)
        part['events']=events;parts.append(part)
    if 'parts' in result:result['parts']=parts
    return result
