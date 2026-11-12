const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
(async()=>{
 const base='https://47.108.51.138/rag',out=path.resolve(__dirname,'../qa/meeting-20261111');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}}),page=await ctx.newPage(),errors=[],checks=[];
 const headers={'X-Requested-With':'risk-workbench'};
 page.on('pageerror',e=>errors.push(e.message));
 const release=await (await ctx.request.get(base+'/api/release')).json();assert.equal(release.version,'20261111-workflow-r1');
 assert((await ctx.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_LIVE_PASSWORD}})).ok());
 const config=await (await ctx.request.get(base+'/api/settings')).json();assert.deepEqual(Object.keys(config.rules.levels).sort(),['lv1','lv2','lv3']);checks.push('三色风险与独立绿色标准');
 const schema=await (await ctx.request.get(base+'/api/knowledge/schema')).json();assert.equal(Object.keys(schema.categories).length,15);checks.push('14类知识资源及未分类');
 assert((await ctx.request.delete(base+'/api/companies/active',{headers})).ok());
 const overview=await (await ctx.request.get(base+'/api/overview')).json();assert(overview.levels.every(r=>['lv1','lv2','lv3'].includes(r.level)));
 const events=await (await ctx.request.get(base+'/api/events')).json();assert.equal(events.total,overview.total);checks.push('事件与总览范围统计一致');
 const cid=overview.scope.company_id;
 if(cid)assert.equal(overview.scope.all_companies,false);
 const first=events.items[0];assert(first);
 const event=await (await ctx.request.get(base+'/api/events/'+first.id)).json();assert(Array.isArray(event.actions)&&Array.isArray(event.changes));assert(!('countermeasures' in event));
 assert.equal((await ctx.request.get(base+'/api/countermeasures')).status(),410);checks.push('内部对策库已退出前端');
 const csv=await ctx.request.get(base+'/api/export/events');assert(csv.ok());const exportText=await csv.text();assert(!exportText.includes('灰色')&&!exportText.includes('V级'));checks.push('导出使用当前等级');
 const html=await (await ctx.request.get(base+'/')).text();assert(!html.includes('data-nav="countermeasures"')&&!html.includes('data-nav="report"'));
 const routes=[['overview','.meeting-company'],['events','#event-filter'],['event/'+first.id,'.meeting-reading'],['documents','.analysis-single-column'],['knowledge','#knowledge-search'],['consultation','#consultation-form'],['drafting','#drafting-template-form'],['settings','#rules-form']];
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  await page.setViewportSize(viewport);
  for(const [route,selector] of routes){
   await page.goto(base+'/#'+route);await page.locator(selector).waitFor();
   assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),route+' overflow '+viewport.width);
   await page.screenshot({path:path.join(out,`live-${route.replace('/','-')}-${viewport.width}.png`),fullPage:true});checks.push(route+' '+viewport.width);
  }
 }
 await ctx.request.post(base+'/api/auth/logout',{headers});await browser.close();assert.deepEqual(errors,[]);
 const result={version:release.version,checks,errors,total:overview.total,levels:overview.levels,production_business_writes:false};
 fs.writeFileSync(path.join(out,'live-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1)});
