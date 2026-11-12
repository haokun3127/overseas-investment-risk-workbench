"""Reject concurrent edits before any promotion writes (local copies only)."""
import json
from pathlib import Path
import shutil
from scripts.local_case_sync import apply,connect
root=Path('qa/local-replay-20261112')
plan=json.loads((root/'case-sync-plan.json').read_text(encoding='utf-8'))
checks=[]
for kind in ('event_edit','reference_edit'):
    path=root/(kind+'-conflict-v2.db');assert not path.exists()
    shutil.copy2(root/'production-baseline.db',path)
    db=connect(path)
    with db:
        if kind=='event_edit':
            did=plan['cases'][0]['target_document_id']
            db.execute("UPDATE documents SET title=title||' concurrent edit' WHERE id=?",(did,))
        else:
            did=next(int(d) for d in plan['dependencies'] if int(d)!=plan['cases'][0]['target_document_id'])
            db.execute("UPDATE documents SET body=body||' concurrent reference edit' WHERE id=?",(did,))
    before=[tuple(r) for r in db.execute('SELECT * FROM documents ORDER BY id')]
    count=db.execute('SELECT count(*) FROM analyses').fetchone()[0];db.close()
    try:apply(root/'case-sync-plan.json',path,root/(kind+'-backup-v2.db'))
    except AssertionError as error:
        assert 'changed' in str(error),str(error)
    else:raise AssertionError('Concurrent edit not rejected')
    db=connect(path)
    assert db.execute('SELECT count(*) FROM analyses').fetchone()[0]==count
    assert [tuple(r) for r in db.execute('SELECT * FROM documents ORDER BY id')]==before
    checks.append(kind);db.close()
result={'rejected_without_import':checks,'production_writes':False}
(root/'conflict-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
