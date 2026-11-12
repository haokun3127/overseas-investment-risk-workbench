const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const base='https://47.108.51.138/rag',out='qa/local-replay-20261112';
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
  const headers={'X-Requested-With':'risk-workbench'},errors=[];
  const login=await ctx.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_LIVE_PASSWORD}});
  assert(login.ok(),'Login failed');
  const get=async path=>{const r=await ctx.request.get(base+'/api/'+path);assert(r.ok(),path);return r.json();};
  const release=await get('release');assert.equal(release.version,'20261112-workflow-r4');
  const companies=await get('companies');assert.equal(companies.active_id,null,'New login silently selected a company');
  const marker=/[〔［【\[]\s*S\d+\s*[〕］】\]]/;
  for(const c of companies.items)for(const v of Object.values(c))if(typeof v==='string')assert(!marker.test(v),'Company metadata marker remains');
  const all=await get('overview'),events=await get('events');
  assert(all.scope.all_companies);assert.equal(all.total,18);assert.equal(events.total,all.total);
  const allNonrisk=all.decisions.find(d=>d.decision==='non_risk').count;
  assert(allNonrisk>=3);
  const plan=JSON.parse(fs.readFileSync(out+'/case-sync-plan.json','utf8'));
  let risk=0,nonrisk=0,caseEvents=0;
  for(const c of plan.cases){
   const d=await get('documents/'+c.target_document_id);assert.equal(d.company_id,c.company_id);
   const a=d.analyses[0];assert.equal(a.decision,c.analysis.decision);
   if(a.decision==='risk')risk++;else nonrisk++;
   assert.equal(a.events.length,c.events.length);caseEvents+=a.events.length;
  }
  assert.equal(risk,16);assert.equal(nonrisk,3);assert.equal(caseEvents,17);
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#overview');
  await page.locator('#company-select').waitFor();
  await page.waitForFunction(()=>document.querySelector('[data-count]')?.dataset.count==='18');
  assert.match(await page.locator('#workspace-label').innerText(),/全部企业/);
  const options=await page.locator('#company-select option').allTextContents();
  assert(options.every(n=>!marker.test(n)));
  const checks=[];
  for(const [id,expected] of [[1,1],[2,1],[14,2],[9,0]]){
   await page.selectOption('#company-select',String(id));
   await page.waitForFunction(id=>state.company?.id===id&&document.querySelector('#company-select')?.value===String(id),id);
   await page.waitForFunction(n=>document.querySelector('[data-count]')?.dataset.count===String(n),expected);
   const overview=await get('overview'),rows=await get('events');
   assert.equal(overview.scope.company_id,id);assert.equal(overview.total,expected);assert.equal(rows.total,expected);
   const companyName=companies.items.find(c=>c.id===id).name;
   assert((await page.locator('#workspace-label').innerText()).includes(companyName));
   checks.push({company_id:id,total:overview.total});
  }
  await page.selectOption('#company-select','');
  await page.waitForFunction(()=>!state.company&&document.querySelector('[data-count]')?.dataset.count==='18');
  await page.screenshot({path:out+'/scope-overview-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:out+'/scope-overview-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(base+'/#events');await page.locator('#event-filter').waitFor();
  assert.equal((await get('events')).total,18);
  await page.screenshot({path:out+'/scope-events.png',fullPage:true});
  assert.deepEqual(errors,[]);
  await ctx.request.post(base+'/api/auth/logout',{headers});
  const result={release:release.version,company_names_clean:true,new_admin_scope:'all',total:all.total,all_nonrisk_documents:allNonrisk,
    reference_cases:{total:19,risk,nonrisk,events:caseEvents},additional_preserved_events:all.total-caseEvents,
    company_switches:checks,browser_errors:errors,model_execution_on_server:false};
  fs.writeFileSync(out+'/scope-live-result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
