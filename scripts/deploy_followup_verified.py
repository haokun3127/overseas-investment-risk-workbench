"""Publish the tested release and reviewed presentation metadata, with rollback."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from scripts.meeting_verification import QA,REMOTE,SSH


def run():
    report=ET.parse(QA/'linux-test.xml').getroot()
    suites=[report] if report.tag=='testsuite' else list(report)
    assert sum(int(s.attrib.get('tests',0)) for s in suites)>=380
    assert all(int(s.attrib.get(k,0))==0 for s in suites for k in ('failures','errors','skipped'))
    digest=hashlib.sha256((QA/'candidate.tar.gz').read_bytes()).hexdigest()
    plan_digest=hashlib.sha256((QA/'material-plan.json').read_bytes()).hexdigest()
    subprocess.run(['scp','-q',str(QA/'material-plan.json'),'root@47.108.51.138:'+REMOTE+'/material-plan.json'],check=True)
    code=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,sys,tarfile,time,urllib.request
from pathlib import Path
root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench');current=root/'current';stage=Path(REMOTE)
previous=current.resolve();release=root/'releases/20261111-workflow-r2';backup=root/'backups/pre-20261111-workflow-r2'
assert str(previous)=='/opt/rag-workbench/releases/20261111-workflow-r1'
assert not release.exists() and not backup.exists()
assert hashlib.sha256((stage/'candidate.tar.gz').read_bytes()).hexdigest()==DIGEST
assert hashlib.sha256((stage/'material-plan.json').read_bytes()).hexdigest()==PLAN_DIGEST
plan=json.loads((stage/'material-plan.json').read_text());tables=['companies','documents','chunks','analyses','events','jobs','web_sources','web_pages','review_history']
def snapshot():
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  for table in ('jobs','web_runs'):
   assert not db.execute("SELECT count(*) FROM "+table+" WHERE status IN ('queued','running')").fetchone()[0],table+' active'
  return {t:{'columns':[r[1] for r in db.execute('PRAGMA table_info('+t+')')], 'rows':db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall()} for t in tables}
snapshot();release.mkdir()
with tarfile.open(stage/'candidate.tar.gz') as tar:
 for m in tar.getmembers():assert m.isfile() and (release/m.name).resolve().is_relative_to(release.resolve())
 tar.extractall(release)
(release/'release.sha256').write_text(DIGEST+'\n')
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True);switched=False
try:
 before=snapshot();backup.mkdir(mode=0o700)
 for name in ('risk.db','vectors.db'):
  if (data/name).exists():
   with sqlite3.connect(data/name) as src,sqlite3.connect(backup/name) as dst:src.backup(dst)
 for folder in ('uploads','reference-data','reference-copies','archive-copies'):
  if (data/folder).exists():shutil.copytree(data/folder,backup/folder)
 sys.path.insert(0,str(release))
 from app.store import Store
 from scripts.apply_meeting_materials import apply
 applied=apply(Store(data),plan)
 assert len(applied['changed'])==66 and not applied['skipped_concurrent_edits'],'Concurrent edits: abort for fresh review'
 link=root/'current-followup.next';assert not link.exists();link.symlink_to(release);os.replace(link,current);switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 healthy=False
 for _ in range(45):
  try:
   health=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health',timeout=3))
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=3))
   if health.get('status')=='ok' and version.get('version')=='20261111-workflow-r2':healthy=True;break
  except (OSError,ValueError):pass
  time.sleep(1)
 assert healthy,'Health or version verification failed'
 allowed={'documents':{'title','source','legal_meta','legal_revision'},'web_sources':{'name'},'web_pages':{'title'},'events':{'title'}}
 counts={}
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  for table,old in before.items():
   columns=','.join('"'+c+'"' for c in old['columns']);after=db.execute('SELECT '+columns+' FROM '+table+' ORDER BY rowid').fetchall()
   assert len(after)==len(old['rows']),(table,'count changed')
   for a,b in zip(old['rows'],after):
    for col,x,y in zip(old['columns'],a,b):
     assert x==y or col in allowed.get(table,set()),(table,a[0],col)
   counts[table]=len(after)
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
  assert db.execute('SELECT count(*) FROM material_changes').fetchone()[0]==66
 result={'release':str(current.resolve()),'previous':str(previous),'backup':str(backup),'sha256':DIGEST,'plan_sha256':PLAN_DIGEST,'counts':counts,'materials':len(applied['changed']),'names_cleaned':len(applied['names_cleaned']),'health':health,'version':version,'body_chunks_analyses_preserved':True}
 (stage/'deployment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  link=root/'current-followup.rollback';link.symlink_to(previous);os.replace(link,current)
 if backup.exists():
  for name in ('risk.db','vectors.db'):
   if (backup/name).exists():
    with sqlite3.connect(backup/name) as src,sqlite3.connect(data/name) as dst:src.backup(dst)
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''.replace('REMOTE',repr(REMOTE)).replace('PLAN_DIGEST',repr(plan_digest)).replace('DIGEST',repr(digest))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=180)
    (QA/'deployment-log.txt').write_bytes(result.stdout+result.stderr)
    print((result.stdout+result.stderr).decode(errors='replace'));result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+REMOTE+'/deployment.json',str(QA/'deployment.json')],check=True)


if __name__=='__main__':run()
