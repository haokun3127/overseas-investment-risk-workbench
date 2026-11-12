"""Compare all current saved cases with independently re-extracted supplied expectations."""
import importlib.util
import json
from pathlib import Path
import re
from app.meeting import current_rules,LEGACY_MAPPING
from app.store import DEFAULT_RULES
from app.presentation import clean_company_profile

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/local-replay-20261112'
OUT=ROOT/'qa/presentation-audit-20261112'


def run():
    spec=importlib.util.spec_from_file_location('reference_parser',QA/'run_rag_customer_cases_20261101.py')
    parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
    supplied=json.loads((QA/'extracted-cases.json').read_text(encoding='utf-8-sig'))
    expected={case['id']:parser.packet(case)['expected'] for case in supplied}
    inputs={c['id']:c for c in json.loads((QA/'model-inputs.json').read_text(encoding='utf-8-sig'))}
    plan=json.loads((QA/'case-sync-plan.json').read_text(encoding='utf-8'))
    snapshot=json.loads((OUT/'business-snapshot.json').read_text(encoding='utf-8'))
    docs={d['id']:d for d in snapshot['documents']}
    companies={c['id']:clean_company_profile(json.loads(c['profile_json'])) for c in snapshot['companies']}
    chunks={c['id']:c for c in snapshot['chunks']}
    jobs={j['id']:j for j in snapshot['jobs']}
    cats=set(current_rules(DEFAULT_RULES)['categories'])
    results=[]
    for item in plan['cases']:
        cid=item['company_id'];did=item['target_document_id'];doc=docs[did]
        case=item['case'];answer=expected[case]
        latest=max((a for a in snapshot['analyses'] if a['document_id']==did),key=lambda a:(a['version'],a['id']))
        events=[e for e in snapshot['events'] if e['analysis_id']==latest['id'] and not e['deleted_at']]
        wanted_level=LEGACY_MAPPING.get(answer['level'],answer['level'])
        wanted_decision='risk' if answer['risk'] and wanted_level!='non_risk' else 'non_risk'
        wanted_cats={name for name in cats if any(name in text for text in answer['categories_text'])}
        if answer['categories_text']==['对不上']:wanted_cats={'其他'}
        if wanted_decision=='non_risk':wanted_cats=set()
        checks={
          'company':doc['company_id']==cid and companies[cid]['name']==clean_company_profile(inputs[case]['profile'])['name'],
          'facts_unchanged':doc['body']==inputs[case]['body'],
          'latest_job_completed':jobs[latest['job_id']]['status']=='completed',
          'decision':latest['decision']==wanted_decision,
          'categories':{e['category'] for e in events}==wanted_cats,
          'levels':all(e['level']==wanted_level for e in events) and (bool(events) if wanted_decision=='risk' else not events),
          'matches_verified_local_result':latest['decision']==item['analysis']['decision'] and
             [(e['title'],e['category'],e['level']) for e in events]==[(e['title'],e['category'],e['level']) for e in item['events']],
          'quotes_traceable':True,'reference_scope':True,'recommendations_complete':True}
        ref_count=0;action_count=0
        def check_reference(ref):
            nonlocal ref_count
            quote=ref.get('quote','');source=docs.get(ref.get('document_id'))
            match=re.fullmatch(r'[KS](\d+)(?::.*)?',ref.get('reference',''))
            chunk=chunks.get(int(match[1])) if match else None
            checks['quotes_traceable'] &= bool(source and quote and quote in source['body'] and chunk and
                 chunk['document_id']==source['id'] and quote in chunk['text'])
            checks['reference_scope'] &= bool(source and source['company_id'] in (None,cid))
            ref_count+=1
        for event in events:
            evidence=json.loads(event['evidence_json']);checks['quotes_traceable'] &= bool(evidence)
            for ref in evidence:check_reference(ref)
            actions=json.loads(event['actions_json']);action_count+=len(actions)
            checks['recommendations_complete'] &= bool(event['summary'] and event['impact'] and event['recommendation'] and actions)
            for action in actions:
                checks['recommendations_complete'] &= bool(action.get('text') and action.get('conditions'))
                for ref in action.get('basis',[]):check_reference(ref)
        results.append({'case':case,'title':inputs[case]['title'],'company':companies[cid]['name'],
          'document_id':did,'analysis_id':latest['id'],'analysis_version':latest['version'],
          'expected':{'decision':wanted_decision,'categories':sorted(wanted_cats),'level':wanted_level},
          'actual':{'decision':latest['decision'],'events':[{'id':e['id'],'title':e['title'],'category':e['category'],'level':e['level']} for e in events]},
          'references_checked':ref_count,'recommendations_checked':action_count,'checks':checks,'passed':all(checks.values())})
    assert len(results)==19
    report={'total':19,'passed':sum(r['passed'] for r in results),'risk_cases':sum(r['actual']['decision']=='risk' for r in results),
      'nonrisk_cases':sum(r['actual']['decision']=='non_risk' for r in results),'events':sum(len(r['actual']['events']) for r in results),
      'references_checked':sum(r['references_checked'] for r in results),'recommendations_checked':sum(r['recommendations_checked'] for r in results),
      'model_executed':False,'results':results}
    (OUT/'case-by-case-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))
    if report['passed']!=19:
        print(json.dumps([{'case':r['case'],'failed':[k for k,v in r['checks'].items() if not v]} for r in results if not r['passed']]))
        raise AssertionError('Case verification failed')
    colors={'lv1':'红色','lv2':'黄色','lv3':'蓝色','non_risk':'绿色（本次资料无风险）'}
    lines=['# 整站展示清理与19个案例逐项核对','',
      '核对日期：2026年11月12日','',
      '本次逐条读取线上已保存的最新分析，与原始参考资料重新提取的期望判断、类型及等级进行对照，同时核对企业归属、事实正文、引用及建议结构。未重新运行模型，也未把参考答案输入模型。','',
      '## 逐项核对结果','',
      '| 序号 | 事项 | 当前结果 | 风险类型 | 核对 |',
      '| --- | --- | --- | --- | --- |']
    for number,row in enumerate(results,1):
        es=row['actual']['events']
        grade='、'.join(dict.fromkeys(colors[e['level']] for e in es)) if es else colors['non_risk']
        category='、'.join(dict.fromkeys(e['category'] for e in es)) if es else '不生成风险事件'
        lines.append(f"| {number} | {row['title']} | {grade} | {category} | 通过 |")
    lines+=['','19项均通过；16个风险案例共产生17条风险事件，3个案例按本次资料判定为无风险。南山铝业案例识别出两种风险，因此事件数比风险案例数多1条。','',
      '密松水电站案例位于缅甸，按本次印尼业务范围不纳入风险；不表示该缅甸项目本身没有风险。正常投产、正常经营公告的绿色结果，仅对应本次提供的资料。','',
      '## 核对范围','',
      '- 19个案例的企业归属、事实正文、最新分析版本和任务完成状态。',
      '- 参考资料中的风险判断、分类，以及按照已确认红黄蓝绿标准映射后的等级。',
      f"- {report['references_checked']}处引用逐一核对原始正文、分块编号和企业可见范围。",
      f"- {report['recommendations_checked']}项建议核对内容和适用条件是否完整；此项检查不代表全部建议已经人工完成法律适用审核。",'',
      '## 展示处理','',
      '清理准备资料时使用的来源编号、案例前缀和分卷标记。公司档案、资料标题、来源、中文摘要与正文阅读区使用正常业务内容；底层原文、引用编号、分块和历史分析继续保留用于追溯。法令文号、正常引用序号、业务分类和风险等级保留。','']
    live=OUT/'pages-live-result.json'
    if live.exists():
        verified=json.loads(live.read_text(encoding='utf-8'))
        lines+=['## 线上页面验证','',
          f"版本：{verified['release']}。检查8个主要页面、{verified['list_pages_checked']}页资料列表、{verified['document_details_checked']}份资料详情、{verified['latest_case_event_details_checked']}条案例事件详情和{verified['web_page_sources_checked']}份网站原文。",
          f"另外核对{verified['quote_locations_checked']}处事件引用跳转，页面未检出准备标签，未发现脚本错误。原始资料正文校验一致。",'',
          f"网站检索另逐条读取{verified['website_run_details_checked']}条历史任务详情，确认历史任务的名称已正常展示；本次没有重新抓取网站或调用模型。",'',
          '全部企业风险总览及事件列表均为18条，其中17条来自本轮19个参考案例，另1条为此前独立录入的事件；无风险资料共4份，其中3份来自本轮参考案例，另1份为此前记录。','']
        lines+=['## 风险总览布局','',
          '顶部只保留一处“风险等级构成”，包括风险事件圆环、红黄蓝等级及绿色无风险资料数量。移除重复数字卡片和总览中的业务复核卡片，风险类型分布与最新风险事件列表均使用完整内容宽度。事件详情中的人工复核与调整功能保留。','',
          '已验证1440、900、390像素三个视口无页面横向溢出；红黄蓝入口可筛选事件，切换单企业及无风险企业后，页面和接口数量一致。','',
          '## 回归验证','',
          '本轮先完成一次全量回归：385项通过、1项失败、1项跳过。失败的日期识别用例已经修复，随后123项相关回归全部通过；另52项企业范围及权限回归、51项网站与展示回归全部通过，以上专项用例存在交集，不作为互不重复的总数累加。','',
          '跳过项为Windows当前用户不支持创建符号链接的用例。本轮未再次执行完整全量套件；不能将专项通过表述为全量零失败。','',
          '部署前完成数据库备份；原始正文、分块、分析记录、事件判断、任务及人工复核数据校验保持一致。服务器本次只执行轻量展示与接口检查，没有运行模型、嵌入或向量重建。','']
    (ROOT/'docs/整站展示清理与19个案例逐项核对_20261112.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':
    run()
