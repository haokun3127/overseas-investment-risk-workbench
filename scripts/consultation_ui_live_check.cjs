const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict'),crypto=require('crypto');
(async()=>{
 const base='https://47.108.51.138/rag',out='qa/consultation-ui-20261112';
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
 const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
 const headers={'X-Requested-With':'risk-workbench'};
 assert((await context.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_LIVE_PASSWORD}})).ok());
 const get=async path=>{const r=await context.request.get(base+'/api/'+path);assert(r.ok(),path);return r.json();};
 assert.equal((await get('release')).version,'20261112-workflow-r7');
 for(const name of ['consultation.js','consultation.css']){
  const r=await context.request.get(base+'/static/'+name+'?v=20261112-workflow-r7');assert(r.ok());
  assert.equal(crypto.createHash('sha256').update(await r.body()).digest('hex'),
    crypto.createHash('sha256').update(fs.readFileSync('web/'+name)).digest('hex'));
 }
 const page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/consultation',route=>route.abort()); // No model calls during live presentation verification.
 await page.goto(base+'/#consultation');await page.locator('#consultation-form').waitFor();
 const saved=JSON.parse(fs.readFileSync('qa/requirements-completion-20261112/real-model-smoke.json','utf8'));
 const answer=structuredClone(saved.answer);
 for(const source of answer.sources)source.document_id=saved.source_document_id;
 await page.evaluate(answer=>{
  consultation.turns=[{question:'这份资料中 TikTok 的罚款金额是多少？能否确认具体付款截止日期？',answer}];
  updateConsultation();
 },answer);
 assert.equal(await page.locator('.consultation-block').count(),answer.blocks.length);
 assert.equal(await page.locator('.consultation-sources').getAttribute('open'),null);
 const checks=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===390?844:1000});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  const font=await page.locator('.consultation-block p').first().evaluate(n=>getComputedStyle(n).fontSize);
  assert.equal(font,width===390?'15px':'16px');checks.push({width,fontSize:font});
 }
 await page.locator('[data-consultation-marker]').first().click();
 assert(await page.locator('.consultation-sources').evaluate(n=>n.open));
 await page.locator('[data-consultation-source]').first().click();
 await page.locator('#source-dialog[open] #source-quote').waitFor();
 assert.equal(await page.locator('#source-quote').innerText(),answer.sources[0].quote);
 await page.locator('#close-source').click();
 const overview=await get('overview');assert.equal(overview.total,18);
 assert.equal(overview.decisions.find(d=>d.decision==='non_risk').count,4);
 await context.request.post(base+'/api/auth/logout',{headers});
 assert.deepEqual(errors,[]);
 const result={release:'20261112-workflow-r7',asset_hashes_match:true,layout:checks,
   saved_answer_rendered:true,original_quote_located:true,browser_errors:errors,
   risk_events:18,nonrisk_documents:4,model_called:false,business_writes:false};
 fs.writeFileSync(out+'/live-result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
