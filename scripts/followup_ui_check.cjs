const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const base='http://127.0.0.1:8899',out=path.resolve(__dirname,'../qa/followup-20261111');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 const headers={'X-Requested-With':'risk-workbench'};
 assert((await context.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_UI_PASSWORD}})).ok());
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  await page.setViewportSize(viewport);
  for(const [route,selector] of [['overview','.meeting-company'],['events','#event-filter'],['event/1','.meeting-reading'],['documents','.analysis-single-column'],['knowledge','#knowledge-search'],['consultation','#consultation-form'],['drafting','[data-open-draft]']]){
   await page.goto(base+'/#'+route);await page.locator(selector).waitFor();
   if(route==='drafting'){await page.locator('[data-open-draft]').click();await page.locator('#draft-edit').waitFor();}
   assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),route+' overflow '+viewport.width);
   if(!process.env.FOLLOWUP_NO_SCREENSHOTS)await page.screenshot({path:path.join(out,`ui-${route.replace('/','-')}-${viewport.width}.png`),fullPage:true});checks.push(route+' '+viewport.width);
  }
 }
 const priorRevision=(await (await context.request.get(base+'/api/drafting/results/1')).json()).revision;
 await page.locator('[data-draft-text="0"]').fill('设备尚未交付，具体交货日期待核实。');
 await page.locator('#draft-edit [name=reason]').fill('核对后补充交货日期缺口');
 await page.locator('#draft-edit [type=submit]').click();
 await page.waitForFunction(()=>document.body.innerText.includes('草稿修改已保存'));
 assert.equal((await (await context.request.get(base+'/api/drafting/results/1')).json()).revision,priorRevision+1);
 assert((await context.request.get(base+'/api/drafting/1/docx')).ok());checks.push('已保存草稿打开、编辑、修订与Word下载');
 await page.goto(base+'/#event/1');await page.locator('#meeting-basis-search').waitFor({state:'attached'});
 await page.locator('details').filter({has:page.locator('#meeting-basis-search')}).locator('summary').click();
 await page.locator('#meeting-basis-search [name=q]').fill('合同履行');await page.locator('#meeting-basis-search button').click();
 await page.locator('[data-basis-choice]').first().click();
 await page.locator('#meeting-basis-form [name=quote]').fill('双方确认已经支付货款，设备尚未交付。');
 await page.locator('#meeting-basis-form [name=reason]').fill('支持付款和未交付事实');
 const beforeEvidence=await (await context.request.get(base+'/api/events/1')).json();
 if(!beforeEvidence.evidence.some(r=>r.quote==='双方确认已经支付货款，设备尚未交付。'))await page.locator('#meeting-basis-form button').click();
 await page.locator('.evidence blockquote').filter({hasText:'双方确认已经支付货款，设备尚未交付。'}).first().waitFor();checks.push('人工补充连续原文及详情展示');
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({checks,errors,model_generation_tested:false},null,2));
 await browser.close();console.log(JSON.stringify({checks,errors}));
})().catch(e=>{console.error(e);process.exit(1)});
