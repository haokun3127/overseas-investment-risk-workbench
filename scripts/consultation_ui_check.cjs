const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
const base=process.env.RAG_UI_BASE||'http://127.0.0.1:8898',out='qa/consultation-ui-20261112';
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
 const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
 await context.addInitScript(()=>{
  Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{if(window.failClipboard)throw Error('denied');window.copiedText=value;}}});
  window.print=()=>{window.printObserved={selected:!!document.querySelector('.print-selected'),sourcesOpen:!!document.querySelector('.print-selected .consultation-sources[open]')};};
 });
 const headers={'X-Requested-With':'risk-workbench'};
 assert((await context.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_UI_PASSWORD||'local-ui-test-only'}})).ok());
 const page=await context.newPage(),errors=[],checks=[],batches=[];
 page.on('pageerror',e=>errors.push(e.message));
 let response,hold=false,release,requests=0,httpStatus=200;
 await page.route('**/api/consultation',async route=>{
  requests++;
  if(hold)await new Promise(resolve=>release=resolve);
  await route.fulfill({status:httpStatus,contentType:'application/json',body:JSON.stringify(response)});
 });
 await page.goto(base+'/#consultation');await page.locator('#consultation-form').waitFor();
 const overflow=async()=>assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Horizontal overflow');
 const screenshot=async name=>{
  await page.locator('#notice').evaluate(n=>n.style.visibility='hidden');
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:width===390?844:1000});await overflow();
   await page.screenshot({path:out+'/'+name+'-'+width+'.png',fullPage:true});batches.push(name+' '+width);
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('#notice').evaluate(n=>n.style.visibility='');
 };
 await screenshot('empty');
 await page.locator('[data-consultation-example="0"]').click();
 assert((await page.locator('#consultation-question').inputValue()).includes('环境许可'));
 await page.locator('#consultation-question').fill('请根据已有资料说明合同履行义务，以及还需要核对哪些内容？');
 const source={number:1,document_id:3,title:'合同履行法律依据',quote:'当事人应当依照合同约定履行义务。',date:'2025-01-02',source:'发布机关',url:'https://example.com/law'};
 response={status:'answered',message:'',blocks:[
   {text:'已提供的资料明确要求当事人依照合同约定履行义务。判断本次事项时，应结合合同中的交付条件、履行期限与已发生事实核对。',citations:[1]},
   {text:'当前材料只支持上述履行原则，不能据此推定具体违约责任或争议解决结果。\n建议核对已签署合同的完整条款，并保留履行和沟通记录。',citations:[1]}],sources:[source]};
 hold=true;await page.locator('#consultation-form [type=submit]').click();
 await page.waitForFunction(()=>document.querySelector('#consultation-form')?.getAttribute('aria-busy')==='true');
 assert(await page.locator('#consultation-form [type=submit]').isDisabled());
 assert((await page.locator('#consultation-status').innerText()).includes('正在检索'));
 await page.waitForFunction(()=>document.querySelector('#consultation-form [type=submit]')?.disabled);
 while(!release)await new Promise(r=>setTimeout(r,20));
 hold=false;release();
 await page.locator('.consultation-block').first().waitFor();
 assert.equal(requests,1);assert.equal(await page.locator('.consultation-block').count(),2);
 assert.equal(await page.locator('.consultation-sources').getAttribute('open'),null);
 assert.equal(await page.locator('#consultation-question').inputValue(),'');
 await page.locator('[data-copy-consultation]').click();
 assert((await page.evaluate(()=>window.copiedText)).includes(source.quote));
 assert((await page.evaluate(()=>window.copiedText)).includes('[1]'));
 await page.locator('[data-consultation-marker]').first().click();
 assert(await page.locator('.consultation-sources').evaluate(n=>n.open));
 assert.equal(await page.evaluate(()=>document.activeElement.id),'consultation-source-0-1');
 await page.locator('[data-consultation-source]').click();
 await page.locator('#source-dialog[open] #source-quote').waitFor();
 await page.locator('#close-source').click();
 await page.locator('.consultation-sources summary').click();
 await screenshot('answer');
 checks.push('loading guard, answer paragraphs, copy with citations, inline citation expands/focuses source and locates original');
 await page.evaluate(()=>window.failClipboard=true);
 await page.locator('[data-copy-consultation]').click();
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('选中回答文字复制'));
 assert(!await page.locator('[data-copy-consultation]').isDisabled());
 await page.evaluate(()=>window.failClipboard=false);
 checks.push('clipboard denial gives recovery and re-enables action');
 await page.locator('#consultation-clear').click();
 assert.equal(await page.locator('.consultation-turn').count(),0);
 response={status:'insufficient',message:'现有资料不足以支持全部判断；未形成结论的部分不表示没有风险。',
   blocks:[{text:'现有条文支持依照合同约定履行义务。',citations:[1]}],sources:[source],
   explanation:{known_materials:['合同履行法律依据'],missing_facts:['缺少合同签订日期及约定的交付期限。'],missing_basis:['尚未提供完整的争议解决条款。'],
    conflicts:['付款凭证与情况说明记载的日期不同，需要核对。'],affected:['不能判断适用版本及本次交付是否逾期。'],needed:['补充已签署合同、付款凭证与交付记录。']}};
 await page.locator('#consultation-question').fill('请核实合同履行风险，缺少哪些资料？');
 await page.locator('#consultation-form [type=submit]').click();
 await page.locator('.consultation-gaps').waitFor();
 assert(await page.locator('.consultation-answer-body').evaluate(n=>n.getBoundingClientRect().top<document.querySelector('.consultation-gap-section').getBoundingClientRect().top));
 assert.equal(await page.locator('.consultation-gaps > div').count(),6);
 await screenshot('partial');
 checks.push('partial supported answer precedes six explicit gap groups, desktop/mobile reflow');
 await page.locator('#consultation-clear').click();
 response={status:'answered',mode:'report',report_id:1,message:'',blocks:[
   {heading:'法律依据',text:'当事人应当依照合同约定履行义务；适用版本应结合签订时间核实。',citations:[1]},
   {heading:'风险判断',text:'现有材料没有提供交付期限，暂不能确定本次事项是否已构成逾期。',citations:[1]},
   {heading:'建议方案',text:'补充签署合同，核对履行条件和期限。',citations:[1]}],
   sources:[source],missing_sections:['类似案例分析'],assessment_note:'具体法律适用需结合事实和资料版本核实。'};
 await page.selectOption('#consultation-form [name=mode]','report');
 await page.locator('#consultation-question').fill('合同履行咨询报告');
 await page.locator('#consultation-form [type=submit]').click();
 await page.locator('[data-print-consultation]').waitFor();
 assert.equal(await page.locator('.consultation-block h4').count(),3);
 assert((await page.locator('.consultation-report-actions a').getAttribute('href')).endsWith('/1/docx'));
 await screenshot('report');
 await page.locator('[data-print-consultation]').click();
 assert.deepEqual(await page.evaluate(()=>window.printObserved),{selected:true,sourcesOpen:true});
 await page.emulateMedia({media:'print'});
 assert.equal(await page.locator('.consultation-form').evaluate(n=>getComputedStyle(n).display),'none');
 await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));
 assert.equal(await page.locator('.consultation-sources').getAttribute('open'),null);
 await page.emulateMedia({media:'screen'});
 checks.push('report headings, Word link, selected report print includes sources and restores fold state');
 await page.setViewportSize({width:900,height:1000});await overflow();
 await page.setViewportSize({width:720,height:1000});await overflow();
 await page.setViewportSize({width:320,height:844});await overflow();
 const computed=await page.locator('.consultation-block p').first().evaluate(n=>({fontSize:getComputedStyle(n).fontSize,lineHeight:getComputedStyle(n).lineHeight}));
 assert.equal(computed.fontSize,'15px');
 await page.locator('#consultation-clear').click();
 response={status:'insufficient',message:'未检索到足以支持本次判断的公共资料。',blocks:[],sources:[],
   explanation:{missing_basis:['没有相关公共依据。'],affected:['暂不能确认适用要求。'],needed:['请补充具体法规或案例原文。']}};
 await page.locator('#consultation-question').fill('没有资料的事项');
 await page.locator('#consultation-form [type=submit]').click();
 await page.locator('.consultation-gap-section').waitFor();
 assert.equal(await page.locator('.consultation-sources').count(),0);
 assert.equal(await page.locator('.consultation-block').count(),0);
 await overflow();
 httpStatus=502;response={detail:'咨询模型暂时不可用，请稍后重试。'};
 await page.locator('#consultation-question').fill('继续核实合同条款');
 await page.locator('#consultation-form [type=submit]').click();
 await page.waitForFunction(()=>document.querySelector('#consultation-error')?.textContent.includes('暂时不可用'));
 assert.equal(await page.locator('.consultation-turn').count(),1);
 assert.equal(await page.locator('#consultation-question').inputValue(),'继续核实合同条款');
 assert(!await page.locator('#consultation-form [type=submit]').isDisabled());
 checks.push('model error preserves prior answer and unsent question, allows retry');
 assert.deepEqual(errors,[]);
 const result={checks,visual_states:batches,additional_widths:[900,720,320],browser_errors:errors,
   model_generation:false,response_source:'isolated UI fixtures',production_writes:false,computed_mobile:computed};
 fs.writeFileSync(out+'/ui-result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
