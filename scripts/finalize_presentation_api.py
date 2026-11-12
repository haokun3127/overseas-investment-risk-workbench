"""Finish the read-only historical website metadata fix in the verified release."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/presentation-audit-20261112'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138']
STAGE='/opt/rag-workbench/presentation-cleanup-20261112'


def run():
    report=ET.parse(QA/'web-presentation-regression.xml').getroot()
    assert not list(report.iter('failure')) and not list(report.iter('error'))
    source=ROOT/'app/websearch.py'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    subprocess.run(['scp','-q',str(source),'root@47.108.51.138:'+STAGE+'/app/websearch.py'],check=True)
    code=r'''
import hashlib,json,os,py_compile,shutil,subprocess,time,urllib.request
from pathlib import Path
stage=Path(STAGE);release=Path('/opt/rag-workbench/current').resolve()
assert release.name=='20261112-workflow-r5'
source=stage/'app/websearch.py';target=release/'app/websearch.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==DIGEST
py_compile.compile(str(source),doraise=True)
saved=Path('/opt/rag-workbench/backups/pre-20261112-presentation-cleanup/websearch.py')
assert not saved.exists();shutil.copy2(target,saved)
subprocess.run(['systemctl','stop','rag-workbench.service'],check=True)
try:
 staged=target.with_suffix('.next');shutil.copy2(source,staged);os.replace(staged,target)
 subprocess.run(['systemctl','start','rag-workbench.service'],check=True)
 for _ in range(20):
  try:
   health=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health',timeout=2))
   if health.get('status')=='ok':break
  except (OSError,ValueError):pass
  time.sleep(1)
 else:raise RuntimeError('Health verification failed')
 print(json.dumps({'website_history_metadata_fixed':True,'source_sha256':DIGEST,'health':health,'model_execution_on_server':False}))
except BaseException:
 shutil.copy2(saved,target)
 subprocess.run(['systemctl','restart','rag-workbench.service'],check=True)
 raise
'''.replace('STAGE',repr(STAGE)).replace('DIGEST',repr(digest))
    done=subprocess.run(SSH+['/opt/rag-workbench/venv/bin/python -'],input=code.encode(),capture_output=True,timeout=60)
    print(done.stdout.decode(errors='replace'));print(done.stderr.decode(errors='replace'))
    done.check_returncode()
    result=json.loads(done.stdout)
    (QA/'website-metadata-deployment.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':
    run()
