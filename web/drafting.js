'use strict';
// Dedicated writing workspace. The route bindings are defined in meeting.js.
let draftCurrent=null,draftDirty=false,draftBusy=false,draftResize=null;
window.addEventListener('beforeunload',e=>{if(draftDirty||draftBusy){e.preventDefault();e.returnValue='';}});
document.addEventListener('click',e=>{
  const a=e.target.closest('a[href^="#"]');
  if(!a||!document.querySelector('.dw')||!a.hash||a.hasAttribute('data-dw-source'))return;
  if(draftBusy){e.preventDefault();e.stopImmediatePropagation();toast('正在处理，请完成后离开。');return;}
  if(draftDirty&&!confirm('正文修改尚未保存，确认离开并放弃修改？')){e.preventDefault();e.stopImmediatePropagation();}
  else draftDirty=false;
},true);
async function dwRefreshHistory(){
  const history=await api('/drafting/results');
  $('.dw-nav [data-dw-tab="history"]').textContent=`已保存文书（${history.items.length}）`;
  $('#dw-history .panel-content').innerHTML=`<ul class="dw-history">${history.items.map(d=>`<li><div><button class="text-button" data-open-draft="${d.id}">${esc(d.name)}</button><small>${when(d.created_at)} · 修改 ${d.revision} 次</small></div><button class="secondary" data-open-draft="${d.id}">打开文书</button></li>`).join('')}</ul>`;
  dwBindHistory();
}
async function draftingWorkspace(){
  draftResize?.disconnect();
  const [templates,history]=await Promise.all([api('/drafting/templates'),api('/drafting/results')]);
  state.draftTemplates=templates.items;draftCurrent=null;draftDirty=false;
  return heading('文书生成','选择模板、补充材料，生成后在成稿中直接修改。')+`<div class="dw">
    <nav class="dw-nav" aria-label="文书工作区"><button class="text-button" data-dw-tab="write" aria-pressed="true">起草文书</button><button class="text-button" data-dw-tab="history" aria-pressed="false">已保存文书（${history.items.length}）</button><button class="text-button" data-dw-tab="templates" aria-pressed="false">模板管理</button></nav>
    <div id="dw-write"><section id="dw-input" class="panel dw-input"><div class="panel-content">${templates.items.length?`
      <form id="drafting-form"><div class="dw-setup-grid"><div class="dw-template-settings"><h2>选择模板</h2><label class="field">文书模板<select name="template_id">${templates.items.map(t=>`<option value="${t.id}">${esc(t.category)} · ${esc(t.name)}</option>`).join('')}</select></label>
      <details class="dw-template-preview"><summary>查看模板内容</summary><div id="dw-template-body" class="preserve-lines"></div></details>
      <div id="dw-fields" class="form-grid"></div></div><div class="dw-material-editor"><h2>补充起草材料</h2>
      <div class="dw-label-row"><label for="dw-facts">事项事实与材料</label><label class="secondary dw-upload">上传事项材料<input id="dw-material" type="file" accept=".docx,.pdf,.txt,.md"></label></div>
      <p id="dw-material-status" class="form-note" role="status">可上传合同、函件等文本材料，也可直接填写。上传内容会带入下方供核对。</p>
      <textarea id="dw-facts" name="facts" rows="6" minlength="10" maxlength="30000" required placeholder="说明当事人、具体事项、时间、金额、适用地区及已有约定；不确定的内容请注明。"></textarea>
      <label class="field dw-instruction">起草要求（选填）<textarea name="instruction" rows="2" maxlength="2000" placeholder="例如：面向合作方发函，措辞客观，保留需要对方确认的事项。"></textarea></label>
      </div></div><div class="dw-generate-bar"><p>按模板结构起草，生成后可直接编辑并导出 Word。</p><div class="form-actions"><button class="primary" type="submit">生成文书草稿 ${icon('arrow')}</button><span id="drafting-status" role="status"></span></div></div><div id="dw-generate-error" role="alert"></div></form>`:
      `<h2>先添加一份文书模板</h2><p>上传已有模板或粘贴正文，保存后即可起草。</p><button class="primary" data-dw-tab="templates">添加模板</button>`}</div></section>
      <section id="drafting-result" class="dw-result" aria-live="polite"><div class="dw-empty"><svg class="icon" aria-hidden="true"><use href="#i-documents"/></svg><h2>成稿将在这里展示</h2><p>生成后可直接编辑正文、补齐缺项，保存并导出 Word。</p></div></section></div>
    <section id="dw-history" class="panel" hidden><div class="panel-heading"><h2>已保存文书</h2></div><div class="panel-content">${history.items.length?`<ul class="dw-history">${history.items.map(d=>`<li><div><button class="text-button" data-open-draft="${d.id}">${esc(d.name)}</button><small>${when(d.created_at)} · 修改 ${d.revision} 次</small></div><button class="secondary" data-open-draft="${d.id}">打开文书</button></li>`).join('')}</ul>`:'<p>还没有保存的文书。生成成功后会自动保存到这里。</p>'}</div></section>
    <section id="dw-templates" class="panel" hidden><div class="panel-heading"><h2>模板管理</h2></div><div class="panel-content"><form id="drafting-template-form"><label class="field">上传模板<input id="drafting-template-file" type="file" accept=".docx,.pdf,.txt,.md"></label><div class="form-grid"><label class="field">文书名称<input name="name" maxlength="150" required></label><label class="field">文书分类<input name="category" maxlength="100" required></label><label class="field full">模板正文<textarea name="body" rows="12" minlength="20" maxlength="30000" required placeholder="保留章节标题；可用 {{当事人}}、【待补充：日期】 标注待填字段。"></textarea></label></div><p class="form-note">上传提取正文及章节结构。请核对后保存；复杂表格、印章与原文件版式需在 Word 中处理。</p><button class="primary" type="submit">保存模板</button><div id="drafting-template-error" role="alert"></div></form><ul class="dw-history">${templates.items.map(t=>`<li><div>${esc(t.name)}<small>${esc(t.category)} · ${t.headings.length} 个章节 · ${t.fields.length} 个待填字段</small></div><button class="text-button" data-remove-template="${t.id}">停用模板</button></li>`).join('')}</ul></div></section></div>`;
}
function dwTab(name){
  if(draftBusy){toast('正在处理，请完成后切换。');return;}
  ['write','history','templates'].forEach(k=>{$('#dw-'+k).hidden=k!==name;});
  $$('.dw-nav [data-dw-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.dwTab===name)));
}
function dwTemplateFields(values={}){
  const form=$('#drafting-form');if(!form)return;
  const t=state.draftTemplates.find(t=>t.id===Number(form.elements.template_id.value));
  $('#dw-template-body').textContent=t?.body||'';
  $('#dw-fields').innerHTML=(t?.fields||[]).map((name,i)=>`<label class="field">${esc(name)}<input data-dw-field="${i}" maxlength="2000" value="${esc(values[name]||'')}" placeholder="未填写的字段将保留待补标记"></label>`).join('');
}
function dwFields(){
  const t=state.draftTemplates.find(t=>t.id===Number($('#drafting-form').elements.template_id.value));
  return Object.fromEntries((t?.fields||[]).map((n,i)=>[n,$(`[data-dw-field="${i}"]`).value]));
}
function dwBindHistory(){
  $$('[data-open-draft]').forEach(b=>b.onclick=async()=>{
    if(draftBusy)return;
    if(draftDirty&&!confirm('当前修改尚未保存，确认放弃并打开另一份文书？'))return;
    try{
      const result=await api('/drafting/results/'+b.dataset.openDraft);dwTab('write');showDraftWorkspace(result);
      const form=$('#drafting-form');
      if(form){
        let option=Array.from(form.elements.template_id.options).find(o=>Number(o.value)===result.template_id);
        if(!option){option=new Option(result.name+'（已停用模板，仅查看原稿）',String(result.template_id));form.elements.template_id.add(option);}
        form.elements.template_id.value=result.template_id;form.elements.facts.value=result.facts||'';
        form.elements.instruction.value=result.context?.instruction||'';dwTemplateFields(result.context?.field_values);
      }
      $('#drafting-result').scrollIntoView({block:'start'});
    }catch(e){toast(e.message);}
  });
}
function bindDraftingWorkspace(){
  // The app invokes all feature binders after every route render.
  // Only bind the writing workspace when its own forms exist.
  const templateForm=$('#drafting-template-form');
  if(!$('.dw')||!templateForm)return;
  $$('[data-dw-tab]').forEach(b=>b.onclick=()=>dwTab(b.dataset.dwTab));
  dwBindHistory();
  dwTemplateFields();
  $('#drafting-form')?.elements.template_id.addEventListener('change',()=>dwTemplateFields());
  for(const [id,path,target] of [['dw-material','/drafting/materials/upload','facts'],['drafting-template-file','/drafting/templates/upload','body']]){
    $('#'+id)?.addEventListener('change',async e=>{
      const file=e.target.files[0];if(!file)return;
      const body=new FormData();body.set('file',file);
      const status=$(target==='facts'?'#dw-material-status':'#drafting-template-error');
      e.target.disabled=true;draftBusy=true;status.textContent='正在读取文件…';
      try{
        const data=await api(path,{method:'POST',body}),form=$(target==='facts'?'#drafting-form':'#drafting-template-form');
        const text=target==='facts'?data.text:data.body,field=form.elements[target];
        if(target==='body'&&field.value.trim()&&!confirm('替换正在编辑的模板正文？已保存的模板不会更改。')){status.textContent='已保留正在编辑的模板正文。';return;}
        const joined=target==='facts'&&field.value.trim()?field.value+'\n\n'+text:text;
        if(joined.length>Number(field.maxLength))throw new Error('合并后的正文超出长度限制，请精简已有内容后重新上传。');
        field.value=joined;
        if(target==='body')form.elements.name.value=data.name;
        status.textContent=data.truncated?'已读取前30000字，请精简并核对模板后保存。':`已读取“${data.name}”，请核对下方正文。`;
      }catch(error){status.textContent='文件未带入：'+error.message;}
      finally{e.target.disabled=false;e.target.value='';draftBusy=false;}
    });
  }
  templateForm.onsubmit=async e=>{
    e.preventDefault();if(draftBusy)return;
    const b=e.currentTarget.querySelector('[type=submit]');b.disabled=true;draftBusy=true;
    try{await api('/drafting/templates',{method:'POST',body:Object.fromEntries(new FormData(e.currentTarget))});toast('模板已保存');draftBusy=false;await render();}
    catch(error){$('#drafting-template-error').innerHTML=errorBox(error.message);}
    finally{b.disabled=false;draftBusy=false;}
  };
  $$('[data-remove-template]').forEach(b=>b.onclick=async()=>{
    if(draftBusy)return;if(!confirm('停用此模板？已生成文书保留。'))return;
    try{await api('/drafting/templates/'+b.dataset.removeTemplate,{method:'DELETE'});await render();}catch(e){toast(e.message);}
  });
  $('#drafting-form')?.addEventListener('submit',e=>{e.preventDefault();dwGenerate();});
}
async function dwGenerate(instruction,previous){
  if(draftBusy)return;
  const form=$('#drafting-form');
  if(!form){toast('原模板已停用；可编辑和下载原稿，继续生成请先添加适用模板。');return;}
  if(!form.reportValidity())return;
  if(draftDirty){toast('请先保存正文修改，再继续生成。');return;}
  const button=form.querySelector('[type=submit]');draftBusy=true;button.disabled=true;
  $('#dw-generate-error').innerHTML='';$('#drafting-status').textContent='正在按模板起草并核对引用，请稍候…';
  const refine=$('#dw-refine button');if(refine)refine.disabled=true;
  const locked=$$('.dw input,.dw textarea,.dw select').map(el=>({el,disabled:el.disabled}));
  locked.forEach(({el})=>el.disabled=true);
  try{
    const result=await api('/drafting',{method:'POST',timeoutMs:190000,body:{
      template_id:Number(form.elements.template_id.value),facts:form.elements.facts.value,
      field_values:dwFields(),instruction:instruction??form.elements.instruction.value,previous_draft_id:previous||null}});
    showDraftWorkspace(result);$('#drafting-result').scrollIntoView({block:'start'});toast('文书已生成并保存');
    try{await dwRefreshHistory();}catch(e){toast('文书已保存；历史列表刷新失败，可重新进入此页查看。');}
  }catch(e){$('#dw-generate-error').innerHTML=errorBox(e.message);}
  finally{locked.forEach(({el,disabled})=>el.disabled=disabled);draftBusy=false;button.disabled=false;if(refine)refine.disabled=false;$('#drafting-status').textContent='';}
}
function dwChecks(checks){
  return `<div class="dw-checks"><span>${checks.sections} 个章节 · ${checks.characters} 字</span><span id="dw-save-status" role="status">已保存</span></div>`+
    (checks.missing_fields?.length?`<div class="dw-missing"><h3>待补充字段</h3><p>${checks.missing_fields.map(esc).join('、')}</p></div>`:'')+
    (checks.warnings?.length?`<div class="dw-missing"><h3>需核对的事项</h3>${checks.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</div>`:'');
}
function showDraftWorkspace(result){
  draftResize?.disconnect();
  draftCurrent=result;draftDirty=false;
  const checks=result.checks||{sections:result.blocks.length,characters:result.blocks.reduce((n,b)=>n+b.text.length,0)};
  $('#dw-input').hidden=true;
  $('#drafting-result').innerHTML=`<div class="dw-result-bar"><div><h2>文书草稿</h2><p>直接点击标题或正文修改；保存后再下载。</p></div><div class="actions"><button id="dw-toggle-input" class="text-button" aria-expanded="false" aria-controls="dw-input">修改事项材料</button><button id="dw-save" class="secondary" disabled>保存修改</button><a id="dw-download" class="primary" href="api/drafting/${result.id}/docx">下载 Word</a></div></div>
    <div id="dw-checks">${dwChecks(checks)}</div><div id="draft-edit-error" role="alert"></div>
    <article class="dw-paper" aria-label="文书编辑区"><h2>${esc(result.name)}</h2>${result.blocks.map((b,i)=>`<section class="dw-section"><input class="dw-heading" data-draft-heading="${i}" aria-label="第${i+1}章标题" value="${esc(b.heading||'')}" maxlength="150"><textarea class="dw-text" data-draft-text="${i}" aria-label="第${i+1}章正文" maxlength="6000">${esc(b.text)}</textarea><small class="dw-refs">${b.citations.map(n=>`<a href="#dw-source-${n}" data-dw-source="${n}">[${n}]</a>`).join(' ')}</small></section>`).join('')}</article>
    <div class="dw-save-note"><label class="field">修改说明（保存修改时填写）<input id="dw-reason" maxlength="2000" placeholder="简要说明补充或调整了什么"></label><p class="form-note">文书需人工审核。正文修改后保留原引用用于追溯，系统不会将手改内容标为已自动核验。</p></div>
    <form id="dw-refine" class="dw-refine"><h3>让模型继续修改</h3><label class="field">修改要求<textarea name="instruction" rows="2" minlength="2" maxlength="2000" required placeholder="例如：保留事实，简化第二条的表达；新增事实请补充到上方事项材料。"></textarea></label><button class="secondary" type="submit">按要求另存一份新稿</button><p class="form-note">原稿保留，可在“已保存文书”中重新打开。</p></form>
    <details id="dw-sources" class="dw-sources"><summary>查看依据与来源（${result.sources.length}）</summary>${result.sources.map(s=>`<article id="dw-source-${s.number}"><h3>[${s.number}] ${esc(s.title)}</h3><small>${esc(({facts:'事项事实',template:'文书模板',knowledge:'参考依据'})[s.role]||'参考资料')}</small><blockquote>${readingEsc(s.quote)}</blockquote>${s.document_id?sourceButton(s.document_id,'查看原文',s.quote):''}${s.url&&/^https?:\/\//.test(s.url)?`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">来源网页</a>`:''}</article>`).join('')}</details>`;
  $('#dw-toggle-input').onclick=()=>{
    if(draftBusy)return;
    const input=$('#dw-input');input.hidden=!input.hidden;
    $('#dw-toggle-input').setAttribute('aria-expanded',String(!input.hidden));
    $('#dw-toggle-input').textContent=input.hidden?'修改事项材料':'收起事项材料';
    if(!input.hidden)input.scrollIntoView({block:'start'});
  };
  function fit(el){el.style.height='auto';el.style.height=Math.max(72,el.scrollHeight+4)+'px';}
  $$('.dw-text').forEach(el=>{fit(el);el.addEventListener('input',()=>fit(el));});
  let paperWidth=0;
  draftResize=new ResizeObserver(entries=>{
    const width=entries[0].contentRect.width;
    if(width!==paperWidth){paperWidth=width;$$('.dw-text').forEach(fit);}
  });
  draftResize.observe($('.dw-paper'));
  $$('.dw-heading,.dw-text').forEach(el=>el.addEventListener('input',()=>{
    draftDirty=true;$('#dw-save').disabled=false;$('#dw-save-status').textContent='有修改未保存';
    $('#dw-download').setAttribute('aria-disabled','true');$('#dw-refine button').disabled=true;
  }));
  $('#dw-download').onclick=e=>{if(draftDirty){e.preventDefault();toast('请先保存修改，再下载最新正文。');}};
  $$('[data-dw-source]').forEach(a=>a.onclick=e=>{
    e.preventDefault();$('#dw-sources').open=true;$('#dw-source-'+a.dataset.dwSource).scrollIntoView({block:'center'});
  });
  $('#dw-save').onclick=async()=>{
    const reason=$('#dw-reason');if(!reason.value.trim()){reason.focus();toast('请填写修改说明。');return;}
    if(draftBusy)return;draftBusy=true;$('#dw-save').disabled=true;
    const blocks=result.blocks.map((b,i)=>({heading:$(`[data-draft-heading="${i}"]`).value,text:$(`[data-draft-text="${i}"]`).value,citations:b.citations}));
    const locked=$$('.dw-heading,.dw-text,#dw-reason');locked.forEach(el=>el.disabled=true);
    try{
      const saved=await api('/drafting/results/'+result.id,{method:'PUT',body:{revision:result.revision||0,blocks,reason:reason.value}});
      result.revision=saved.revision;result.blocks=blocks;result.checks=saved.checks;result.manually_edited=true;
      draftDirty=false;$('#dw-download').removeAttribute('aria-disabled');$('#dw-checks').innerHTML=dwChecks(saved.checks);
      $('#dw-refine button').disabled=false;toast('修改已保存，Word 已同步更新');
    }catch(e){$('#draft-edit-error').innerHTML=errorBox(e.message);$('#dw-save').disabled=false;}
    finally{locked.forEach(el=>el.disabled=false);draftBusy=false;}
  };
  $('#dw-refine').onsubmit=e=>{e.preventDefault();dwGenerate(e.currentTarget.elements.instruction.value,result.id);};
}
