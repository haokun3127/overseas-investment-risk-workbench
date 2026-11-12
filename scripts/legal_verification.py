"""Isolated legal knowledge UI fixture and bounded Linux release verification."""
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa'/'legal-knowledge-20261111'
REMOTE='/opt/rag-workbench/verification-legal-20261111'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','root@47.108.51.138']

def package():
    QA.mkdir(parents=True,exist_ok=True)
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
        for folder in ('app','web','tests','scripts'):
            for file in sorted((ROOT/folder).rglob('*')):
                if not file.is_file() or '__pycache__' in file.parts or file.suffix=='.pyc': continue
                data=file.read_bytes()
                if file.suffix=='.sh': data=data.replace(b'\r\n',b'\n')
                info=tarfile.TarInfo(file.relative_to(ROOT).as_posix());info.size=len(data);info.mode=0o755 if file.suffix=='.sh' else 0o644
                tar.addfile(info,io.BytesIO(data))
    path=QA/'candidate.tar.gz';path.write_bytes(buffer.getvalue())
    return path

def stage():
    path=package()
    subprocess.run(SSH+['mkdir -p '+REMOTE],check=True)
    subprocess.run(['scp','-q',str(path),'root@47.108.51.138:'+REMOTE+'/candidate.tar.gz'],check=True)
    code=f'''
import json,subprocess,tarfile
from pathlib import Path
root=Path('{REMOTE}');source=root/'source';source.mkdir(exist_ok=True)
with tarfile.open(root/'candidate.tar.gz') as tar:
 for m in tar.getmembers():
  assert m.isfile() and (source/m.name).resolve().is_relative_to(source.resolve())
 tar.extractall(source)
result=subprocess.run(['systemd-run','--unit=rag-legal-tests-'+str(__import__('time').time_ns()),'--wait','--pipe','--collect','-p','MemoryMax=536870912','-p','MemorySwapMax=0','-p','CPUQuota=50%','-p','Nice=10','-p','RuntimeMaxSec=600','-p','WorkingDirectory='+str(source),'-p','Environment=PYTHONPATH='+str(source),'/opt/rag-workbench/venv/bin/python','-m','pytest','-q','--junitxml='+str(root/'pytest.xml')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(root/'pytest.txt').write_text(result.stdout)
print(result.stdout)
raise SystemExit(result.returncode)
'''
    result=subprocess.run(SSH+['python3 -'],input=code.encode(),capture_output=True,timeout=650)
    (QA/'linux-test.txt').write_bytes(result.stdout+result.stderr)
    print((result.stdout+result.stderr).decode(errors='replace'))
    subprocess.run(['scp','-q','root@47.108.51.138:'+REMOTE+'/pytest.xml',str(QA/'linux-test.xml')],check=True)
    raise SystemExit(result.returncode)

def ui():
    from app.config import Settings
    from app.main import create_app,password_hash
    from app.ingest import insert_document
    import uvicorn
    QA.mkdir(parents=True,exist_ok=True)
    app=create_app(Settings(data_dir=QA/'ui-data',model_base_url='',model_name='',model_api_key=''),run_worker=False)
    salt=secrets.token_hex(16)
    app.state.store.set_setting('admin',{'salt':salt,'hash':password_hash(os.environ['RAG_UI_PASSWORD'],salt)})
    insert_document(app.state.store,{'title':'合成合同争议判决','body':'事实认定\n买方已支付合同货款但未收到设备。\n法院认为\n合同履行责任应依据双方约定判断。\n判决如下\n被告返还货款。','legal_metadata':{'category':'judgment','jurisdiction':'印度尼西亚'}},'knowledge')
    uvicorn.run(app,host='127.0.0.1',port=8898,log_level='warning')

if __name__=='__main__':
    {'stage':stage,'ui':ui}[sys.argv[1]]()
