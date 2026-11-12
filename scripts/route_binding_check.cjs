// Exercise real page renderers and every globally invoked feature binder.
const {chromium}=require('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
const live=process.env.RAG_CHECK_LIVE==='1';
const base=live?'https://47.108.51.138/rag':'http://127.0.0.1:8898';
const out='qa/route-binding-20261112';
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const context=await browser.newContext({ignoreHTTPSErrors:true});
  const login=await context.request.post(base+'/api/auth/login',{
   headers:{'X-Requested-With':'risk-workbench'},
   data:{username:'admin',password:process.env.RAG_CHECK_PASSWORD||'local-ui-test-only'}});
  assert(login.ok(),'Administrator login failed');
  const page=await context.newPage(),errors=[],checked=[];
  page.on('pageerror',e=>errors.push(e.message));
  // The regression is swallowed by render(), so pageerror alone is insufficient.
  async function checkRoute(route,direct=false){
   if(direct)await page.goto(base+'/#'+route);
   else await page.evaluate(r=>{location.hash='#'+r;},route);
   const expected=route==='jobs'?'documents':route.split('/')[0];
   try{await page.waitForFunction(r=>typeof state!=='undefined'&&state.route===r&&!state.renderSignal,expected);}
   catch(error){console.error('Route wait failed',route,await page.evaluate(()=>({url:location.href,route:typeof state!=='undefined'?state.route:null,main:document.querySelector('#main')?.innerText?.slice(0,500)})));throw error;}
   assert.equal(await page.locator('#retry-page').count(),0,'Render failed: '+route+' '+await page.locator('#main').innerText());
   assert(!/Cannot (?:set|read) properties of null/.test(await page.locator('#main').innerText()),route);
   assert((await page.locator('#main').innerText()).trim().length>10,'Empty page: '+route);
   checked.push({route,entry:direct?'direct':'navigation'});
  }
  const routes=['drafting','consultation','overview','events','event-new','documents','knowledge','websites','settings','jobs','updates'];
  for(const route of routes)await checkRoute(route,true);
  await checkRoute('drafting');
  for(const route of ['consultation','overview','documents','knowledge','events','websites','settings','drafting','consultation'])
   await checkRoute(route);
  // UI-only response fixture: no model invocation or production business writes.
  let fail=false,requests=0;
  await page.route('**/api/consultation',async route=>{
   requests++;
   await route.fulfill({status:fail?502:200,contentType:'application/json',body:JSON.stringify(fail?
    {detail:'咨询服务暂时不可用，请稍后重试。'}:
    {status:'answered',blocks:[{text:'请结合已签署合同核对履行期限与交付条件。',citations:[]}],sources:[]})});
  });
  await page.locator('#consultation-question').fill('请核对合同履行期限');
  await page.locator('#consultation-form [type=submit]').click();
  await page.locator('.consultation-block').waitFor();
  assert((await page.locator('.consultation-block').innerText()).includes('交付条件'));
  fail=true;
  await page.locator('#consultation-question').fill('请继续核对履行条件');
  await page.locator('#consultation-form [type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#consultation-error')?.textContent.includes('暂时不可用'));
  assert.equal(await page.locator('#consultation-question').inputValue(),'请继续核对履行条件');
  assert(await page.locator('#consultation-form [type=submit]').isEnabled());
  assert.equal(requests,2);
  await page.screenshot({path:out+'/'+(live?'live':'local')+'-consultation.png',fullPage:true});
  await checkRoute('drafting');await checkRoute('overview');
  if(live){
   const events=await(await context.request.get(base+'/api/events')).json();
   assert(events.items.length,'Expected existing production events');
   await checkRoute('event/'+events.items[0].id,true);
   await checkRoute('consultation');await checkRoute('drafting');
  }
  assert.deepEqual(errors,[]);
  const version=await(await context.request.get(base+'/api/release')).json();
  if(live){
   const expectedVersion=process.env.RAG_EXPECT_VERSION||'20261112-workflow-r9';
   assert.equal(version.version,expectedVersion);
   const crypto=require('crypto');
   for(const name of ['drafting.js']){
    const response=await context.request.get(base+'/static/'+name);
    assert(response.ok());
    assert.equal(crypto.createHash('sha256').update(await response.body()).digest('hex'),
     crypto.createHash('sha256').update(fs.readFileSync('web/'+name)).digest('hex'));
   }
   assert.equal(await page.locator('meta[name=app-version]').getAttribute('content'),version.version);
   assert((await page.locator('script[src*="drafting.js"]').getAttribute('src')).includes(expectedVersion));
  }
  const result={passed:true,version:version.version,checked,browser_errors:errors,
   consultation_send_and_error_recovery:true,consultation_response:'browser route fixture',
   model_execution:false,production_business_writes:false};
  fs.writeFileSync(out+'/'+(live?'live':'local')+'-result.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify({passed:true,live,route_checks:checked.length,version:version.version,browser_errors:errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
