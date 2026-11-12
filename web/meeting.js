'use strict';
names.drafting='文书生成';
names['event-new']='新增风险事件';
function meetingView(route,html){
  const root=document.createElement('div');root.innerHTML=html;
  const admin=state.auth?.role==='admin';
  if(route==='overview'){
    if(state.overviewGaps?.length){
      const section=document.createElement('section');section.className='panel';
      section.innerHTML='<div class="panel-heading"><h2>待补充资料</h2></div><div class="panel-content"><p>以下资料尚未形成完整判断，不计为绿色无风险。展示最近20项，补充资料由管理员处理。</p>'+
        state.overviewGaps.map(item=>`<article><h3>${esc(item.title)}</h3><p class="preserve-lines">${readingEsc(item.reason)}</p></article>`).join('')+'</div>';
      root.append(section);
    }
    if(!admin){
      root.querySelectorAll('a[href^="#documents"],.setup-alert,.demo-note,.review-cta,.review-panel .panel-link').forEach(n=>n.remove());
      const standby=root.querySelector('.standby-copy');
      if(standby)standby.innerHTML='<h2>本企业暂无风险事件</h2><p>绿色栏展示已判定无风险的资料数量；待分析与证据不足不计为无风险。</p>';
    }
  }
  if(route==='events'){
    const actions=root.querySelector('.page-heading .actions');
    actions?.querySelector('a[href="#documents"]')?.remove();
    if(admin)actions?.insertAdjacentHTML('beforeend','<a class="primary" href="#event-new">新增风险事件</a>');
    if(!admin){const copy=root.querySelector('.page-heading p');if(copy)copy.textContent='查看本企业风险等级、事实依据与应对建议。';}
    const select=root.querySelector('[name=level]');
  }
  if(route==='event')return meetingDetail(state.currentEvent);
  return root.innerHTML;
}
async function meetingDrafting(){return draftingWorkspace();}
function bindDrafting(){bindDraftingWorkspace();}
function showMeetingDraft(result){showDraftWorkspace(result);}
function meetingEvidence(r,i){
  const admin=state.auth?.role==='admin';
  return `<article class="evidence"><h3>${i+1}. ${esc(r.title||'引用资料')}</h3><blockquote>${readingEsc(r.quote)}</blockquote><p>${esc(r.reason||'')}</p><small>${esc([r.source,r.date,r.locator].filter(Boolean).join(' · '))}</small><div>${admin&&r.document_id?sourceButton(r.document_id,'查看原文',r.quote):''}${r.url&&/^https?:\/\//.test(r.url)?`<a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">来源网页</a>`:''}</div></article>`;
}
function meetingDetail(e){
  e={...e,changes:(e.changes||[]).map(change=>({...change,action:change.action==='review_level'?'复核调整风险等级':change.action}))};
  const admin=state.auth?.role==='admin',refs=e.evidence||[];
  const back=state.eventListReturn?.scope===JSON.stringify([state.auth?.username,state.company?.id||null])?state.eventListReturn.href:'#events';
  const legal=refs.filter(r=>(r.kind==='knowledge'||String(r.reference||'').startsWith('K'))&&['id_law','cn_law','treaty','regional','judgment','arbitration','case'].includes(r.legal_metadata?.category));
  return `<a class="back-link" href="${esc(back)}">返回风险事件</a><header class="meeting-detail-head">${badge(e.level)}<h1>${esc(e.title)}</h1><p>${esc(e.category)} · ${esc(dateLabel(e))}${admin?' · '+(e.mode==='manual'?'人工录入':'模型研判'):''}${e.company_name?' · '+esc(e.company_name):''}</p></header>
    ${!e.is_latest?'<p class="notice-inline">这是历史分析版本，最新结果请从风险事件列表查看。</p>':''}
    <div class="meeting-reading"><section class="panel"><div class="panel-heading"><h2>事件摘要</h2></div><div class="panel-content"><p>${esc(e.summary)}</p>${e.impact?`<h3>影响判断</h3><p>${esc(e.impact)}</p>`:''}</div></section>
    <section class="panel"><div class="panel-heading"><h2>风险依据与来源</h2></div>${refs.length?refs.map(meetingEvidence).join(''):'<p class="panel-content">人工记录尚未附原文依据，请管理员补充核实。</p>'}</section>
    <section class="panel"><div class="panel-heading"><h2>应对对策</h2></div>${e.actions?.length?e.actions.map(action=>`<article class="panel-content"><h3>${esc(action.text)}</h3><p>适用条件：${esc(action.conditions)}</p>${action.basis.length?action.basis.map(meetingEvidence).join(''):'<p class="form-note">这项建议尚无可核验的法律依据，需人工核实后采用。</p>'}</article>`).join(''):`<div class="panel-content"><p class="preserve-lines">${esc(e.recommendation||'尚未填写应对建议。')}</p><h3>相关法律与案例来源</h3><p class="form-note">本结果尚未建立逐项对策与法律依据的对应关系，不能作为已确认的法定义务。</p></div>${legal.length?legal.map(meetingEvidence).join(''):'<p class="panel-content">本次没有可核验的法律或案例引用，请补充适用的法律依据。</p>'}`}</section>
    ${admin?`<section class="panel"><div class="panel-heading"><h2>人工复核与调整</h2>${badge(e.review_status)}</div><div class="panel-content">${meetingEditor(e)}${meetingBasisEditor(e)}<details><summary>修改记录（${(e.changes||[]).length}）</summary>${(e.changes||[]).map(c=>`<p>${when(c.created_at)} · ${esc(c.actor)} · ${esc({create:'新增',update:'修改',delete:'删除',standard_migration:'标准迁移',evidence:'补充依据',action_basis:'补充对策依据'}[c.action]||c.action)}<br>${esc(c.reason)}</p>`).join('')||'<p>暂无字段修改记录。</p>'}${(e.review_history||[]).map(c=>`<p>${when(c.created_at)} · ${esc(statuses[c.status])}<br>${esc(c.note)}</p>`).join('')}</details></div></section>`:e.reviewed_at?`<section class="panel"><div class="panel-heading"><h2>复核结果</h2>${badge(e.review_status)}</div><div class="panel-content"><p>更新于 ${when(e.reviewed_at)}</p>${e.review_note?`<p>${esc(e.review_note)}</p>`:''}</div></section>`:''}</div>`;
}
function meetingBasisEditor(e){
  const actions=e.actions?.length?e.actions:(e.recommendation?[{text:e.recommendation}]:[]);
  return `<details><summary>补充原文依据</summary><form id="meeting-basis-search"><label class="field">查找已有资料<input name="q" required placeholder="输入资料名称或关键词"></label><button class="secondary" type="submit">查找资料</button></form><div id="meeting-basis-options"></div><form id="meeting-basis-form" hidden><input type="hidden" name="document_id"><label class="field">依据用于<select name="target"><option value="event">事件风险判断</option>${actions.map((action,i)=>`<option value="${i}">对策 ${i+1}：${esc(action.text.slice(0,50))}${action.text.length>50?'…':''}</option>`).join('')}</select></label><label class="field">引用原文<textarea name="quote" required rows="5" minlength="6" maxlength="8000"></textarea></label><label class="field">依据说明<textarea name="reason" required rows="2" maxlength="2000" placeholder="说明原文支持哪项判断，以及适用范围"></textarea></label><p class="form-note">对策依据使用已分类的法律或裁判案例；法律效力须先在知识库核实。</p><button class="secondary" type="submit">保存依据</button></form><div id="meeting-basis-error" role="alert"></div></details>`;
}
function bindMeetingBasis(){
  const search=$('#meeting-basis-search'),form=$('#meeting-basis-form');if(!search)return;
  search.onsubmit=async e=>{e.preventDefault();try{
    const result=await api('/knowledge/search?q='+encodeURIComponent(search.elements.q.value));
    state.basisHits=result.items;$('#meeting-basis-options').innerHTML=result.items.map((r,i)=>`<p><button class="text-button" data-basis-choice="${i}">${esc(r.title)}</button></p>`).join('')||'<p>未找到相关资料，请先在知识库上传原文。</p>';
    $$('[data-basis-choice]').forEach(b=>b.onclick=()=>{const r=state.basisHits[Number(b.dataset.basisChoice)];form.hidden=false;form.elements.document_id.value=r.document_id;form.elements.quote.value=r.text;form.elements.quote.focus();});
  }catch(error){$('#meeting-basis-error').innerHTML=errorBox(error.message);}};
  form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;try{const target=form.elements.target.value;const endpoint=target==='event'?'/evidence':'/actions/'+Number(target)+'/basis';await api('/events/'+state.currentEvent.id+endpoint,{method:'POST',body:{revision:state.currentEvent.revision,document_id:Number(form.elements.document_id.value),quote:form.elements.quote.value,reason:form.elements.reason.value}});toast('依据已保存');await render();}catch(error){$('#meeting-basis-error').innerHTML=errorBox(error.message);button.disabled=false;}};
}
function meetingEditor(e={}){
  const cats=[...new Set([...(state.config.rules.categories||[]),'其他'])];
  return `<form id="meeting-event-form" data-id="${e.id||''}" data-revision="${e.revision||0}"><div class="form-grid">${!e.id?`<label class="field full">所属企业<select name="company_id" required><option value="">请选择企业</option>${companyData.items.map(c=>`<option value="${c.id}" ${c.id===state.company?.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label>`:''}<label class="field full">事件标题<input name="title" required maxlength="240" value="${esc(e.title||'')}"></label><label class="field">风险等级<select name="level">${Object.entries(e.id?{...levels,non_risk:'绿色 · 无风险'}:levels).map(([v,l])=>`<option value="${v}" ${e.level===v?'selected':''}>${esc(l)}</option>`).join('')}</select></label><label class="field">风险类型<select name="category">${cats.map(c=>`<option ${e.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label>${[['summary','事件摘要'],['impact','影响判断'],['recommendation','应对对策']].map(([k,l])=>`<label class="field full">${l}<textarea name="${k}" ${k==='summary'?'required':''} maxlength="10000" rows="3">${esc(e[k]||'')}</textarea></label>`).join('')}<label class="field full">${e.id?'调整':'新增'}原因<textarea name="reason" required maxlength="2000" rows="2" placeholder="请记录事实、依据及调整原因"></textarea></label></div><div class="form-actions"><button class="primary" type="submit">${e.id?'保存调整并认可':'新增事件'}</button>${e.id?'<button class="secondary" type="button" id="meeting-delete">删除事件</button>':''}</div><p class="form-note">绿色表示无风险；证据不足不能认定为无风险。历史模型分析保留原始记录，人工调整另行留痕。</p><div id="meeting-error" role="alert"></div></form>`;
}
function meetingCreate(){return heading('新增风险事件','填写已核实的风险事实，新增原因会随记录保存。','<a class="secondary" href="#events">返回事件列表</a>')+`<section class="panel"><div class="panel-content">${meetingEditor()}</div></section>`;}
function bindMeeting(){
  bindMeetingBasis();
  const form=$('#meeting-event-form');if(!form)return;
  form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    const data=Object.fromEntries(new FormData(form));data.revision=Number(form.dataset.revision);if(data.company_id)data.company_id=Number(data.company_id);
    try{const result=await api('/events'+(form.dataset.id?'/'+form.dataset.id:''),{method:form.dataset.id?'PUT':'POST',body:data});toast('风险事件已保存');if(form.dataset.id)await render();else location.hash='#event/'+result.id;}
    catch(error){$('#meeting-error').innerHTML=errorBox(error.message);button.disabled=false;}
  };
  $('#meeting-delete')?.addEventListener('click',async()=>{
    const reason=form.elements.reason.value.trim();if(!reason){$('#meeting-error').innerHTML=errorBox('请先填写删除原因。');form.elements.reason.focus();return;}
    if(!confirm(`确认删除《${state.currentEvent.title}》？\n所属企业：${state.currentEvent.company_name||'未归属企业'}\n删除后不再计入列表和统计，修改记录仍保留。`))return;
    try{await api('/events/'+form.dataset.id,{method:'DELETE',body:{revision:Number(form.dataset.revision),reason}});toast('事件已删除');location.hash='#events';}catch(error){$('#meeting-error').innerHTML=errorBox(error.message);}
  });
}
