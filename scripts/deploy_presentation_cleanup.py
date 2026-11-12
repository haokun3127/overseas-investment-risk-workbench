"""Deploy reading/metadata fixes; preserve all source and analysis rows."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/presentation-audit-20261112'
STAGE='/opt/rag-workbench/presentation-cleanup-20261112'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138']
FILES=['app/presentation.py','app/ingest.py','app/enrich.py','app/retrieval.py',
       'app/main.py','app/consultation.py','app/drafting.py','app/meeting.py','app/websearch.py',
       'web/app.js','web/knowledge.js','web/workspace.js','web/workflows.js',
       'web/meeting.js','web/consultation.js','web/websearch.js','web/evidence.js',
       'web/index.html','web/overview-classic.css','scripts/clean_remaining_presentation.py']


def run():
    tests=ET.parse(QA/'full-regression.xml').getroot()
    retest=ET.parse(QA/'final-targeted-regression.xml').getroot()
    assert not list(retest.iter('failure')) and not list(retest.iter('error'))
    for filename in ('web-presentation-regression.xml','permissions-regression.xml'):
        additional=ET.parse(QA/filename).getroot()
        assert not list(additional.iter('failure')) and not list(additional.iter('error'))
    failed={(c.get('classname'),c.get('name')) for c in tests.iter('testcase')
            if c.find('failure') is not None or c.find('error') is not None}
    passed={(c.get('classname'),c.get('name')) for c in retest.iter('testcase')
            if c.find('skipped') is None}
    assert failed<=passed,'Every full-suite failure must have a passing final retest'
    assert json.loads((QA/'case-by-case-verification.json').read_text(encoding='utf-8'))['passed']==19
    subprocess.run(['node','tests/reading_presentation.cjs'],cwd=ROOT,check=True)
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    subprocess.run(SSH+['mkdir -m 700 -p '+STAGE+'/app '+STAGE+'/web '+STAGE+'/scripts'],check=True)
    for name in FILES:
        subprocess.run(['scp','-q',str(ROOT/name),'root@47.108.51.138:'+STAGE+'/'+name],check=True)
    code=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(STAGE);root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench')
previous=(root/'current').resolve();release=root/'releases/20261112-workflow-r5'
backup=root/'backups/pre-20261112-presentation-cleanup'
assert str(previous)=='/opt/rag-workbench/releases/20261112-workflow-r4'
assert not release.exists() and not backup.exists()
for name,want in HASHES.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==want
shutil.copytree(previous,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in HASHES:
 target=release/name;target.parent.mkdir(exist_ok=True);shutil.copy2(stage/name,target)
subprocess.run([sys.executable,'-m','py_compile',*[str(release/n) for n in HASHES if n.endswith('.py')]],check=True)
def preserved(db):
 result={}
 for table in ('analyses','events','jobs','chunks','review_history','companies'):
  result[table]=hashlib.sha256(json.dumps(db.execute('SELECT * FROM '+table+' ORDER BY id').fetchall(),ensure_ascii=False).encode()).hexdigest()
 result['source_text']=hashlib.sha256(json.dumps(db.execute('SELECT id,body,digest,company_id,date FROM documents ORDER BY id').fetchall(),ensure_ascii=False).encode()).hexdigest()
 return result
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
switched=False
try:
 with sqlite3.connect(data/'risk.db') as db:
  assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone(),'Analysis job active'
  assert not db.execute("SELECT 1 FROM web_runs WHERE status IN ('queued','running')").fetchone(),'Web job active'
  before=preserved(db);backup.mkdir(mode=0o700)
  with sqlite3.connect(backup/'risk.db') as saved:db.backup(saved)
 sys.path.insert(0,str(release))
 from app.store import Store,now
 from scripts.clean_remaining_presentation import apply
 store=Store(data);result=apply(store)
 with store.db() as db:
  db.execute("INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,NULL)",
             ('presentation_cleaned','Preparation markers removed from summaries and reading views; source citations retained',now()))
 with sqlite3.connect(data/'risk.db') as db:
  assert preserved(db)==before,'Source or analysis rows changed'
  assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
 link=root/'current-presentation.next';assert not link.exists();link.symlink_to(release);os.replace(link,root/'current');switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(25):
  try:
   health=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health',timeout=2))
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=2))
   if health.get('status')=='ok' and version.get('version')=='20261112-workflow-r5':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('Release health verification failed')
 result.update(release=version['version'],backup=str(backup/'risk.db'),
               sources_and_analysis_preserved=True,model_execution_on_server=False,health=health)
 (stage/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  link=root/'current-presentation.rollback';link.symlink_to(previous);os.replace(link,root/'current')
 if (backup/'risk.db').exists():
  with sqlite3.connect(backup/'risk.db') as src,sqlite3.connect(data/'risk.db') as dst:src.backup(dst)
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''.replace('HASHES',repr(hashes)).replace('STAGE',repr(STAGE))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=90)
    (QA/'deployment.log').write_bytes(result.stdout+result.stderr)
    print(result.stdout.decode(errors='replace'));print(result.stderr.decode(errors='replace'))
    result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+STAGE+'/result.json',str(QA/'deployment.json')],check=True)


if __name__=='__main__':
    run()
