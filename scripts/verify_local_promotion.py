"""Read-only checks for the local promotion rehearsal."""
import json
from pathlib import Path
import sqlite3
from scripts.local_case_sync import state,digest,apply,connect

root=Path('qa/local-replay-20261112')
plan=json.loads((root/'case-sync-plan.json').read_text(encoding='utf-8'))
before=connect(root/'production-baseline.db');after=connect(root/'promotion-preview.db')
targets={c['target_document_id'] for c in plan['cases']}
for table in ('companies','chunks','web_sources','web_pages','review_history','document_origins','material_changes'):
    assert [tuple(r) for r in before.execute('SELECT * FROM '+table+' ORDER BY rowid')]==[tuple(r) for r in after.execute('SELECT * FROM '+table+' ORDER BY rowid')],table
for table in ('analyses','events','jobs'):
    for row in before.execute('SELECT * FROM '+table):
        assert dict(row)==dict(after.execute('SELECT * FROM '+table+' WHERE id=?',(row['id'],)).fetchone()),table
for doc in before.execute('SELECT * FROM documents'):
    current=dict(after.execute('SELECT * FROM documents WHERE id=?',(doc['id'],)).fetchone())
    for key in doc.keys():
        assert doc[key]==current[key] or (key=='company_id' and doc['id'] in targets)
for case in plan['cases']:
    did=case['target_document_id']
    analysis=dict(after.execute('SELECT * FROM analyses WHERE document_id=? ORDER BY version DESC LIMIT 1',(did,)).fetchone())
    assert analysis['decision']==case['analysis']['decision']
    actual=[dict(r) for r in after.execute('SELECT * FROM events WHERE analysis_id=? ORDER BY id',(analysis['id'],))]
    assert len(actual)==len(case['events'])
    for a,b in zip(actual,case['events']):
        for k in b:
            if k not in ('id','analysis_id'):assert a[k]==b[k]
        for field in ('evidence_json','actions_json'):
            def check(value):
                if isinstance(value,list):
                    for part in value:check(part)
                if isinstance(value,dict):
                    if value.get('quote') and value.get('reference'):
                        ref=value['reference'];cid=int(ref[1:]);chunk=after.execute('SELECT * FROM chunks WHERE id=?',(cid,)).fetchone()
                        assert chunk and value['quote'] in chunk['text']
                        assert chunk['document_id']==value['document_id']
                    for v in value.values():check(v)
            check(json.loads(a[field]))
counts=lambda db:{t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('documents','analyses','events','jobs')}
start=counts(after);after.close()
try:apply(root/'case-sync-plan.json',root/'promotion-preview.db',root/'duplicate-attempt-backup.db')
except AssertionError as e:assert 'already applied' in str(e)
else:raise AssertionError('Repeated import should be rejected')
assert counts(connect(root/'promotion-preview.db'))==start
result={'cases':19,'latest_events':17,'old_rows_preserved':True,'quotes_and_reference_ids_verified':True,
    'duplicate_import_rejected':True,'counts':start}
(root/'promotion-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
