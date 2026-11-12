const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const base='https://47.108.51.138/rag',out='qa/requirements-completion-20261112';
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
 const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
 const headers={'X-Requested-With':'risk-workbench'},errors=[];
 assert((await context.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_LIVE_PASSWORD}})).ok());
 const get=async(path)=>{const r=await context.request.get(base+'/api/'+path);assert(r.ok(),path);return r.json();};
 assert.equal((await get('release')).version,'20261112-workflow-r6');
 const overview=await get('overview'),events=await get('events'),companies=await get('companies');
 assert.equal(overview.total,18);assert.equal(events.total,18);assert.equal(companies.items.length,22);
 assert.equal(overview.decisions.find(d=>d.decision==='non_risk').count,4);
 assert(Array.isArray((await get('company-users')).items));
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 const routes=[];
 for(const route of ['overview','events','documents','knowledge','consultation','drafting','websites','settings']){
  await page.goto(base+'/#'+route);
  await page.waitForFunction(()=>!!document.querySelector('#main h1')&&!document.querySelector('#main > .loading'));
  assert.equal(await page.locator('#main > .error').count(),0,route);
  const text=await page.locator('#main').innerText();
  assert(!/[〔［【\[]\s*S\d+\s*[〕］】\]]|客户测试|已剔除参考答案|原文分卷/.test(text),route+' preparation marker');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),route+' overflow');
  if(route==='overview'){
   assert.equal(await page.locator('.overview-composition').count(),1);
   assert.equal(await page.locator('.review-panel,.kpi-strip').count(),0);
   await page.screenshot({path:out+'/live-overview-desktop.png',fullPage:true});
  }
  routes.push(route);
 }
 await page.goto(base+'/#overview');await page.locator('#company-accounts').waitFor();
 await page.locator('#company-accounts').click();await page.locator('#company-account-form').waitFor();
 assert.equal(await page.locator('#company-account-form [name=company_id] option').count(),23);
 await page.locator('#accounts-close').click();
 const scopes=[];
 for(const [id,total] of [[1,1],[14,2],[9,0]]){
  await page.selectOption('#company-select',String(id));
  await page.waitForFunction(({id,total})=>state.company?.id===id&&document.querySelector('.overview-composition .ring-total')?.textContent===String(total),{id,total});
  assert.equal((await get('overview')).total,total);assert.equal((await get('events')).total,total);scopes.push({id,total});
 }
 await page.selectOption('#company-select','');
 await page.waitForFunction(()=>!state.company&&document.querySelector('.overview-composition .ring-total')?.textContent==='18');
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:out+'/live-overview-mobile.png',fullPage:true});
 const law=(await get('documents?kind=knowledge')).items.find(d=>d.kind_label!=='公司档案');
 assert(law);assert(Array.isArray((await get('documents/'+law.id+'/metadata-history')).items));
 await page.evaluate(id=>showSource(id),law.id);
 await page.locator('#document-metadata-form').waitFor({state:'attached'});
 assert.equal(await page.locator('#document-metadata-form').count(),1);
 await page.locator('#close-source').click();
 await page.goto(base+'/#event/'+events.items[0].id);await page.locator('.meeting-reading').waitFor();
 assert.equal(await page.locator('#meeting-basis-form [name=target]').count(),1);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 const anonymous=await browser.newContext({ignoreHTTPSErrors:true});
 assert.equal((await anonymous.request.get(base+'/api/company-users')).status(),401);
 assert.equal((await anonymous.request.post(base+'/api/auth/register',{headers,data:{username:'read_only_probe',password:'unused-only-test',name:'unused-only-test'}})).status(),401);
 await anonymous.close();
 await context.request.post(base+'/api/auth/logout',{headers});
 assert.deepEqual(errors,[]);
 const result={release:'20261112-workflow-r6',routes,company_scopes:scopes,events:18,nonrisk_documents:4,
  knowledge_metadata_form:true,per_action_basis_target:true,account_provision_form:true,
  anonymous_account_creation_denied:true,browser_errors:errors,
  business_writes:false,model_or_embedding_execution:false};
 fs.writeFileSync(out+'/live-result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
