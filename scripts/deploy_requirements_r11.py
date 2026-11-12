"""Ship r11 display cleanup and fill the 19 reference-case dates from their case files."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/requirements-audit-20261112'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138']
STAGE='/opt/rag-workbench/requirements-r11-20261112'
FILES=['app/main.py','app/meeting.py','app/presentation.py','web/index.html','web/app.js','web/meeting.js']

REMOTE=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
stage=Path(STAGE);root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench')
previous=(root/'current').resolve();release=root/'releases/20261112-workflow-r11'
backup=root/'backups/pre-20261112-requirements-r11'
assert str(previous)=='/opt/rag-workbench/releases/20261112-workflow-r10'
assert not release.exists() and not backup.exists()
for name,want in HASHES.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==want
shutil.copytree(previous,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in HASHES:shutil.copy2(stage/name,release/name)
TABLES=('documents','chunks','companies','company_users','analyses','events','jobs','review_history',
 'event_changes','document_metadata_changes','drafting_templates','drafting_results',
 'drafting_changes','consultation_reports','web_sources','web_pages','web_runs','settings')
def snapshot(db):
 return {t:hashlib.sha256(json.dumps(db.execute('SELECT * FROM "'+t+'" ORDER BY 1').fetchall(),ensure_ascii=False).encode()).hexdigest() for t in TABLES}
def idle(db):
 assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone(),'Analysis job active'
 assert not db.execute("SELECT 1 FROM web_runs WHERE status IN ('queued','running')").fetchone(),'Web job active'
with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:idle(db)
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True);switched=False;filled=[]
try:
 db=sqlite3.connect(data/'risk.db')
 idle(db);backup.mkdir(mode=0o700)
 with sqlite3.connect(backup/'risk.db') as saved:db.backup(saved)
 before=snapshot(db)
 stamp=time.strftime('%Y-%m-%dT%H:%M:%S+08:00')
 for doc_id,date in PLAN:
  row=db.execute("SELECT date,date_source FROM documents WHERE id=? AND kind='event' AND date=''",(doc_id,)).fetchone()
  if not row:continue
  db.execute("UPDATE documents SET date=?,date_source='provided' WHERE id=?",(date,doc_id))
  db.execute('INSERT INTO document_metadata_changes(document_id,actor,before_json,after_json,reason,created_at) VALUES(?,?,?,?,?,?)',
   (doc_id,'admin',json.dumps({'date':row[0],'date_source':row[1]}),json.dumps({'date':date,'date_source':'provided'}),
    '按事项资料中的发生时间补录资料日期',stamp));filled.append(doc_id)
 db.commit();after=snapshot(db);db.close()
 changed={k for k in before if before[k]!=after[k]}
 assert changed<={'documents','document_metadata_changes'},changed
 link=root/'current-r11.next';assert not link.exists();link.symlink_to(release);os.replace(link,root/'current');switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(25):
  try:
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=2))
   if version.get('version')=='20261112-workflow-r11':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('New release did not become healthy')
 with sqlite3.connect(data/'risk.db') as db:
  assert snapshot(db)==after,'Rows changed after start'
  assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 result={'release':version['version'],'backup':str(backup/'risk.db'),'files':list(HASHES),
  'changed_tables':sorted(changed),'case_dates_filled':filled,'server_model_or_embedding_execution':False}
 (stage/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if filled:
  with sqlite3.connect(backup/'risk.db') as saved, sqlite3.connect(data/'risk.db') as live:saved.backup(live)
 if switched:
  link=root/'current-r11.rollback';link.symlink_to(previous);os.replace(link,root/'current')
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''


def run():
    plan=json.loads((QA/'date-plan.json').read_text())
    for file in FILES:
        if file.endswith('.js'):subprocess.run(['node','--check',file],cwd=ROOT,check=True)
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    subprocess.run(SSH+[f'mkdir -m 700 -p {STAGE}/app {STAGE}/web'],check=True)
    for name in FILES:
        subprocess.run(['scp','-q',str(ROOT/name),'root@47.108.51.138:'+STAGE+'/'+name],check=True)
    code=REMOTE.replace('HASHES',repr(hashes)).replace('STAGE',repr(STAGE)).replace('PLAN',repr(plan))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=120)
    (QA/'deployment.log').write_bytes(result.stdout+result.stderr)
    print(result.stdout.decode(errors='replace'))
    if result.returncode:print(result.stderr.decode(errors='replace'))
    result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+STAGE+'/result.json',str(QA/'deployment.json')],check=True)


if __name__=='__main__':
    run()
