"""Publish a verified narrow release; no production model or embedding jobs."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/requirements-completion-20261112'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138']
FILES=['app/main.py','app/consultation.py','app/document_maintenance.py','app/event_management.py','app/meeting.py',
       'web/app.js','web/companies.js','web/meeting.js','web/legal-knowledge.js','web/consultation.js','web/consultation.css','web/index.html']
STAGE='/opt/rag-workbench/requirements-completion-20261112'


def run():
    for name in ('full-final.xml','permissions-and-flows.xml'):
        report=ET.parse(QA/name).getroot()
        assert not list(report.iter('failure')) and not list(report.iter('error')),name
    assert not json.loads((QA/'ui-result.json').read_text(encoding='utf-8'))['browser_errors']
    assert json.loads((QA/'real-model-smoke.json').read_text(encoding='utf-8'))['passed']
    for name in [f for f in FILES if f.endswith('.js')]:
        subprocess.run(['node','--check',name],cwd=ROOT,check=True)
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    subprocess.run(SSH+[f'mkdir -m 700 -p {STAGE}/app {STAGE}/web'],check=True)
    for name in FILES:
        subprocess.run(['scp','-q',str(ROOT/name),'root@47.108.51.138:'+STAGE+'/'+name],check=True)
    code=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(STAGE);root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench')
previous=(root/'current').resolve();release=root/'releases/20261112-workflow-r6'
backup=root/'backups/pre-20261112-requirements-completion'
assert str(previous)=='/opt/rag-workbench/releases/20261112-workflow-r5'
assert not release.exists() and not backup.exists()
for name,want in HASHES.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==want
shutil.copytree(previous,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in HASHES:
 target=release/name;target.parent.mkdir(exist_ok=True);shutil.copy2(stage/name,target)
subprocess.run([sys.executable,'-m','py_compile',*[str(release/n) for n in HASHES if n.endswith('.py')]],check=True)
tables=('documents','chunks','companies','company_users','analyses','events','jobs','review_history',
        'event_changes','drafting_templates','drafting_results','drafting_changes',
        'consultation_reports','web_sources','web_pages','web_runs')
def preserved(db):
 return {t:hashlib.sha256(json.dumps(db.execute('SELECT * FROM '+t+' ORDER BY id').fetchall(),ensure_ascii=False).encode()).hexdigest() for t in tables}
def no_jobs(db):
 assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone(),'Active analysis job'
 assert not db.execute("SELECT 1 FROM web_runs WHERE status IN ('queued','running')").fetchone(),'Active web run'
with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:no_jobs(db)
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
switched=False
try:
 with sqlite3.connect(data/'risk.db') as db:
  no_jobs(db);before=preserved(db)
  backup.mkdir(mode=0o700)
  with sqlite3.connect(backup/'risk.db') as saved:db.backup(saved)
 link=root/'current-requirements.next';assert not link.exists();link.symlink_to(release);os.replace(link,root/'current');switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(25):
  try:
   health=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health',timeout=2))
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=2))
   if health.get('status')=='ok' and version.get('version')=='20261112-workflow-r6':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('Release health verification failed')
 with sqlite3.connect(data/'risk.db') as db:
  assert before==preserved(db),'Business rows changed during release'
  assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
  assert db.execute("SELECT name FROM sqlite_master WHERE name='document_metadata_changes'").fetchone()
  counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in tables}
 result={'release':version['version'],'health':health,'backup':str(backup/'risk.db'),
         'all_original_business_rows_preserved':True,'tables_verified':list(tables),'counts':counts,
         'new_table':'document_metadata_changes','server_model_or_embedding_execution':False}
 (stage/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  link=root/'current-requirements.rollback';link.symlink_to(previous);os.replace(link,root/'current')
 if (backup/'risk.db').exists():
  with sqlite3.connect(backup/'risk.db') as src,sqlite3.connect(data/'risk.db') as dst:src.backup(dst)
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
