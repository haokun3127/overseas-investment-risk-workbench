const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');
const base='https://47.108.51.138/rag',out='qa/presentation-audit-20261112';
const marker=/[〔［【\[]\s*S\d+\s*[〕］】\]]|(?:^|\n)\s*[LPSN]\d+(?:\s+S\d+)?\s+|客户测试|客户案例|已剔除参考答案|原文分卷/;
// Bare "S3" in a scanned legal decision can be the OCR of page 53, not a pack label.
const readingMarker=/[〔［【\[]\s*S\d+\s*[〕］】\]]|客户测试|客户案例|已剔除参考答案|原文分卷/;
const reading=value=>String(value||'').replace(/[ \t]*[〔［【\[]\s*S\d+\s*[〕］】\]]/g,'').replace(/\r\n?/g,'\n');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
  const headers={'X-Requested-With':'risk-workbench'},errors=[];
  assert((await ctx.request.post(base+'/api/auth/login',{headers,data:{username:'admin',password:process.env.RAG_LIVE_PASSWORD}})).ok());
  const get=async path=>{const r=await ctx.request.get(base+'/api/'+path);assert(r.ok(),path);return r.json();};
  assert.equal((await get('release')).version,'20261112-workflow-r5');
  const baseline=JSON.parse(fs.readFileSync(out+'/business-snapshot.json','utf8'));
  const cases=JSON.parse(fs.readFileSync(out+'/case-by-case-verification.json','utf8'));
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
  const clean=async(locator,label)=>{
   const text=await locator.innerText();assert(!readingMarker.test(text),'Visible preparation marker: '+label+' '+(text.match(readingMarker)||[])[0]);
  };
  const routes=[];
  for(const route of ['overview','events','documents','knowledge','consultation','drafting','websites','settings']){
   await page.goto(base+'/#'+route);
   await page.waitForFunction(()=>!document.querySelector('#main > .loading')&&!!document.querySelector('#main h1'));
   assert.equal(await page.locator('#main > .error').count(),0,route);
   await clean(page.locator('#main'),route);routes.push(route);
   if(['knowledge','consultation','drafting','websites'].includes(route))await page.screenshot({path:out+'/'+route+'-desktop.png',fullPage:true});
  }
  let listPages=0;
  for(const kind of ['event','knowledge']){
   const first=await get('documents?kind='+kind);const pages=Math.ceil(first.total/first.page_size);
   for(let n=1;n<=pages;n++){
    const data=await get('documents?kind='+kind+'&page='+n);
    for(const row of data.items)for(const field of ['title','source','zh_summary','zh_keywords'])
     assert(!marker.test(row[field]||''),'Metadata marker '+row.id+' '+field);
    await page.goto(base+'/#'+(kind==='event'?'documents':'knowledge')+'?page='+n);
    await page.waitForFunction(()=>!document.querySelector('#main > .loading')&&!!document.querySelector('#main h1'));
    await clean(page.locator('#main'),kind+' list '+n);listPages++;
   }
  }
  let documents=0,rawMarkedDocuments=0;
  for(const original of baseline.documents){
   const doc=await get('documents/'+original.id);
   assert.equal(doc.body,original.body,'Original source changed '+doc.id);
   await page.evaluate(id=>showSource(id),doc.id);
   await clean(page.locator('#source-content'),'document '+doc.id);
   assert.equal(await page.locator('#source-content .source-body').textContent(),reading(doc.body));
   if(readingMarker.test(original.body))rawMarkedDocuments++;
   if([5,13,37].includes(doc.id))await page.screenshot({path:out+'/source-'+doc.id+'.png',fullPage:true});
   await page.evaluate(()=>document.querySelector('#source-dialog').close());
   documents++;
  }
  let eventDetails=0,quoteLocations=0;
  for(const row of cases.results){
   for(const event of row.actual.events){
    await page.goto(base+'/#event/'+event.id);
    await page.locator('.meeting-detail-head').waitFor();
    await clean(page.locator('#main'),'event '+event.id);
    assert.equal(await page.locator('.meeting-detail-head h1').innerText(),event.title);
    const quoteButton=page.locator('.meeting-reading [data-source][data-quote]').first();
    if(await quoteButton.count()){
     const raw=await quoteButton.getAttribute('data-quote'),did=Number(await quoteButton.getAttribute('data-source'));
     const doc=await get('documents/'+did);assert(doc.body.includes(raw));
     await quoteButton.click();
     await page.locator('#source-quote').waitFor();
     assert.equal(await page.locator('#source-quote').textContent(),reading(raw));
     await clean(page.locator('#source-content'),'quote '+event.id);
     await page.evaluate(()=>document.querySelector('#source-dialog').close());quoteLocations++;
    }
    if(!eventDetails)await page.screenshot({path:out+'/event-detail-desktop.png',fullPage:true});
    eventDetails++;
   }
  }
  let webPages=0;
  for(const original of baseline.web_pages){
   const doc=await get('web/pages/'+original.id);
   assert.equal(doc.body,original.body);
   assert(!marker.test(doc.title),'Website title '+doc.id);webPages++;
  }
  const sources=await get('web/sources?size=100');
  assert(sources.items.every(s=>!marker.test(s.name)));
  const runs=await get('web/runs?size=100');
  let websiteRuns=0;
  for(let n=1;n<=Math.ceil(runs.total/runs.size);n++){
   const batch=await get('web/runs?size=100&page='+n);
   for(const item of batch.items){
    const detail=await get('web/runs/'+item.id);
    assert(!marker.test(detail.config.name),'Historic website run name '+item.id);
    assert(detail.items.every(p=>!marker.test(p.title)),'Historic webpage title '+item.id);
    websiteRuns++;
   }
  }
  await page.goto(base+'/#overview');await page.locator('#company-select').waitFor();
  assert.equal(await page.locator('#company-select').inputValue(),'');
  assert.equal((await get('overview')).total,18);
  const layoutCheck=async()=>{
   assert.equal(await page.locator('.overview-composition').count(),1);
   assert.equal(await page.locator('.kpi-strip,.review-panel').count(),0);
   const composition=await page.locator('.overview-composition').boundingBox();
   const network=await page.locator('.network-panel').boundingBox();
   const events=await page.locator('.events-panel').boundingBox();
   assert(composition.y+composition.height<=network.y+1,'Composition must precede categories');
   assert(network.y+network.height<=events.y+1,'Events must follow categories');
   assert(Math.abs(network.width-composition.width)<3,'Categories must span the summary width');
   assert(Math.abs(events.width-composition.width)<3,'Events must span the summary width');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Page overflow');
  };
  await page.waitForFunction(()=>document.querySelector('.overview-composition .ring-total')?.textContent==='18');
  await layoutCheck();
  assert.equal(await page.locator('.composition-no-risk strong').innerText(),'4');
  await page.screenshot({path:out+'/overview-desktop.png',fullPage:true});
  for(const [level,total] of [['lv1',2],['lv2',8],['lv3',8]]){
   await page.locator('.overview-composition a[href*="level='+level+'"]').click();
   await page.locator('#event-filter').waitFor();
   assert.equal(await page.locator('#event-filter [name=level]').inputValue(),level);
   assert.equal((await get('events?level='+level)).total,total);
   await page.goto(base+'/#overview');
   await page.locator('#company-select').waitFor();
  }
  const companySwitches=[];
  for(const [id,total] of [[1,1],[14,2],[9,0]]){
   await page.selectOption('#company-select',String(id));
   await page.waitForFunction(({id,total})=>state.company?.id===id&&document.querySelector('.overview-composition .ring-total')?.textContent===String(total),{id,total});
   const overview=await get('overview'),rows=await get('events');
   assert.equal(overview.scope.company_id,id);assert.equal(overview.total,total);assert.equal(rows.total,total);
   await clean(page.locator('#main'),'company '+id);
   await layoutCheck();companySwitches.push({id,total});
   if(!total)await page.screenshot({path:out+'/overview-no-risk.png',fullPage:true});
  }
  await page.selectOption('#company-select','');
  await page.waitForFunction(()=>!state.company&&document.querySelector('.overview-composition .ring-total')?.textContent==='18');
  await page.setViewportSize({width:900,height:1000});await layoutCheck();
  await page.setViewportSize({width:390,height:844});
  await layoutCheck();
  await page.screenshot({path:out+'/overview-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  await ctx.request.post(base+'/api/auth/logout',{headers});
  const result={release:'20261112-workflow-r5',routes,list_pages_checked:listPages,
   document_details_checked:documents,marked_originals_displayed_cleanly:rawMarkedDocuments,
   latest_case_event_details_checked:eventDetails,quote_locations_checked:quoteLocations,
   web_page_sources_checked:webPages,website_names_checked:sources.items.length,website_run_details_checked:websiteRuns,
   reference_cases_verified:cases.passed,recommendations_verified:cases.recommendations_checked,
   all_company_event_total:18,company_switches:companySwitches,
   layout:{single_composition:true,no_review_sidebar:true,full_width_categories_and_events:true,viewports:[1440,900,390]},
   visible_preparation_markers:0,browser_errors:errors,
   source_bodies_unchanged:true,model_or_embedding_executed_by_check:false};
  fs.writeFileSync(out+'/pages-live-result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
