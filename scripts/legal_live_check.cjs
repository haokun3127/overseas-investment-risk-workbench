const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}}),page=await ctx.newPage();
 const base='https://47.108.51.138/rag',headers={'X-Requested-With':'risk-workbench'},errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 const version=await ctx.request.get(base+'/api/release');assert.equal((await version.json()).version,'20261111-legal-knowledge-r1');checks.push('线上版本');
 const login=await ctx.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_LIVE_PASSWORD}});assert(login.ok(),'管理员登录失败');
 const schema=await ctx.request.get(base+'/api/knowledge/schema');assert.equal(Object.keys((await schema.json()).categories).length,15);checks.push('知识分类接口');
 const docs=await (await ctx.request.get(base+'/api/documents?kind=knowledge')).json();
 assert(docs.items.every(d=>d.legal_metadata?.validity==='unknown'));checks.push('历史资料未冒认效力');
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  await page.setViewportSize(viewport);
  for(const route of ['knowledge','consultation']){
   await page.goto(base+'/#'+route);
   await page.locator(route==='knowledge'?'#knowledge-search [name=section]':'#consultation-form [name=mode]').waitFor();
   assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));
   await page.screenshot({path:path.resolve(__dirname,`../qa/legal-knowledge-20261111/live-${route}-${viewport.width}.png`),fullPage:true});
   checks.push(route+' '+viewport.width);
  }
 }
 const detail=await (await ctx.request.get(base+'/api/documents/'+docs.items[0].id)).json();assert(detail.legal_metadata && detail.legal_sections);checks.push('线上原文与法律元数据');
 await ctx.request.post(base+'/api/auth/logout',{headers});
 await browser.close();assert.deepEqual(errors,[]);
 fs.writeFileSync(path.resolve(__dirname,'../qa/legal-knowledge-20261111/live-result.json'),JSON.stringify({checks,errors,version:'20261111-legal-knowledge-r1'},null,2));
 console.log(JSON.stringify({checks,errors}));
})().catch(error=>{console.error(error);process.exit(1)});
