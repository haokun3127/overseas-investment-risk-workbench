"""Ship r12 (legal retrieval + withheld unverifiable citations) and append the locally built statutes and re-analyses.

Only rows created locally above the production maxima are appended; existing rows, reviews and history are untouched.
No model, embedding or batch work runs on the server: the 79 statute vectors were computed locally.
"""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'qa/legal-import-20261112'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'root@47.108.51.138']
STAGE = '/opt/rag-workbench/legal-r12-20261112'
FILES = ['app/jobs.py', 'app/model.py', 'app/retrieval.py', 'app/meeting.py', 'web/index.html']
DATA = {'replica-risk.db': WORK / 'replica/risk.db', 'replica-vectors.db': WORK / 'replica/vectors.db'}

REMOTE = r'''
import hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
import sqlite_vec
stage=Path(STAGE);root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench')
previous=(root/'current').resolve();release=root/'releases/20261112-workflow-r12'
backup=root/'backups/pre-20261112-legal-r12'
assert str(previous)=='/opt/rag-workbench/releases/20261112-workflow-r11'
assert not release.exists() and not backup.exists()
for name,want in HASHES.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==want,name
BASE={'documents':108,'chunks':542,'jobs':42,'analyses':42,'events':36,'audit':129}
shutil.copytree(previous,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in HASHES:
 if name.startswith(('app/','web/')):shutil.copy2(stage/name,release/name)
def maxima(db):return {t:db.execute('SELECT COALESCE(MAX(rowid),0) FROM "'+t+'"').fetchone()[0] for t in BASE}
def digest(db,t,limit):return hashlib.sha256(json.dumps(db.execute('SELECT * FROM "'+t+'" WHERE rowid<=? ORDER BY rowid',(limit,)).fetchall(),ensure_ascii=False).encode()).hexdigest()
with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
 assert maxima(db)==BASE,maxima(db)
 assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone()
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True);switched=False;written=False
try:
 backup.mkdir(mode=0o700)
 for n in ('risk.db','vectors.db'):
  with sqlite3.connect(data/n) as live, sqlite3.connect(backup/n) as saved:live.backup(saved)
 db=sqlite3.connect(data/'risk.db');assert maxima(db)==BASE
 old={t:digest(db,t,BASE[t]) for t in BASE};old_reviews=db.execute('SELECT * FROM review_history').fetchall()
 db.execute('ATTACH ? AS r',(str(stage/'replica-risk.db'),))
 added={}
 for t in ('documents','chunks','jobs','analyses','events','audit'):
  cols=[c[1] for c in db.execute('PRAGMA main.table_info("'+t+'")')];lst=','.join('"'+c+'"' for c in cols)
  cur=db.execute('INSERT INTO main."'+t+'"('+lst+') SELECT '+lst+' FROM r."'+t+'" WHERE rowid>? ORDER BY rowid',(BASE[t],));added[t]=cur.rowcount
 db.commit();written=True
 assert {t:digest(db,t,BASE[t]) for t in BASE}==old and db.execute('SELECT * FROM review_history').fetchall()==old_reviews
 assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok';db.execute('DETACH r');db.close()
 v=sqlite3.connect(data/'vectors.db');v.enable_load_extension(True);sqlite_vec.load(v)
 v.execute('ATTACH ? AS r',(str(stage/'replica-vectors.db'),))
 assert v.execute("SELECT value FROM meta WHERE key='model'").fetchone()==v.execute("SELECT value FROM r.meta WHERE key='model'").fetchone()
 rows=v.execute('SELECT chunk_id,embedding,owner FROM r.chunk_vec WHERE chunk_id>542 ORDER BY chunk_id').fetchall()
 v.executemany('INSERT INTO chunk_vec(chunk_id,embedding,owner) VALUES(?,?,?)',rows)
 v.execute('INSERT INTO chunk_index SELECT * FROM r.chunk_index WHERE chunk_id>542')
 v.commit();added['vectors']=len(rows)
 v.execute('DETACH r');v.close()
 link=root/'current-r12.next';link.symlink_to(release);os.replace(link,root/'current');switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(30):
  try:
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=2))
   if version.get('version')=='20261112-workflow-r12':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('New release did not become healthy')
 result={'release':version['version'],'backup':str(backup),'added':added,'server_model_or_embedding_execution':False}
 (stage/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'])
 if written or (backup/'vectors.db').exists():
  for n in ('risk.db','vectors.db'):
   if (backup/n).exists():
    with sqlite3.connect(backup/n) as saved, sqlite3.connect(data/n) as live:saved.backup(live)
 if switched:
  link=root/'current-r12.rollback';link.symlink_to(previous);os.replace(link,root/'current')
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''


def run():
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}
    hashes.update({name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in DATA.items()})
    subprocess.run(SSH + [f'mkdir -m 700 -p {STAGE}/app {STAGE}/web'], check=True)
    for name in FILES:
        subprocess.run(['scp', '-q', str(ROOT / name), f'root@47.108.51.138:{STAGE}/{name}'], check=True)
    for name, path in DATA.items():
        subprocess.run(['scp', '-q', str(path), f'root@47.108.51.138:{STAGE}/{name}'], check=True)
    code = REMOTE.replace('HASHES', repr(hashes)).replace('STAGE', repr(STAGE))
    result = subprocess.run(SSH + ['/opt/rag-workbench/venv/bin/python -'], input=code.encode(), capture_output=True, timeout=180)
    (WORK / 'deployment.log').write_bytes(result.stdout + result.stderr)
    print(result.stdout.decode(errors='replace'))
    if result.returncode:
        print(result.stderr.decode(errors='replace'))
    result.check_returncode()
    subprocess.run(['scp', '-q', f'root@47.108.51.138:{STAGE}/result.json', str(WORK / 'deployment.json')], check=True)


if __name__ == '__main__':
    run()
