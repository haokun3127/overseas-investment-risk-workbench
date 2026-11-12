const {chromium}=require('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),crypto=require('crypto'),assert=require('assert/strict');
const base='https://47.108.51.138/rag',out='qa/drafting-workspace-20261112';
(async()=>{
 assert(process.env.RAG_ADMIN_PASSWORD,'Admin password must be passed in process memory');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const c=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
  const login=await c.request.post(base+'/api/auth/login',{headers:{'X-Requested-With':'risk-workbench'},
   data:{username:'admin',password:process.env.RAG_ADMIN_PASSWORD}});
  assert(login.ok(),'Login failed');
  const version=await(await c.request.get(base+'/api/release')).json();assert.equal(version.version,'20261112-workflow-r8');
  const templates=await(await c.request.get(base+'/api/drafting/templates')).json();
  const history=await(await c.request.get(base+'/api/drafting/results')).json();
  assert(templates.items.length>=1);assert(templates.items[0].headings.length>=4);
  const page=await c.newPage(),errors=[],modelRequests=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/drafting',route=>{
   if(route.request().method()==='POST'){modelRequests.push('blocked');return route.abort();}
   return route.continue();
  });
  await page.goto(base+'/#drafting');await page.locator('#drafting-form').waitFor();
  assert.equal(await page.locator('meta[name=app-version]').getAttribute('content'),version.version);
  assert.equal(await page.locator('.dw-nav').evaluate(n=>getComputedStyle(n).flexDirection),'row');
  for(const file of ['drafting.js','drafting.css','meeting.js']){
   const response=await c.request.get(base+'/static/'+file);
   assert(response.ok());
   assert.equal(crypto.createHash('sha256').update(await response.body()).digest('hex'),
    crypto.createHash('sha256').update(fs.readFileSync('web/'+file)).digest('hex'));
  }
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:900});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
  await page.locator('.dw-nav [data-dw-tab=history]').click();assert(await page.locator('#dw-history').isVisible());
  await page.locator('.dw-nav [data-dw-tab=templates]').click();assert(await page.locator('#dw-templates').isVisible());
  assert.deepEqual(errors,[]);assert.deepEqual(modelRequests,[]);
  const report={passed:true,version:version.version,template_count:templates.items.length,
   saved_drafts:history.items.length,asset_hashes_match:true,desktop_mobile:true,browser_errors:errors,
   server_model_execution:false,business_writes:false};
  fs.writeFileSync(out+'/live-result.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
