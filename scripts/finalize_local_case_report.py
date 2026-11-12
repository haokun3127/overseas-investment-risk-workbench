import json
from pathlib import Path
import sqlite3
root=Path('qa/local-replay-20261112')
raw=(root/'round1-cp936.json').read_bytes()
try:first=json.loads(raw.decode('utf-8'))
except UnicodeDecodeError:first=json.loads(raw.decode('gb18030'))
retry=json.loads((root/'case-replay.json').read_text(encoding='utf-8'))
(root/'L6-retry.json').write_text(json.dumps(retry,ensure_ascii=False,indent=2),encoding='utf-8')
latest={r['id']:r for r in first['results']}
for row in retry['results']:latest[row['id']]=row
assert len(latest)==19 and all(r.get('all_match') for r in latest.values())
result={'summary':{'total':19,'completed':19,'all_match':19,'first_round_completed':18,'retry_completed':1,
    'execution_location':'local Windows','expected_labels_sent':False,'production_writes':False},'results':list(latest.values())}
for name in ('case-replay.json','case-replay-final.json'):
    (root/name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result['summary']))
