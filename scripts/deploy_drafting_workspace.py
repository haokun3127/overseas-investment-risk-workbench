"""Publish drafting r8. Model tests remain local; production business data is preserved."""
import hashlib
import json
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/drafting-workspace-20261112'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138']
STAGE='/opt/rag-workbench/drafting-workspace-20261112'
FILES=['app/drafting.py','app/drafting_word.py','app/quantities.py','app/meeting.py',
       'web/drafting.js','web/drafting.css','web/meeting.js','web/index.html']


def run():
    for filename in ('full.xml','final-regression.xml'):
        report=ET.parse(QA/filename).getroot()
        assert not list(report.iter('failure')) and not list(report.iter('error'))
    for filename in ('ui-result.json','real-model.json'):
        assert json.loads((QA/filename).read_text(encoding='utf-8'))['passed']
    word=json.loads((QA/'word-validation.json').read_text(encoding='utf-8'))
    assert word['content_and_structure_passed']
    subprocess.run(['node','--check','web/drafting.js'],cwd=ROOT,check=True)
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    subprocess.run(SSH+[f'mkdir -m 700 -p {STAGE}/app {STAGE}/web'],check=True)
    for name in FILES:subprocess.run(['scp','-q',str(ROOT/name),'root@47.108.51.138:'+STAGE+'/'+name],check=True)
    code=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
stage=Path(STAGE);root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench')
previous=(root/'current').resolve();release=root/'releases/20261112-workflow-r8'
backup=root/'backups/pre-20261112-drafting-workspace'
assert str(previous)=='/opt/rag-workbench/releases/20261112-workflow-r7'
assert not release.exists() and not backup.exists()
for name,want in HASHES.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==want
shutil.copytree(previous,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in HASHES:shutil.copy2(stage/name,release/name)
tables=('documents','chunks','companies','company_users','analyses','events','jobs','review_history',
        'event_changes','document_metadata_changes','drafting_templates','drafting_results',
        'drafting_changes','consultation_reports','web_sources','web_pages','web_runs','settings')
def snapshot(db,columns):
 return {t:hashlib.sha256(json.dumps(db.execute('SELECT '+','.join('"'+c+'"' for c in columns[t])+
        ' FROM "'+t+'" ORDER BY 1').fetchall(),ensure_ascii=False).encode()).hexdigest() for t in tables}
def idle(db):
 assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone(),'Analysis job active'
 assert not db.execute("SELECT 1 FROM web_runs WHERE status IN ('queued','running')").fetchone(),'Web job active'
with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:idle(db)
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True);switched=False
try:
 with sqlite3.connect(data/'risk.db') as db:
  idle(db);columns={t:[r[1] for r in db.execute('PRAGMA table_info("'+t+'")')] for t in tables}
  before=snapshot(db,columns);backup.mkdir(mode=0o700)
  with sqlite3.connect(backup/'risk.db') as saved:db.backup(saved)
 link=root/'current-drafting.next';assert not link.exists();link.symlink_to(release);os.replace(link,root/'current');switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(25):
  try:
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=2))
   if version.get('version')=='20261112-workflow-r8':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('Drafting release did not become healthy')
 with sqlite3.connect(data/'risk.db') as db:
  assert snapshot(db,columns)==before,'Existing business values changed'
  assert 'context_json' in [r[1] for r in db.execute('PRAGMA table_info(drafting_results)')]
  assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 result={'release':version['version'],'business_values_unchanged':True,'backup':str(backup/'risk.db'),
         'files':list(HASHES),'migration':'drafting_results.context_json added with empty default',
         'server_model_or_embedding_execution':False}
 (stage/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  link=root/'current-drafting.rollback';link.symlink_to(previous);os.replace(link,root/'current')
 # The additive column is compatible with r7. Never overwrite concurrent business data.
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''.replace('HASHES',repr(hashes)).replace('STAGE',repr(STAGE))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=100)
    (QA/'deployment.log').write_bytes(result.stdout+result.stderr)
    print(result.stdout.decode(errors='replace'))
    if result.returncode:print(result.stderr.decode(errors='replace'))
    result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+STAGE+'/result.json',str(QA/'deployment.json')],check=True)


if __name__=='__main__':run()
