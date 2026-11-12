"""Promote the exact Linux-tested archive with database backup and audited grade conversion."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from scripts.meeting_verification import QA, REMOTE, SSH


def run():
    report = ET.parse(QA/'linux-test.xml').getroot()
    suites = [report] if report.tag == 'testsuite' else list(report)
    assert sum(int(s.attrib.get('tests', 0)) for s in suites) >= 375
    assert all(int(s.attrib.get(k, 0)) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    archive = QA/'candidate.tar.gz'
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    # Do not rebuild: this is the archive used by the passing Linux test run.
    code = r'''
import hashlib,json,os,shutil,sqlite3,subprocess,tarfile,time,urllib.request
from pathlib import Path
root=Path('/opt/rag-workbench');data=Path('/var/lib/rag-workbench');current=root/'current'
previous=current.resolve();stage=Path(REMOTE)
release=root/'releases/20261111-workflow-r1';backup=root/'backups/pre-20261111-workflow-r1'
assert str(previous)=='/opt/rag-workbench/releases/20261111-legal-knowledge-r1'
assert not release.exists() and not backup.exists()
assert hashlib.sha256((stage/'candidate.tar.gz').read_bytes()).hexdigest()==DIGEST
mapping={'lv4':'lv3','lv5':'non_risk','red':'lv1','orange':'lv2','yellow':'lv3'}
def state():
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  for table in ('jobs','web_runs'):
   assert db.execute("SELECT count(*) FROM "+table+" WHERE status IN ('queued','running')").fetchone()[0]==0,table+' active'
  tables=['companies','documents','chunks','analyses','events','jobs','web_sources','web_pages','review_history']
  return {t:{'columns':[r[1] for r in db.execute('PRAGMA table_info('+t+')')], 'rows':db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall()} for t in tables}
state();release.mkdir()
with tarfile.open(stage/'candidate.tar.gz') as tar:
 for m in tar.getmembers():assert m.isfile() and (release/m.name).resolve().is_relative_to(release.resolve())
 tar.extractall(release)
(release/'release.sha256').write_text(DIGEST+'\n')
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
switched=False
try:
 before=state();backup.mkdir(mode=0o700)
 for name in ('risk.db','vectors.db'):
  if (data/name).exists():
   with sqlite3.connect(data/name) as src,sqlite3.connect(backup/name) as dst:src.backup(dst)
 for folder in ('uploads','reference-data','reference-copies','archive-copies'):
  if (data/folder).exists():shutil.copytree(data/folder,backup/folder)
 link=root/'current-meeting.next';assert not link.exists();link.symlink_to(release);os.replace(link,current);switched=True
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 healthy=False
 for _ in range(45):
  try:
   health=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health',timeout=3))
   version=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/release',timeout=3))
   if health.get('status')=='ok' and version.get('version')=='20261111-workflow-r1':healthy=True;break
  except (OSError,ValueError):pass
  time.sleep(1)
 assert healthy,'Health or release verification failed'
 preserved={};migrated=[]
 with sqlite3.connect('file:'+str(data/'risk.db')+'?mode=ro',uri=True) as db:
  for table,old in before.items():
   columns=','.join('"'+col+'"' for col in old['columns'])
   after=db.execute('SELECT '+columns+' FROM '+table+' ORDER BY rowid').fetchall()
   indexed={row[0]:row for row in after}
   for row in old['rows']:
    expected=list(row)
    if table=='events':
     grade=old['columns'].index('level');old_grade=row[grade]
     if old_grade in mapping:
      expected[grade]=mapping[old_grade]
      if 'revision' in old['columns']:
       revision=old['columns'].index('revision');expected[revision]+=1
      audit=db.execute("SELECT before_json,after_json FROM event_changes WHERE event_id=? AND action='standard_migration'",(row[0],)).fetchall()
      assert len(audit)==1 and json.loads(audit[0][0])['level']==old_grade and json.loads(audit[0][1])['level']==mapping[old_grade]
      migrated.append({'id':row[0],'before':old_grade,'after':mapping[old_grade]})
    assert indexed.get(row[0])==tuple(expected),(table,row[0])
   assert table=='chunks' or len(after)==len(old['rows']),table
   preserved[table]={'before':len(old['rows']),'after':len(after),'preserved_except_authorized_grades':True}
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
  assert db.execute("SELECT count(*) FROM events WHERE level IN ('lv4','lv5','red','orange','yellow')").fetchone()[0]==0
 result={'release':str(current.resolve()),'backup':str(backup),'previous':str(previous),'sha256':DIGEST,'tables':preserved,'migrated':migrated,'health':health,'version':version}
 (stage/'deployment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False))
except BaseException:
 subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
 if switched:
  rollback=root/'current-meeting.rollback';rollback.symlink_to(previous);os.replace(rollback,current)
  for name in ('risk.db','vectors.db'):
   if (backup/name).exists():
    with sqlite3.connect(backup/name) as src,sqlite3.connect(data/name) as dst:src.backup(dst)
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 raise
'''.replace('REMOTE', repr(REMOTE)).replace('DIGEST', repr(digest))
    result=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=180)
    (QA/'deployment-log.txt').write_bytes(result.stdout+result.stderr)
    print((result.stdout+result.stderr).decode(errors='replace'))
    result.check_returncode()
    subprocess.run(['scp','-q','root@47.108.51.138:'+REMOTE+'/deployment.json',str(QA/'deployment.json')],check=True)


if __name__=='__main__':run()
