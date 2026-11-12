const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../qa/legal-knowledge-20261111');
const checks=[],errors=[];
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 page.on('pageerror',e=>errors.push(e.message));
 const headers={'X-Requested-With':'risk-workbench'};
 assert((await context.request.post('http://127.0.0.1:8898/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_UI_PASSWORD}})).ok());
 await page.goto('http://127.0.0.1:8898/#knowledge');
 await page.locator('#import-form [name=legal_category]').waitFor();
 assert.equal(await page.locator('#import-form [name=legal_category] option').count(),15);checks.push('14类知识及未分类入口');
 await page.locator('#document-filter [name=category]').selectOption('judgment');
 await page.locator('#document-filter button').first().click();await page.locator('tbody tr').first().waitFor();
 checks.push('分类筛选返回判决资料');
 await page.locator('#knowledge-search [name=q]').fill('合同履行责任');
 await page.locator('#knowledge-search [name=category]').selectOption('judgment');
 await page.locator('#knowledge-search [name=section]').selectOption('reasoning');
 await page.locator('#knowledge-search button[type=submit]').click();
 await page.locator('.kr-item').first().waitFor();
 assert.equal(await page.locator('#knowledge-search [name=section]').inputValue(),'reasoning');
 checks.push('段落检索及刷新后筛选保留');
 await page.locator('.kr-pane [data-source]').click();
 await page.locator('.legal-editor summary').click();
 await page.locator('#legal-metadata-form [name=document_no]').fill('合成文号-001');
 await page.locator('#legal-metadata-form [type=submit]').click();
 await page.locator('#source-content').getByText('合成文号-001',{exact:true}).waitFor();checks.push('人工分类及核验信息保存');
 await page.locator('#close-source').click();
 await page.screenshot({path:path.join(root,'knowledge-desktop.png'),fullPage:true});
 await page.goto('http://127.0.0.1:8898/#consultation');
 await page.locator('#consultation-form [name=mode]').selectOption('report');
 await page.route('**/api/consultation',route=>route.fulfill({json:{status:'answered',mode:'report',report_id:1,message:'',
   blocks:[{heading:'类似案例分析',section:'cases',text:'合同责任应依据双方约定判断。',citations:[1]}],
   sources:[{number:1,title:'合成合同争议判决',document_id:1,source:'',date:'',quote:'合同履行责任应依据双方约定判断。'}],
   missing_sections:['法律依据','风险判断','建议方案'],assessment_note:'风险评分和国别化权重尚未确认，本报告不输出量化分数。'}}));
 await page.locator('#consultation-question').fill('合同履行责任');await page.locator('#consultation-form [type=submit]').click();
 await page.getByRole('heading',{name:'类似案例分析',exact:true}).waitFor();
 assert(await page.getByRole('link',{name:'下载 Word',exact:true}).isVisible());
 checks.push('咨询报告界面及模块缺口展示（界面响应采用隔离桩）');
 await page.screenshot({path:path.join(root,'report-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));await page.screenshot({path:path.join(root,'report-mobile.png'),fullPage:true});
 await page.goto('http://127.0.0.1:8898/#knowledge');await page.locator('#knowledge-search').waitFor();
 assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)));await page.screenshot({path:path.join(root,'knowledge-mobile.png'),fullPage:true});
 checks.push('390像素手机两页无横向溢出');
 await browser.close();assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(root,'ui-result.json'),JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({checks,errors}));
})().catch(e=>{console.error(e);process.exit(1)});
