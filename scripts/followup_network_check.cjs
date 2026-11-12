// Read-only diagnostics for this server's connections. Never print proxy secrets.
const fs=require('fs'),http=require('http');
const config=fs.readFileSync('C:/Users/10397/AppData/Roaming/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml','utf8');
function value(name){let v=(config.match(new RegExp('^'+name+':\\s*(.*)$','m'))||[])[1]||'';return v.trim().replace(/^(['"])(.*)\1$/,'$2');}
const pipe='\\\\.\\pipe\\'+fs.readdirSync('\\\\.\\pipe\\').find(n=>n.startsWith('verge-mihomo-production-')),secret=value('secret');
function get(path){return new Promise((resolve,reject)=>{http.get({socketPath:pipe,path,headers:secret?{Authorization:'Bearer '+secret}:{}},r=>{let text='';r.on('data',c=>text+=c);r.on('end',()=>resolve({status:r.statusCode,data:JSON.parse(text)}));}).on('error',reject).setTimeout(10000,function(){this.destroy();});});}
if(process.argv.includes('--selectors'))(async()=>{
 const proxies=(await get('/proxies')).data.proxies;
 console.log(JSON.stringify(Object.values(proxies).filter(p=>p.now).map(p=>({name:p.name,type:p.type,now:p.now}))));
})().catch(e=>console.log(JSON.stringify({error:e.code||e.message})));
else if(process.argv.includes('--route-probe'))(async()=>{
 const proxies=(await get('/proxies')).data.proxies;
 const selected=Object.values(proxies).find(p=>!['Direct','Reject','Selector','URLTest','Fallback','LoadBalance','Pass','Compatible'].includes(p.type));
 for(const name of ['DIRECT',selected?.name].filter(Boolean)){
  const result=await get('/proxies/'+encodeURIComponent(name)+'/delay?timeout=5000&url='+encodeURIComponent('http://47.108.51.138/rag/api/health'));
  console.log(JSON.stringify({route:name==='DIRECT'?'direct':'existing_proxy',...result}));
 }
})().catch(e=>console.log(JSON.stringify({error:e.code||e.message})));
else http.get({socketPath:pipe,path:'/connections',headers:secret?{Authorization:'Bearer '+secret}:{}},r=>{
 let text='';r.on('data',c=>text+=c);r.on('end',()=>{
  if(r.statusCode!==200){console.log(JSON.stringify({controller_status:r.statusCode}));return;}
  const data=JSON.parse(text);console.log(JSON.stringify({target_connections:(data.connections||[]).filter(c=>c.metadata?.destinationIP==='47.108.51.138').map(c=>({port:c.metadata.destinationPort,rule:c.rule,rulePayload:c.rulePayload,chains:c.chains}))}));
 });
}).on('error',e=>{console.log(JSON.stringify({controller_error:e.code}));process.exitCode=1;}).setTimeout(5000,function(){this.destroy();});
