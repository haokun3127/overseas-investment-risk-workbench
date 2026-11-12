import json
from pathlib import Path
import sqlite3
root=Path('qa/local-replay-20261112').resolve()
with sqlite3.connect(root.joinpath('replica/risk.db').as_uri()+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    print(json.dumps({'documents':[dict(r) for r in db.execute("SELECT id,company_id,title,length(body) size,source FROM documents WHERE kind='event' ORDER BY id")],
        'schema':{t:[dict(r) for r in db.execute('PRAGMA table_info('+t+')')] for t in ('jobs','analyses','events','chunks')},
        'example_event':dict(db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 1').fetchone()),
        'example_docs':[dict(r) for r in db.execute("SELECT id,body FROM documents WHERE id IN (1,108)")]},ensure_ascii=True))
