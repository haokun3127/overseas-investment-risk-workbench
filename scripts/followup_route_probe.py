"""Per-process alternate route. No system proxy, routing, or existing app changes."""
import base64
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request
import yaml

config_path=Path('C:/Users/10397/AppData/Roaming/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml')
original=yaml.safe_load(config_path.read_text(encoding='utf-8'))
proxies=original.get('proxies',[])
# Skip subscription notices that sometimes masquerade as proxy records.
proxies=[p for p in proxies if not any(w in p.get('name','') for w in ('剩余','到期','官网','流量','套餐','重置','更新'))]
assert proxies,'No existing proxy endpoints found'
proxies=[p for p in proxies if p.get('name')=='🇭🇰 香港W02 | IEPL']
assert proxies,'Selected active endpoint not found'
target='https://47.108.51.138/rag/api/release'
with tempfile.TemporaryDirectory(prefix='rag-route-check-') as directory:
    for index,proxy in enumerate(proxies[:4]):
        name=proxy['name']
        config={'mixed-port':17898,'allow-lan':False,'bind-address':'127.0.0.1','mode':'rule','log-level':'silent',
                'tun':{'enable':False},'dns':{'enable':False},'ipv6':False,
                'proxies':[proxy], 'rules':['MATCH,'+name]}
        encoded=base64.b64encode(json.dumps(config,ensure_ascii=False).encode()).decode()
        process=subprocess.Popen(['D:/Clash Verge/verge-mihomo.exe','-d',directory,'-config',encoded],
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
        try:
            for _ in range(30):
                try:
                    with socket.create_connection(('127.0.0.1',17898),timeout=.1):break
                except OSError:time.sleep(.1)
            control=subprocess.run(['curl.exe','--proxy','http://127.0.0.1:17898','-sS','--connect-timeout','5','--max-time','8','https://api.ipify.org'],capture_output=True,text=True)
            print(json.dumps({'control_status':control.returncode,'control_response':control.stdout[:80],'control_error':control.stderr[:150]}),flush=True)
            result=subprocess.run(['curl.exe','--proxy','http://127.0.0.1:17898','-k','-sS','--connect-timeout','5','--max-time','12',target],capture_output=True,text=True)
            print(json.dumps({'route':index+1,'status':result.returncode,'response':result.stdout[:300],
                              'error':result.stderr[:200]},ensure_ascii=False),flush=True)
            if result.returncode==0:break
        finally:
            process.terminate();process.wait(timeout=5)
