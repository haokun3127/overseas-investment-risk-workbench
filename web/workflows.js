'use strict';
function navigateList(){const hash='#'+state.route+'?'+new URLSearchParams({...state.filter,page:state.page,...(['events','report'].includes(state.route)?{demo:state.scope}:{})});if(location.hash===hash)render();else location.hash=hash;}

async function jobsPage(){
  const data=await api('/jobs?'+new URLSearchParams({...state.filter,page:state.page}));
  return heading('分析任务','查询全部任务历史，查看进度、处理失败任务，并取消尚未开始的任务。','<button class="secondary" data-refresh>刷新状态</button><a class="primary" href="#documents">选择资料</a>')+
  `<section class="panel"><div class="panel-heading"><h2>任务记录</h2><small>${data.active} 条任务正在排队或运行</small></div><form class="filters" id="job-filter"><label class="search-field">资料或任务编号<input name="q" value="${esc(state.filter.q||'')}" placeholder="输入标题或完整任务编号"></label><label>任务状态<select name="status"><option value="">全部状态</option>${['queued','running','completed','failed','cancelled'].map(s=>`<option value="${s}" ${state.filter.status===s?'selected':''}>${statuses[s]}</option>`).join('')}</select></label><button class="secondary small">筛选</button><span id="job-match" aria-live="polite">当前显示 ${data.items.length} 条 · 共 ${data.total} 条匹配</span></form>${data.items.length?`<div class="table-wrap"><table><thead><tr><th>任务与资料</th><th>状态</th><th>处理进度</th><th>时间</th><th>结果与操作</th></tr></thead><tbody>${data.items.map(j=>`<tr><td class="title-cell">${esc(j.title)}<span class="source-line">任务 #${j.id}</span></td><td>${badge(j.status)}</td><td>${j.progress} / ${j.total||'—'} 个片段<progress value="${j.progress}" max="${j.total||1}" aria-label="已分析片段数"></progress></td><td>提交：${when(j.created_at)}<br><small>${j.finished_at?'结束：'+when(j.finished_at):j.started_at?'开始：'+when(j.started_at):'等待调度'}</small></td><td>${j.error?`<p>${esc(j.error)}</p>`:''}${j.status==='queued'?`<button class="secondary small" data-cancel-job="${j.id}">取消排队</button>`:j.status==='failed'||j.status==='cancelled'?`<button class="secondary small" data-analyze="${j.document_id}">重新提交分析</button>`:j.status==='completed'?sourceButton(j.document_id,'查看分析记录'):'正在分析，请稍候'}</td></tr>`).join('')}</tbody></table></div>`:empty('没有匹配的任务','调整查询条件，或从资料页启动新的分析任务。')}${pagination(data)}</section>`;
}

async function reportView(){
  const data=await api('/report?'+new URLSearchParams({...state.filter,demo:state.scope}));
  const counts=Object.fromEntries(Object.keys(levels).map(l=>[l,data.items.filter(i=>i.level===l).length]));
  const accepted=data.items.filter(i=>i.review_status==='accepted').length;
  const range=state.filter.date_from||state.filter.date_to?`${state.filter.date_from||'起始不限'} — ${state.filter.date_to||'截止不限'}`:'全部资料日期';
  const filters=[state.filter.category,levels[state.filter.level],statuses[state.filter.review],state.filter.q&&'关键词：'+state.filter.q].filter(Boolean);
  const priority=[...data.items].sort((a,b)=>['red','orange','yellow'].indexOf(a.level)-['red','orange','yellow'].indexOf(b.level));
  return heading('风险简报','查看风险重点与应对建议，支持打印或保存 PDF。',`<a class="secondary" href="${esc(eventHref(state.filter))}">返回风险列表</a><button class="primary" id="print-report">打印 / 保存 PDF</button>`)+reportControls()+
  `<article class="report-paper brief-paper"><header class="brief-cover"><div class="brief-kicker"><span>投资与经营 · 风险研判</span><span>印度尼西亚</span></div><h1>海外投资风险分析简报</h1><p class="brief-subtitle">汇总风险信号、业务影响与应对建议</p><div class="brief-cover-meta"><div><span>生成时间</span><strong>${when(data.generated_at)}</strong></div><div><span>资料范围</span><strong>${esc(range)}</strong></div><div><span>纳入范围</span><strong>${state.scope==='all'?'工作台全部资料':'当前筛选资料'}</strong></div></div>${filters.length?`<div class="brief-filters">${filters.map(t=>`<span>${esc(t)}</span>`).join('')}</div>`:''}</header>
  <section class="brief-overview"><div class="brief-section-title"><h2>风险概况</h2><span>${accepted} 条已认可 · ${data.total-accepted} 条待复核或修正</span></div><div class="brief-metrics"><div class="brief-metric total"><span>纳入风险事件</span><strong>${data.total}<small>条</small></strong></div>${Object.entries(levels).map(([key,label])=>`<div class="brief-metric ${key}"><span><i></i>${label}</span><strong>${counts[key]}<small>条</small></strong></div>`).join('')}</div><p class="brief-note">本简报汇总已有分析记录。潜在影响与建议供业务复核，来源时效性及适用性需结合实际情况核验。</p></section>
  ${data.items.length?`<section class="brief-index"><div class="brief-section-title"><h2>风险速览</h2><span>按风险等级排列</span></div><div class="table-wrap"><table class="brief-index-table"><thead><tr><th>等级</th><th>风险事项</th><th>类型</th><th>复核</th></tr></thead><tbody>${priority.map(e=>`<tr><td>${badge(e.level)}</td><td>${esc(e.title)}</td><td>${esc(e.category)}</td><td>${esc(statuses[e.review_status])}</td></tr>`).join('')}</tbody></table></div></section>
  <div class="brief-section-title brief-details-title"><h2>风险分析与应对</h2><span>共 ${data.total} 项</span></div>${priority.map((e,i)=>`<section class="report-event brief-event"><div class="brief-event-heading"><span class="brief-event-number">${String(i+1).padStart(2,'0')}</span><div><div class="brief-event-tags">${badge(e.level)}<span>${esc(e.category)}</span><span>${esc(statuses[e.review_status])}</span></div><h2>${esc(e.title)}</h2></div></div><div class="brief-block brief-summary"><h3>事件摘要</h3><p>${esc(e.summary)}</p></div><div class="brief-analysis-grid"><div class="brief-block brief-impact"><h3>潜在影响</h3><p>${esc(e.impact)}</p></div><div class="brief-block brief-action"><h3>应对建议</h3><p>${esc(e.recommendation)}</p></div></div>${e.review_note?`<div class="brief-review"><h3>业务复核意见</h3><p>${esc(e.review_note)}</p></div>`:''}<div class="brief-evidence"><h3>引用依据 <span>${e.evidence.length} 条</span></h3>${e.evidence.map((r,n)=>`<blockquote><span class="brief-reference">${n+1}</span><div><p>${esc(r.quote)}</p><footer><strong>${esc(r.title.replace(/^API演示[：:]\s*/,''))}</strong><span>${esc(r.locator)}</span><p>${esc(r.reason)}</p></footer></div></blockquote>`).join('')}</div><div class="brief-provenance"><span>来源：${esc(e.source||'未填写')}</span><span>资料日期：${esc(e.date||'未注明')}</span><span>事件 #${e.id} · 分析 v${e.version}</span>${e.url?`<span class="brief-url">原始链接：${esc(e.url)}</span>`:''}</div></section>`).join('')}`:`<section class="brief-empty"><h2>当前范围暂无风险事件</h2><p>可调整日期与复核条件，或先导入资料并完成分析。</p></section>`}<footer class="brief-end"><span>海外投资风险工作台</span><span>资料与判断依据可在风险事件中进一步核验</span></footer></article>`;
}

function reportControls(){return `<form class="filters report-controls" id="report-filter"><label>开始日期<input type="date" name="date_from" value="${esc(state.filter.date_from||'')}"></label><label>结束日期<input type="date" name="date_to" value="${esc(state.filter.date_to||'')}"></label><label>复核结论<select name="review"><option value="">全部结论</option>${['pending','accepted','needs_change'].map(s=>`<option value="${s}" ${state.filter.review===s?'selected':''}>${statuses[s]}</option>`).join('')}</select></label><button class="secondary">更新简报范围</button><small>等级、类型及关键词沿用风险列表的筛选条件</small></form>`;}

async function inspectAnalysis(ids,button){
  if(!ids.length){toast('请先选择需要分析的资料。');return;}
  button.disabled=true;
  try{
    const result=await api('/jobs/preflight',{method:'POST',body:{document_ids:ids}});
    let panel=$('#preflight-panel');if(panel)panel.remove();
    $('#main .route-enter').insertAdjacentHTML('afterbegin',`<section class="panel" id="preflight-panel" tabindex="-1"><div class="panel-heading"><h2>分析前检查</h2><button class="text-button" id="close-preflight">收起</button></div><div class="panel-content"><p>本次会向已配置的外部模型 API 发送所选正文，以及允许外发的相关知识片段。共 ${ids.length} 条资料。</p><p class="form-note">当前公司：${esc(state.company?.name||'未选择')} · ${state.company?.allow_external?'将使用已授权的公司背景':'外部 AI 不发送公司背景'}。公司背景在提交时保存，后续切换不会改变已提交任务。</p>${result.blockers.map(v=>`<p>${esc(v)} · <a href="#settings">前往配置</a></p>`).join('')}<ul class="preflight-list">${result.items.map(i=>`<li><strong>${esc(i.title)}</strong><span>${i.issues.length?esc(i.issues.join('；')):i.existing_job?'已有任务 #'+i.existing_job:'检查通过'}</span>${sourceButton(i.id,'查看资料与授权')}</li>`).join('')}</ul><div class="form-actions"><button class="primary" id="confirm-analysis" ${result.ready?'':'disabled'}>确认提交 ${ids.length} 条资料</button><small>服务端提交时会再次检查；重复任务不会重复入队。</small></div></div></section>`);
    $('#close-preflight').onclick=()=>$('#preflight-panel').remove();
    $$('[data-source]',$('#preflight-panel')).forEach(b=>b.onclick=()=>showSource(b.dataset.source));
    $('#confirm-analysis').onclick=e=>analyze(ids,e.currentTarget);
    $('#preflight-panel').focus();$('#preflight-panel').scrollIntoView({block:'start',behavior:'smooth'});
    if(result.blockers.length)toast(result.blockers.join('；'));
  }catch(e){toast(e.message);}finally{button.disabled=false;}
}

function bindWorkflows(){
  $('#report-filter')?.addEventListener('submit',e=>{e.preventDefault();const f=Object.fromEntries(new FormData(e.currentTarget));if(f.date_from&&f.date_to&&f.date_from>f.date_to){toast('开始日期不能晚于结束日期。');return;}state.scope=f.demo;delete f.demo;state.filter={...state.filter,...f};state.page=1;navigateList();});
  $('#knowledge-search')?.addEventListener('submit',async e=>{
    e.preventDefault();e.stopImmediatePropagation();const form=e.currentTarget,target=$('#knowledge-results'),button=$('button',form),query=form.elements.q.value.trim();
    if(!query)return;button.disabled=true;button.textContent='正在检索…';target.innerHTML='<p class="loading" role="status">正在本地知识库中匹配依据…</p>';
    try{const data=await api('/knowledge/search?q='+encodeURIComponent(query));if(!target.isConnected)return;const sourceCount=new Set(data.items.map(r=>r.document_id)).size;
      target.innerHTML=`<section class="panel"><div class="panel-heading"><h2>检索结果</h2><small>${sourceCount} 份资料 · ${data.items.length} 个片段</small></div><p class="panel-content form-note">检索词：${esc(query)}。匹配分数用于本次结果排序，不代表正确率或风险概率。</p>${data.items.length?data.items.map(r=>`<article class="search-hit"><h3>${esc(r.title)}</h3><p>${esc(r.text).split(esc(query)).join('<mark>'+esc(query)+'</mark>')}</p><small>${esc(r.locator)} · 匹配分数 ${r.score}</small><br>${sourceButton(r.document_id,'定位原文片段',r.text)}</article>`).join(''):empty('没有匹配的片段','尝试更具体的原文关键词，或补充政策、案例等参考资料。')}</section>`;
      $$('[data-source]',target).forEach(b=>b.onclick=()=>showSource(b.dataset.source,b.dataset.quote));
    }catch(err){if(target.isConnected)target.innerHTML=errorBox(err.message);}finally{button.disabled=false;button.textContent='检索资料';}
  },true);
  $('#print-report')?.addEventListener('click',()=>window.print());
  $$('[data-analyze]').forEach(b=>b.onclick=()=>inspectAnalysis([Number(b.dataset.analyze)],b));
  $('#analyze-selected')?.addEventListener('click',e=>{e.stopImmediatePropagation();inspectAnalysis($$('[name=doc-select]:checked').map(c=>Number(c.value)),e.currentTarget);},true);
  $$('[data-cancel-job]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api(`/jobs/${b.dataset.cancelJob}/cancel`,{method:'POST'});toast('排队任务已取消，可稍后重新提交。');await render();}catch(e){toast(e.message);b.disabled=false;}});
}
