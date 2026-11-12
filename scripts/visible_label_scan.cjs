// Read-only: render every event and document detail page and scan visible text for internal markers.
const {chromium}=require('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
const base=process.env.RAG_BASE||'https://47.108.51.138/rag';
const re=/〔\s*S\d+\s*〕|\[S\d+\]|(?<![A-Za-z0-9])[SKLP]\d{1,4}(?![A-Za-z0-9])|客户测试|已抓取|待核验|已剔除参考答案|参考答案|对不上|风险简报|灰色风险/g;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
 const h={'X-Requested-With':'risk-workbench'};
 if(!(await ctx.request.post(base+'/api/auth/login',{headers:h,data:{username:'admin',password:process.env.RAG_CHECK_PASSWORD}})).ok())throw 'login';
 await ctx.request.delete(base+'/api/companies/active',{headers:h});
 const events=(await (await ctx.request.get(base+'/api/events')).json()).items;
 const docs=[];for(let p=1;p<6;p++){const j=await (await ctx.request.get(base+'/api/documents?page='+p)).json();docs.push(...j.items);if(j.items.length<30)break;}
 const page=await ctx.newPage(),hits=[];
 const scan=async(route,sel)=>{await page.goto(base+'/#'+route);await page.waitForTimeout(1800);
  const t=await page.locator(sel).first().innerText().catch(()=>'' );
  for(const m of t.matchAll(re))hits.push({route,m:m[0],ctx:t.slice(Math.max(0,m.index-40),m.index+40).replace(/\s+/g,' ')});};
 for(const r of ['overview','events','documents','knowledge','websites','settings','consultation','drafting'])await scan(r,'#main');
 for(const e of events)await scan('event/'+e.id,'#main');
 await page.goto(base+'/#documents');await page.waitForTimeout(1500);
 for(const d of docs){await page.evaluate(id=>showSource(id),d.id);await page.waitForFunction(()=>!document.querySelector('#source-content .loading'));
  const t=await page.locator('#source-content').innerText().catch(()=>'' );
  for(const m of t.matchAll(re))hits.push({route:'source/'+d.id,m:m[0],ctx:t.slice(Math.max(0,m.index-40),m.index+40).replace(/\s+/g,' ')});}
 fs.writeFileSync((process.env.RAG_AUDIT_OUT||'qa/requirements-audit-20261112')+'/visible-hits.json',JSON.stringify(hits,null,1));
 const g={};for(const x of hits)g[x.route]=(g[x.route]||0)+1;console.log(hits.length,JSON.stringify(g));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

