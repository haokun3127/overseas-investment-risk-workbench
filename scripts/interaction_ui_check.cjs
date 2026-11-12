const {chromium}=require('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
const out='qa/interaction-layout-20261112',base=process.env.RAG_UI_BASE||'http://127.0.0.1:8898',live=process.env.RAG_UI_LIVE==='1';
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const c=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1050}});
  assert((await c.request.post(base+'/api/auth/login',{headers:{'X-Requested-With':'risk-workbench'},
   data:{username:'admin',password:process.env.RAG_UI_PASSWORD||'local-ui-test-only'}})).ok());
  const page=await c.newPage(),errors=[],checks=[],shots=[];
  page.on('pageerror',e=>errors.push(e.message));
  async function route(name){
   await page.goto(base+'/#'+name);await page.waitForFunction(()=>typeof state!=='undefined'&&!state.renderSignal&&document.querySelector('#main .workspace-page'));
   assert.equal(await page.locator('#retry-page').count(),0,await page.locator('#main').innerText());
  }
  async function capture(name){
   for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===390?844:1050});
    await page.evaluate(()=>scrollTo(0,0));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'overflow: '+name+' '+width);
    await page.screenshot({path:`${out}/${live?'live-':''}${name}-${width}.png`,fullPage:true,animations:'disabled'});
    shots.push(name+' '+width);
   }
   await page.setViewportSize({width:1440,height:1050});
  }
  await route('overview');
  assert.equal(await page.locator('.overview-composition .risk-composition-levels a').count(),3);
  assert.equal(await page.locator('.overview-composition .severity-ring').count(),0);
  assert(await page.locator('.risk-composition-bar>span').first().evaluate(n=>n.getBoundingClientRect().width>0),'Risk share bar must be rendered');
  const others=page.locator('.signal-network a[aria-label^="其他 "]');
  assert.equal(await others.count(),1);
  const rect=await others.locator('.network-node').evaluate(n=>({x:+n.getAttribute('x'),y:+n.getAttribute('y')}));
  const positions=await page.locator('.signal-network .network-node').evaluateAll(nodes=>nodes.map(n=>+n.getAttribute('y')));
  assert(rect.x>300&&rect.y===Math.max(...positions));
  checks.push('composition has one severity summary; other is lower-right');
  await capture('overview');
  await route('consultation');
  await capture('consultation');
  await page.route('**/api/consultation',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({
   status:'answered',blocks:[{heading:'核对履行条件',text:'应结合双方签署合同核对设备交付条件及履行期限。仅凭付款事实，不能推定全部交付条件已经成就。',citations:[]}],sources:[]})}));
  await page.locator('[data-consultation-example="0"]').click();
  await page.locator('#consultation-form [type=submit]').click();
  await page.locator('.consultation-block').waitFor();
  await capture('consultation-answer');
  checks.push('question example, send and answer rendering with browser fixture');
  await route('drafting');
  await page.locator('#drafting-form').waitFor();
  await capture('drafting');
  await page.locator('[data-dw-tab=templates]').first().click();
  assert(await page.locator('#drafting-template-form').isVisible());
  await page.locator('[data-dw-tab=write]').first().click();
  checks.push('writing form, template fields and workspace tab navigation');
  await route('events');
  await page.locator('[data-preview]').first().click();
  await page.locator('#inspection-review').waitFor();
  assert.equal(await page.locator('.event-results:visible').count(),0);
  assert.equal(await page.locator('.workspace-filters:visible').count(),0);
  assert.equal(await page.locator('.inspection-savebar').evaluate(n=>getComputedStyle(n).position),'static');
  assert.equal(await page.locator('#inspection-review [name=level] option').count(),4);
  await capture('verification');
  const overviewBefore=await(await c.request.get(base+'/api/overview')).json();
  if(!live){
   const old=await page.locator('#inspection-review [name=level]').inputValue(),next=old==='lv1'?'lv2':'lv1';
   await page.locator('#inspection-review [name=level]').selectOption(next);
   await page.locator('#inspection-review [name=note]').fill('已核对合同约定，调整风险等级。');
   await page.locator('[type=submit][form=inspection-review]').click();
   await page.waitForFunction(()=>document.querySelector('#inspection-feedback')?.textContent.includes('复核已保存'));
   assert.equal(await page.locator('#inspection-review [name=level]').inputValue(),next);
   await page.locator('#inspection-review [name=level]').selectOption('non_risk');
   await page.locator('#inspection-review [name=note]').fill('已核实履行条件尚未成就，本事项不构成风险。');
   await page.locator('[type=submit][form=inspection-review]').click();
   await page.waitForFunction(()=>document.querySelector('.inspection-body .metadata')?.textContent.includes('无风险'));
   assert.equal((await(await c.request.get(base+'/api/overview')).json()).total,overviewBefore.total-1);
   checks.push('real isolated review saves grade twice, including green; revisions and totals update');
  }
  await page.locator('[data-close-inspection]').click();
  await page.locator('.event-results:visible').waitFor();
  assert.equal(await page.locator('.inspection-panel:visible').count(),0);
  checks.push('verification is focused; return restores refreshed event list');
  for(const width of [320,720,1024]){
   await page.setViewportSize({width,height:900});
   for(const name of ['overview','consultation','drafting']){
    await route(name);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' overflow '+width);
   }
  }
  assert.deepEqual(errors,[]);
  const result={passed:true,live,checks,screenshots:shots,browser_errors:errors,
   server_model_execution:false,production_business_writes:false};
  fs.writeFileSync(out+'/'+(live?'live':'local')+'-result.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify({passed:true,live,checks,screenshots:shots.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
