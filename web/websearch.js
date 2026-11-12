'use strict';
let webSelectedRun=null,webPoll=null,webRunsPoll=null,webSources=[],webEditorOpen=false,webImportOpen=false;
let webView=(()=>{try{return localStorage.getItem('webView')||'cards';}catch{return 'cards';}})();
const webFilter={q:'',category:'',status:'',page:1},webRunPage={page:1};
let webGroupNames = [];
function modelStatusText(){return !state.config.configured?'模型待配置':state.config.last_success?'最近模型分析成功':'模型已配置 · 尚无分析记录';}
function webDateLabel(p) {
  const source = p.date_source || { rss: 'feed', api: 'api' }[p.method] || 'publication';
  return dateLabel({ date: p.date, date_source: source, date_note: p.date_note });
}
function webCompanyOptions(selected) {
  return companyData.items.map((c) => `<option value="${c.id}" ${c.id === selected ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
}
function webHint(hint){return hint?`<span class="web-hint">${esc(hint)}</span>`:'';}
function webReason(hint,error){
  if(!hint)return error?`<span class="source-line">${esc(error)}</span>`:'';
  return webHint(hint)+(error&&error!==hint?`<details class="tech-detail"><summary>技术详情</summary>${esc(error)}</details>`:'');
}
function webStage(r){
  if(r.status==='queued')return '排队等待';
  if(r.status!=='running')return '';
  return r.stage==='review'?`AI 筛选中 ${r.judged??0} / ${r.pages??r.items?.length??0} 页`:`采集中 ${r.progress} / ${r.max_pages??r.config?.max_pages} 页`;
}
function webStatus(r){const stage=webStage(r);return badge(r.status)+(stage?`<span class="source-line">${stage}</span>`:'')+webReason(r.hint,r.error);}
function webSourceStatus(s){
  if(s.last_status==='completed'&&s.last_undecided)return `<span class="web-tag">判定待核验 ${s.last_undecided} 页</span>`;
  return s.last_status?badge(s.last_status):'<span class="badge">待检索</span>';
}
function webManualBadge(s){return s.enabled?'': '<span class="web-tag muted" title="不参与定时和分组检索，仍可手动检索">仅手动检索</span>';}
function webBatchName(b) {
  const raw = String(b.batch || '');
  const at = raw.lastIndexOf('@');
  const name = (at > 0 ? raw.slice(0, at) : String(b.category || raw)).trim() || '未命名批次';
  return webGroupNames.includes(name) ? `分组“${name}”` : name;
}
function webBatches(batches) {
  return (batches || []).map((b) => {
    const name = webBatchName(b);
    const total = Number(b.total) || 0;
    const done = Number(b.done) || 0;
    const cancel = b.queued ? `<button class="text-button danger web-batch-cancel" data-web-batch="${esc(b.batch)}">取消剩余</button>` : '';
    return `<div class="web-batch"><div class="web-batch-body"><strong class="web-batch-name" title="${esc(name)}">${esc(name)}</strong>`
      + `<div class="web-batch-progress"><span>已完成 ${done} / ${total}</span><progress max="${total}" value="${done}"></progress></div></div>${cancel}</div>`;
  }).join('');
}
function keywordChips(kw){
  const parts=String(kw||'').split(/[,，、;；\s]+/).filter(Boolean).slice(0,6);
  return parts.map(k=>`<span class="kw-chip">${esc(k)}</span>`).join('');
}
function webSourceRow(s){
  const rate=s.run_count?`${s.ok_count}/${s.run_count}`:'—';
  return `<tr><td><strong>${esc(s.name)}</strong><a class="source-line" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a></td><td><span class="web-tag">${esc(s.category||'未分组')}</span>${webManualBadge(s)}</td><td>${webSourceStatus(s)}${s.last_error?`<span class="source-line">${esc(s.last_hint||s.last_error)}</span>`:''}</td><td>${rate}</td><td><div class="actions"><button class="primary small" data-web-run="${s.id}">检索</button>${s.last_run_id?`<button class="secondary small" data-web-detail="${s.last_run_id}">结果</button>`:''}<button class="text-button" data-web-edit="${s.id}">编辑</button><button class="text-button" data-web-toggle="${s.id}" data-enabled="${s.enabled?0:1}">${s.enabled?'暂停自动':'恢复批量/定时'}</button><button class="text-button danger" data-web-delete="${s.id}">删除</button></div></td></tr>`;
}
function webSourceTable(items){return `<div class="table-wrap web-source-table"><table><thead><tr><th>网站名称与地址</th><th>所属分组</th><th>最近状态</th><th>成功次数</th><th>操作</th></tr></thead><tbody>${items.map(webSourceRow).join('')}</tbody></table></div>`;}
function webPager(data,kind){
  const pages=Math.max(1,Math.ceil(data.total/data.size));
  if(pages<2)return '';
  return `<div class="web-pager"><button class="secondary small" data-web-page="${kind}:${data.page-1}" ${data.page<=1?'disabled':''}>上一页</button><span>第 ${data.page} / ${pages} 页 · 共 ${data.total} 条</span><button class="secondary small" data-web-page="${kind}:${data.page+1}" ${data.page>=pages?'disabled':''}>下一页</button></div>`;
}
function webSourceCard(s){
  const rate=s.run_count?`采集 ${s.ok_count}/${s.run_count} 次成功`:'尚无采集记录';
  const autoText=s.auto_import!=='none'?`自动入${{knowledge:'知识库',event:'风险资料',both:'双库'}[s.auto_import]}`:'手动入库';
  return `<article class="web-source-card">`+
    `<div class="wsc-head"><div class="wsc-title-wrap"><h3>${esc(s.name)}</h3><div class="wsc-badges">${s.category?`<span class="web-tag">${esc(s.category)}</span>`:''}${webManualBadge(s)}<span class="wsc-meta-pill">${s.max_pages}页 · ${autoText}</span></div></div>`+
    `<div class="wsc-status">${webSourceStatus(s)}<small>${s.last_run_at?when(s.last_run_at):''}</small></div></div>`+
    `<a class="wsc-url" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" title="${esc(s.url)}">${esc(s.url)}</a>`+
    `<div class="wsc-keywords">${keywordChips(s.keywords)}</div>`+
    (s.last_error?`<div class="wsc-error">${webReason(s.last_hint,s.last_error)}</div>`:'')+
    `<div class="wsc-foot"><span class="wsc-foot-info">${s.enabled&&s.interval_hours?'每 '+s.interval_hours+' 小时定时':'手动触发'} · ${rate}${s.last_review_only?' · 最近为原文重新筛选':''}</span>`+
    `<div class="wsc-actions"><button class="primary small" data-web-run="${s.id}">开始检索</button>${s.last_run_id?`<button class="secondary small" data-web-detail="${s.last_run_id}">查看结果</button>`:''}<button class="text-button" data-web-edit="${s.id}">编辑</button><button class="text-button" data-web-toggle="${s.id}" data-enabled="${s.enabled?0:1}">${s.enabled?'暂停自动':'恢复批量/定时'}</button><button class="text-button danger" data-web-delete="${s.id}">删除</button></div></div>`+
  `</article>`;
}
function webRunSide(r) {
  const pages = Number(r.pages) || 0;
  const relevant = Number(r.relevant) || 0;
  const count = pages > 0 ? `<span class="wri-count ${relevant ? 'has-hit' : ''}">${pages} 页 · ${relevant} 命中</span>` : '';
  return count + (r.status==='completed'&&Number(r.judged)<pages?'<span class="web-tag">部分待核验</span>':badge(r.status));
}
function webRunItem(r) {
  const selected = webSelectedRun === r.id;
  const tip = r.status === 'failed' && r.hint ? `${r.name}\n${r.hint}` : r.name;
  return `<div class="web-run-item ${selected ? 'is-selected-row' : ''}" data-web-row="${r.id}" data-web-detail="${r.id}" role="option" tabindex="0" aria-selected="${selected}" title="${esc(tip)}">`
    + `<div class="wri-main"><strong class="wri-name">${esc(r.name)}</strong><span class="wri-time">${when(r.created_at)}</span></div>`
    + `<div class="wri-side">${webRunSide(r)}</div></div>`;
}
function webRunsPanel(runs){
  return `<div class="panel-heading"><div><h2>最近检索任务 <small>共 ${runs.total} 次${runs.active?` · ${runs.active} 个运行中`:''}</small></h2></div><button class="secondary small" id="refresh-web-runs">刷新记录</button></div>${webBatches(runs.batches)}${runs.items.length?`<div class="web-runs-list" role="listbox" aria-label="最近检索任务">${runs.items.map(webRunItem).join('')}</div>${webPager(runs,'runs')}`:empty('尚无检索记录','在上方任一网站卡片点击“开始检索”。')}`;
}
const WEB_GROUP_ORDER = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'];
function webGroupRank(name) {
  const prefix = String(name || '').split('、')[0];
  const index = WEB_GROUP_ORDER.indexOf(prefix);
  return index < 0 ? 100 : index;
}
function webGroupFamily(name) {
  const rank = webGroupRank(name);
  if (rank >= 0 && rank <= 3) {
    return '印尼国内法规与执法';
  }
  if (rank >= 4 && rank <= 7) {
    return '国际规则与制裁';
  }
  if (rank >= 8 && rank <= 11) {
    return '舆情、涉华与经贸';
  }
  return '其他分组';
}
function webGroupOptions(groups, selected) {
  const sorted = [...groups].filter((group) => group.name).sort((a, b) => webGroupRank(a.name) - webGroupRank(b.name));
  const families = ['印尼国内法规与执法', '国际规则与制裁', '舆情、涉华与经贸', '其他分组'];
  return families.map((family) => {
    const items = sorted.filter((group) => webGroupFamily(group.name) === family);
    if (!items.length) {
      return '';
    }
    return `<optgroup label="${esc(family)}">${items.map((group) => `<option value="${esc(group.name)}" ${group.name === selected ? 'selected' : ''}>${esc(group.name)}（${group.count}）</option>`).join('')}</optgroup>`;
  }).join('');
}
async function websitePage(){
  const query=new URLSearchParams({q:webFilter.q,category:webFilter.category,status:webFilter.status,page:webFilter.page,size:24});
  const [sources,runs]=await Promise.all([api('/web/sources?'+query),api('/web/runs?page='+webRunPage.page)]);webSources=sources.items;
  webGroupNames = sources.groups.map((group) => group.name).filter(Boolean);
  if(!webSelectedRun&&runs.items?.length)webSelectedRun=runs.items[0].id;
  const all=sources.groups.reduce((n,g)=>n+g.count,0),filtered=webFilter.q||webFilter.category||webFilter.status;
  const closed=all&&!webEditorOpen;
  const health=await api('/web/health').catch(()=>null);
  return heading('网站检索',`从已配置的 ${all} 个网站采集公开网页，AI 初筛后由人工核验入库。`,'<a class="secondary" href="#updates">网站更新待办</a><a class="secondary" href="#knowledge">查看知识库</a><a class="secondary" href="#events">查看风险事件</a>')+
    collectionHealth(health)+
    '<ol class="collection-steps"><li><span class="step-num">01</span><div><strong>指定采集来源</strong><span>按分组管理站点与检索词；来源是否官方需自行核实</span></div></li><li><span class="step-num">02</span><div><strong>多通道抓取与 AI 初筛</strong><span>直连 + 渲染 + 网页存档兜底，AI 自动剔除导航页与无关页</span></div></li><li><span class="step-num">03</span><div><strong>核验后入库</strong><span>默认人工勾选入库；仅开启“自动保存”的网站会自动入库</span></div></li></ol>'+
    `<div class="web-workbench ${closed?'editor-closed':''}"><section class="panel web-sources-panel"><div class="panel-heading"><div><h2>采集网站库 <small>共 ${all} 个网站</small></h2></div><div class="actions"><div class="segmented" role="group" aria-label="显示方式"><button type="button" class="${webView==='cards'?'selected':''}" aria-pressed="${webView==='cards'}" data-web-view="cards">双列卡片</button><button type="button" class="${webView==='table'?'selected':''}" aria-pressed="${webView==='table'}" data-web-view="table">紧凑表格</button></div><button class="secondary small" id="open-web-import">批量导入</button><button class="primary small" id="new-web-source">添加网站</button></div></div>`+
    `<form class="filters web-filters" id="web-source-filter"><label class="search-field">搜索网站<input name="q" value="${esc(webFilter.q)}" placeholder="输入机构名称、域名网址或中英文关键词…"></label><label>所属分组<select name="category"><option value="">全部分组（${all}）</option>${webGroupOptions(sources.groups, webFilter.category)}</select></label><label>工作状态<select name="status"><option value="">全部状态</option>${Object.entries(webSourceStatuses).map(([key,label])=>`<option value="${key}" ${webFilter.status===key?'selected':''}>${label}</option>`).join('')}</select></label><button class="secondary small" type="submit">查询</button>${filtered?'<button class="text-button" type="button" id="reset-web-filter">重置</button>':''}${webFilter.category?`<button class="primary small" type="button" id="run-web-group">一键检索本组（${sources.total}）</button>`:''}</form>`+
    `<div class="panel-content">${sources.items.length?(webView==='table'?webSourceTable(sources.items):`<div class="web-source-grid">${sources.items.map(webSourceCard).join('')}</div>`)+webPager(sources,'sources'):(filtered?empty('没有匹配的网站','请尝试调整搜索词或切换上方分组标签。'):empty('先添加一个网站','填入公开网站或栏目地址及关注关键词，或批量导入网址清单。'))}</div></section>`+
    `<section class="panel" id="web-import-panel" ${webImportOpen?'':'hidden'}><div class="panel-heading"><h2>批量导入网站</h2><button class="text-button" type="button" id="close-web-import">收起</button></div><form class="panel-content" id="web-import-sources"><p class="form-note">每行一个网站，用 Tab 或逗号分隔：<strong>分组, 名称, 网址, 关键词</strong>（只有三列时为 名称, 网址, 关键词）。可直接从表格复制粘贴，或选择 JSON / CSV 文件。已存在的网址会自动跳过。</p><label class="field">网址清单<textarea name="text" rows="8" placeholder="一、印尼国内	印尼法律部	https://kemenkum.go.id	peraturan regulation 法规"></textarea></label><label class="field">或选择文件<input type="file" name="file" accept=".json,.csv,.txt,.tsv"></label><div class="form-grid"><label class="field">每次最多访问页面<select name="max_pages"><option value="1">1 页</option><option value="5" selected>5 页</option><option value="10">10 页</option></select></label></div><button class="primary" type="submit">导入</button><div id="web-import-sources-feedback" role="status"></div></form></section>`+
    `<section class="panel" id="web-source-editor" ${closed?'hidden':''}><div class="panel-heading"><h2 id="web-editor-title">添加网站</h2><button class="text-button" type="button" id="close-web-editor">收起配置</button></div><form class="panel-content" id="web-source-form"><input name="source_id" type="hidden"><label class="field">网站名称<input name="name" required maxlength="100" placeholder="例如：政策法规信息源"></label><label class="field">网站或栏目地址<input name="url" type="url" required maxlength="2000" placeholder="https://网站域名/栏目/"></label><label class="field">分组<input name="category" maxlength="60" list="web-groups" placeholder="例如：一、印尼国内"><datalist id="web-groups">${sources.groups.filter(g=>g.name).map(g=>`<option value="${esc(g.name)}">`).join('')}</datalist></label><label class="field">关键词或检索主题<textarea name="keywords" required maxlength="500" rows="3" placeholder="例如：进口限制、劳工政策、原料供应中断"></textarea></label><div class="form-grid"><label class="field">每次最多访问页面<select name="max_pages"><option value="1">1 页</option><option value="5">5 页</option><option value="10" selected>10 页</option><option value="20">20 页</option></select></label><label class="field">检索频率<select name="interval_hours"><option value="0">手动检索</option><option value="6">每 6 小时</option><option value="24">每天</option><option value="168">每周</option></select></label></div><label class="field">检索完成后<select name="auto_import"><option value="none" selected>核验后手动入库</option><option value="knowledge">自动保存至知识库</option><option value="event">自动保存为风险资料</option><option value="both">同时保存知识库和风险资料</option></select></label><label class="field" id="web-target-company" hidden>风险资料归属公司<select name="target_company_id"><option value="">请选择公司</option>${webCompanyOptions(null)}</select></label><label class="check-field"><input name="auto_analyze" type="checkbox"><span>对新入库的风险资料自动启动分析，结果进入风险事件列表。</span></label><p class="form-note">只访问此域名及填写的栏目路径，遵守 robots.txt。支持网页、文本和 PDF；直连失败时会尝试备用出口和互联网档案馆快照。</p><button class="primary" type="submit">保存网站</button><div id="web-source-feedback" role="status"></div></form></section></div>`+
    `<div class="web-runs-split"><section class="panel" id="web-runs-panel">${webRunsPanel(runs)}</section><section class="panel" id="web-results" aria-live="polite"><div class="panel-content form-note">点击左侧任一检索任务，在此查看抓取到的页面原文与 AI 筛选依据。</div></section></div>`+
    (runs.active?'<span hidden id="web-runs-active"></span>':'');
}
function parseSourceList(text){
  text=text.replace(/^﻿/,'').trim();
  if(!text)return [];
  if(text.startsWith('[')){
    return JSON.parse(text).map(r=>({category:String(r.category??r.sec??'').trim(),name:String(r.name??'').trim(),url:String(r.url??'').trim(),keywords:String(r.keywords??r.kw??'').trim()}));
  }
  const rows=[];
  for(const line of text.split(/\r?\n/)){
    if(!line.trim())continue;
    const cells=(line.includes('\t')?line.split('\t'):line.split(',')).map(c=>c.trim().replace(/^"|"$/g,''));
    if(/^(分组|名称|网址|url|name|category)$/i.test(cells[0])||cells.some(c=>/^(网址|url)$/i.test(c)))continue;
    const [category,name,url,...rest]=cells.length>=4?cells:['',...cells];
    rows.push({category,name:name||url,url,keywords:rest.join(' ')||name});
  }
  return rows;
}
async function refreshWebRuns(){
  clearTimeout(webRunsPoll);
  if(state.route!=='websites')return;
  try{
    const runs=await api('/web/runs?page='+webRunPage.page);
    const panel=$('#web-runs-panel');if(!panel||state.route!=='websites')return;
    panel.innerHTML=webRunsPanel(runs);bindWebRuns();
    if(runs.active)webRunsPoll=setTimeout(refreshWebRuns,5000);
  }catch(error){}
}
function bindWebRuns(){
  $$('[data-web-detail]').forEach(b=>b.onclick=async()=>{
    const rid=Number(b.dataset.webDetail);
    $$('[data-web-row]').forEach(tr=>tr.classList.toggle('is-selected-row',Number(tr.dataset.webRow)===rid));
    await showWebRun(rid);
    const results=$('#web-results');
    if(results){results.tabIndex=-1;results.focus({preventScroll:true});results.scrollIntoView({block:'start',behavior:'instant'});}
    $('#return-web-source')?.remove();
    if(results){const back=document.createElement('button');back.id='return-web-source';back.type='button';back.className='secondary small';back.textContent='返回网站列表';back.onclick=()=>{b.focus({preventScroll:true});b.scrollIntoView({block:'center',behavior:'instant'});};$('.panel-heading .actions',results)?.prepend(back);}
  });
  $('#refresh-web-runs').onclick=refreshWebRuns;
  $$('[data-web-batch]').forEach(b=>b.onclick=async()=>{if(!confirm('取消这一批中还在排队的检索？正在运行的网站会继续完成。'))return;b.disabled=true;try{const r=await api('/web/runs/batch/cancel',{method:'POST',body:{batch:b.dataset.webBatch}});toast(`已取消 ${r.cancelled} 个排队中的检索`);refreshWebRuns();}catch(e){toast(e.message);b.disabled=false;}});
  $$('[data-web-page^="runs:"]').forEach(b=>b.onclick=()=>{webRunPage.page=Number(b.dataset.webPage.split(':')[1]);refreshWebRuns();});
}
async function showWebRun(id){
  webSelectedRun=id;clearTimeout(webPoll);
  if(state.route!=='websites')return;
  const target=$('#web-results');
  try{
    const r=await api('/web/runs/'+id);if(state.route!=='websites'||webSelectedRun!==id)return;
    const active=['queued','running'].includes(r.status);
    $$('[data-web-row]').forEach((el) => el.setAttribute('aria-selected', String(Number(el.dataset.webRow) === id)));
    const row=$('[data-web-row="'+id+'"]');
    if(row){
      row.classList.add('is-selected-row');
      const side=row.querySelector('.wri-side');
      if (side) {
        side.innerHTML = webRunSide({ pages: r.items.length, judged: r.judged, relevant: r.items.filter((p) => p.relevant === 1).length, status: r.status });
      }
    }
    const waiting = r.status === 'queued' || (r.status === 'running' && !r.items.length);
    const relItems=r.items.filter(p=>p.relevant===1);
    const otherItems=r.items.filter(p=>p.relevant!==1);
    const inKbCount=r.items.filter(p=>p.in_knowledge).length;
    const rejected=r.items.filter(p=>p.relevant===0).length;
    const undecided=r.items.filter(p=>p.relevant===null).length;
    const renderPageCard=(p,isHit)=>`<article class="web-result-card ${isHit?'is-hit':'is-skipped'}" data-change-status="${p.change?.status||'added'}">`+
      `<p><span class="change-label ${p.change?.status||'added'}">${changeNames[p.change?.status||'added']}</span>${p.change?.previous_fetched_at?` <small>对比 ${when(p.change.previous_fetched_at)} 的快照</small>`:''}</p>`+
      `<div class="wrc-head"><label class="wrc-check">${isHit?`<input type="checkbox" name="web-page" value="${p.id}" aria-label="选择 ${esc(p.title)}" ${r.status==='completed'?'':'disabled'}>`:''}<h3>${esc(p.title)}</h3></label><div class="wrc-badges"><span class="web-tag">${esc(webDateLabel(p))}</span>${p.archived_at?`<span class="web-tag">存档快照 ${esc(p.archived_at)}</span>`:''}${p.in_knowledge?`<span class="web-tag ok">${p.knowledge_from_history?'历史已存知识库':'已存知识库'}</span>`:''}<span class="badge ${p.relevant===1?'accepted':''}">${p.relevant===null?(p.review_origin==='unverified'?'校验未通过':'待判定'):p.relevant?'相关':'不相关'}</span></div></div>`+
      `<a class="wsc-url" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer" title="${esc(p.url)}">${esc(p.url)}</a>`+
      (p.knowledge_from_history?`<p class="history-saved-note">资料保存于 ${when(p.knowledge_saved_at)}；本次筛选不会删除历史入库资料。</p>`:'')+
      `${p.reason?`<p class="wrc-reason">${esc(p.reason)}</p>`:''}`+
      (p.review_origin?`<p class="source-line">${esc({model:'本次模型判定',quote_repair:'本次模型判定 · 引文已按原文句段校正',reused:'沿用相同正文和主题的历史判定',unverified:'模型判定未通过校验'}[p.review_origin]||'')}</p>`:'')+
      (p.quote?`<blockquote class="wrc-quote">${readingEsc(p.quote)}</blockquote>`:'')+
      `<div class="wrc-foot"><span>收录于 ${when(p.fetched_at)} · ${p.characters.toLocaleString('zh-CN')} 字符</span><div class="wrc-actions">${r.status==='completed'?`<button class="secondary small" data-web-compare="${p.id}" aria-expanded="false" aria-controls="compare-${p.id}">查看更新对比</button>`:''}<button class="secondary small" data-web-original="${p.id}">查看原文</button>${Object.entries(p.imports).map(([kind,doc])=>`<button class="secondary small" data-source="${doc}">${kind==='knowledge'?'查看知识库详情':'查看分析记录'}</button>`).join('')}</div></div><section id="compare-${p.id}" class="web-comparison" aria-label="正文版本对比" hidden></section>`+
    `</article>`;

    const runHeading=`<div class="panel-heading"><div><h2>${esc(r.config.name)} <small>任务 #${r.id}</small></h2></div><div class="actions">${r.status==='completed'&&undecided?'<span class="web-tag">部分待核验</span>':badge(r.status)}${active?`<button class="secondary small" id="cancel-web-run">取消检索</button>`:''}${!active&&r.items.some(p=>p.relevant===null)?`<button class="primary small" id="rereview-web-run">重新筛选</button>`:''}</div></div>`;
    const execution=`<p class="web-execution source-line">${r.config.review_only?'已有原文重新筛选':'网页采集与筛选'} · 模型有效响应 ${r.model_responses??r.usage?.length??0} 次 · 沿用历史判定 ${r.reused_pages??0} 页${r.finished_at?' · 完成于 '+esc(when(r.finished_at)):''}</p>`;
    const waitingNote = r.status === 'queued' ? '正在等待前面的网站' : webStage({ ...r, pages: 0 });
    target.innerHTML = waiting
      ? `${runHeading}<div class="panel-content"><p role="status" class="web-waiting">${waitingNote}<span>可离开页面稍后查看。</span></p>${r.error ? (r.hint ? `<div class="web-reason-box">${webReason(r.hint, r.error)}</div>` : errorBox(r.error)) : ''}</div>`
      : runHeading+
      `<div class="panel-content">`+
      execution+
      `<div class="wrd-summary-strip"><div class="wrd-stat"><span>收录资料</span><strong>${r.items.length} <small>/ 最多 ${r.config.max_pages} 页</small></strong></div><div class="wrd-stat hit"><span>相关资料</span><strong>${relItems.length} <small>篇相关</small></strong></div><div class="wrd-stat"><span>知识库资料</span><strong>${inKbCount} <small>篇</small></strong></div><div class="wrd-kw"><span>检索词与模型</span><div class="wsc-keywords">${keywordChips(r.config.keywords)}${r.model?`<span class="wsc-meta-pill">${esc(r.model)}</span>`:''}</div></div></div>`+
      (r.status==='completed'&&r.items.length?changeControls(r.items):'')+
      (active?`<p role="status" class="web-progress">${webStage({...r,pages:r.items.length})}<span>可离开页面稍后查看。</span></p>`:'')+
      (r.error?(r.hint?`<div class="web-reason-box">${webReason(r.hint,r.error)}</div>`:errorBox(r.error)):'')+
      (relItems.length?`<div class="wrd-section-title"><span>相关命中页面（${relItems.length} 篇）</span></div><div class="web-result-list">${relItems.map(p=>renderPageCard(p,true)).join('')}</div>`:(!active&&!r.items.length?empty('没有可展示的页面','请查看下方失败原因与处理建议。'):''))+
      (r.status==='completed'&&relItems.length?`<form id="web-import-form" class="web-import-bar"><label class="field">勾选页面转存用途<select name="kind"><option value="knowledge">知识库参考资料</option><option value="event">待分析风险资料</option><option value="both">同时存入知识库与风险资料</option></select></label><label class="field" data-web-company>归属公司<select name="company_id"><option value="">按网站归属</option>${webCompanyOptions(r.config.target_company_id)}</select></label><label class="check-field"><input type="checkbox" name="analyze"><span>转存为风险资料后立即启动分析</span></label><div class="actions"><button class="secondary small" type="button" id="web-select-all">全选命中页</button><button class="primary small" type="submit" disabled id="web-import-button">选择命中页后入库</button></div><div id="web-import-feedback" role="status"></div></form>`:'')+
      (otherItems.length?`<details class="web-skipped-drawer" ${relItems.length?'':'open'}><summary>其他资料（不相关 ${rejected} · 未筛选 ${undecided}）</summary><div class="web-result-list skipped-list">${otherItems.map(p=>renderPageCard(p,false)).join('')}</div></details>`:'')+
      (r.errors.length?`<details class="web-errors" ${r.items.length?'':'open'}><summary>未采集成功的链接（${r.errors.length} 个）</summary>${r.errors.map(e=>`<p>${e.hint?`<strong>${esc(e.hint)}</strong>`:`<strong>${esc(e.error)}</strong>`}<br><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.url)}</a>${e.hint?`<details class="tech-detail"><summary>技术详情</summary>${esc(e.error)}</details>`:''}</p>`).join('')}</details>`:'')+
      `</div>`;
    bindWebChanges(target);
    $('#cancel-web-run')?.addEventListener('click',async()=>{try{await api('/web/runs/'+id+'/cancel',{method:'POST'});await showWebRun(id);}catch(e){toast(e.message);}});
    $('#rereview-web-run')?.addEventListener('click',async e=>{e.currentTarget.disabled=true;try{await api('/web/runs/'+id+'/review',{method:'POST'});toast('已排队重新筛选');await showWebRun(id);refreshWebRuns();}catch(err){toast(err.message);e.currentTarget.disabled=false;}});
    $$('[data-web-original]').forEach((b) => {
      b.onclick = async () => {
        try {
          const p = await api(`/web/pages/${b.dataset.webOriginal}`);
          const quote = r.items.find((item) => String(item.id) === b.dataset.webOriginal)?.quote || '';
          const marked = quote ? markRanges(p.body, [quote]) : { html: readingEsc(p.body), count: 0 };
          const quoteTools = !quote ? '' : marked.count
            ? '<button type="button" class="secondary small" id="jump-web-quote">跳到 AI 引用片段</button>'
            : '<p class="notice-inline" role="note">原文中未找到 AI 引用的片段，请人工核对。</p>';
          const dialog = $('#source-dialog');
          $('#source-title').textContent = '采集原文';
          $('#source-content').innerHTML = `<h2>${esc(p.title)}</h2><dl class="detail-meta-grid"><div><dt>网址</dt><dd><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.url)}</a></dd></div><div><dt>发布日期</dt><dd>${esc(webDateLabel(p))}</dd></div>${p.archived_at ? `<div><dt>存档快照</dt><dd>${esc(p.archived_at)}</dd></div>` : ''}<div><dt>收录时间</dt><dd>${esc(when(p.fetched_at))}</dd></div></dl><div class="actions source-actions">${quoteTools}</div><div class="source-body">${marked.html}</div>`;
          $('#jump-web-quote')?.addEventListener('click', () => $('#source-content .kr-hit')?.scrollIntoView({ block: 'start' }));
          if (!dialog.open) {
            dialog.showModal();
          }
          dialog.scrollTop = 0;
        } catch (e) {
          toast(e.message);
        }
      };
    });
    $$('[data-source]',target).forEach(b=>b.onclick=()=>showSource(b.dataset.source));
    const importKind=$('#web-import-form [name=kind]'),importAnalyze=$('#web-import-form [name=analyze]');
    if(importKind&&importAnalyze){const sync=()=>{importAnalyze.disabled=importKind.value==='knowledge';if(importAnalyze.disabled)importAnalyze.checked=false;$('[data-web-company]',target).hidden=false;$('#web-import-form [name=company_id] option').textContent=importKind.value==='knowledge'?'按网站归属（未设置则公共）':'请选择公司';};importKind.onchange=sync;sync();}
    const syncPicked=()=>{const n=$$('[name=web-page]:checked',target).length;const b=$('#web-import-button');if(b){b.disabled=!n;b.textContent=n?`保存 ${n} 个页面`:'选择命中页后入库';}};
    $$('[name=web-page]',target).forEach(c=>c.onchange=syncPicked);
    $('#web-select-all')?.addEventListener('click',()=>{const boxes=$$('[name=web-page]:not(:disabled)',target).filter(c=>!c.closest('.web-result-card')?.hidden);const all=boxes.every(c=>c.checked);boxes.forEach((c,i)=>c.checked=!all&&i<20);syncPicked();});
    $('#web-import-form')?.addEventListener('submit',async e=>{e.preventDefault();const f=new FormData(e.currentTarget),b=$('#web-import-button');b.disabled=true;try{const result=await api('/web/import',{method:'POST',body:{page_ids:$$('[name=web-page]:checked',target).map(c=>Number(c.value)),kind:f.get('kind'),analyze:f.has('analyze'),company_id:Number(f.get('company_id'))||null}});toast(`已保存 ${result.items.filter(i=>i.created).length} 条资料${result.items.some(i=>i.job_id)?'；风险分析已排队':''}`);await showWebRun(id);}catch(error){$('#web-import-feedback').innerHTML=errorBox(error.message);b.disabled=false;}});
    if(active)webPoll=setTimeout(()=>showWebRun(id),3000);
  }catch(error){if(target)target.innerHTML=errorBox(error.message);}
}
function bindWebsite(){
  const form=$('#web-source-form');
  if(state.route!=='websites'||!form){clearTimeout(webPoll);clearTimeout(webRunsPoll);return;}
  const fresh=()=>{form.reset();form.elements.source_id.value='';$('#web-target-company').hidden=true;$('#web-editor-title').textContent='添加网站';$('#web-source-feedback').innerHTML='';};
  const openEditor=()=>{webEditorOpen=true;$('#web-source-editor').hidden=false;$('.web-workbench').classList.remove('editor-closed');};
  const targetCompany=$('#web-target-company');
  const syncTarget=()=>{targetCompany.hidden=!['event','both'].includes(form.elements.auto_import.value);};
  form.elements.auto_import.addEventListener('change',syncTarget);syncTarget();
  $('#close-web-editor').onclick=()=>{webEditorOpen=false;$('#web-source-editor').hidden=true;$('.web-workbench').classList.add('editor-closed');$('#new-web-source').focus();};
  $('#new-web-source').onclick=()=>{fresh();openEditor();form.elements.name.focus();form.scrollIntoView({block:'start',behavior:'smooth'});};
  $('#open-web-import').onclick=()=>{webImportOpen=true;$('#web-import-panel').hidden=false;$('#web-import-panel').scrollIntoView({block:'start',behavior:'smooth'});$('#web-import-sources [name=text]').focus();};
  $('#close-web-import').onclick=()=>{webImportOpen=false;$('#web-import-panel').hidden=true;};
  $('#web-import-sources').onsubmit=async e=>{
    e.preventDefault();const f=e.currentTarget,b=$('[type=submit]',f),out=$('#web-import-sources-feedback');b.disabled=true;out.innerHTML='';
    try{
      const file=f.elements.file.files[0];const text=file?await file.text():f.elements.text.value;
      const items=parseSourceList(text);
      if(!items.length)throw new Error('没有识别到网址，请检查格式。');
      const bad=items.filter(i=>!i.url||!i.name||!i.keywords);if(bad.length)throw new Error(`有 ${bad.length} 行缺少名称、网址或关键词。`);
      let created=0,skipped=0,errors=[];
      for(let i=0;i<items.length;i+=500){const r=await api('/web/sources/import',{method:'POST',body:{items:items.slice(i,i+500),max_pages:Number(f.elements.max_pages.value)}});created+=r.created;skipped+=r.skipped;errors=errors.concat(r.errors.map(x=>({...x,row:x.row+i})));}
      toast(`已导入 ${created} 个网站，跳过重复 ${skipped} 个${errors.length?`，${errors.length} 个网址无效`:''}`);
      webImportOpen=!!errors.length;await render();
      if(errors.length)$('#web-import-sources-feedback').innerHTML=errorBox(errors.map(x=>`第 ${x.row} 行 ${x.url}：${x.error}`).join('；'));
    }catch(error){out.innerHTML=errorBox(error.message);b.disabled=false;}
  };
  $('#web-source-filter').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);webFilter.q=String(f.get('q')||'').trim();webFilter.category=String(f.get('category')||'');webFilter.status=String(f.get('status')||'');webFilter.page=1;render();};
  $('#web-source-filter [name=category]').onchange=e=>{webFilter.category=e.target.value;webFilter.page=1;render();};
  $('#web-source-filter [name=status]').onchange=e=>{webFilter.status=e.target.value;webFilter.page=1;render();};
  $('#reset-web-filter')?.addEventListener('click',()=>{webFilter.q='';webFilter.category='';webFilter.status='';webFilter.page=1;render();});
  $$('[data-cat-pill]').forEach(b=>b.onclick=()=>{webFilter.category=b.dataset.catPill;webFilter.page=1;render();});
  $('#run-web-group')?.addEventListener('click',async e=>{const b=e.currentTarget;if(!confirm(`对“${webFilter.category}”分组中已启用的网站逐个排队检索？`))return;b.disabled=true;try{const r=await api('/web/runs/group',{method:'POST',body:{category:webFilter.category}});toast(`已排队 ${r.queued} 个检索任务，将依次执行`);await render();}catch(error){toast(error.message);b.disabled=false;}});
  $$('[data-web-view]').forEach(b=>b.onclick=()=>{webView=b.dataset.webView;try{localStorage.setItem('webView',webView);}catch{}render();});
  $$('[data-web-page^="sources:"]').forEach(b=>b.onclick=()=>{webFilter.page=Number(b.dataset.webPage.split(':')[1]);render();});
  $$('[data-web-edit]').forEach(b=>b.onclick=()=>{openEditor();const s=webSources.find(s=>s.id===Number(b.dataset.webEdit));for(const key of ['name','url','keywords','max_pages','interval_hours','auto_import','category','target_company_id'])form.elements[key].value=s[key]??'';syncTarget();for(const key of ['auto_analyze'])form.elements[key].checked=!!s[key];form.elements.source_id.value=s.id;$('#web-editor-title').textContent='编辑网站';form.scrollIntoView({block:'start',behavior:'smooth'});form.elements.name.focus();});
  form.onsubmit=async e=>{e.preventDefault();const f=new FormData(form),id=f.get('source_id'),b=$('[type=submit]',form);b.disabled=true;try{await api('/web/sources'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{name:f.get('name'),url:f.get('url'),category:f.get('category')||'',keywords:f.get('keywords'),max_pages:Number(f.get('max_pages')),interval_hours:Number(f.get('interval_hours')),auto_import:f.get('auto_import'),target_company_id:['event','both'].includes(f.get('auto_import'))?(Number(f.get('target_company_id'))||null):null,auto_analyze:f.has('auto_analyze')}});toast('网站配置已保存');webEditorOpen=false;await render();}catch(error){$('#web-source-feedback').innerHTML=errorBox(error.message);b.disabled=false;}};
  $$('[data-web-run]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await api('/web/runs',{method:'POST',body:{source_id:Number(b.dataset.webRun)}});webSelectedRun=r.id;await render();$('#web-runs-panel')?.scrollIntoView({block:'start',behavior:'smooth'});}catch(error){toast(error.message);b.disabled=false;}});
  $$('[data-web-toggle]').forEach(b=>b.onclick=async()=>{try{await api('/web/sources/'+b.dataset.webToggle+'/toggle',{method:'POST',body:{enabled:b.dataset.enabled==='1'}});toast(b.dataset.enabled==='1'?'已恢复分组检索及配置的定时任务':'已暂停定时和分组检索，仍可手动检索');await render();}catch(error){toast(error.message);}});
  $$('[data-web-delete]').forEach(b=>b.onclick=async()=>{const s=webSources.find(s=>s.id===Number(b.dataset.webDelete));if(!confirm(`删除网站“${s?.name||''}”？已有的检索记录和入库资料会保留。`))return;try{await api('/web/sources/'+b.dataset.webDelete,{method:'DELETE'});toast('网站已删除');await render();}catch(error){toast(error.message);}});
  $$('[data-web-pause]').forEach(b=>b.onclick=async()=>{try{await api('/web/sources/'+b.dataset.webPause+'/pause',{method:'POST'});toast('定时检索已暂停，当前任务如需停止请点击取消');await render();}catch(error){toast(error.message);}});
  bindWebRuns();
  clearTimeout(webRunsPoll);if($('#web-runs-active'))webRunsPoll=setTimeout(refreshWebRuns,5000);
  if(webSelectedRun)showWebRun(webSelectedRun);
}
