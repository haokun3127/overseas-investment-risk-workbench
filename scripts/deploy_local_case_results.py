"""Small transactional data promotion and model-protocol fix; no server model tests."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/local-replay-20261112'
STAGE='/opt/rag-workbench/local-promotion-20261112'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138']

def run():
    reports=[ET.parse(QA/name).getroot() for name in ('regression.xml','regression-fixes.xml','protocol-final.xml')]
    # Require an explicit passing retest for every failure in the full run.
    suites=[s for r in reports for s in (list(r) if r.tag!='testsuite' else [r])]
    assert sum(int(s.attrib.get('tests',0)) for s in suites)>=383
    failures=[case.attrib['name'] for r in reports for case in r.iter('testcase') if case.find('failure') is not None or case.find('error') is not None]
    passed=set()
    for fixed in reports[1:]:
        assert not list(fixed.iter('failure')) and not list(fixed.iter('error'))
        passed.update(c.attrib['name'] for c in fixed.iter('testcase') if c.find('skipped') is None)
    assert set(failures)<=passed,failures
    assert json.loads((QA/'promotion-check.json').read_text())['old_rows_preserved']
    files=[ROOT/'app/model.py',ROOT/'app/meeting.py',ROOT/'web/index.html',ROOT/'scripts/local_case_sync.py',QA/'case-sync-plan.json']
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    subprocess.run(SSH+['mkdir -m 700 -p '+STAGE],check=True)
    subprocess.run(['scp','-q',*[str(p) for p in files],'root@47.108.51.138:'+STAGE+'/'],check=True)
    code=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(STAGE);root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench');current=root/'current'
previous=current.resolve();release=root/'releases/20261112-workflow-r3';backup=root/'backups/pre-20261112-local-cases'
assert str(previous)=='/opt/rag-workbench/releases/20261111-workflow-r2'
assert not release.exists() and not backup.exists()
for name,want in HASHES.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==want
shutil.copytree(previous,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in ('model.py','meeting.py'):shutil.copy2(stage/name,release/'app'/name)
shutil.copy2(stage/'index.html',release/'web/index.html')
subprocess.run([sys.executable,'-m','py_compile',str(release/'app/model.py'),str(release/'app/meeting.py')],check=True)
sys.path.insert(0,str(stage));from local_case_sync import apply
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
switched=False
try:
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  assert not db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone(),'Analysis job active'
  assert not db.execute("SELECT 1 FROM web_runs WHERE status IN ('queued','running')").fetchone(),'Web job active'
 backup.mkdir(mode=0o700)
 result=apply(stage/'case-sync-plan.json',data/'risk.db',backup/'risk.db')
 link=root/'current-local-cases.next';assert not link.exists();link.symlink_to(release);os.replace(link,current);switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(30):
  try:
   health=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health',timeout=2))
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=2))
   if health.get('status')=='ok' and version.get('version')=='20261112-workflow-r3':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('Release health verification failed')
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('companies','documents','chunks','analyses','events','jobs','review_history')}
 result.update(release=str(release),previous=str(previous),health=health,version=version,counts=counts,source_hashes=HASHES)
 (stage/'deployment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  link=root/'current-local-cases.rollback';link.symlink_to(previous);os.replace(link,current)
 if (backup/'risk.db').exists():
  with sqlite3.connect(backup/'risk.db') as src,sqlite3.connect(data/'risk.db') as dst:src.backup(dst)
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''.replace('HASHES',repr(hashes)).replace('STAGE',repr(STAGE))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=90)
    (QA/'deployment.log').write_bytes(result.stdout+result.stderr)
    print(result.stdout.decode(errors='replace'));print(result.stderr.decode(errors='replace'));result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+STAGE+'/deployment.json',str(QA/'deployment.json')],check=True)

if __name__=='__main__':run()
