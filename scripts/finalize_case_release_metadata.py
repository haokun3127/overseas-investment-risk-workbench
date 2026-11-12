import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1];qa=root/'qa/local-replay-20261112'
r=ET.parse(qa/'release-final.xml').getroot()
assert not list(r.iter('failure')) and not list(r.iter('error'))
code='''
import hashlib,json,os
from pathlib import Path
release=Path('/opt/rag-workbench/current').resolve()
assert release.name=='20261112-workflow-r3'
p=release/'web/index.html';before=p.read_text(encoding='utf-8')
old='name="app-version" content="20261111-workflow-r2"';new='name="app-version" content="20261112-workflow-r3"'
assert before.count(old)==1
backup=Path('/opt/rag-workbench/backups/pre-20261112-local-cases/index-before-meta.html')
assert not backup.exists();backup.write_bytes(p.read_bytes())
after=before.replace(old,new);tmp=release/'web/index-meta.next';tmp.write_text(after,encoding='utf-8');os.replace(tmp,p)
result={'html_version':'20261112-workflow-r3','only_meta_changed':after.replace(new,old)==before,'backup':str(backup),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
Path('/opt/rag-workbench/local-promotion-20261112/metadata-fix.json').write_text(json.dumps(result));print(json.dumps(result))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@47.108.51.138','python3 -'],input=code.encode(),capture_output=True,timeout=30)
print(result.stdout.decode());print(result.stderr.decode());result.check_returncode()
(qa/'metadata-fix.json').write_bytes(result.stdout)
