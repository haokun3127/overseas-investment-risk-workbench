"""Promote locally verified analysis versions, without running models on production."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def connect(path):
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');return db
def one(db,sql,args=()):
    r=db.execute(sql,args).fetchone();return dict(r) if r else None
def state(db,did):
    return {'document':one(db,'SELECT * FROM documents WHERE id=?',(did,)),
        'analyses':[dict(r) for r in db.execute('SELECT * FROM analyses WHERE document_id=? ORDER BY id',(did,))],
        'events':[dict(r) for r in db.execute('SELECT e.* FROM events e JOIN analyses a ON a.id=e.analysis_id WHERE a.document_id=? ORDER BY e.id',(did,))]}
def insert(db,table,row):
    row={k:v for k,v in row.items() if k!='id'}
    keys=list(row);return db.execute('INSERT INTO '+table+'('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',[row[k] for k in keys]).lastrowid

def prepare(root):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from app.presentation import match_company
    report=json.loads((root/'case-replay.json').read_text(encoding='utf-8'))
    assert len(report['results'])==19 and all(r.get('all_match') for r in report['results']), 'All 19 verified cases are required'
    inputs={r['id']:r for r in json.loads((root/'model-inputs.json').read_text(encoding='utf-8-sig'))}
    base=connect(root/'production-baseline.db');local=connect(root/'replica/risk.db')
    plan={'created_at':stamp(),'cases':[],'dependencies':{},'model_execution_on_server':False}
    for result in report['results']:
        item=inputs[result['id']]
        owner=dict(match_company(base.execute('SELECT * FROM companies'),item['profile']))
        source=one(local,"SELECT * FROM documents WHERE kind='event' AND company_id=? AND body=? ORDER BY id DESC LIMIT 1",(owner['id'],item['body']))
        candidates=[dict(r) for r in base.execute("SELECT * FROM documents WHERE kind='event' AND body=? AND company_id=?",(item['body'],owner['id']))]
        if not candidates:candidates=[dict(r) for r in base.execute("SELECT * FROM documents WHERE kind='event' AND body=? AND company_id IS NULL",(item['body'],))]
        assert len(candidates)==1, 'Ambiguous target '+item['id']
        target=candidates[0];aid=one(local,'SELECT * FROM analyses WHERE document_id=? ORDER BY version DESC LIMIT 1',(source['id'],))
        job=one(local,'SELECT * FROM jobs WHERE id=?',(aid['job_id'],));assert job['status']=='completed'
        events=[dict(r) for r in local.execute('SELECT * FROM events WHERE analysis_id=? ORDER BY id',(aid['id'],))]
        assert aid['decision']==result['decision'], 'Report no longer matches saved decision'
        assert [(e['category'],e['level']) for e in events]==[(e['category'],e['level']) for e in result['events']], 'Report no longer matches saved events'
        chunks={r['id']:dict(r) for r in local.execute('SELECT * FROM chunks WHERE document_id=?',(source['id'],))}
        target_chunks=[dict(r) for r in base.execute('SELECT * FROM chunks WHERE document_id=?',(target['id'],))]
        cmap={k:next(t['id'] for t in target_chunks if t['text']==v['text'] and t['locator']==v['locator']) for k,v in chunks.items()}
        def remap(value):
            if isinstance(value,list):return [remap(v) for v in value]
            if not isinstance(value,dict):return value
            out={k:remap(v) for k,v in value.items()}
            if out.get('document_id')==source['id']:out['document_id']=target['id']
            for key in ('reference','unit_id'):
                if isinstance(out.get(key),str):
                    for old,new in cmap.items():
                        if out[key]=='S'+str(old) or out[key].startswith('S'+str(old)+':'):
                            out[key]='S'+str(new)+out[key][len('S'+str(old)):];break
            if 'sent_chunk_ids' in out:out['sent_chunk_ids']=[cmap.get(v,v) for v in out['sent_chunk_ids']]
            if 'category_chunks' in out:out['category_chunks']={k:[cmap.get(v,v) for v in vals] for k,vals in out['category_chunks'].items()}
            if 'quote' in out and 'document_id' in out:
                ref=one(base,'SELECT * FROM documents WHERE id=?',(out['document_id'],));assert ref and out['quote'] in ref['body']
                for key in ('title','source','url','date'):
                    if key in out:out[key]=ref[key]
                for b in base.execute('SELECT id,text FROM chunks WHERE document_id=?',(ref['id'],)):
                    if out['quote'] in b['text']:break
                else:raise AssertionError('Quote does not match target chunk')
                plan['dependencies'][str(ref['id'])]=digest({k:ref[k] for k in ('body','company_id','legal_meta','quarantined_at')})
            return out
        for field in ('knowledge_json','result_json','rules_json'):
            parsed=json.loads(aid[field]);aid[field]=json.dumps(remap(parsed),ensure_ascii=False)
        # Match knowledge titles to the current production metadata; preserve source text.
        knowledge=json.loads(aid['knowledge_json'])
        for key,ref in knowledge.items():
            prod=one(base,'SELECT d.* FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.id=?',(int(key),))
            assert prod
            original=one(base,'SELECT text FROM chunks WHERE id=?',(int(key),))
            assert ref['text']==original['text']
            for f in ('title','source','url','date'):ref[f]=prod[f]
            plan['dependencies'][str(prod['id'])]=digest({k:prod[k] for k in ('body','company_id','legal_meta','quarantined_at')})
        aid['knowledge_json']=json.dumps(knowledge,ensure_ascii=False)
        for event in events:
            for field in ('evidence_json','actions_json'):event[field]=json.dumps(remap(json.loads(event[field])),ensure_ascii=False)
        aid['document_id']=target['id'];job['document_id']=target['id'];job['parent_analysis_id']=None
        plan['cases'].append({'case':item['id'],'target_document_id':target['id'],'company_id':owner['id'],
            'company_hash':digest(owner),'before_hash':digest(state(base,target['id'])),
            'analysis':aid,'job':job,'events':events})
    plan['payload_hash']=digest(plan['cases'])
    (root/'case-sync-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(plan['cases']),'events':sum(len(c['events']) for c in plan['cases']),'payload_hash':plan['payload_hash']}))

def apply(plan_path,database,backup):
    plan=json.loads(plan_path.read_text(encoding='utf-8'));assert digest(plan['cases'])==plan['payload_hash']
    db=connect(database)
    backup.parent.mkdir(parents=True,exist_ok=True)
    assert not backup.exists(),'Never overwrite a backup'
    with sqlite3.connect(backup) as saved:db.backup(saved)
    with db:
        db.execute('BEGIN IMMEDIATE')
        marker='local-case-sync:'+plan['payload_hash']
        assert not db.execute('SELECT 1 FROM audit WHERE detail=?',(marker,)).fetchone(),'Plan already applied'
        for did,want in plan['dependencies'].items():
            doc=one(db,'SELECT * FROM documents WHERE id=?',(int(did),))
            assert digest({k:doc[k] for k in ('body','company_id','legal_meta','quarantined_at')})==want,'Reference changed'
        for case in plan['cases']:
            did=case['target_document_id'];assert digest(state(db,did))==case['before_hash'],'Case changed; replan required'
            assert digest(one(db,'SELECT * FROM companies WHERE id=?',(case['company_id'],)))==case['company_hash'],'Company changed'
        for case in plan['cases']:
            did=case['target_document_id'];db.execute('UPDATE documents SET company_id=? WHERE id=?',(case['company_id'],did))
            job=copy.deepcopy(case['job']);jid=insert(db,'jobs',job)
            row=copy.deepcopy(case['analysis']);row['job_id']=jid
            row['version']=db.execute('SELECT COALESCE(MAX(version),0)+1 FROM analyses WHERE document_id=?',(did,)).fetchone()[0]
            aid=insert(db,'analyses',row)
            for event in case['events']:
                e=copy.deepcopy(event);e['analysis_id']=aid;insert(db,'events',e)
            db.execute('INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,?)',('analysis_imported',marker,stamp(),case['company_id']))
        assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    result={'cases':len(plan['cases']),'events':sum(len(c['events']) for c in plan['cases']),
        'database_quick_check':'ok','backup':str(backup),'model_execution_on_server':False,'payload_hash':plan['payload_hash']}
    print(json.dumps(result))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','apply']);p.add_argument('--root',type=Path,default=Path('qa/local-replay-20261112'))
    p.add_argument('--database',type=Path);p.add_argument('--backup',type=Path);args=p.parse_args()
    if args.mode=='prepare':prepare(args.root.resolve())
    else:apply(args.root/'case-sync-plan.json',args.database,args.backup)
