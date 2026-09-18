'use strict';
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = {overview:'风险总览',events:'风险事件',documents:'资料与导入',knowledge:'知识库',jobs:'分析任务',settings:'模型与规则',report:'风险简报'};
const levels = {red:'高风险',orange:'中风险',yellow:'一般关注'};
const statuses = {pending:'待复核',accepted:'已认可',needs_change:'需修正',queued:'排队中',running:'分析中',completed:'已完成',failed:'失败',cancelled:'已取消',risk:'发现风险',non_risk:'非风险',insufficient:'资料不足'};
const state = {config:null,scope:'all',page:1,route:'overview',importMode:'file',filter:{},renderId:0};
let toastTimer;
function toast(message){$('#notice').textContent=message;$('#notice').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#notice').hidden=true,4500);}
async function api(path, options={}){
  const headers={'X-Requested-With':'risk-workbench',...(options.headers||{})};
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  let response;
  try{response=await fetch('/api'+path,{...options,headers,signal:options.signal||AbortSignal.timeout(120000)});}
  catch(e){throw new Error(e.name==='TimeoutError'?'请求超时。操作可能已被接收，请刷新列表确认后再重试。':'无法连接本地服务，请检查服务是否启动，再重试。');}
  const data=await response.json().catch(()=>({detail:'服务响应无法读取。'}));
  if(!response.ok){
    if(response.status===401 && !path.startsWith('/auth/')){await boot();}
    const detail=Array.isArray(data.detail)?'输入内容格式不正确，请检查必填字段和长度。':data.detail;
    throw new Error(detail||'请求失败，请稍后重试。');
  }
  return data;
}
function badge(value){return `<span class="badge ${esc(value)}">${esc(levels[value]||statuses[value]||value||'未分析')}</span>`;}
function demoTag(demo){return demo?'<span class="demo-tag">虚构示例</span>':'';}
function when(date){return date?new Date(date).toLocaleString('zh-CN',{hour12:false}):'—';}
function errorBox(message){return `<div class="error" role="alert">${esc(message)}</div>`;}
function icon(name){return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;}
function heading(title,subtitle,actions=''){return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${actions}</div></div>`;}
function eventHref(filter={}){return '#events?'+new URLSearchParams({...filter,demo:state.scope});}
function openEvents(filter={}){const target=eventHref(filter);if(location.hash===target)render();else location.hash=target;}
function severityChart(stats,count){
  let offset=0;
  const segments=Object.keys(levels).map(level=>{
    const amount=count[level]||0,percent=stats.total?amount/stats.total*100:0;
    const segment=percent?`<circle class="ring-segment ${level}" cx="92" cy="92" r="70" pathLength="100" stroke-dasharray="${percent} ${100-percent}" stroke-dashoffset="${-offset}"/>`:'';
    offset+=percent;return segment;
  }).join('');
  return `<div class="severity-chart"><svg viewBox="0 0 184 184" class="severity-ring" role="img" aria-label="${Object.entries(levels).map(([v,l])=>`${l}${count[v]||0}条`).join('，')}"><circle class="ring-track" cx="92" cy="92" r="70"/>${segments}<circle class="ring-inner" cx="92" cy="92" r="53"/><text x="92" y="94" class="ring-total">${stats.total}</text><text x="92" y="117" class="ring-caption">风险事件</text></svg><div class="severity-legend">${Object.entries(levels).map(([v,l])=>`<a href="${eventHref({level:v})}" class="legend-row"><span class="dot ${v}"></span><span>${l}</span><strong>${count[v]||0}<small> 条</small></strong></a>`).join('')}</div></div>`;
}
function categoryNetwork(stats){
  if(!stats.categories.length)return empty('等待第一条风险信号','完成分析后，这里会展示风险类型及对应事件。','<a class="secondary" href="#documents">导入资料</a>');
  const nodes=stats.categories.slice(0,6);
  const rows=Math.ceil(nodes.length/2),step=rows===2?118:86;
  const positions=nodes.map((_,i)=>({x:i%2?425:15,y:100+(Math.floor(i/2)-(rows-1)/2)*step}));
  const links=positions.map(p=>`<path class="network-link" d="M300 127 C${p.x<300?220:380} 127 ${p.x<300?225:375} ${p.y+27} ${p.x<300?p.x+160:p.x} ${p.y+27}"/>`).join('');
  return `<div class="signal-canvas"><svg class="signal-network" viewBox="0 0 600 252" role="group" aria-label="风险类型与事件数量，点击类型筛选事件"><defs><pattern id="signal-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7"/></pattern></defs><rect class="network-grid" width="600" height="252" fill="url(#signal-grid)"/><ellipse class="network-orbit" cx="300" cy="127" rx="101" ry="101"/><ellipse class="network-orbit" cx="300" cy="127" rx="80" ry="80"/>${links}<circle class="network-core" cx="300" cy="127" r="60"/><text x="300" y="117" class="network-total">${stats.total}</text><text x="300" y="142" class="network-caption">已识别风险</text><text x="300" y="159" class="network-unit">当前数据范围</text>${nodes.map((c,i)=>{const p=positions[i];return `<a href="${eventHref({category:c.category})}" aria-label="${esc(c.category)}，${c.count}条，查看事件"><rect class="network-node" x="${p.x}" y="${p.y}" width="160" height="54" rx="8"/><circle class="network-port" cx="${p.x<300?p.x+160:p.x}" cy="${p.y+27}" r="3"/><text class="network-label" x="${p.x+14}" y="${p.y+23}">${esc(c.category.length>9?c.category.slice(0,8)+'…':c.category)}</text><text class="network-count" x="${p.x+14}" y="${p.y+42}">${c.count} 条风险事件</text></a>`;}).join('')}</svg><div class="network-mobile-list">${stats.categories.map(c=>`<a href="${eventHref({category:c.category})}"><span>${esc(c.category)}</span><strong>${c.count}<small> 条</small></strong></a>`).join('')}</div></div><div class="chart-footnote"><span>${stats.categories.length} 个风险类型${stats.categories.length>6?' · 图示数量最多的6类':''}</span><a href="${eventHref()}">查看分类事件 ${icon('arrow')}</a></div>`;
}
function sourceButton(id,label='查看原文',quote=''){return `<button class="text-button source-action" data-source="${id}" data-quote="${esc(quote)}">${icon('source')}${label}</button>`;}
function empty(title,description,actions=''){return `<div class="empty"><span class="empty-symbol" aria-hidden="true">${icon('documents')}</span><h2>${title}</h2><p>${description}</p><div class="actions">${actions}</div></div>`;}
function scope(){return `<div class="scope-bar"><span class="muted">分析范围：印度尼西亚 · 制造业</span><div class="segmented" aria-label="数据范围">${[['all','全部数据'],['real','真实资料'],['demo','演示数据']].map(([v,l])=>`<button data-scope="${v}" class="${state.scope===v?'selected':''}" aria-pressed="${state.scope===v}">${l}</button>`).join('')}</div></div>`;}
function demonstration(){return `<div class="notice-inline"><p><strong>演示数据已明确标注。</strong> 内置案例为虚构内容，未调用大模型，不代表真实风险研判。</p><button class="text-button" data-scope="real">仅看真实资料</button></div>`;}
function pagination(data){return `<div class="pagination"><span>共 ${data.total} 条 · 第 ${data.page} / ${Math.max(1,Math.ceil(data.total/data.page_size))} 页</span><div class="actions"><button class="secondary small" data-page="${data.page-1}" ${data.page<=1?'disabled':''}>上一页</button><button class="secondary small" data-page="${data.page+1}" ${data.page*data.page_size>=data.total?'disabled':''}>下一页</button></div></div>`;}
function tableEvents(items,compact=false){return `<div class="table-wrap"><table><thead><tr><th>风险事件</th><th>等级</th>${compact?'':'<th>风险类型</th>'}<th>复核状态</th><th>资料日期</th></tr></thead><tbody>${items.map(e=>`<tr><td class="title-cell"><a class="event-link" href="#event/${e.id}">${esc(e.title)}</a>${demoTag(e.demo)}<span class="source-line">${esc(e.source||'来源未填写')}</span></td><td>${badge(e.level)}</td>${compact?'':`<td class="nowrap">${esc(e.category)}</td>`}<td>${badge(e.review_status)}</td><td class="nowrap">${esc(e.date||'未注明')}</td></tr>`).join('')}</tbody></table></div>`;}
async function boot(){
  const auth=await api('/auth/status');
  $('#auth').hidden=auth.authenticated;$('#shell').hidden=!auth.authenticated;
  if(!auth.authenticated){
    workDrafts.clear();
    $('#auth').innerHTML=`<section class="auth-card"><div class="auth-brand">海外投资风险分析工作台</div><h1>${auth.initialized?'欢迎回来':'设置本地管理员'}</h1><p>${auth.initialized?'登录后查看资料、分析任务和风险研判结果。':'首次使用请设置管理员密码。资料和分析结果保存在当前服务器。'}</p><form id="login-form"><label class="field">${auth.initialized?'管理员密码':'设置密码（至少10位）'}<input type="password" name="password" minlength="10" maxlength="128" autocomplete="${auth.initialized?'current-password':'new-password'}" required></label>${auth.initialized?'':'<label class="field">再次输入密码<input type="password" name="confirm" minlength="10" autocomplete="new-password" required></label>'}<div id="auth-error"></div><button class="primary" type="submit">${auth.initialized?'登录工作台':'创建管理员并进入'}</button></form><p class="form-note">${auth.initialized?'登录有效期为8小时。':'首次设置需在服务器本机完成。'}</p></section>`;
    $('#login-form').onsubmit=async event=>{
      event.preventDefault();const form=event.currentTarget;const values=new FormData(form);
      if(!auth.initialized&&values.get('password')!==values.get('confirm')){$('#auth-error').innerHTML=errorBox('两次输入的密码不一致。');return;}
      const b=$('button',form);b.disabled=true;
      try{await api(auth.initialized?'/auth/login':'/auth/setup',{method:'POST',body:{password:values.get('password')}});await boot();}
      catch(e){$('#auth-error').innerHTML=errorBox(e.message);b.disabled=false;}
    };
    return;
  }
  state.config=await api('/settings');
  $('#model-status').textContent=state.config.configured?'模型已配置 · 待任务验证':'模型待配置';
  $('#mode-label').textContent=state.config.mode==='local'?'本地模型模式':'外部 API 模式';
  await render();
}
async function render(){
  if($('#shell').hidden)return;
  const renderId=++state.renderId;
  const [routePath,routeSearch='']=location.hash.slice(1).split('?');
  const parts=routePath.split('/');
  const route=parts[0]||'overview',id=parts[1];
  if(state.route!==route||state.routeKey!==location.hash){
    state.filter={};state.page=1;
    if(['events','documents','knowledge','jobs','report'].includes(route)){
      const params=new URLSearchParams(routeSearch);
      for(const key of ['q','level','category','review','date_from','date_to','status','policy'])if(params.has(key))state.filter[key]=params.get(key);
      state.page=Math.max(1,parseInt(params.get('page'),10)||1);
      if(['all','real','demo'].includes(params.get('demo')))state.scope=params.get('demo');
    }
  }
  state.routeKey=location.hash;
  state.route=route;
  const active=route==='event'?'events':route;
  $$('[data-nav]').forEach(a=>{a.classList.toggle('active',a.dataset.nav===active);if(a.dataset.nav===active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#breadcrumb').textContent=`工作台 / ${names[active]||'风险详情'}`;
  $('#main').innerHTML='<div class="loading" role="status">正在加载…</div>';
  try{
    let html='';
    if(route==='overview')html=await overview();
    else if(route==='events')html=await eventList();
    else if(route==='event')html=await eventDetail(id);
    else if(route==='documents'||route==='knowledge')html=await documents(route==='knowledge');
    else if(route==='jobs')html=await jobsPage();
    else if(route==='settings')html=await settings();
    else if(route==='report')html=await reportView();
    else html=empty('页面不存在','请从左侧导航选择工作区。','<a href="#overview" class="primary">返回总览</a>');
    if(renderId!==state.renderId)return;
    html=await enhanceView(route,html);
    if(renderId!==state.renderId)return;
    $('#main').innerHTML=`<div class="route-enter">${composeWorkspace(route,html)}</div>`;bind();bindFeatures();bindWorkflows();bindWorkspace();
  }catch(e){if(renderId===state.renderId)$('#main').innerHTML=errorBox(e.message)+'<button class="secondary" id="retry-page">重新加载</button>';$('#retry-page')?.addEventListener('click',render);}
}
async function overview(){
  const [stats,data]=await Promise.all([api(`/overview?demo=${state.scope}`),api(`/events?demo=${state.scope}`)]);
  const count=Object.fromEntries(stats.levels.map(v=>[v.level,v.count]));
  const recent=data.items.slice(0,6);
  const reviewed=Math.max(0,stats.total-stats.pending);
  return heading('风险总览','从风险信号到判断依据，让每一次分析可核验。',`<button class="secondary icon-button" data-refresh aria-label="刷新总览">${icon('refresh')}</button><a class="secondary" href="#events">查看全部事件</a><a class="primary" href="#documents">${icon('upload')}导入资料</a>`)+scope()+
    (state.scope!=='real'&&recent.some(e=>e.demo)?demonstration():'')+
    `<section class="stats" aria-label="风险统计"><a class="stat total-stat" href="${eventHref()}"><div class="stat-label">${icon('source')}已识别风险事件</div><div class="stat-number">${stats.total}<span>条</span></div><small>${stats.documents} 条资料 · ${stats.pending} 条待复核</small></a>${Object.entries(levels).map(([v,l])=>`<a class="stat ${v}" href="${eventHref({level:v})}"><div class="stat-label"><span class="dot ${v}"></span>${l}${icon('arrow')}</div><div class="stat-number">${count[v]||0}<span>条</span></div><small>${v==='red'?'优先核验影响范围':v==='orange'?'关注影响与应对':'保留关注与复核'}</small></a>`).join('')}</section>`+
    `<div class="situation-grid"><section class="panel network-panel"><div class="panel-heading"><h2>${icon('overview')}风险类型分布</h2><small>基于当前资料</small></div>${categoryNetwork(stats)}</section><section class="panel severity-panel"><div class="panel-heading"><h2>风险等级构成</h2><small>点击等级查看</small></div>${severityChart(stats,count)}<div class="chart-footnote"><span>仅统计各资料的最新分析版本</span></div></section></div>`+
    `<div class="overview-grid"><section class="panel events-panel"><div class="panel-heading"><h2>${icon('risk')}最新风险事件</h2><a class="panel-link" href="${eventHref()}">全部事件 ${icon('arrow')}</a></div>${recent.length?tableEvents(recent,true):empty('从第一份资料开始','导入待分析资料，并配置模型和甲方规则，即可开始风险识别。你也可以先载入虚构案例体验工作台。','<a class="primary" href="#documents">导入资料</a><button class="secondary" data-demo>载入演示案例</button>')}</section><section class="panel review-panel"><div class="panel-heading"><h2>${icon('check')}业务复核</h2><a class="panel-link" href="${eventHref({review:'pending'})}">待办 ${icon('arrow')}</a></div><div class="review-summary"><span>待复核风险事件</span><a class="review-number" href="${eventHref({review:'pending'})}">${stats.pending}<small> 条</small>${icon('arrow')}</a><div class="review-progress-label"><span>已记录复核</span><strong>${reviewed} / ${stats.total}</strong></div><progress value="${reviewed}" max="${stats.total||1}" aria-label="已记录复核 ${reviewed} 条，共 ${stats.total} 条"></progress></div><ol class="review-steps"><li>${icon('documents')}<div><strong>查看原始资料</strong><small>保留正文与出处</small></div></li><li>${icon('source')}<div><strong>核验分析依据</strong><small>逐条定位引用原文</small></div></li><li>${icon('check')}<div><strong>记录业务意见</strong><small>保留判断与修正建议</small></div></li></ol><a class="review-cta" href="${eventHref({review:'pending'})}">进入复核列表 ${icon('arrow')}</a></section></div>`;
}
async function eventList(){
  const query=new URLSearchParams({...state.filter,page:state.page,demo:state.scope});
  const data=await api('/events?'+query);
  const categories=[...new Set([...state.config.rules.categories,state.filter.category].filter(Boolean))];
return heading('风险事件','逐条核验风险判断，查看来源并记录业务复核意见。','<a href="#documents" class="primary">导入新资料</a>')+scope()+`<section class="panel"><form class="filters" id="event-filter"><label class="search-field">搜索事件<input name="q" placeholder="输入事件标题或摘要" value="${esc(state.filter.q||'')}"></label><label>风险等级<select name="level"><option value="">全部等级</option>${Object.entries(levels).map(([v,l])=>`<option value="${v}" ${state.filter.level===v?'selected':''}>${l}</option>`).join('')}</select></label><label>复核状态<select name="review"><option value="">全部状态</option>${['pending','accepted','needs_change'].map(v=>`<option value="${v}" ${state.filter.review===v?'selected':''}>${statuses[v]}</option>`).join('')}</select></label><label>风险类型<select name="category"><option value="">全部类型</option>${categories.map(c=>`<option ${state.filter.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label><label>开始日期<input type="date" name="date_from" value="${esc(state.filter.date_from||'')}"></label><label>结束日期<input type="date" name="date_to" value="${esc(state.filter.date_to||'')}"></label><button class="secondary small" type="submit">查询</button><button class="text-button" type="button" id="clear-filter">重置</button></form>${data.items.length?tableEvents(data.items):empty('没有符合条件的风险事件','尝试调整筛选条件，或在资料页导入并分析新资料。')}${pagination(data)}</section>`;
}
async function eventDetail(id){
  const e=await api('/events/'+encodeURIComponent(id));
  state.currentEvent=e;
  return `<a class="back-link" href="#events">返回风险事件</a><h1 class="detail-title">${esc(e.title)}</h1><div class="metadata">${badge(e.level)}<span>${esc(e.category)}</span><span>${esc(e.date||'日期未注明')}</span><span>${esc(e.source||'来源未填写')}</span>${demoTag(e.demo)}</div>`+
    (e.demo?demonstration():'')+(!e.is_latest?'<div class="notice-inline">这是历史版本，最新分析结果请从风险列表查看。</div>':'')+
    (e.result.partial_context?'<div class="notice-inline">这份长资料已分段分析。跨段关联及事件重复需人工核验。</div>':'')+
    `<div class="detail-grid"><div><section class="panel">${[['事件摘要',e.summary],['潜在影响',e.impact],['初步应对建议',e.recommendation]].map(([title,text])=>`<section class="detail-section"><h2>${title}</h2><p>${esc(text)}</p></section>`).join('')}</section><section class="panel"><div class="panel-heading"><h2>业务复核</h2>${badge(e.review_status)}</div><form id="review-form" class="panel-content review-form" data-id="${e.id}"><div class="form-grid"><label class="field">复核结论<select name="status">${['pending','accepted','needs_change'].map(v=>`<option value="${v}" ${e.review_status===v?'selected':''}>${statuses[v]}</option>`).join('')}</select></label><label class="field full">复核意见<textarea name="note" rows="3" maxlength="2000" placeholder="记录判断分歧、需要补充的资料或修正建议">${esc(e.review_note)}</textarea></label></div><div class="form-actions"><button class="primary" type="submit">保存复核意见</button><small>${e.reviewed_at?'上次保存 '+when(e.reviewed_at):'尚未记录复核意见'}</small></div><div id="review-error"></div></form></section></div><div><section class="panel"><div class="panel-heading"><h2>判断依据与来源</h2><small>${e.evidence.length} 条引用</small></div>${e.evidence.map((r,i)=>`<article class="evidence"><span class="ref">引用 ${i+1} · ${esc(r.reference)}</span><h3>${esc(r.title)}</h3><blockquote>${esc(r.quote)}</blockquote><p>${esc(r.reason)}</p><small>${esc(r.locator)}</small><br>${sourceButton(r.document_id,'定位原文',r.quote)}</article>`).join('')}</section><section class="panel"><div class="panel-heading"><h2>分析记录</h2></div><div class="panel-content"><dl class="definition"><dt>分析版本</dt><dd>v${e.version}</dd><dt>模型</dt><dd>${esc(e.model)}</dd><dt>运行模式</dt><dd>${e.mode==='demo'?'演示结果 · 未调用模型':e.mode==='local'?'本地模型':'外部 API'}</dd><dt>规则版本</dt><dd>${esc(e.rules.version)}</dd><dt>分析时间</dt><dd>${when(e.created_at)}</dd><dt>处理耗时</dt><dd>${e.duration_ms/1000} 秒</dd></dl><div class="form-actions">${sourceButton(e.document_id,'查看输入资料')}</div></div></section></div></div>`;
}
function importForm(knowledge){
  return `<div class="tabs"><button data-import-mode="file" class="${state.importMode==='file'?'selected':''}">上传文件</button><button data-import-mode="manual" class="${state.importMode==='manual'?'selected':''}">手动录入</button></div><form id="import-form" data-kind="${knowledge?'knowledge':'event'}">${state.importMode==='file'?`<label class="upload-area"><strong>选择需要导入的资料</strong><br><small>Excel / CSV / Word / PDF / TXT / Markdown · 最大10MB</small><br><input type="file" name="file" accept=".csv,.xlsx,.docx,.pdf,.txt,.md" required></label>`:`<div class="form-grid"><label class="field full">标题<input name="title" maxlength="240" required placeholder="输入资料标题"></label><label class="field">资料日期<input type="date" name="date"></label><label class="field">信息来源<input name="source" maxlength="300" placeholder="发布机构或资料出处"></label><label class="field full">原始链接<input name="url" type="url" placeholder="https://"></label><label class="field full">正文<textarea name="body" rows="7" maxlength="60000" required placeholder="粘贴完整正文，保留有助于核验的上下文"></textarea></label></div>`}<label class="check-field"><input type="checkbox" name="allow_external"><span>我确认这份资料允许发送至已配置的外部模型服务。<br>未勾选的资料仅保存在本地，可在本地模型模式下使用。</span></label><div class="form-actions"><button class="primary" type="submit">${knowledge?'导入知识库':'保存待分析资料'}</button>${state.importMode==='file'?'<a href="/api/template" class="text-button">下载表格模板</a>':''}</div><div id="import-result" aria-live="polite"></div></form>`;
}
async function documents(knowledge){
  const kind=knowledge?'knowledge':'event';
  const data=await api('/documents?'+new URLSearchParams({...state.filter,kind,page:state.page}));
  return heading(knowledge?'知识库':'资料与导入',knowledge?'保存政策、案例与业务资料，为风险分析提供可追溯的参考依据。':'先保存原始资料，再选择需要分析的内容。')+
    `<div class="split"><section class="panel"><div class="panel-heading"><h2>${knowledge?'添加参考资料':'导入待分析资料'}</h2></div><div class="panel-content">${importForm(knowledge)}</div></section><section class="panel"><div class="panel-heading"><h2>${knowledge?'检索与使用说明':'导入说明'}</h2></div><div class="panel-content form-note">${knowledge?'<p>知识库使用本地 BM25 文本检索，不需要向量 API。引用片段随分析版本保存。</p><p>外部 API 模式仅检索已获准外发的参考资料；内置演示案例不会进入知识库检索。</p><form id="knowledge-search"><label class="field">试查知识库<input name="q" required placeholder="输入关键词或业务问题"></label><button class="secondary small" type="submit">检索资料</button></form>':'<ul><li>每条记录至少包含标题和正文。</li><li>CSV / Excel 使用模板列名；逐行报告成功、重复和失败结果。</li><li>PDF 需含可提取文本；扫描件请先 OCR。</li><li>单条正文最多60000字符，超长资料请按章节拆分。</li><li>文件保存成功后，在下方资料列表启动分析。</li></ul>'}<p>模型状态：<strong>${state.config.configured?'已配置，等待实际任务验证':'尚未配置'}</strong><br>分类规则：${state.config.rules.confirmed?'已确认':'待甲方确认'}</p><a href="#settings">查看模型与规则设置</a></div></section></div><div id="knowledge-results"></div>`+
    `<section class="panel"><div class="panel-heading"><h2>${knowledge?'参考资料':'待分析资料'} <small>${data.total} 条</small></h2>${knowledge?'':'<button class="primary small" id="analyze-selected">分析所选资料</button>'}</div><form class="filters" id="document-filter"><label class="search-field">搜索资料<input name="q" value="${esc(state.filter.q||'')}" placeholder="按标题搜索"></label><button class="secondary small">查询</button></form>${data.items.length?`<div class="table-wrap"><table><thead><tr>${knowledge?'':'<th><input type="checkbox" id="select-all" aria-label="选择当前页可分析资料"></th>'}<th>资料标题</th><th>日期</th><th>${knowledge?'文本长度':'分析状态'}</th><th>数据范围</th><th>操作</th></tr></thead><tbody>${data.items.map(d=>`<tr>${knowledge?'':`<td><input type="checkbox" name="doc-select" value="${d.id}" aria-label="选择 ${esc(d.title)}" ${d.demo?'disabled':''}></td>`}<td class="title-cell">${esc(d.title)}${demoTag(d.demo)}<span class="source-line">${esc(d.source||'来源未填写')}</span></td><td class="nowrap">${esc(d.date||'未注明')}</td><td>${knowledge?`${d.characters} 字符`:badge(d.job_status||d.decision)}</td><td class="nowrap">${d.allow_external?'允许外部分析':'仅限本地'}</td><td><div class="document-actions">${sourceButton(d.id)}${knowledge||d.demo?'':`<button class="secondary small" data-analyze="${d.id}">${d.decision?'重新分析':'分析'}</button>`}</div></td></tr>`).join('')}</tbody></table></div>`:empty(knowledge?'知识库还没有资料':'暂无待分析资料',knowledge?'导入甲方提供的政策法规或案例后，可以先检索检查内容。':'在上方上传文件或手动录入，原始内容会保存在本地。')}${pagination(data)}</section>`;
}
async function jobs(){
  const data=await api('/jobs');
  return heading('分析任务','后台逐条处理资料。失败任务不会覆盖已有分析结果。','<button class="secondary" data-refresh>刷新状态</button><a class="primary" href="#documents">选择资料</a>')+
    `<section class="panel"><div class="panel-heading"><h2>最近100条任务</h2><small>排队与运行中的任务每4秒更新</small></div>${data.items.length?`<div class="table-wrap"><table><thead><tr><th>任务与资料</th><th>状态</th><th>处理进度</th><th>提交时间</th><th>结果与操作</th></tr></thead><tbody>${data.items.map(j=>`<tr><td class="title-cell">${esc(j.title)}<span class="source-line">任务 #${j.id}</span></td><td>${badge(j.status)}</td><td class="nowrap">${j.progress} / ${j.total||'—'} 个片段<progress class="job-progress" value="${j.progress}" max="${j.total||1}" aria-label="任务进度"></progress></td><td class="nowrap">${when(j.created_at)}</td><td>${j.error?`<p>${esc(j.error)}</p>`:''}${j.status==='failed'?`<button class="secondary small" data-analyze="${j.document_id}">重试分析</button>`:j.status==='completed'?sourceButton(j.document_id,'查看分析记录'):'等待处理'}</td></tr>`).join('')}</tbody></table></div>`:empty('还没有分析任务','在资料页选择一条或多条资料，启动后台分析。','<a class="primary" href="#documents">进入资料页</a>')}</section>`;
}
async function settings(){
  state.config=await api('/settings');const c=state.config;
  return heading('模型与规则','先配置 API 验证业务，再按甲方服务器条件切换本地模型。')+`<div class="settings-grid"><section class="panel"><div class="panel-heading"><h2>模型连接</h2><span class="status-chip">${c.configured?'已填写配置':'等待配置'}</span></div><div class="panel-content"><dl class="definition"><dt>运行模式</dt><dd>${c.mode==='local'?'本地模型':'外部 API'}</dd><dt>模型名称</dt><dd>${esc(c.model||'未设置')}</dd><dt>服务地址</dt><dd>${esc(c.base_url||'未设置')}</dd><dt>知识库检索</dt><dd>${esc(c.retrieval)}</dd></dl><h3>在服务器配置</h3><p class="form-note">将项目根目录的 .env.example 复制为 .env，填写以下字段后重启服务。密钥只保存在服务端，不会显示在页面中。</p><pre class="code-note">MODEL_MODE=external
MODEL_BASE_URL=https://你的服务地址/v1
MODEL_NAME=你的模型名称
MODEL_API_KEY=你的API密钥</pre><p class="form-note">兼容 Chat Completions 接口。基础地址以 /v1 等实际 API 前缀结尾，不要填写 /chat/completions。配置已填写不代表真实连接测试通过。</p><h3>后续切换本地模型</h3><p class="form-note">将 MODEL_MODE 改为 local，填写甲方内网推理服务地址与实际模型名称，完成效果和性能复测。本地模式不会自动回退外部 API。</p></div></section><section class="panel"><div class="panel-heading"><h2>风险分类分级规则</h2><span class="status-chip">${c.rules.confirmed?'已确认':'示例规则 · 待确认'}</span></div><form class="panel-content" id="rules-form"><p class="form-note">默认分类仅为起始示例。请根据甲方提供的标准修改分类、等级定义和版本，再勾选确认。历史分析保留当时使用的规则。</p><label class="field">规则内容（JSON）<textarea name="rules" class="rules-editor" spellcheck="false">${esc(JSON.stringify(c.rules,null,2))}</textarea></label><label class="check-field"><input type="checkbox" name="confirmed" ${c.rules.confirmed?'checked':''}><span>这份规则已经过甲方业务确认，可以用于后续风险分析。</span></label><button class="primary" type="submit">保存规则</button><div id="rules-error"></div></form></section></div>`;
}
async function showSource(id,quote=''){
  const sourceRequest=state.sourceRequest=(state.sourceRequest||0)+1;
  const dialog=$('#source-dialog');$('#source-content').innerHTML='<div class="loading">正在读取原文…</div>';if(!dialog.open)dialog.showModal();
  try{
    const d=await api('/documents/'+id);
    if(sourceRequest!==state.sourceRequest||!dialog.open)return;
    let text=esc(d.body);
    if(quote&&d.body.includes(quote)){const i=d.body.indexOf(quote);text=esc(d.body.slice(0,i))+'<mark>'+esc(quote)+'</mark>'+esc(d.body.slice(i+quote.length));}
    $('#source-content').innerHTML=`<h2>${esc(d.title)}${demoTag(d.demo)}</h2><div class="metadata"><span>${esc(d.source||'来源未填写')}</span><span>${esc(d.date||'日期未注明')}</span><span>资料 #${d.id}</span></div><div class="actions">${d.filename?`<a class="secondary small" href="/api/documents/${d.id}/file">下载原始附件</a>`:''}${d.url?`<a class="secondary small" href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">打开来源链接</a>`:''}</div><div class="source-body">${text}</div><h3>分析版本</h3>${d.analyses.length?d.analyses.map(a=>`<p class="form-note">v${a.version} · ${badge(a.decision)} · ${esc(a.model)} · ${when(a.created_at)}<br>${esc(a.result.reason||a.result.parts?.map(p=>p.reason).join('；')||'查看风险列表中的分析结果。')}</p>`).join(''):'<p class="muted">尚无分析记录。</p>'}`;
    const history=d.analyses.filter(a=>a.events?.length);
    if(history.length){
      $('#source-content').insertAdjacentHTML('beforeend','<h3>各版本风险事件</h3>'+history.map(a=>`<div class="version-links"><small>v${a.version}</small>${a.events.map(e=>`<a href="#event/${e.id}" data-history>${esc(e.title)}</a>`).join('')}</div>`).join(''));
      $$('[data-history]',dialog).forEach(a=>a.onclick=()=>dialog.close());
    }
    if(!d.demo){
      $('#source-content').insertAdjacentHTML('beforeend',`<form class="policy-form" id="policy-form"><h3>资料使用范围</h3><label class="check-field"><input type="checkbox" name="allow_external" ${d.allow_external?'checked':''}><span>我确认此资料允许发送至已配置的外部模型服务。取消勾选后，后续仅在本地模型模式使用。</span></label><button class="secondary small" type="submit">保存使用范围</button><div id="policy-error"></div></form>`);
      $('#policy-form').onsubmit=async event=>{event.preventDefault();const button=$('button',event.currentTarget);button.disabled=true;try{await api(`/documents/${d.id}/policy`,{method:'PATCH',body:{allow_external:new FormData(event.currentTarget).has('allow_external')}});toast('资料使用范围已更新');await render();}catch(e){$('#policy-error').innerHTML=errorBox(e.message);}finally{button.disabled=false;}};
    }
    $('mark',dialog)?.scrollIntoView({block:'center'});
  }catch(e){if(sourceRequest===state.sourceRequest&&dialog.open)$('#source-content').innerHTML=errorBox(e.message);}
}
async function analyze(ids,button){
  if(!ids.length){toast('请先选择需要分析的资料。');return;}
  if(button)button.disabled=true;
  try{const result=await api('/jobs',{method:'POST',body:{document_ids:ids}});toast(`${result.items.length} 条资料已进入任务列表`);if(location.hash==='#jobs')await render();else location.hash='#jobs';}
  catch(e){toast(e.message);if(button)button.disabled=false;}
}
function bind(){
  $$('[data-scope]').forEach(b=>b.onclick=()=>{state.scope=b.dataset.scope;state.page=1;if(state.route==='event'||state.route==='events')openEvents(state.route==='event'?{}:state.filter);else render();});
  $$('[data-page]').forEach(b=>b.onclick=()=>{state.page=Number(b.dataset.page);navigateList();});
  $$('[data-source]').forEach(b=>b.onclick=()=>showSource(b.dataset.source,b.dataset.quote));
  $$('[data-analyze]').forEach(b=>b.onclick=()=>analyze([Number(b.dataset.analyze)],b));
  $$('[data-refresh]').forEach(b=>b.onclick=render);
  $$('[data-demo]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const d=await api('/demo',{method:'POST'});toast(`已载入 ${d.added} 条虚构演示案例`);await render();}catch(e){toast(e.message);b.disabled=false;}});
  $('#event-filter')?.addEventListener('submit',e=>{e.preventDefault();state.filter=Object.fromEntries(new FormData(e.currentTarget));state.page=1;openEvents(state.filter);});
  $('#clear-filter')?.addEventListener('click',()=>{state.filter={};state.page=1;openEvents();});
  $('#document-filter')?.addEventListener('submit',e=>{e.preventDefault();state.filter=Object.fromEntries(new FormData(e.currentTarget));state.page=1;navigateList();});
  $$('[data-import-mode]').forEach(b=>b.onclick=()=>{state.importMode=b.dataset.importMode;render();});
  $('#select-all')?.addEventListener('change',e=>$$('[name=doc-select]:not(:disabled)').forEach(c=>c.checked=e.target.checked));
  $('#analyze-selected')?.addEventListener('click',e=>analyze($$('[name=doc-select]:checked').map(c=>Number(c.value)),e.currentTarget));
  $('#import-form')?.addEventListener('submit',async e=>{
    e.preventDefault();const form=e.currentTarget;const values=new FormData(form);const button=$('[type=submit]',form);button.disabled=true;$('#import-result').innerHTML='';
    try{
      let message;
      if(state.importMode==='file'){
        values.set('kind',form.dataset.kind);values.set('allow_external',values.has('allow_external')?'true':'false');
        const result=await api('/import',{method:'POST',body:values});
        const failed=result.results.filter(r=>r.status==='failed');const dup=result.results.filter(r=>r.status==='duplicate');
        message=`导入完成：新增 ${result.created} 条，重复 ${dup.length} 条，失败 ${failed.length} 条。`;
        sessionStorage.setItem('importFeedback',JSON.stringify({route:state.route,message,failed}));
      }else{
        const record=Object.fromEntries(values);record.kind=form.dataset.kind;record.allow_external=values.has('allow_external');
        const result=await api('/documents',{method:'POST',body:record});
        message=result.created?'资料已保存，可在下方启动分析。':'资料已存在，没有重复导入。';
        sessionStorage.setItem('importFeedback',JSON.stringify({route:state.route,message,failed:[]}));
      }
      toast(message);await render();
    }catch(error){$('#import-result').innerHTML=errorBox(error.message);button.disabled=false;}
  });
  let feedback=null;try{feedback=JSON.parse(sessionStorage.getItem('importFeedback')||'null');}catch{sessionStorage.removeItem('importFeedback');}
  if(feedback&&feedback.route===state.route&&$('#import-result')){$('#import-result').innerHTML=`<div class="success">${esc(feedback.message)}</div>${feedback.failed.length?'<ul class="result-list">'+feedback.failed.map(r=>`<li>第 ${r.row} 行：${esc(r.error)}</li>`).join('')+'</ul>':''}`;sessionStorage.removeItem('importFeedback');}
  $('#review-form')?.addEventListener('submit',async e=>{
    e.preventDefault();const form=e.currentTarget;const b=$('[type=submit]',form);b.disabled=true;
    try{await api(`/events/${form.dataset.id}/review`,{method:'PUT',body:Object.fromEntries(new FormData(form))});toast('复核意见已保存');await render();}catch(err){$('#review-error').innerHTML=errorBox(err.message);b.disabled=false;}
  });
  $('#knowledge-search')?.addEventListener('submit',async e=>{
    e.preventDefault();const q=new FormData(e.currentTarget).get('q');
    try{const data=await api('/knowledge/search?q='+encodeURIComponent(q));$('#knowledge-results').innerHTML=`<section class="panel"><div class="panel-heading"><h2>检索结果</h2><small>${data.items.length} 个片段</small></div>${data.items.length?data.items.map(r=>`<article class="search-hit"><h3>${esc(r.title)}</h3><p>${esc(r.text)}</p><small>${esc(r.locator)} · 匹配分数 ${r.score}</small><br>${sourceButton(r.document_id,'查看原文')}</article>`).join(''):empty('没有匹配的片段','尝试使用资料中的关键词，或先导入相关知识。')}</section>`;$$('[data-source]',$('#knowledge-results')).forEach(b=>b.onclick=()=>showSource(b.dataset.source));}catch(err){toast(err.message);}
  });
}
$('#close-source').onclick=()=>$('#source-dialog').close();
$('#logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});await boot();}catch(e){toast(e.message);}};
$('#mobile-logout').onclick=()=>$('#logout').click();
window.addEventListener('hashchange',render);
let polling=false;
setInterval(async()=>{if($('#shell').hidden||polling||document.hidden)return;polling=true;try{const jobs=await api('/jobs');const active=jobs.active;$('#job-count').textContent=active||'';const editing=document.activeElement?.closest('form');if(state.route==='jobs'&&!editing&&!$('#source-dialog').open&&(active||state.lastActive)){await render();}state.lastActive=active;}catch{}finally{polling=false;}},4000);
boot().catch(e=>{$('#auth').hidden=false;$('#auth').innerHTML=`<section class="auth-card"><h1>暂时无法连接服务</h1>${errorBox(e.message)}<p>请检查后端是否启动，再刷新页面。</p></section>`;});
