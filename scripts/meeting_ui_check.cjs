const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
(async()=>{
 const base='http://127.0.0.1:8898',out=path.resolve(__dirname,'../qa/meeting-20261111');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}}),page=await ctx.newPage(),errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 const headers={'X-Requested-With':'risk-workbench'};
 assert((await ctx.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_UI_PASSWORD}})).ok());
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  await page.setViewportSize(viewport);
  for(const [route,selector] of [['overview','.meeting-company'],['events','#event-filter'],['event/1','.meeting-reading'],['documents','.analysis-single-column'],['knowledge','#knowledge-search'],['consultation','#consultation-form'],['drafting','#drafting-template-form'],['settings','#rules-form']]){
   await page.goto(base+'/#'+route);await page.locator(selector).waitFor();
   assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),route+' overflow '+viewport.width);
   assert.equal(await page.locator('[data-nav=report],[data-nav=countermeasures]').count(),0);
   await page.screenshot({path:path.join(out,`ui-${route.replace('/','-')}-${viewport.width}.png`),fullPage:true});
   checks.push(route+' '+viewport.width);
  }
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(base+'/#event/1');await page.locator('#meeting-event-form').waitFor();
 await page.locator('#meeting-event-form [name=level]').selectOption('lv3');
 await page.locator('#meeting-event-form [name=reason]').fill('合成界面验证，调整风险级别');
 await page.locator('#meeting-event-form [type=submit]').click();
 await page.locator('.meeting-reading details').filter({hasText:'合成界面验证，调整风险级别'}).waitFor({state:'attached'});
 checks.push('人工等级调整保存与审计');
 await page.goto(base+'/#event-new');await page.locator('#meeting-event-form').waitFor();
 await page.locator('#meeting-event-form [name=company_id]').selectOption({index:1});
 await page.locator('#meeting-event-form [name=title]').fill('合成手动新增事件');
 await page.locator('#meeting-event-form [name=summary]').fill('合同到期但尚未交付设备，已核实。');
 await page.locator('#meeting-event-form [name=reason]').fill('隔离环境端到端新增验证');
 await page.locator('#meeting-event-form [type=submit]').click();await page.locator('.meeting-detail-head h1').filter({hasText:'合成手动新增事件'}).waitFor();
 checks.push('新增事件与详情跳转');
 await page.goto(base+'/#drafting');await page.locator('#drafting-template-form').waitFor();
 await page.locator('#drafting-template-form [name=name]').fill('合成界面函件');
 await page.locator('#drafting-template-form [name=category]').fill('合成分类');
 await page.locator('#drafting-template-form [name=body]').fill('合同履行通知\n双方应核对合同约定，具体设备、时间和当事人待补充。');
 await page.locator('#drafting-template-form [type=submit]').click();await page.locator('#drafting-form').waitFor();checks.push('模板保存与草稿入口');
 const tenant=await browser.newContext({viewport:{width:390,height:844}}),tp=await tenant.newPage();
 tp.on('pageerror',e=>errors.push(e.message));
 assert((await tenant.request.post(base+'/api/auth/register',{headers,data:{username:'qa_company_'+Date.now(),password:'qa-tenant-only-12345',name:'合成只读企业'}})).ok());
 await tp.goto(base+'/#knowledge');await tp.waitForURL('**/#overview');await tp.locator('.kpi-strip').waitFor();
 for(const nav of ['knowledge','documents','settings','drafting','consultation'])assert(!(await tp.locator('[data-nav='+nav+']').isVisible()));
 assert.equal((await tenant.request.get(base+'/api/documents?kind=knowledge')).status(),403);
 await tp.screenshot({path:path.join(out,'company-mobile.png'),fullPage:true});
 checks.push('企业菜单、直接路由与接口隔离');
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({checks,errors},null,2));
 await browser.close();console.log(JSON.stringify({checks,errors}));
})().catch(e=>{console.error(e);process.exit(1)});
