// Read-only API scan of all visible business text for preparation labels.
const {request}=require('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base=process.env.RAG_BASE||'https://47.108.51.138/rag';
const re=/〔S\d+〕|\[S\d+\]|\bS\d{1,4}\b|客户测试|已抓取|待核验|已剔除参考答案|参考答案|对不上|风险简报|灰色风险|\b[LP]\d{1,2}\b/g;
(async()=>{
 const c=await request.newContext({ignoreHTTPSErrors:true});
 const h={'X-Requested-With':'risk-workbench'};
 if(!(await c.post(base+'/api/auth/login',{headers:h,data:{username:'admin',password:process.env.RAG_CHECK_PASSWORD}})).ok())throw 'login';
 await c.delete(base+'/api/companies/active',{headers:h});
 const hits=[];
 const walk=(o,p,where)=>{if(typeof o==='string'){const m=o.match(re);if(m)hits.push({where,path:p,m:[...new Set(m)],s:o.slice(0,160)})}
  else if(o&&typeof o==='object')for(const[k,v]of Object.entries(o))walk(v,p+'.'+k,where)};
 const events=(await (await c.get(base+'/api/events')).json()).items;
 for(const e of events)walk(await (await c.get(base+'/api/events/'+e.id)).json(),'',`event ${e.id}`);
 for(const p of ['/api/documents','/api/knowledge','/api/companies','/api/overview']){const r=await c.get(base+p);if(r.ok())walk(await r.json(),'',p)}
 const docs=(await (await c.get(base+'/api/documents')).json()).items||[];
 for(const d of docs){const r=await c.get(base+'/api/documents/'+d.id);if(r.ok()){const j=await r.json();delete j.text;delete j.content;delete j.chunks;walk(j,'',`doc ${d.id}`)}}
 console.log(JSON.stringify(hits.filter(x=>!/\.(id|hash|sha|url|source_url|quote_ref|chunk_id)$/i.test(x.path)),null,1));
})().catch(e=>{console.error(e);process.exit(1)});
