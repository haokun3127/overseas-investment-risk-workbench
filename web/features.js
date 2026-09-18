'use strict';
// Business workflow enhancements share the same API and design tokens as the workbench.
const workDrafts = new Map();
const activityNames={rules_updated:'更新风险规则',document_imported:'导入资料',file_imported:'上传文件',document_policy_changed:'调整资料使用范围',event_reviewed:'保存业务复核',analysis_completed:'完成风险分析',analysis_failed:'分析失败',events_exported:'导出风险台账',demo_seeded:'载入虚构演示案例',model_checked:'检查模型连接'};
function activityDetail(detail){return detail.replace(/connection and JSON protocol verified/g,'连接与 JSON 协议验证通过').replace(/allow_external=True/g,'允许外部分析').replace(/allow_external=False/g,'仅限本地').replace(/created=True/g,'已新增').replace(/created=False/g,'资料重复').replace(/status=accepted/g,'结论：已认可').replace(/status=needs_change/g,'结论：需修正').replace(/status=pending/g,'结论：待复核').replace(/scope=demo/g,'范围：虚构演示').replace(/scope=real/g,'范围：真实资料').replace(/scope=all/g,'范围：全部资料').replace(/event=/g,'事件编号：').replace(/document=/g,'资料编号：').replace(/job=/g,'任务编号：').replace(/analysis=/g,'分析编号：').replace(/count=/g,'数量：').replace(/rows=/g,'记录数：').replace(/created=/g,'新增数：').replace(/id=/g,'资料编号：');}

function ruleFields(r){
  return `<p class="form-note">逐项填写业务标准。保存后用于后续分析，历史版本保留原规则。</p><div class="form-grid"><label class="field full">规则版本<input name="version" maxlength="60" required value="${esc(r.version)}"></label><label class="field full">风险类型（每行一个，最多30个）<textarea name="categories" rows="6" required>${esc(r.categories.join('\n'))}</textarea></label>${Object.entries(levels).map(([v,l])=>`<label class="field full">${l}判定标准<textarea name="level_${v}" maxlength="2000" rows="3" required>${esc(r.levels[v])}</textarea></label>`).join('')}<label class="field full">适用范围与补充说明<textarea name="notes" rows="3" maxlength="5000">${esc(r.notes)}</textarea></label></div><label class="check-field"><input type="checkbox" name="confirmed" ${r.confirmed?'checked':''}><span>这份规则已经过甲方业务确认，可以用于后续风险分析。</span></label><button class="primary" type="submit">保存规则</button><div id="rules-error" aria-live="polite"></div>`;
}

function workspacePanel(w){
  return `<section class="panel workflow-panel"><div class="panel-heading"><h2>分析准备与业务待办</h2><small>真实资料 · 当前服务器</small></div><div class="workspace-checks">${w.checks.map(c=>`<a href="${c.href}"><span class="check-state">${icon(c.ready?'check':'arrow')}</span><span><strong>${esc(c.label)}</strong><small>${c.ready?'已具备':'前往准备'}</small></span></a>`).join('')}</div><div class="workspace-next"><span>尚未产出分析结果 <strong>${w.unanalyzed}</strong> 条</span><a href="#documents">处理待分析资料 ${icon('arrow')}</a><a href="#knowledge">补充参考依据 ${icon('arrow')}</a></div></section>`;
}

async function enhanceView(route,html){
  const host=document.createElement('div');host.innerHTML=html;
  if(route==='settings'){
    host.querySelector('#rules-form').innerHTML=ruleFields(state.config.rules);
    host.querySelector('.panel-content').insertAdjacentHTML('beforeend',`<h3>连接检查</h3><p class="form-note">仅发送固定合成测试内容，不读取业务资料。外部 API 可能产生少量调用费用。</p><button class="secondary" id="model-check" ${state.config.configured?'':'disabled'}>发送合成内容并检查连接</button><div id="model-check-result" aria-live="polite"></div>`);
    try{const r=await api('/runtime');host.insertAdjacentHTML('beforeend',`<section class="panel"><div class="panel-heading"><h2>本地运行状态</h2><button class="text-button" data-refresh>更新状态</button></div><div class="panel-content"><dl class="definition"><dt>状态时间</dt><dd>${when(r.checked_at)}</dd><dt>后台队列</dt><dd>${r.worker_enabled?'已启用':'未启用（当前实例不执行任务）'}</dd><dt>资料与索引</dt><dd>${r.documents} 条资料 · ${r.chunks} 个文本片段 · ${r.analyses} 个分析版本</dd><dt>数据库大小</dt><dd>${(r.database_bytes/1048576).toFixed(2)} MB（不含附件及 WAL 文件）</dd><dt>磁盘可用</dt><dd>${(r.disk_free_bytes/1073741824).toFixed(2)} GB</dd><dt>最近分析记录</dt><dd>${r.last_analysis?when(r.last_analysis.created_at)+' · '+esc(r.last_analysis.model):'暂无分析记录'}</dd></dl><p class="form-note">上线前请由运维人员按项目 README 的备份与恢复步骤验证恢复流程。系统不会自动生成备份。</p></div></section>`);}catch(e){host.insertAdjacentHTML('beforeend',errorBox('运行状态读取失败：'+e.message));}
  }
  if(route==='events'){
    const href='/api/export/events?'+new URLSearchParams({...state.filter,demo:state.scope});
    host.querySelector('.page-heading .actions').insertAdjacentHTML('afterbegin',`<a class="secondary" href="${esc(href)}">导出当前筛选 CSV</a>`);
    host.querySelector('.page-heading .actions').insertAdjacentHTML('afterbegin',`<a class="secondary" href="#report?${esc(new URLSearchParams({...state.filter,demo:state.scope}))}">生成风险简报</a>`);
    host.querySelector('#event-filter').insertAdjacentHTML('beforeend','<span class="filter-help">导出包含全部匹配事件、复核意见及引用依据。</span>');
  }
  if(route==='event'){
    const e=state.currentEvent;
    const form=host.querySelector('#review-form');
    form.insertAdjacentHTML('beforeend',`<details class="review-history"><summary>复核历史 · ${e.review_history.length} 条</summary>${e.review_history.length?e.review_history.map(h=>`<article><div>${badge(h.status)} <small>${when(h.created_at)}</small></div><p>${esc(h.note||'未填写意见')}</p></article>`).join(''):'<p class="form-note">保存复核后会在此保留每次结论与意见。</p>'}</details>`);
    host.querySelector('.back-link').href=state.lastEvents||eventHref();
  }
  if(route==='documents'||route==='knowledge'){
    const form=host.querySelector('#document-filter');
    form.querySelector('input').placeholder='按标题或来源搜索';
    form.insertAdjacentHTML('beforeend',`<label>使用范围<select name="policy">${[['','全部资料'],['local','仅限本地'],['external','允许外部分析']].map(([v,l])=>`<option value="${v}" ${state.filter.policy===v?'selected':''}>${l}</option>`).join('')}</select></label>${route==='documents'?`<label>分析状态<select name="status">${[['','全部状态'],['unanalysed','尚无分析结果'],['queued','排队中'],['running','分析中'],['completed','已完成'],['failed','失败']].map(([v,l])=>`<option value="${v}" ${state.filter.status===v?'selected':''}>${l}</option>`).join('')}</select></label>`:''}<button class="text-button" type="button" id="reset-doc-filter">重置</button>`);
    const importForm=host.querySelector('#import-form');
    importForm.insertAdjacentHTML('afterbegin','<p class="draft-hint" id="draft-status" role="status">手动录入内容在本次页面会话内暂存。</p>');
    const body=importForm.querySelector('[name=body]');
    if(body)body.insertAdjacentHTML('afterend','<small id="body-count">0 / 60000 字符</small>');
    const select=host.querySelector('#analyze-selected');
    if(select)select.textContent='分析所选资料（0）';
  }
  if(route==='jobs'&&!host.querySelector('#job-filter')){
    host.querySelector('.panel-heading').insertAdjacentHTML('afterend',`<form class="filters" id="job-filter"><label class="search-field">搜索任务<input name="q" placeholder="输入资料标题或任务编号"></label><label>任务状态<select name="status"><option value="">全部状态</option>${['queued','running','completed','failed'].map(s=>`<option value="${s}">${statuses[s]}</option>`).join('')}</select></label><button class="secondary small">筛选</button><span id="job-match" class="muted" aria-live="polite"></span></form>`);
    host.querySelectorAll('tbody tr').forEach(row=>{
      const badgeNode=row.querySelector('.badge');row.dataset.jobStatus=[...badgeNode.classList].find(v=>v!=='badge');
    });
  }
  if(route==='overview'||route==='settings'||route==='knowledge'){
    try{
      const w=await api('/workspace');
      if(route==='overview'){
        host.querySelector('.overview-grid').insertAdjacentHTML('afterend',workspacePanel(w));
        host.querySelector('.page-heading').classList.add('overview-heading');
        host.querySelector('.page-heading h1').insertAdjacentHTML('beforebegin','<div class="page-eyebrow">海外投资 · 风险研判</div>');
      }
      if(route==='knowledge'){
        const d=w.documents.knowledge||{count:0,authorized:0,characters:0};
        host.querySelector('.page-heading').insertAdjacentHTML('afterend',`<div class="library-summary"><span><strong>${d.count}</strong> 份真实参考资料</span><span><strong>${d.characters.toLocaleString('zh-CN')}</strong> 字符</span><span><strong>${d.authorized}</strong> 份允许外部分析</span><span>检索结果始终可以追溯原文</span></div>`);
      }
      if(route==='settings')host.insertAdjacentHTML('beforeend',`<section class="panel"><div class="panel-heading"><h2>最近操作记录</h2><small>最近15次已记录操作</small></div><div class="activity-list">${w.recent_activity.length?w.recent_activity.map(a=>`<article><strong>${esc(activityNames[a.action]||a.action)}</strong><time>${when(a.created_at)}</time><p>${esc(activityDetail(a.detail))}</p></article>`).join(''):'<p class="form-note">导入、分析、规则修改及业务复核后将产生操作记录。</p>'}</div></section>`);
    }catch(e){host.insertAdjacentHTML('beforeend',`<p class="form-note">补充统计暂不可用：${esc(e.message)}。主要业务功能仍可使用。</p>`);}
  }
  return host.innerHTML;
}

function bindFeatures(){
  $('#model-check')?.addEventListener('click',async e=>{const b=e.currentTarget;b.disabled=true;$('#model-check-result').innerHTML='<p role="status">正在验证连接与响应协议…</p>';try{const r=await api('/model/check',{method:'POST'});$('#model-check-result').innerHTML=`<div class="success">${esc(r.message)}<br>${when(r.checked_at)} · ${r.duration_ms} 毫秒</div>`;}catch(err){$('#model-check-result').innerHTML=errorBox(err.message);}finally{b.disabled=false;}});
  if(state.route==='events')state.lastEvents=location.hash;
  const rulesForm=$('#rules-form');
  if(rulesForm){
    rulesForm.addEventListener('submit',async e=>{
      e.preventDefault();e.stopImmediatePropagation();const b=$('[type=submit]',rulesForm);b.disabled=true;
      const f=new FormData(rulesForm);
      const rules={version:f.get('version').trim(),categories:f.get('categories').split('\n').map(v=>v.trim()).filter(Boolean),levels:Object.fromEntries(Object.keys(levels).map(v=>[v,f.get('level_'+v).trim()])),notes:f.get('notes'),confirmed:f.has('confirmed')};
      try{await api('/rules',{method:'PUT',body:rules});toast('规则已保存，后续分析使用此版本');await render();}catch(err){$('#rules-error').innerHTML=errorBox(err.message);b.disabled=false;}
    },true);
  }
  $('#event-filter')?.addEventListener('submit',e=>{
    const f=new FormData(e.currentTarget);
    if(f.get('date_from')&&f.get('date_to')&&f.get('date_from')>f.get('date_to')){e.preventDefault();e.stopImmediatePropagation();toast('开始日期不能晚于结束日期。');}
  },true);
  $('#reset-doc-filter')?.addEventListener('click',()=>{state.filter={};state.page=1;navigateList();});
  const importForm=$('#import-form');
  if(importForm){
    const key=state.route;
    const fields=['title','date','source','url','body'];
    if(state.importMode==='manual'){
      const draft=workDrafts.get(key);
      if(draft)for(const name of fields){const input=importForm.elements.namedItem(name);if(input)input.value=draft[name]||'';}
      const update=()=>{$('#body-count').textContent=`${importForm.elements.body.value.length} / 60000 字符`;};update();
      importForm.addEventListener('input',()=>{workDrafts.set(key,Object.fromEntries(fields.map(name=>[name,importForm.elements.namedItem(name).value])));update();$('#draft-status').textContent='草稿已在本次页面会话内暂存；关闭或刷新页面将清除。';});
      if($('.success',importForm)){workDrafts.delete(key);for(const name of fields)importForm.elements.namedItem(name).value='';update();}
    }
    importForm.addEventListener('submit',e=>{
      const file=importForm.elements.namedItem('file')?.files?.[0];
      if(file&&(file.size>10*1024*1024||! /\.(csv|xlsx|docx|pdf|txt|md)$/i.test(file.name))){e.preventDefault();e.stopImmediatePropagation();$('#import-result').innerHTML=errorBox('请选择10MB以内的 CSV、Excel、Word、文本型 PDF、TXT 或 Markdown 文件。');}
    },true);
  }
  const selected=$('#analyze-selected');
  if(selected){const update=()=>{selected.textContent=`分析所选资料（${$$('[name=doc-select]:checked').length}）`;};$$('[name=doc-select],#select-all').forEach(c=>c.addEventListener('change',update));}
  const jobForm=$('#job-filter');
  if(jobForm){
    const apply=()=>{state.filter=Object.fromEntries(new FormData(jobForm));state.page=1;navigateList();};
    jobForm.addEventListener('submit',e=>{e.preventDefault();apply();});jobForm.elements.status.addEventListener('change',apply);
  }
}
