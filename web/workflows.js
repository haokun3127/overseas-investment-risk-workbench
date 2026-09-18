'use strict';
function navigateList(){const hash='#'+state.route+'?'+new URLSearchParams({...state.filter,page:state.page,...(['events','report'].includes(state.route)?{demo:state.scope}:{})});if(location.hash===hash)render();else location.hash=hash;}

async function jobsPage(){
  const data=await api('/jobs?'+new URLSearchParams({...state.filter,page:state.page}));
  return heading('分析任务','查询全部任务历史，查看进度、处理失败任务，并取消尚未开始的任务。','<button class="secondary" data-refresh>刷新状态</button><a class="primary" href="#documents">选择资料</a>')+
  `<section class="panel"><div class="panel-heading"><h2>任务记录</h2><small>${data.active} 条任务正在排队或运行</small></div><form class="filters" id="job-filter"><label class="search-field">资料或任务编号<input name="q" value="${esc(state.filter.q||'')}" placeholder="输入标题或完整任务编号"></label><label>任务状态<select name="status"><option value="">全部状态</option>${['queued','running','completed','failed','cancelled'].map(s=>`<option value="${s}" ${state.filter.status===s?'selected':''}>${statuses[s]}</option>`).join('')}</select></label><button class="secondary small">筛选</button><span id="job-match" aria-live="polite">当前显示 ${data.items.length} 条 · 共 ${data.total} 条匹配</span></form>${data.items.length?`<div class="table-wrap"><table><thead><tr><th>任务与资料</th><th>状态</th><th>处理进度</th><th>时间</th><th>结果与操作</th></tr></thead><tbody>${data.items.map(j=>`<tr><td class="title-cell">${esc(j.title)}<span class="source-line">任务 #${j.id}</span></td><td>${badge(j.status)}</td><td>${j.progress} / ${j.total||'—'} 个片段<progress value="${j.progress}" max="${j.total||1}" aria-label="已分析片段数"></progress></td><td>提交：${when(j.created_at)}<br><small>${j.finished_at?'结束：'+when(j.finished_at):j.started_at?'开始：'+when(j.started_at):'等待调度'}</small></td><td>${j.error?`<p>${esc(j.error)}</p>`:''}${j.status==='queued'?`<button class="secondary small" data-cancel-job="${j.id}">取消排队</button>`:j.status==='failed'||j.status==='cancelled'?`<button class="secondary small" data-analyze="${j.document_id}">重新提交分析</button>`:j.status==='completed'?sourceButton(j.document_id,'查看分析记录'):'正在分析，请稍候'}</td></tr>`).join('')}</tbody></table></div>`:empty('没有匹配的任务','调整查询条件，或从资料页启动新的分析任务。')}${pagination(data)}</section>`;
}

async function reportView(){
  const data=await api('/report?'+new URLSearchParams({...state.filter,demo:state.scope}));
  const levelCounts=Object.fromEntries(Object.keys(levels).map(l=>[l,data.items.filter(i=>i.level===l).length]));
  const accepted=data.items.filter(i=>i.review_status==='accepted').length;
  const scopeNames={all:'全部资料（含演示）',real:'真实资料',demo:'虚构演示'};
  return heading('风险简报','汇总当前范围内的最新分析结果，可通过浏览器打印或保存为 PDF。',`<a class="secondary" href="${esc(eventHref(state.filter))}">返回筛选列表</a><button class="primary" id="print-report">打印 / 保存 PDF</button>`)+
  reportControls()+`<article class="report-paper"><header><h1>海外投资风险分析简报</h1><p>印度尼西亚 · 制造业</p><p>生成时间：${when(data.generated_at)} ｜ 数据范围：${scopeNames[state.scope]}</p><p>日期：${esc(state.filter.date_from||'不限')} 至 ${esc(state.filter.date_to||'不限')} ｜ 类型：${esc(state.filter.category||'全部')} ｜ 等级：${levels[state.filter.level]||'全部'} ｜ 复核：${statuses[state.filter.review]||'全部'}</p>${state.filter.q?`<p>检索词：${esc(state.filter.q)}</p>`:''}</header><section><h2>风险概况</h2><p>本次纳入 ${data.total} 条事件：高风险 ${levelCounts.red} 条，中风险 ${levelCounts.orange} 条，一般关注 ${levelCounts.yellow} 条。已认可 ${accepted} 条，其余 ${data.total-accepted} 条待复核或需修正。</p><p>本简报整理系统已有分析结果，未额外调用模型。${data.items.some(i=>i.demo)?'包含明确标记的虚构演示案例，不得作为真实投资风险结论。':''}分析建议供业务复核参考，来源时效性和适用性需人工核验。</p></section>${data.items.length?data.items.map((e,i)=>`<section class="report-event"><h2>${i+1}. ${esc(e.title)}${e.demo?'（虚构演示）':''}</h2><p class="report-meta">${levels[e.level]} ｜ ${esc(e.category)} ｜ ${statuses[e.review_status]} ｜ 资料日期：${esc(e.date||'未注明')}</p>${[['事件摘要',e.summary],['潜在影响',e.impact],['初步应对建议',e.recommendation],['业务复核意见',e.review_note||'未填写']].map(([label,value])=>`<h3>${label}</h3><p>${esc(value)}</p>`).join('')}<h3>引用依据</h3>${e.evidence.map(r=>`<blockquote><p>${esc(r.quote)}</p><footer>${esc(r.title)} · ${esc(r.locator)}<br>${esc(r.reason)}</footer></blockquote>`).join('')}<p class="report-meta">来源：${esc(e.source||'未填写')}<br>${esc(e.url||'无原始链接')}<br>事件 #${e.id} ｜ 分析 v${e.version} ｜ 规则 ${esc(e.rule_version)} ｜ 模型 ${esc(e.model)} ｜ ${e.mode==='demo'?'演示结果':e.mode==='local'?'本地模型':'外部 API'}</p></section>`).join(''):'<section><p>当前范围没有风险事件。此处为空不代表不存在投资风险，请核对资料覆盖范围。</p></section>'}</article>`;
}

function reportControls(){return `<form class="filters report-controls" id="report-filter"><label>数据范围<select name="demo">${[['all','全部资料'],['real','真实资料'],['demo','虚构演示']].map(([v,l])=>`<option value="${v}" ${state.scope===v?'selected':''}>${l}</option>`).join('')}</select></label><label>开始日期<input type="date" name="date_from" value="${esc(state.filter.date_from||'')}"></label><label>结束日期<input type="date" name="date_to" value="${esc(state.filter.date_to||'')}"></label><label>复核结论<select name="review"><option value="">全部结论</option>${['pending','accepted','needs_change'].map(s=>`<option value="${s}" ${state.filter.review===s?'selected':''}>${statuses[s]}</option>`).join('')}</select></label><button class="secondary">更新简报范围</button><small>其他等级、类型和关键词条件从风险列表带入。</small></form>`;}

async function inspectAnalysis(ids,button){
  if(!ids.length){toast('请先选择需要分析的资料。');return;}
  button.disabled=true;
  try{
    const result=await api('/jobs/preflight',{method:'POST',body:{document_ids:ids}});
    let panel=$('#preflight-panel');if(panel)panel.remove();
    $('#main .route-enter').insertAdjacentHTML('afterbegin',`<section class="panel" id="preflight-panel" tabindex="-1"><div class="panel-heading"><h2>分析前检查</h2><button class="text-button" id="close-preflight">收起</button></div><div class="panel-content"><p>${result.mode==='external'?'本次会向已配置的外部模型发送所选正文，以及允许外发的相关知识片段。':'本次使用本地模型处理所选正文和相关知识片段。'}共 ${ids.length} 条资料。</p>${result.blockers.map(v=>`<p>${esc(v)} · <a href="#settings">前往配置</a></p>`).join('')}<ul class="preflight-list">${result.items.map(i=>`<li><strong>${esc(i.title)}</strong><span>${i.issues.length?esc(i.issues.join('；')):i.existing_job?'已有任务 #'+i.existing_job:'检查通过'}</span>${sourceButton(i.id,'查看资料与授权')}</li>`).join('')}</ul><div class="form-actions"><button class="primary" id="confirm-analysis" ${result.ready?'':'disabled'}>确认提交 ${ids.length} 条资料</button><small>服务端提交时会再次检查；重复任务不会重复入队。</small></div></div></section>`);
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
