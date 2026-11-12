"""Deploy only after verified Linux tests, backing up data and preserving pre-existing rows."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from scripts.legal_verification import QA,REMOTE,SSH,package

def run():
    report=ET.parse(QA/'linux-test.xml').getroot()
    suites=[report] if report.tag=='testsuite' else list(report)
    assert sum(int(s.attrib.get('tests',0)) for s in suites)>=364
    assert all(int(s.attrib.get(k,0))==0 for s in suites for k in ('failures','errors','skipped'))
    path=package();digest=hashlib.sha256(path.read_bytes()).hexdigest()
    subprocess.run(['scp','-q',str(path),'root@47.108.51.138:'+REMOTE+'/candidate.tar.gz'],check=True)
    code=r'''
import hashlib,json,os,shutil,sqlite3,subprocess,tarfile,time,urllib.request
from pathlib import Path
root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench');current=root/'current'
previous=current.resolve();stage=Path(REMOTE)
release=root/'releases/20261111-legal-knowledge-r1';backup=root/'backups/pre-20261111-legal-knowledge-r1'
assert str(previous)=='/opt/rag-workbench/releases/20261111-workbench-verified-r2'
assert not release.exists() and not backup.exists()
assert hashlib.sha256((stage/'candidate.tar.gz').read_bytes()).hexdigest()==DIGEST
def state():
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]==0
  assert db.execute("SELECT count(*) FROM web_runs WHERE status IN ('queued','running')").fetchone()[0]==0
  tables=['companies','documents','chunks','analyses','events','jobs','web_sources','web_pages','review_history']
  return {t:{'columns':[r[1] for r in db.execute('PRAGMA table_info('+t+')')], 'rows':db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall()} for t in tables}
before=state();release.mkdir()
with tarfile.open(stage/'candidate.tar.gz') as tar:
 for member in tar.getmembers():
  assert member.isfile() and (release/member.name).resolve().is_relative_to(release.resolve())
 tar.extractall(release)
(release/'release.sha256').write_text(DIGEST+'\n')
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
switched=False
try:
 before=state();backup.mkdir(mode=0o700)
 for name in ('risk.db','vectors.db'):
  if (data/name).exists():
   with sqlite3.connect(data/name) as src,sqlite3.connect(backup/name) as dst: src.backup(dst)
 for folder in ('uploads','reference-data','reference-copies','archive-copies'):
  if (data/folder).exists():shutil.copytree(data/folder,backup/folder)
 link=root/'current-legal.next';assert not link.exists();link.symlink_to(release);os.replace(link,current);switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 healthy=False
 for _ in range(40):
  try:
   health=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health',timeout=3))
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=3))
   if health.get('status')=='ok' and version.get('version')=='20261111-legal-knowledge-r1':healthy=True;break
  except (OSError,ValueError): pass
  time.sleep(1)
 assert healthy, 'Health or release verification failed'
 preserved={}
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  for table,old in before.items():
   columns=','.join('"'+col+'"' for col in old['columns'])
   after=db.execute('SELECT '+columns+' FROM '+table+' ORDER BY rowid').fetchall()
   # Existing chunks keep IDs, locators, text; legal tags/new fragments are additive only.
   indexed={row[0]:row for row in after}
   assert all(indexed.get(row[0])==row for row in old['rows']), table
   assert table=='chunks' or len(after)==len(old['rows']),table
   preserved[table]={'before':len(old['rows']),'after':len(after),'existing_rows_unchanged':True}
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
 result={'release':str(current.resolve()),'backup':str(backup),'previous':str(previous),'sha256':DIGEST,'tables':preserved,'health':health,'version':version}
 (stage/'deployment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  rollback=root/'current-legal.rollback';rollback.symlink_to(previous);os.replace(rollback,current)
  for name in ('risk.db','vectors.db'):
   if (backup/name).exists():
    with sqlite3.connect(backup/name) as src,sqlite3.connect(data/name) as dst:src.backup(dst)
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''.replace('REMOTE',repr(REMOTE)).replace('DIGEST',repr(digest))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=180)
    (QA/'deployment-log.txt').write_bytes(result.stdout+result.stderr)
    print((result.stdout+result.stderr).decode(errors='replace'))
    result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+REMOTE+'/deployment.json',str(QA/'deployment.json')],check=True)

if __name__=='__main__': run()
