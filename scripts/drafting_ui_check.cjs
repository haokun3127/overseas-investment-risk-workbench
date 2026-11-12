const {chromium}=require('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
const out='qa/drafting-workspace-20261112',base='http://127.0.0.1:8898';
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),headers={'X-Requested-With':'risk-workbench'};
  assert((await context.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:'local-ui-test-only'}})).ok());
  const page=await context.newPage(),errors=[],checks=[],screenshots=[];
  page.on('pageerror',e=>errors.push(e.message));
  const capture=async name=>{
   for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===390?844:1000});
    await page.evaluate(()=>scrollTo(0,0));
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('.dw-text')).every(n=>n.scrollHeight<=n.clientHeight+1));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' overflows at '+width);
    await page.locator('#notice').evaluate(n=>n.style.visibility='hidden');
    await page.screenshot({path:`${out}/${name}-${width}.png`,fullPage:true,animations:'disabled'});screenshots.push(name+' '+width);
   }
   await page.setViewportSize({width:1440,height:1000});
   await page.locator('#notice').evaluate(n=>n.style.visibility='');
  };
  await page.goto(base+'/#drafting');await page.locator('#drafting-form').waitFor();
  assert.equal(await page.locator('[data-dw-field]').count(),2);
  await capture('input');
  await page.locator('#dw-material').setInputFiles({name:'事项说明.txt',mimeType:'text/plain',buffer:Buffer.from('甲公司已按合同支付货款，设备尚未交付，双方正在核对交付安排。')});
  await page.waitForFunction(()=>document.querySelector('#dw-material-status').textContent.includes('已读取'));
  assert((await page.locator('#dw-facts').inputValue()).includes('设备尚未交付'));
  await page.locator('[data-dw-field="0"]').fill('乙公司');
  await page.locator('#drafting-form [type=submit]').click();
  await page.locator('.dw-paper').waitFor();
  await page.waitForFunction(()=>!document.querySelector('#drafting-form [type=submit]').disabled);
  assert.equal(await page.locator('.dw-section').count(),3);
  assert((await page.locator('.dw-missing').first().innerText()).includes('联系人'));
  assert((await page.locator('.dw-nav [data-dw-tab=history]').innerText()).includes('1'));
  await page.locator('[data-draft-text="0"]').fill('甲公司已付款，交付时间仍需双方核对。');
  assert(await page.locator('#dw-save').isEnabled());
  assert.equal(await page.locator('#dw-download').getAttribute('aria-disabled'),'true');
  assert(await page.locator('#dw-refine button').isDisabled());
  await page.locator('#dw-reason').fill('核实付款并精简表述');
  await page.locator('#dw-save').click();
  await page.waitForFunction(()=>document.querySelector('#dw-save-status')?.textContent==='已保存');
  const saved=(await context.request.get(base+'/api/drafting/results/1')).json();
  assert.equal((await saved).revision,1);
  assert.equal((await saved).blocks[0].text,'甲公司已付款，交付时间仍需双方核对。');
  const download=await context.request.get(base+'/api/drafting/1/docx');assert(download.ok());
  fs.writeFileSync(out+'/ui-edited.docx',await download.body());
  checks.push('material upload, template fields, complete draft, missing fields, edit/save CAS and Word');
  await page.locator('[data-dw-source]').first().click();
  assert(await page.locator('#dw-sources').evaluate(n=>n.open));
  await page.locator('#dw-sources summary').click();
  await capture('draft');
  await page.locator('#dw-refine textarea').fill('保留事实，简化措辞');
  await page.locator('#dw-refine button').click();
  await page.waitForFunction(()=>document.querySelector('#dw-download')?.getAttribute('href')==='api/drafting/2/docx');
  await page.waitForFunction(()=>document.querySelector('.dw-nav [data-dw-tab=history]')?.textContent.includes('2'));
  await page.locator('.dw-nav [data-dw-tab=history]').click();
  await capture('history');
  await page.locator('button[data-open-draft="1"]').last().click();
  await page.waitForFunction(()=>document.querySelector('[data-draft-text="0"]')?.value==='甲公司已付款，交付时间仍需双方核对。');
  checks.push('citation reveal, revision creates new draft, history reopens original edited version');
  await page.route('**/api/drafting',route=>route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({detail:'模型服务暂不可用，请稍后重试。'})}));
  await page.locator('#dw-toggle-input').click();
  await page.locator('#drafting-form [type=submit]').click();
  await page.locator('#dw-generate-error .error-box, #dw-generate-error').waitFor();
  await page.waitForFunction(()=>document.querySelector('#dw-generate-error').textContent.includes('模型服务暂不可用'));
  assert.equal(await page.locator('[data-draft-text="0"]').inputValue(),'甲公司已付款，交付时间仍需双方核对。');
  assert((await page.locator('#dw-facts').inputValue()).includes('设备尚未交付'));
  assert(await page.locator('#drafting-form [type=submit]').isEnabled());
  checks.push('generation failure preserves original draft and input, retry enabled');
  await page.locator('.dw-nav [data-dw-tab=templates]').click();
  await capture('templates');
  for(const width of [320,720,900]){
   await page.setViewportSize({width,height:900});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'template overflow '+width);
  }
  checks.push('desktop/mobile input, document, history and template layouts; 320/720/900 widths');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(out+'/ui-result.json',JSON.stringify({passed:true,browser_errors:errors,checks,screenshots},null,2));
  console.log(JSON.stringify({passed:true,checks:checks.length,screenshots:screenshots.length,browser_errors:errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
