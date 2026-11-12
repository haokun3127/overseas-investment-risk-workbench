"""Read only presentation fields; do not export private bodies or credentials."""
import json
from pathlib import Path
import sqlite3

folder=Path('/opt/rag-workbench/verification-followup-20261111')
with sqlite3.connect('file:/var/lib/rag-workbench/risk.db?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    result={table:[dict(r) for r in db.execute('SELECT '+','.join(columns)+' FROM '+table+' ORDER BY id')]
            for table,columns in [('documents',['id','title','source']),('web_sources',['id','name']),
                                  ('web_pages',['id','title']),('events',['id','title'])]}
(folder/'name-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({t:len(rows) for t,rows in result.items()}))
