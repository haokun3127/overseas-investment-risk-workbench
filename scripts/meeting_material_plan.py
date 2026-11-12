"""Build reviewed classification/name changes against retained source fingerprints."""
import hashlib
import json
from pathlib import Path
from app.presentation import clean_name

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/followup-20261111'
# Each entry was reviewed against the retained original and its source, not inferred from host names.
GROUPS={
 'arbitration':[15,16,17,22,23,24,31,62,63,64,65,66],
 'case':[11,18,21,61,88,90],
 'administrative':[82,83,84],
 'sanctions':[27,28],
}


def build():
    rows=json.loads((QA/'knowledge-review.json').read_text(encoding='utf-8'))
    changes=[]
    for row in rows:
        category=next((key for key,ids in GROUPS.items() if row['id'] in ids),'incident')
        title=clean_name(row['title']);source=clean_name(row['source'])
        if title.lower().endswith('.pdf') or row['title'].startswith('［PDF文本副本］'):title=source
        if row['id']==94:title='华电科工新闻动态'
        note={
          'arbitration':'正文为仲裁裁决、管辖权决定或程序命令原文。',
          'case':'正文为既有争议解决案件的记录、当事人披露或案件结果报道，不作为法律条文或裁判原文。',
          'administrative':'正文为竞争主管机关对具体经营者行政执法结果的公告，不是通用法规。',
          'sanctions':'正文为制裁执法通知及和解资料，不自动视为现行通用法规。',
          'incident':'正文为新闻、企业经营公告、情况介绍或政策说明，不是法律条文或裁判原文。',
        }[category]
        changes.append({'id':row['id'],'body_sha256':hashlib.sha256(row['body'].encode()).hexdigest(),
          'before':{k:row[k] for k in ('title','source','legal_meta','legal_revision')},
          'title':title,'source':source,'category':category,'reason':note})
    names=[]
    name_file=QA/'name-review.json'
    if name_file.exists():
        for table,records in json.loads(name_file.read_text(encoding='utf-8')).items():
            for row in records:
                # Knowledge fields already have the more detailed reviewed changes above.
                if table=='documents' and row['id'] in {c['id'] for c in changes}:continue
                for field,value in row.items():
                    if field=='id':continue
                    cleaned=clean_name(value)
                    if cleaned!=value:names.append({'table':table,'id':row['id'],'field':field,'before':value,'after':cleaned})
    plan={'reviewed_documents':len(changes),'changes':changes,'names':names,'templates':[{
       'name':'风险事项说明','category':'事项说明',
       'body':'风险事项说明\n一 事件摘要\n根据提供的事项经过填写发生时间、地点、主体和已经发生的事实，缺失信息保留待补充。\n二 风险判断\n依据提供的原文说明事实支持的风险和不确定性，不预设风险等级或参考答案。\n三 处理建议\n写明可以采取的核实或处理措施及适用条件，法律依据不足时明确待核实。\n四 依据与来源\n列出本次引用的原文及来源，不编造法律或判决。',
       'origin':'依据既有案例资料的事项、事实、风险说明及来源结构整理，未载入任何参考结论。'}]}
    (QA/'material-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'documents':len(changes),'categories':{c:sum(r['category']==c for r in changes) for c in set(r['category'] for r in changes)},'templates':len(plan['templates'])},ensure_ascii=False))


if __name__=='__main__':build()
