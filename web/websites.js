'use strict';
const siteTaskNames={queued:'排队中',running:'检索中',completed:'已完成',partial:'部分结果可用',failed:'失败'};
const siteContentNames={ready:'正文可用',summary_only:'只有检索摘要，不能入库',too_long:'正文超出长度限制，不能入库'};
async function websitePage(){
  const [config,sources,searches]=await Promise.all([api('/websites/config'),api('/websites/sources'),api('/websites/searches')]);
  state.websiteSources=sources.items;
  const selected=new URLSearchParams(location.hash.split('?')[1]||'').get('task');
  const detail=selected?await api('/websites/searches/'+encodeURIComponent(selected)):null;
  state.websiteActive=searches.items.some(t=>['queued','running'].includes(t.status));
  state.websiteDetail=detail;
  return heading('网站检索','发现指定网站的相关资料，确认来源后加入知识库或启动风险分析。','<button class="secondary" data-refresh>刷新结果</button>')+
    (!config.configured?'<div class="notice-inline"><p>检索服务尚未配置。请联系管理员配置检索服务后使用；你可以先添加网站来源。</p></div>':'<p class="form-note">检索会向外部服务发送关键词和网站范围，可能产生接口费用。仅匹配指定域名与栏目，不保证全站覆盖。</p>')+
    `<div class="website-grid"><section class="panel"><div class="panel-heading"><h2>发起检索</h2></div><form id="website-search-form" class="panel-content"><fieldset><legend>选择网站来源</legend>${sources.items.filter(s=>s.enabled).map(s=>`<label class="check-field"><input name="source_ids" type="checkbox" value="${s.id}"><span>${esc(s.name)}<small class="source-line">${esc(s.url)}</small></span></label>`).join('')||'<p class="form-note">先在右侧添加一个网站或栏目。</p>'}</fieldset><label class="field">关键词或关注主题<input name="query" maxlength="500" placeholder="例如：印度尼西亚 制造业 电力供应" required></label><div class="form-grid"><label class="field">开始日期<input name="date_from" type="date"></label><label class="field">结束日期<input name="date_to" type="date"></label><label class="field">最多返回条数<input name="limit" type="number" min="1" max="20" value="10" required></label></div><p class="form-note">发布时间未知的结果会标明；设置时间范围时不能直接入库。</p><button class="primary" ${config.configured&&sources.items.some(s=>s.enabled)?'':'disabled'}>检索指定网站</button><div id="website-search-error" role="alert"></div></form></section>
    <section class="panel"><div class="panel-heading"><h2>网站来源</h2></div><div class="panel-content"><form id="website-source-form"><input name="id" type="hidden"><label class="field">来源名称<input name="name" maxlength="120" required placeholder="例如：政策公告网站"></label><label class="field">网站或栏目地址<input name="url" type="url" maxlength="2000" required placeholder="https://example.com/news/"></label><p class="form-note">仅包含这个域名和栏目下的链接。其他子域名需要单独添加。</p><label class="check-field"><input name="enabled" type="checkbox" checked>启用来源</label><div class="actions"><button class="secondary">保存来源</button><button class="text-button" type="reset">取消编辑</button></div><div id="website-source-error" role="alert"></div></form><div class="website-source-list">${sources.items.map(s=>`<article><strong>${esc(s.name)}</strong> · ${s.enabled?'已启用':'已停用'}<p>${esc(s.url)}</p><button class="text-button" data-edit-site="${s.id}">编辑</button></article>`).join('')}</div></div></section></div>
    <section class="panel"><div class="panel-heading"><h2>最近检索任务</h2><small>最近30次</small></div>${searches.items.length?`<div class="table-wrap"><table><thead><tr><th>主题与范围</th><th>状态</th><th>结果</th><th>发起时间</th><th>操作</th></tr></thead><tbody>${searches.items.map(t=>`<tr><td><a href="#websites?task=${t.id}">${esc(t.request.query)}</a><span class="source-line">${t.request.sources.map(s=>esc(s.name)).join('、')}</span></td><td>${esc(siteTaskNames[t.status])}</td><td>${t.result_count} 条 · 排除 ${t.rejected} 条</td><td>${when(t.created_at)}</td><td><a href="#websites?task=${t.id}">查看结果</a></td></tr>`).join('')}</tbody></table></div>`:empty('还没有检索任务','配置网站来源后，输入主题开始检索。')}</section>`+
    (detail?websiteResults(detail):'');
}
function websiteResults(detail){
  const t=detail.task,request=t.request;
  return `<section class="panel" id="website-results"><div class="panel-heading"><h2>检索结果 · ${esc(request.query)}</h2><span>${esc(siteTaskNames[t.status])}</span></div><div class="panel-content"><p class="form-note">${esc(request.sources.map(s=>s.url).join('、'))}<br>时间范围：${esc(request.date_from||'不限')} 至 ${esc(request.date_to||'不限')} · ${detail.items.length} 条结果 · ${t.rejected} 条因范围或格式被排除</p>${t.error?errorBox(t.error)+`<button class="secondary" id="website-retry">按原条件重新检索</button>`:''}${['queued','running'].includes(t.status)?'<p role="status">正在等待检索完成，可在此刷新结果。离开页面后任务仍继续。</p>':''}${!detail.items.length&&!['queued','running','failed'].includes(t.status)?'<p>本次没有可展示的匹配资料。未检索到资料不代表没有风险。</p>':''}${detail.items.map(r=>{
    const usable=r.content_status==='ready'&&r.review_status!=='ignored'&&(!(request.date_from||request.date_to)||r.published_date);
    return `<article class="website-result" data-site-result="${r.id}"><h3><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a></h3><p class="source-line">${esc(r.url)}</p><p class="form-note">发布时间：${esc(r.published_date||'未知')} · 采集时间：${when(r.fetched_at)}<br>${esc(siteContentNames[r.content_status])}${r.duplicate?' · 已保存的来源版本':''} · ${r.review_status==='ignored'?'已忽略':r.review_status==='imported'?'已入库':'待确认'}</p>${(request.date_from||request.date_to)&&!r.published_date?'<p class="form-note">无法核实发布时间，请去掉时间范围重新检索后再确认入库。</p>':''}<details><summary>检索摘要（不作为原文证据）</summary><p class="website-body">${esc(r.summary||'未提供摘要')}</p></details>${r.body?`<details><summary>查看来源正文快照</summary><p class="form-note">由检索服务 ${esc(r.provider)} 提供的文本快照；未独立核对网页完整性，请人工核验原始链接。</p><pre class="website-body">${esc(r.body)}</pre></details>`:''}<div class="website-review"><label class="check-field"><input type="checkbox" data-site-external="${r.id}" ${usable?'':'disabled'}>允许将正文发送外部分析模型（含知识库引用）</label><div class="actions"><button class="secondary" data-site-import="${r.id}" data-kind="knowledge" ${usable?'':'disabled'}>加入知识库</button><button class="primary" data-site-import="${r.id}" data-kind="event" ${usable?'':'disabled'}>加入待分析资料</button><button class="text-button" data-site-ignore="${r.id}" ${r.review_status==='pending'?'':'disabled'}>忽略</button></div>${r.documents.map(d=>`<p>${d.kind==='knowledge'?'知识库':'待分析资料'} #${d.document_id} · ${sourceButton(d.document_id,'查看入库原文')}${d.kind==='event'?` · <a href="#documents">前往资料列表分析</a>`:''}</p>`).join('')}<div class="website-result-feedback" role="status"></div></div></article>`;
  }).join('')}</div></section>`;
}
function bindWebsites(){
  const sourceForm=$('#website-source-form');
  sourceForm?.addEventListener('submit',async e=>{
    e.preventDefault();const b=$('button',sourceForm);b.disabled=true;
    const f=new FormData(sourceForm),id=f.get('id');
    try{await api('/websites/sources'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{name:f.get('name'),url:f.get('url'),enabled:f.has('enabled')}});toast('网站来源已保存');await render();}catch(err){$('#website-source-error').innerHTML=errorBox(err.message);b.disabled=false;}
  });
  $$('[data-edit-site]').forEach(b=>b.onclick=()=>{
    const source=state.websiteSources.find(s=>s.id===Number(b.dataset.editSite));
    sourceForm.elements.id.value=source.id;sourceForm.elements.name.value=source.name;sourceForm.elements.url.value=source.url;sourceForm.elements.enabled.checked=Boolean(source.enabled);sourceForm.elements.name.focus();
  });
  $('#website-search-form')?.addEventListener('submit',async e=>{
    e.preventDefault();const form=e.currentTarget,b=$('button',form);b.disabled=true;const f=new FormData(form);
    try{
      const ids=f.getAll('source_ids').map(Number);if(!ids.length)throw new Error('请选择至少一个网站来源。');
      const body={source_ids:ids,query:f.get('query'),limit:Number(f.get('limit')),date_from:f.get('date_from')||null,date_to:f.get('date_to')||null};
      const r=await api('/websites/searches',{method:'POST',body});toast('检索任务已提交');const hash='#websites?task='+r.id;if(location.hash===hash)await render();else location.hash=hash;
    }catch(err){$('#website-search-error').innerHTML=errorBox(err.message);b.disabled=false;}
  });
  $('#website-retry')?.addEventListener('click',async e=>{
    e.currentTarget.disabled=true;const r=state.websiteDetail.task.request;
    try{const result=await api('/websites/searches',{method:'POST',body:{source_ids:r.sources.map(s=>s.id),query:r.query,limit:r.limit,date_from:r.date_from,date_to:r.date_to}});location.hash='#websites?task='+result.id;}catch(err){toast(err.message);e.currentTarget.disabled=false;}
  });
  $$('[data-site-import]').forEach(b=>b.onclick=async()=>{
    b.disabled=true;const id=b.dataset.siteImport,card=b.closest('[data-site-result]');
    try{const r=await api(`/websites/results/${id}/import`,{method:'POST',body:{kind:b.dataset.kind,allow_external:$(`[data-site-external="${id}"]`).checked}});toast(r.created?'资料已入库，可前往资料页面继续处理':'该来源版本已入库，复用已有资料；授权范围保持原设置');await render();}catch(err){$('.website-result-feedback',card).innerHTML=errorBox(err.message);b.disabled=false;}
  });
  $$('[data-site-ignore]').forEach(b=>b.onclick=async()=>{
    b.disabled=true;try{await api(`/websites/results/${b.dataset.siteIgnore}/ignore`,{method:'POST'});await render();}catch(err){toast(err.message);b.disabled=false;}
  });
}
