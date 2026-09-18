import json
from .ingest import insert_document
from .store import DEFAULT_RULES, now

SAMPLES = [
    ('示例：工业园区供电中断影响生产','2026-09-08','环境与安全','red',
     '【虚构演示资料】某制造业园区供电设施故障，连续停电导致部分生产线暂停，恢复时间尚未确定。',
     '演示案例描述供电中断及生产线暂停。', '可能影响交付进度，并增加停工和恢复成本。此项为演示推断。', '核实恢复时间和受影响工序，评估备用供电与交付调整方案。'),
    ('示例：进口原料清关材料要求调整','2026-09-07','政策与监管','orange',
     '【虚构演示资料】某原料进口环节拟增加材料核验，企业正在确认过渡安排。新要求的适用范围尚待核实。',
     '演示案例描述进口材料核验要求可能调整。', '可能延长到货周期或增加手续成本，实际影响需进一步核实。', '向业务主管渠道核实适用范围，盘点在途原料及材料准备情况。'),
    ('示例：港口运输班次临时减少','2026-09-06','供应链与物流','orange',
     '【虚构演示资料】某港口因设备检修临时减少运输班次，部分货物发运延后。运营方尚未提供完整恢复计划。',
     '演示案例描述运输班次减少和发运延后。', '可能影响原料到货或产品出运，需评估库存缓冲。', '核实受影响航次，协调替代运输和库存安排。'),
    ('示例：用工沟通出现争议','2026-09-05','劳工与社会','yellow',
     '【虚构演示资料】某工厂员工对排班方式提出异议，管理方已安排沟通会议，目前生产正常。',
     '演示案例描述排班争议，尚未发生生产中断。', '若沟通不畅可能影响人员稳定；当前影响仍需关注。', '记录争议事项，开展沟通并核验相关用工要求。'),
]

def seed(store):
    added = 0
    for title,date,category,level,body,summary,impact,recommendation in SAMPLES:
        doc_id,created = insert_document(store,{'title':title,'date':date,'source':'内置虚构案例 · 非真实新闻','body':body},demo=True)
        if not created:
            continue
        chunk = store.one('SELECT * FROM chunks WHERE document_id=?',(doc_id,))
        evidence=[{'reference':f'S{chunk["id"]}','quote':body,'reason':'仅用于展示引用与原文追溯交互，不构成真实风险判断。','document_id':doc_id,'locator':chunk['locator'],'title':title}]
        with store.db() as db:
            analysis_id=db.execute('''INSERT INTO analyses(document_id,version,decision,model,mode,rules_json,knowledge_json,result_json,created_at,duration_ms,usage_json)
                VALUES (?,1,'risk','内置展示样例','demo',?,'{}',?,?,0,'{}')''',(doc_id,json.dumps(DEFAULT_RULES,ensure_ascii=False),json.dumps({'demo':True,'reason':'虚构演示结果，未调用模型。'},ensure_ascii=False),now())).lastrowid
            db.execute('''INSERT INTO events(analysis_id,title,category,level,summary,impact,recommendation,evidence_json)
                VALUES (?,?,?,?,?,?,?,?)''',(analysis_id,title,category,level,summary,impact,recommendation,json.dumps(evidence,ensure_ascii=False)))
        added+=1
    store.audit('demo_seeded',f'count={added}')
    return added
