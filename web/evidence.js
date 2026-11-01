'use strict';
const changeNames={added:'首次收录',changed:'正文更新',unchanged:'未变化',incomparable:'采集方式变化'};

async function evidencePage(id){
  if(id)return evidenceDetail(await api('/evidence/'+id));
  const status=state.filter.status||'pending';
  const data=await api('/evidence?'+new URLSearchParams({status,q:state.filter.q||'',page:state.page}));
  return heading('待补证','集中处理证据不足的分析，补充原文或业务材料后重新判断。','<a class="secondary" href="#documents">资料与分析</a>')+
    `<nav class="evidence-tabs" aria-label="补证状态"><a href="#evidence?status=pending" ${status==='pending'?'aria-current="page"':''}>待补证 <strong>${data.counts.pending}</strong></a><a href="#evidence?status=resolved" ${status==='resolved'?'aria-current="page"':''}>已形成结论 <strong>${data.counts.resolved}</strong></a></nav>`+
    `<form class="filters" id="evidence-search"><label>查找资料<input name="q" value="${esc(state.filter.q||'')}" placeholder="标题或来源"></label><button class="secondary">查询</button></form>`+
    (data.items.length?`<section class="panel evidence-queue"><ul>${data.items.map(a=>`<li><div class="evidence-queue-main"><h2><a href="#evidence/${a.id}">${esc(a.title)}</a></h2><p class="form-note">${esc(a.company_name||'未指定归属公司')} · 分析 v${a.version} · ${when(a.created_at)}</p>${a.reasons.length?`<p>${esc(a.reasons[0].slice(0,180))}${a.reasons[0].length>180?'…':''}</p>`:''}</div><div class="evidence-queue-action">${a.reasons.length>1?`<span>共 ${a.reasons.length} 段分析说明</span>`:''}${badge(a.decision)}${['queued','running'].includes(a.job_status)?badge(a.job_status):''}<span>${a.supplements} 份补充材料${a.checklist.total?` · ${a.checklist.remaining} 项待补`: ''}</span><a class="${status==='pending'?'primary':'secondary'} small" href="#evidence/${a.id}">${status==='pending'?'处理补证':'查看结论'}</a></div></li>`).join('')}</ul>${pagination(data)}</section>`:empty(status==='pending'?'当前没有待补证资料':'尚无补证后的新结论',status==='pending'?'最新分析为“证据不足”的非演示资料会出现在这里。':'补充证据并重新分析后，可在这里查看已形成的风险或非风险结论。'));
}

function evidenceDetail(a){
  const current=a.id===a.latest_analysis_id;
  const blocked=a.supplements.some(s=>s.quarantined_at);
  const canStart=a.editable&&a.supplements.length&&!blocked;
  return heading('补充证据',a.title,'<a class="secondary" href="#evidence">返回补证列表</a>')+
    `<div class="evidence-detail" data-evidence-id="${a.id}">${checklistPanel(a)}<section class="panel"><div class="panel-heading"><h2>原分析与缺失依据</h2>${badge(a.decision)}</div><div class="panel-content"><p class="form-note">分析 v${a.version} · ${when(a.created_at)} · 规则 ${esc(a.rules.version)}</p>${a.reasons.length?`<details class="evidence-original-reason"><summary>查看完整分析说明（${a.reasons.length} 段）</summary>${a.reasons.map(r=>`<p class="evidence-reason">${esc(r)}</p>`).join('')}</details>`:''}${!a.reasons.length?`<p>${esc(a.result.parts?.map(p=>p.reason).join('；')||a.result.reason||'已形成新结论，请核验分析记录。')}</p>`:''}<div class="actions">${sourceButton(a.document_id,'查看原文与全部分析记录')}${!current?`<a class="primary small" href="#evidence/${a.latest_analysis_id}">查看最新分析</a>`:''}</div>${!current?'<p class="notice-inline">正在查看历史版本。补充材料以当前关联清单为准；各次分析实际使用的材料编号保存在分析记录中。</p>':''}${a.active_job?`<p role="status">${badge(a.active_job.status)} 任务 #${a.active_job.id} 已提交。完成后刷新查看新版本。</p><button class="secondary small" data-refresh>刷新分析状态</button>`:''}</div></section>`+
    `<section class="panel"><div class="panel-heading"><h2>已关联补充材料</h2><span>${a.supplements.length} / 10 份 · ${a.characters.toLocaleString('zh-CN')} / 24,000 字符</span></div><div class="panel-content">${a.supplements.length?`<ul class="supplement-list">${a.supplements.map(s=>`<li><div><strong>${esc(s.title)}</strong><p class="form-note">${s.characters.toLocaleString('zh-CN')} 字符${s.quarantined_at?' · 已隔离':''}</p></div><div class="actions">${sourceButton(s.id,'查看材料')}${a.editable?`<button class="text-button" data-unlink-evidence="${s.id}">移除关联</button>`:''}</div></li>`).join('')}</ul>`:'<p class="muted">尚未添加材料。可补充政策原文、通知附件或与该事项有关的业务事实。</p>'}<p class="form-note">材料仅关联这条资料，不会自动进入公共知识库。保存材料后仍需提交重新分析。</p></div></section>`+
    (a.editable?`<section class="panel"><div class="panel-heading"><h2>添加补充材料</h2></div><div class="panel-content"><form id="evidence-text" class="form-grid"><label class="field full">材料标题<input name="title" maxlength="240" required></label><label class="field full">补充原文或业务事实<textarea name="body" rows="7" maxlength="24000" required placeholder="填写可核验的事实，并注明出处；请勿只填写希望模型得出的结论。"></textarea></label><label class="field">来源说明<input name="source" maxlength="300" placeholder="发布机构、文件名称或业务部门"></label><label class="field">原始链接（可选）<input name="url" type="url" maxlength="2000" placeholder="https://"></label><div class="full actions"><button class="secondary" type="submit">保存补充材料</button></div><div id="evidence-text-feedback" class="full" role="status"></div></form><details class="evidence-upload"><summary>上传附件作为补充材料</summary><form id="evidence-upload"><label class="field">选择附件<input type="file" name="file" accept=".txt,.md,.docx,.pdf,.csv,.xlsx" required></label><p class="form-note">支持 Word、文本 PDF、TXT 和单条记录表格；文件不超过10MB，所有补充正文合计不超过24000字符。</p><button class="secondary" type="submit">上传并保存</button><div id="evidence-upload-feedback" role="status"></div></form></details></div></section>`:'')+
    `<section class="panel"><div class="panel-heading"><h2>分析版本</h2></div><div class="panel-content"><ol class="evidence-history">${a.history.map(h=>`<li><a href="#evidence/${h.id}" ${h.id===a.id?'aria-current="page"':''}>v${h.version}</a>${badge(h.decision)}<time>${when(h.created_at)}</time></li>`).join('')}</ol>${a.editable?`<div class="evidence-submit"><p>重新分析会发送原资料、补充正文和相关知识片段。提交时固定当前规则；原分析记录继续保留。</p>${blocked?'<p class="error">部分补充材料已隔离，请核对或移除关联。</p>':''}<button class="primary" id="evidence-reanalyze" ${canStart?'':'disabled'}>使用补充材料重新分析</button><div id="evidence-submit-feedback" role="status"></div></div>`:''}</div></section></div>`;
}

function bindEvidence(){
  $('#evidence-search')?.addEventListener('submit',e=>{e.preventDefault();state.filter.q=new FormData(e.currentTarget).get('q');state.page=1;navigateList();});
  const host=$('[data-evidence-id]');if(!host)return;
  const id=host.dataset.evidenceId;
  for(const mode of ['text','upload'])$('#evidence-'+mode)?.addEventListener('submit',async e=>{
    e.preventDefault();const form=e.currentTarget,b=$('[type=submit]',form),out=$('#evidence-'+mode+'-feedback');b.disabled=true;out.innerHTML='';
    try{const data=new FormData(form);const body=mode==='upload'?data:Object.fromEntries(data);await api('/evidence/'+id+(mode==='upload'?'/upload':'/supplements'),{method:'POST',body});toast('补充材料已保存');await render({quiet:true});}catch(error){out.innerHTML=errorBox(error.message);b.disabled=false;}
  });
  $$('[data-unlink-evidence]',host).forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api(`/evidence/${id}/supplements/${b.dataset.unlinkEvidence}`,{method:'DELETE'});toast('已移除关联，历史分析仍保留');await render({quiet:true});}catch(e){toast(e.message);b.disabled=false;}});
  $('#evidence-reanalyze')?.addEventListener('click',async e=>{const b=e.currentTarget;b.disabled=true;try{const job=await api('/evidence/'+id+'/reanalyze',{method:'POST'});toast(`补证分析任务 #${job.id} 已提交`);await render({quiet:true});}catch(error){$('#evidence-submit-feedback').innerHTML=errorBox(error.message);b.disabled=false;}});
}

function changeControls(items){
  const counts=Object.fromEntries(Object.keys(changeNames).map(s=>[s,items.filter(p=>p.change?.status===s).length]));
  return `<div class="web-change-controls"><label for="web-change-filter">正文变化<select id="web-change-filter"><option value="">全部 ${items.length} 页</option>${Object.entries(changeNames).map(([s,label])=>`<option value="${s}">${label} ${counts[s]} 页</option>`).join('')}</select></label></div><p id="web-change-empty" class="notice-inline" hidden>当前筛选下没有页面，可切换正文变化条件。</p>`;
}

function comparisonHtml(c){
  const stamp=p=>`${when(p.fetched_at)}${p.archived_at?' · 存档 '+esc(p.archived_at):''}`;
  return `<div class="comparison-head"><h4>${changeNames[c.status]}</h4><p>本次快照：${stamp(c.current)}</p>${c.previous?`<p>对比快照：${stamp(c.previous)} · 任务 #${c.previous_run_id}</p>`:''}</div>`+
    (c.status==='added'?'<p>该网址在此来源下尚无更早的成功快照，暂时无法比较。</p>':c.status==='unchanged'?'<p>正文未变化（忽略空白格式差异）。</p>':c.status==='incomparable'?'<p>历史存档与在线版本，无法直接比较。</p>':`<p class="diff-totals">新增 ${c.added_characters.toLocaleString('zh-CN')} 字符 · 删除 ${c.removed_characters.toLocaleString('zh-CN')} 字符</p><div class="diff-hunks">${c.hunks.map(rows=>`<div class="diff-hunk">${rows.map(r=>`<div class="diff-row ${r.kind}"><span>${{added:'新增',removed:'删除',context:'上下文'}[r.kind]}</span><p>${esc(r.text)}</p></div>`).join('')}</div>`).join('')}</div>${c.truncated?'<p class="notice-inline">差异较多，当前展示部分片段，请打开两份完整原文继续核验。</p>':''}`)+
    `<div class="actions"><button class="secondary small" data-compare-original="${c.current.id}">本次完整原文</button>${c.previous?`<button class="secondary small" data-compare-original="${c.previous.id}">上次完整原文</button>`:''}</div>`;
}

function bindWebChanges(target){
  $('#web-change-filter',target)?.addEventListener('change',e=>{
    let visible=0;
    $$('[data-change-status]',target).forEach(card=>{
      card.hidden=!!e.target.value&&card.dataset.changeStatus!==e.target.value;
      if(!card.hidden)visible++;
      else $$('[name=web-page]:checked',card).forEach(box=>{box.checked=false;box.dispatchEvent(new Event('change',{bubbles:true}));});
    });
    const skipped=$('.web-skipped-drawer',target);
    if(e.target.value&&skipped&&$$('[data-change-status]',skipped).some(card=>!card.hidden))skipped.open=true;
    $('#web-change-empty',target).hidden=visible>0;
  });
  $$('[data-web-compare]',target).forEach(b=>b.onclick=async()=>{
    const panel=$('#compare-'+b.dataset.webCompare,target);if(b.getAttribute('aria-expanded')==='true'){panel.hidden=true;b.setAttribute('aria-expanded','false');return;}
    panel.hidden=false;b.setAttribute('aria-expanded','true');if(panel.dataset.loaded)return;
    b.disabled=true;panel.innerHTML='<p role="status">正在比较两份正文…</p>';
    try{const c=await api(`/web/pages/${b.dataset.webCompare}/compare`);panel.innerHTML=comparisonHtml(c);panel.dataset.loaded='true';$$('[data-compare-original]',panel).forEach(button=>button.onclick=()=>showComparedSnapshot(button.dataset.compareOriginal));}catch(e){panel.innerHTML=errorBox(e.message);}finally{b.disabled=false;}
  });
}

async function showComparedSnapshot(id){
  try{const p=await api('/web/pages/'+id);$('#source-title').textContent='采集快照原文';$('#source-content').innerHTML=`<h2>${esc(p.title)}</h2><p>${when(p.fetched_at)}${p.archived_at?' · 存档 '+esc(p.archived_at):''}</p><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.url)}</a><div class="source-body">${esc(p.body)}</div>`;const dialog=$('#source-dialog');if(!dialog.open)dialog.showModal();dialog.scrollTop=0;$('#source-content').scrollTop=0;}catch(e){toast(e.message);}
}
