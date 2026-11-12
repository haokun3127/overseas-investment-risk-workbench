"""Read-only snapshot of scoped business data; never collect credentials/settings."""
import argparse
import collections
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'qa/presentation-audit-20261112'
MARKER=re.compile(r'[〔［【\[]\s*S\d+\s*[〕］】\]]|^\s*[LPSN]\d+(?:\s+S\d+)?\s+|客户测试|客户案例|已剔除参考答案|［PDF文本副本］|［网页存档|原文分卷')
COLLECT=r'''
import json,sqlite3
db=sqlite3.connect('file:/var/lib/rag-workbench/risk.db?mode=ro',uri=True);db.row_factory=sqlite3.Row
fields={
 'companies':'id,profile_json,document_id',
 'documents':'id,title,date,date_source,source,url,body,kind,filename,zh_summary,zh_keywords,company_id,quarantined_at,legal_meta',
 'chunks':'id,document_id,locator,text',
 'analyses':'id,document_id,job_id,version,decision,result_json,knowledge_json,rules_json',
 'events':'id,analysis_id,title,category,level,summary,impact,recommendation,evidence_json,actions_json,deleted_at,review_status',
 'jobs':'id,document_id,status,error,company_json',
 'web_sources':'id,name,keywords,category,deleted_at',
 'web_pages':'id,run_id,title,body,reason,quote',
 'drafting_templates':'id,name,category,body,deleted_at',
 'drafting_results':'id,template_json,result_json',
 'consultation_reports':'id,result_json'}
result={}
with db:
 for table,columns in fields.items():
  if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
   result[table]=[dict(r) for r in db.execute('SELECT '+columns+' FROM '+table+' ORDER BY id')]
print(json.dumps(result,ensure_ascii=False))
'''


def walk(value,path=''):
    if isinstance(value,str):
        match=MARKER.search(value)
        if match:
            start=max(0,match.start()-45);end=min(len(value),match.end()+75)
            yield {'path':path,'sample':value[start:end].replace('\n',' ')}
    elif isinstance(value,list):
        for i,v in enumerate(value):
            yield from walk(v,f'{path}[{i}]')
    elif isinstance(value,dict):
        for key,v in value.items():
            if key.endswith('_json') and isinstance(v,str):
                try:v=json.loads(v)
                except ValueError:pass
            yield from walk(v,path+'.'+key if path else key)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fetch',action='store_true');args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    snapshot=OUT/'business-snapshot.json'
    if args.fetch:
        run=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138',
            '/opt/rag-workbench/venv/bin/python -'],input=COLLECT.encode(),capture_output=True,timeout=45)
        run.check_returncode();data=json.loads(run.stdout);snapshot.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    else:data=json.loads(snapshot.read_text(encoding='utf-8'))
    findings=[]
    for table,rows in data.items():
        for row in rows:
            findings.extend({'table':table,'id':row['id'],**v} for v in walk(row))
    (OUT/'raw-marker-findings.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'records':{t:len(r) for t,r in data.items()},
        'marker_fields':dict(collections.Counter(f['table']+'.'+f['path'].split('.')[0] for f in findings)),
        'findings':len(findings)},ensure_ascii=False))


if __name__=='__main__':
    main()
