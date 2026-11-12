"""Publish consultation UI assets and version marker, keeping all business rows."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/consultation-ui-20261112'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138']
STAGE='/opt/rag-workbench/consultation-ui-20261112'
FILES=['web/consultation.js','web/consultation.css','web/index.html','app/meeting.py']


def run():
    report=ET.parse(QA/'regression.xml').getroot()
    assert not list(report.iter('failure')) and not list(report.iter('error'))
    assert not json.loads((QA/'ui-result.json').read_text(encoding='utf-8'))['browser_errors']
    subprocess.run(['node','--check','web/consultation.js'],check=True,cwd=ROOT)
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    subprocess.run(SSH+[f'mkdir -m 700 -p {STAGE}/app {STAGE}/web'],check=True)
    for name in FILES:subprocess.run(['scp','-q',str(ROOT/name),'root@47.108.51.138:'+STAGE+'/'+name],check=True)
    code=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
stage=Path(STAGE);root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench')
previous=(root/'current').resolve();release=root/'releases/20261112-workflow-r7'
backup=root/'backups/pre-20261112-consultation-ui'
assert str(previous)=='/opt/rag-workbench/releases/20261112-workflow-r6'
assert not release.exists() and not backup.exists()
for name,want in HASHES.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==want
shutil.copytree(previous,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in HASHES:shutil.copy2(stage/name,release/name)
def snapshot(db):
 tables=('documents','chunks','companies','company_users','analyses','events','jobs','review_history',
         'event_changes','document_metadata_changes','drafting_templates','drafting_results',
         'drafting_changes','consultation_reports','web_sources','web_pages','web_runs','settings')
 return {t:hashlib.sha256(json.dumps(db.execute('SELECT * FROM "'+t+'" ORDER BY 1').fetchall(),ensure_ascii=False).encode()).hexdigest() for t in tables}
def idle(db):
 assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone(),'Analysis job active'
 assert not db.execute("SELECT 1 FROM web_runs WHERE status IN ('queued','running')").fetchone(),'Web job active'
with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:idle(db)
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True);switched=False
try:
 with sqlite3.connect(data/'risk.db') as db:
  idle(db);before=snapshot(db);backup.mkdir(mode=0o700)
  with sqlite3.connect(backup/'risk.db') as saved:db.backup(saved)
 link=root/'current-consultation.next';assert not link.exists();link.symlink_to(release);os.replace(link,root/'current');switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(25):
  try:
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=2))
   if version.get('version')=='20261112-workflow-r7':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('New release did not become healthy')
 with sqlite3.connect(data/'risk.db') as db:
  assert snapshot(db)==before,'Database rows changed'
  assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 result={'release':version['version'],'business_rows_unchanged':True,'backup':str(backup/'risk.db'),
         'files':list(HASHES),'database_migration':False,'server_model_or_embedding_execution':False}
 (stage/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  link=root/'current-consultation.rollback';link.symlink_to(previous);os.replace(link,root/'current')
 # No migration is performed. Existing database is preserved on rollback.
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''.replace('HASHES',repr(hashes)).replace('STAGE',repr(STAGE))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=90)
    (QA/'deployment.log').write_bytes(result.stdout+result.stderr)
    print(result.stdout.decode(errors='replace'))
    if result.returncode:print(result.stderr.decode(errors='replace'))
    result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+STAGE+'/result.json',str(QA/'deployment.json')],check=True)


if __name__=='__main__':run()
