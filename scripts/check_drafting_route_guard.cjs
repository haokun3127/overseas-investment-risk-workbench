// Other routes must be safe when the application invokes every feature binder.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const context={window:{addEventListener(){}},document:{addEventListener(){}},$:()=>null};
vm.createContext(context);
const source=fs.readFileSync('web/drafting.js','utf8');
// Removing the fix must reproduce the regression, proving this check covers it.
const oldContext={window:{addEventListener(){}},document:{addEventListener(){}},$:()=>null,$$:()=>[]};
vm.createContext(oldContext);
vm.runInContext(source.replace("if(!$('.dw')||!templateForm)return;",""),oldContext);
assert.throws(()=>vm.runInContext('bindDraftingWorkspace()',oldContext),/null/);
vm.runInContext(source,context);
assert.doesNotThrow(()=>vm.runInContext('bindDraftingWorkspace()',context));
console.log('PASS: drafting binder is inert outside the drafting route');
