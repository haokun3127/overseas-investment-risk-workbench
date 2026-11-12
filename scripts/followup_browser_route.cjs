const {chromium}=require('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try {
  const context=await browser.newContext({ignoreHTTPSErrors:true});
  const page=await context.newPage();
  for(const url of ['https://47.108.51.138/rag/api/release','http://47.108.51.138/rag/api/release']){
   try{const response=await page.goto(url,{timeout:12000,waitUntil:'domcontentloaded'}); console.log(JSON.stringify({url,status:response.status(),body:(await page.textContent('body')).slice(0,400)}));}
   catch(error){console.log(JSON.stringify({url,error:error.message.split('\n')[0]}));}
  }
 }finally{await browser.close();}
})().catch(error=>{console.log(JSON.stringify({error:error.message.split('\n')[0]}));process.exitCode=1;});
