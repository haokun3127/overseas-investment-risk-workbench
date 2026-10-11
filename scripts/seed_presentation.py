"""Seed fictional presentation cases; run offline with the service stopped."""
import argparse
import asyncio
import copy
import json
from pathlib import Path
from dotenv import load_dotenv


CASES = [
    ('API演示：港口拥堵导致原料断供风险',
     '【虚构演示资料，不是真实新闻】印度尼西亚某制造企业的采购负责人在演示记录中报告：'
     '10月11日，原计划当天到厂的两批生产原料因港口设备故障滞留。港口通知预计延迟七天放行。'
     '工厂当前原料库存仅能维持三天生产。采购部门尚未找到可在三天内交付的替代供应商。'
     '生产负责人表示，若第四天仍未收到原料，核心生产线将停工，原定客户交付计划可能受影响。'
     '上述企业、港口及事件均为虚构，金额和损失概率未提供。'),
    ('API演示：例行培训不构成风险事件',
     '【虚构演示资料，不是真实新闻】印度尼西亚某制造企业的演示周报记录：'
     '10月11日，公司按原计划完成新员工安全培训，培训覆盖全部新入职员工。'
     '培训未影响正常生产，订单交付、原料库存和设备运行均符合已确认的计划。'
     '记录未报告事故、争议、监管变化或经营异常。上述企业及周报为虚构演示内容。'),
    ('API演示：缺少原始证据需补充资料',
     '【虚构演示资料，不是真实新闻】演示录入人员仅写下“某地好像有新消息，可能和投资有关”。'
     '没有提供国家、企业、事件经过、时间、发布机构、原文、链接或可核对的证据。'
     '无法确认消息是否涉及印度尼西亚制造业，也无法确认是否发生了任何具体风险事件。'
     '本条用于展示资料不足的处理流程，不得补写或推测未提供的事件事实。'),
]


async def run(args):
    from app.config import Settings
    from app.demo import seed
    from app.ingest import insert_document
    from app.jobs import Worker
    from app.store import Store, DEFAULT_RULES, now
    settings = Settings()
    if args.analyze and (not args.allow_external_demo or not settings.configured):
        raise ValueError('真实API演示需配置模型并显式提供 --allow-external-demo。')
    store = Store(settings.data_dir)
    seed(store)
    ids = []
    for title, body in CASES:
        doc_id, _ = insert_document(store, {
            'title':title, 'body':body, 'date':'2026-10-11',
            'source':'合成API演示 · 非真实新闻',
        }, demo=True, allow_external=args.analyze)
        ids.append(doc_id)
    print(json.dumps({'demo_document_ids':ids}, ensure_ascii=False), flush=True)
    if not args.analyze:
        return
    if not args.allow_external_demo or not settings.configured:
        raise ValueError('真实API演示需配置模型并显式提供 --allow-external-demo。')
    rules = store.setting('rules')
    if not rules['confirmed']:
        if rules != DEFAULT_RULES:
            raise ValueError('已有自定义规则未确认，拒绝自动修改。')
        if store.one('SELECT COUNT(*) n FROM documents WHERE demo=0')['n']:
            raise ValueError('已有非演示资料，拒绝自动启用演示规则。')
        rules = copy.deepcopy(DEFAULT_RULES)
        rules.update(version='demo-validation-v1', confirmed=True,
                     notes='仅用于虚构资料的功能演示，非甲方正式规则；正式分析前须替换并确认业务标准。')
        store.set_setting('rules', rules)
        store.audit('rules_updated', 'demo-validation-v1: fictional presentation only')
    worker = Worker(store, settings)
    failures = []
    for doc_id in ids:
        doc = store.one('SELECT demo,source FROM documents WHERE id=?', (doc_id,))
        assert doc['demo'] and doc['source']=='合成API演示 · 非真实新闻'
        latest = store.one('SELECT * FROM analyses WHERE document_id=? ORDER BY version DESC LIMIT 1', (doc_id,))
        if latest and latest['model']==settings.model_name:
            print(json.dumps({'document_id':doc_id, 'decision':latest['decision'], 'existing':True}), flush=True)
            continue
        with store.db() as db:
            db.execute('UPDATE documents SET allow_external=1 WHERE id=?', (doc_id,))
            job_id = db.execute("INSERT INTO jobs(document_id,status,created_at) VALUES (?,'queued',?)", (doc_id,now())).lastrowid
        store.audit('demo_api_authorized', f'fictional document={doc_id}, model={settings.model_name}')
        await worker.process(store.one('SELECT * FROM jobs WHERE id=?', (job_id,)))
        job = store.one('SELECT * FROM jobs WHERE id=?', (job_id,))
        latest = store.one('SELECT * FROM analyses WHERE job_id=?', (job_id,))
        print(json.dumps({'document_id':doc_id, 'job_id':job_id, 'status':job['status'],
                          'decision':latest['decision'] if latest else None, 'error':job['error']},ensure_ascii=False),flush=True)
        if job['status']!='completed':
            failures.append(job_id)
    if failures:
        raise ValueError(f'演示分析任务未全部完成：{failures}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--analyze', action='store_true')
    parser.add_argument('--allow-external-demo', action='store_true')
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    asyncio.run(run(args))


if __name__=='__main__':
    main()
