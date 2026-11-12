// Read-only live audit of meeting requirements: screenshots, visible text and API scope counts.
const {chromium}=require('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
const base=process.env.RAG_BASE||'https://47.108.51.138/rag';
const out=process.env.RAG_AUDIT_OUT||'qa/requirements-audit-20261112';
const banned=/〔S\d+〕|\[S\d+\]|客户测试|已抓取|待核验|已剔除参考答案|参考答案|对不上|风险简报|对策库|灰色风险|五级|\bL\d{1,2}\b|\bP\d{1,2}\b/g;
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
 const login=await context.request.post(base+'/api/auth/login',{headers:{'X-Requested-With':'risk-workbench'},
  data:{username:'admin',password:process.env.RAG_CHECK_PASSWORD}});
 if(!login.ok())throw new Error('login '+login.status());
 const page=await context.newPage(),result={pages:{},api:{}};
 page.on('pageerror',e=>(result.errors=result.errors||[]).push(e.message));
 const get=async p=>{const r=await context.request.get(base+p);return {status:r.status(),body:await r.json().catch(()=>null)};};
 await context.request.delete(base+'/api/companies/active',{headers:{'X-Requested-With':'risk-workbench'}});
 result.api.overview=(await get('/api/overview')).body;
 const events=(await get('/api/events')).body;
 result.api.event_count=events?.items?.length;
 result.api.events=(events?.items||[]).map(e=>({id:e.id,title:e.title,level:e.level,category:e.category||e.risk_type,company:e.company_name}));
 result.api.companies=((await get('/api/companies')).body?.items||[]).map(c=>c.name||c.profile?.name);
 const routes=['overview','events','documents','knowledge','consultation','drafting','websites','settings'];
 if(events?.items?.length)routes.push('event/'+events.items[0].id);
 for(const r of routes){
  await page.goto(base+'/#'+r);await page.waitForTimeout(2500);
  const text=await page.locator('body').innerText();
  result.pages[r]={banned:[...new Set(text.match(banned)||[])],text:text.slice(0,5000)};
  await page.screenshot({path:`${out}/${r.replace('/','-')}.png`,fullPage:true});
 }
 fs.writeFileSync(out+'/audit.json',JSON.stringify(result,null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
