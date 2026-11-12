"""Read-only production snapshot; remove authentication only from the isolated copy."""
import json
from pathlib import Path
import shutil
import sqlite3

ROOT=Path('/opt/rag-workbench/verification-followup-20261111')
ROOT.mkdir(exist_ok=True,mode=0o700)
target=ROOT/'replica'
target.mkdir(exist_ok=False,mode=0o700)
data=Path('/var/lib/rag-workbench')
for name in ('risk.db','vectors.db'):
    if (data/name).exists():
        with sqlite3.connect('file:'+str(data/name)+'?mode=ro',uri=True) as src,sqlite3.connect(target/name) as dst:src.backup(dst)
with sqlite3.connect(target/'risk.db') as db:
    db.execute('DELETE FROM sessions');db.execute('DELETE FROM company_users')
    db.execute("DELETE FROM settings WHERE key='admin'")
    db.row_factory=sqlite3.Row
    knowledge=[dict(r) for r in db.execute("SELECT id,title,source,url,date,legal_meta,legal_revision,body FROM documents WHERE kind='knowledge' AND source!='公司信息档案' AND quarantined_at IS NULL ORDER BY id")]
    (ROOT/'knowledge-review.json').write_text(json.dumps(knowledge,ensure_ascii=False,indent=2))
for folder in ('models','reference-data'):
    if (data/folder).exists():shutil.copytree(data/folder,target/folder,copy_function=__import__('os').link)
print(json.dumps({'replica':str(target),'knowledge':len(knowledge),'authentication_removed':True,'production_writes':False}))
