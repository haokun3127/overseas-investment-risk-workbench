const assert=require('assert/strict'),fs=require('fs'),vm=require('vm');
const app=fs.readFileSync('web/app.js','utf8').split('const RISK_TREE')[0];
const knowledge=fs.readFileSync('web/knowledge.js','utf8').split('function groupHits')[0];
const context={window:{matchMedia:()=>({matches:true})},document:{}};
vm.createContext(context);
vm.runInContext(app+knowledge+'\nthis.testReading={readingText,readingEsc,markRanges};',context);
const {readingText,readingEsc,markRanges}=context.testReading;
const raw='原文〔S1〕 TikTok依据法令〔2025〕42号办理，S1业务部参与；引用[1]。';
assert.equal(readingText(raw),'原文 TikTok依据法令〔2025〕42号办理，S1业务部参与；引用[1]。');
assert.equal(readingEsc('<img src=x onerror=alert(1)>〔S2〕'),'&lt;img src=x onerror=alert(1)&gt;');
const marked=markRanges(raw,['TikTok','S1']);
assert.equal(marked.count,2); // TikTok plus the legitimate S1 business unit.
assert(marked.html.includes(`data-start="${raw.indexOf('TikTok')}"`));
assert(!marked.html.includes('〔S1〕'));
assert(marked.html.includes('法令〔2025〕42号'));
assert(marked.html.includes('引用[1]'));
assert(raw.includes('〔S1〕'),'Source string was mutated');
console.log('Reading presentation: original offsets, meaningful identifiers, citation numbers and HTML escaping verified.');
