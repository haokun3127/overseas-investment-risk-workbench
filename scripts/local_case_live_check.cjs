const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const base='https://47.108.51.138/rag',out='qa/local-replay-20261112';
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}}),errors=[];
  const headers={'X-Requested-With':'risk-workbench'};
  const login=await ctx.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_LIVE_PASSWORD}});
  assert(login.ok(),'Login failed');
  const release=await (await ctx.request.get(base+'/api/release')).json();assert.equal(release.version,'20261112-workflow-r3');
  const plan=JSON.parse(fs.readFileSync(out+'/case-sync-plan.json','utf8'));
  let risk=0,nonrisk=0,events=0,actions=0;
  for(const item of plan.cases){
   const detail=await (await ctx.request.get(base+'/api/documents/'+item.target_document_id)).json();
   assert(!detail.detail,'Analysis endpoint rejected '+item.case);
   assert.equal(detail.company_id,item.company_id,item.case);
   const a=detail.analyses[0];assert(a,'Missing analysis '+item.case);
   assert.equal(a.decision,item.analysis.decision,item.case);
   if(a.decision==='risk')risk++;else nonrisk++;
   const rows=a.events;assert.equal(rows.length,item.events.length,item.case);
   for(const [index,row] of rows.entries()){
    const response=await ctx.request.get(base+'/api/events/'+row.id);assert(response.ok());
    const event=await response.json();assert(['lv1','lv2','lv3'].includes(event.level));
    assert.equal(event.category,item.events[index].category);
    assert.equal(event.level,item.events[index].level);
    assert.equal(event.is_latest,true);
    assert.equal(event.document_id,item.target_document_id);
    assert.deepEqual(event.evidence.map(e=>[e.reference,e.quote,e.document_id]),JSON.parse(item.events[index].evidence_json).map(e=>[e.reference,e.quote,e.document_id]));
    assert(event.actions.length>0);events++;actions+=event.actions.length;
   }
  }
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#events');await page.locator('#event-filter').waitFor({timeout:10000});
  assert.equal(await page.locator('meta[name="app-version"]').getAttribute('content'),release.version);
  await page.screenshot({path:out+'/live-events.png',fullPage:true});
  assert.deepEqual(errors,[]);
  await ctx.request.post(base+'/api/auth/logout',{headers});
  const result={release:release.version,cases:plan.cases.length,risk,nonrisk,events,actions,errors,model_execution_on_server:false};
  fs.writeFileSync(out+'/live-result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
