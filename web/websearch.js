'use strict';
let webSelectedRun=null,webPoll=null,webRunsPoll=null,webSources=[],webEditorOpen=false,webImportOpen=false;
const webFilter={q:'',category:'',page:1},webRunPage={page:1};
function modelStatusText(){return !state.config.configured?'模型待配置':state.config.last_success?'最近模型分析成功':'模型已配置 · 尚无分析记录';}
function webHint(hint){return hint?`<span class="web-hint">${esc(hint)}</span>`:'';}
function webPager(data,kind){
  const pages=Math.max(1,Math.ceil(data.total/data.size));
  if(pages<2)return '';
  return `<div class="web-pager"><button class="secondary small" data-web-page="${kind}:${data.page-1}" ${data.page<=1?'disabled':''}>上一页</button><span>第 ${data.page} / ${pages} 页 · 共 ${data.total} 条</span><button class="secondary small" data-web-page="${kind}:${data.page+1}" ${data.page>=pages?'disabled':''}>下一页</button></div>`;
}
function webSourceCard(s){
  const rate=s.run_count?`成功 ${s.ok_count}/${s.run_count} 次`:'尚未检索';
  const last=s.last_status?`${badge(s.last_status)} <small>${when(s.last_run_at)}</small>`:'';
  return `<article class="web-source ${s.enabled?'':'is-disabled'}"><div><h3>${esc(s.name)}${s.category?`<span class="web-tag">${esc(s.category)}</span>`:''}${s.enabled?'':'<span class="web-tag muted">已停用</span>'}</h3><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a><p>${esc(s.keywords)}</p><small>${s.interval_hours?'每 '+s.interval_hours+' 小时检索 · 下次 '+when(new Date(s.next_run*1000).toISOString()):'手动检索'} · 最多 ${s.max_pages} 页 · ${s.allow_external?'允许外部AI筛选':'尚未授权外部AI'} · ${rate}</small>${last?`<div class="web-last">${last}</div>`:''}${s.last_status==='failed'?webHint(s.last_hint||s.last_error):''}${s.auto_import!=='none'?`<p class="form-note">自动保存至${{knowledge:'知识库',event:'风险资料',both:'知识库和风险资料'}[s.auto_import]}${s.auto_analyze?'，新资料启动风险分析':''}</p>`:''}</div><div class="actions"><button class="primary small" data-web-run="${s.id}" ${s.enabled?'':'disabled'}>开始检索</button><button class="secondary small" data-web-edit="${s.id}">编辑</button><button class="text-button" data-web-toggle="${s.id}" data-enabled="${s.enabled?0:1}">${s.enabled?'停用':'启用'}</button>${s.interval_hours?`<button class="text-button" data-web-pause="${s.id}">暂停定时</button>`:''}<button class="text-button danger" data-web-delete="${s.id}">删除</button></div></article>`;
}
function webRunsPanel(runs){
  return `<div class="panel-heading"><h2>检索记录 <small>${runs.total} 条${runs.active?` · ${runs.active} 条排队或运行中，自动刷新`:''}</small></h2><button class="text-button" id="refresh-web-runs">刷新</button></div>${runs.items.length?`<div class="table-wrap"><table><thead><tr><th>网站</th><th>状态</th><th>页面 / 相关</th><th>开始时间</th><th>操作</th></tr></thead><tbody>${runs.items.map(r=>`<tr data-web-row="${r.id}"><td>${esc(r.name)}<span class="source-line">任务 #${r.id}</span></td><td>${badge(r.status)}${r.error?`<span class="source-line">${esc(r.error)}</span>`:''}${webHint(r.hint)}</td><td>${r.pages} / ${r.relevant}</td><td>${when(r.created_at)}</td><td><button class="secondary small" data-web-detail="${r.id}">查看结果</button></td></tr>`).join('')}</tbody></table></div>${webPager(runs,'runs')}`:empty('尚无检索记录','保存网站后点击“开始检索”。')}`;
}
async function websitePage(){
  const query=new URLSearchParams({q:webFilter.q,category:webFilter.category,page:webFilter.page,size:30});
  const [sources,runs]=await Promise.all([api('/web/sources?'+query),api('/web/runs?page='+webRunPage.page)]);webSources=sources.items;
  const all=sources.groups.reduce((n,g)=>n+g.count,0),filtered=webFilter.q||webFilter.category;
  const closed=all&&!webEditorOpen;
  return heading('网站检索','从指定网站发现相关资料，核验来源后用于知识库和风险预警。','<a class="secondary" href="#knowledge">查看知识库</a><a class="secondary" href="#events?demo=real">查看真实风险</a>')+
    '<ol class="collection-steps"><li><strong>1 配置来源</strong><span>指定网站范围与主题</span></li><li><strong>2 AI筛选</strong><span>查看原文与相关性依据</span></li><li><strong>3 入库与预警</strong><span>保存知识或启动风险分析</span></li></ol>'+
    `<div class="web-workbench ${closed?'editor-closed':''}"><section class="panel"><div class="panel-heading"><h2>指定网站 <small>${all} 个</small></h2><div class="actions"><button class="secondary small" id="open-web-import">批量导入</button><button class="secondary small" id="new-web-source">添加网站</button></div></div>`+
    `<form class="filters web-filters" id="web-source-filter"><label class="search-field">搜索网站<input name="q" value="${esc(webFilter.q)}" placeholder="名称、网址或关键词"></label><label>分组<select name="category"><option value="">全部分组（${all}）</option>${sources.groups.map(g=>`<option value="${esc(g.name)}" ${g.name===webFilter.category?'selected':''}>${esc(g.name||'未分组')}（${g.count}）</option>`).join('')}</select></label><button class="secondary small">筛选</button>${webFilter.category?`<button class="primary small" type="button" id="run-web-group">检索本组已启用网站</button>`:''}</form>`+
    `<div class="panel-content">${sources.items.length?sources.items.map(webSourceCard).join('')+webPager(sources,'sources'):(filtered?empty('没有匹配的网站','调整搜索词或分组。'):empty('先添加一个网站','网站尚未指定。填入公开网站或栏目地址，以及需要关注的关键词；也可以批量导入网址清单。'))}</div></section>`+
    `<section class="panel" id="web-import-panel" ${webImportOpen?'':'hidden'}><div class="panel-heading"><h2>批量导入网站</h2><button class="text-button" type="button" id="close-web-import">收起</button></div><form class="panel-content" id="web-import-sources"><p class="form-note">每行一个网站，用 Tab 或逗号分隔：<strong>分组, 名称, 网址, 关键词</strong>（只有三列时为 名称, 网址, 关键词）。可直接从表格复制粘贴，或选择 JSON / CSV 文件。已存在的网址会自动跳过。</p><label class="field">网址清单<textarea name="text" rows="8" placeholder="一、印尼国内	印尼法律部	https://kemenkum.go.id	peraturan regulation 法规"></textarea></label><label class="field">或选择文件<input type="file" name="file" accept=".json,.csv,.txt,.tsv"></label><div class="form-grid"><label class="field">每次最多访问页面<select name="max_pages"><option value="1">1 页</option><option value="5" selected>5 页</option><option value="10">10 页</option></select></label></div><label class="check-field"><input name="allow_external" type="checkbox"><span>允许将这些网站采集的正文发送至当前配置的外部AI服务进行筛选。</span></label><button class="primary" type="submit">导入</button><div id="web-import-sources-feedback" role="status"></div></form></section>`+
    `<section class="panel" id="web-source-editor" ${closed?'hidden':''}><div class="panel-heading"><h2 id="web-editor-title">添加网站</h2><button class="text-button" type="button" id="close-web-editor">收起配置</button></div><form class="panel-content" id="web-source-form"><input name="source_id" type="hidden"><label class="field">网站名称<input name="name" required maxlength="100" placeholder="例如：政策法规信息源"></label><label class="field">网站或栏目地址<input name="url" type="url" required maxlength="2000" placeholder="https://网站域名/栏目/"></label><label class="field">分组<input name="category" maxlength="60" list="web-groups" placeholder="例如：一、印尼国内"><datalist id="web-groups">${sources.groups.filter(g=>g.name).map(g=>`<option value="${esc(g.name)}">`).join('')}</datalist></label><label class="field">关键词或检索主题<textarea name="keywords" required maxlength="500" rows="3" placeholder="例如：进口限制、劳工政策、原料供应中断"></textarea></label><div class="form-grid"><label class="field">每次最多访问页面<select name="max_pages"><option value="1">1 页</option><option value="5">5 页</option><option value="10" selected>10 页</option><option value="20">20 页</option></select></label><label class="field">检索频率<select name="interval_hours"><option value="0">手动检索</option><option value="6">每 6 小时</option><option value="24">每天</option><option value="168">每周</option></select></label></div><label class="field">检索完成后<select name="auto_import"><option value="none">核验后手动入库</option><option value="knowledge">自动保存至知识库</option><option value="event">自动保存为风险资料</option><option value="both">同时保存知识库和风险资料</option></select></label><label class="check-field"><input name="auto_analyze" type="checkbox"><span>对新入库的风险资料自动启动分析，结果进入风险事件列表。</span></label><label class="check-field"><input name="allow_external" type="checkbox"><span>允许将该网站采集的正文发送至当前配置的外部AI服务进行筛选和分析。</span></label><p class="form-note">只访问此域名及填写的栏目路径，遵守 robots.txt。支持网页、文本和 PDF；直连失败时会尝试备用出口和互联网档案馆快照。美国联邦公报、eCFR、OFAC 制裁名单和世界银行文献会自动改用官方接口（关键词需含英文）。AI每页筛选前6000字符，相关性不等于风险结论。</p><button class="primary" type="submit">保存网站</button><div id="web-source-feedback" role="status"></div></form></section></div>`+
    `<section class="panel" id="web-runs-panel">${webRunsPanel(runs)}</section><section class="panel" id="web-results" aria-live="polite"><div class="panel-content form-note">选择检索记录，查看页面原文与AI筛选依据。</div></section>`+
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
  $$('[data-web-detail]').forEach(b=>b.onclick=async()=>{await showWebRun(Number(b.dataset.webDetail));$('#web-results')?.scrollIntoView({block:'start',behavior:'smooth'});});
  $('#refresh-web-runs').onclick=refreshWebRuns;
  $$('[data-web-page^="runs:"]').forEach(b=>b.onclick=()=>{webRunPage.page=Number(b.dataset.webPage.split(':')[1]);refreshWebRuns();});
}
async function showWebRun(id){
  webSelectedRun=id;clearTimeout(webPoll);
  if(state.route!=='websites')return;
  const target=$('#web-results');
  try{
    const r=await api('/web/runs/'+id);if(state.route!=='websites'||webSelectedRun!==id)return;
    const active=['queued','running'].includes(r.status);
    const row=$('[data-web-row="'+id+'"]');if(row){row.children[1].innerHTML=badge(r.status)+(r.error?'<span class="source-line">'+esc(r.error)+'</span>':'')+webHint(r.hint);row.children[2].textContent=r.items.length+' / '+r.items.filter(p=>p.relevant===1).length;}

    target.innerHTML=`<div class="panel-heading"><h2>${esc(r.config.name)} · 检索 #${r.id}</h2><div class="actions">${badge(r.status)}${active?`<button class="secondary small" id="cancel-web-run">取消检索</button>`:''}</div></div><div class="panel-content"><p class="form-note">已访问 ${r.progress} / 最多 ${r.config.max_pages} 页 · ${esc(r.config.keywords)}${r.model?' · AI模型 '+esc(r.model):''}</p>${active?'<p role="status">正在采集网页并进行AI相关性筛选，可离开页面稍后查看。</p>':''}${r.error?errorBox(r.error)+webHint(r.hint):''}${r.items.length?`<div class="web-result-list">${r.items.map(p=>`<article class="web-result"><div class="web-result-title"><input type="checkbox" name="web-page" value="${p.id}" aria-label="选择 ${esc(p.title)}" ${r.status==='completed'&&p.relevant===1?'':'disabled'}><div><h3>${esc(p.title)}</h3><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.url)}</a></div><span class="badge ${p.relevant===1?'accepted':''}">${p.relevant===null?'待筛选':p.relevant?'相关':'不相关'}</span></div><p>${esc(p.reason)}</p>${p.quote?`<blockquote>${esc(p.quote)}</blockquote>`:''}<div class="web-result-foot"><small>抓取 ${when(p.fetched_at)} · ${p.characters} 字符${Object.keys(p.imports).length?' · 已入库':''}</small><button class="secondary small" data-web-original="${p.id}">查看采集原文</button>${Object.entries(p.imports).map(([kind,doc])=>`<button class="text-button" data-source="${doc}">${kind==='knowledge'?'知识库原文':'分析记录'}</button>`).join('')}</div></article>`).join('')}</div>`:(!active?empty('没有可展示的页面','请查看下方失败原因与处理建议。'):'')}${r.status==='completed'&&r.items.some(p=>p.relevant)?`<form id="web-import-form" class="web-import-bar"><label class="field">选中页面用途<select name="kind"><option value="knowledge">知识库参考资料</option><option value="event">风险分析资料</option><option value="both">两种用途同时保存</option></select></label><label class="check-field"><input type="checkbox" name="analyze"><span>保存后启动风险分析</span></label><button class="primary" type="submit" disabled id="web-import-button">选择相关页面后入库</button><div id="web-import-feedback" role="status"></div></form>`:''}${r.errors.length?`<details class="web-errors" ${r.items.length?'':'open'}><summary>${r.errors.length} 个页面未采集成功</summary>${r.errors.map(e=>`<p><strong>${esc(e.error)}</strong>${webHint(e.hint)}<br>${esc(e.url)}</p>`).join('')}</details>`:''}</div>`;
    $('#cancel-web-run')?.addEventListener('click',async()=>{try{await api('/web/runs/'+id+'/cancel',{method:'POST'});await showWebRun(id);}catch(e){toast(e.message);}});
    $$('[data-web-original]').forEach(b=>b.onclick=async()=>{try{const p=await api('/web/pages/'+b.dataset.webOriginal);$('#source-content').innerHTML=`<h2>${esc(p.title)}</h2><p>${esc(p.url)} · 抓取 ${when(p.fetched_at)}</p><div class="source-body">${esc(p.body)}</div>`;$('#source-dialog').showModal();}catch(e){toast(e.message);}});
    $$('[data-source]',target).forEach(b=>b.onclick=()=>showSource(b.dataset.source));
    const importKind=$('#web-import-form [name=kind]'),importAnalyze=$('#web-import-form [name=analyze]');
    if(importKind&&importAnalyze){const sync=()=>{importAnalyze.disabled=importKind.value==='knowledge';if(importAnalyze.disabled)importAnalyze.checked=false;};importKind.onchange=sync;sync();}
    $$('[name=web-page]',target).forEach(c=>c.onchange=()=>{const n=$$('[name=web-page]:checked',target).length;const b=$('#web-import-button');if(b){b.disabled=!n;b.textContent=n?`保存 ${n} 个页面`:'选择相关页面后入库';}});
    $('#web-import-form')?.addEventListener('submit',async e=>{e.preventDefault();const f=new FormData(e.currentTarget),b=$('#web-import-button');b.disabled=true;try{const result=await api('/web/import',{method:'POST',body:{page_ids:$$('[name=web-page]:checked',target).map(c=>Number(c.value)),kind:f.get('kind'),analyze:f.has('analyze')}});toast(`已保存 ${result.items.filter(i=>i.created).length} 条资料，重复内容不会新增${result.items.some(i=>i.job_id)?'；风险分析已排队':''}`);await showWebRun(id);}catch(error){$('#web-import-feedback').innerHTML=errorBox(error.message);b.disabled=false;}});
    if(active)webPoll=setTimeout(()=>showWebRun(id),3000);
  }catch(error){if(target)target.innerHTML=errorBox(error.message);}
}
function bindWebsite(){
  if(state.route!=='websites'){clearTimeout(webPoll);clearTimeout(webRunsPoll);return;}
  const form=$('#web-source-form');
  const fresh=()=>{form.reset();form.elements.source_id.value='';$('#web-editor-title').textContent='添加网站';$('#web-source-feedback').innerHTML='';};
  const openEditor=()=>{webEditorOpen=true;$('#web-source-editor').hidden=false;$('.web-workbench').classList.remove('editor-closed');};
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
      for(let i=0;i<items.length;i+=500){const r=await api('/web/sources/import',{method:'POST',body:{items:items.slice(i,i+500),max_pages:Number(f.elements.max_pages.value),allow_external:f.elements.allow_external.checked}});created+=r.created;skipped+=r.skipped;errors=errors.concat(r.errors.map(x=>({...x,row:x.row+i})));}
      toast(`已导入 ${created} 个网站，跳过重复 ${skipped} 个${errors.length?`，${errors.length} 个网址无效`:''}`);
      webImportOpen=!!errors.length;await render();
      if(errors.length)$('#web-import-sources-feedback').innerHTML=errorBox(errors.map(x=>`第 ${x.row} 行 ${x.url}：${x.error}`).join('；'));
    }catch(error){out.innerHTML=errorBox(error.message);b.disabled=false;}
  };
  $('#web-source-filter').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);webFilter.q=String(f.get('q')||'').trim();webFilter.category=String(f.get('category')||'');webFilter.page=1;render();};
  $('#web-source-filter [name=category]').onchange=e=>{webFilter.category=e.target.value;webFilter.page=1;render();};
  $('#run-web-group')?.addEventListener('click',async e=>{const b=e.currentTarget;if(!confirm(`对“${webFilter.category}”分组中已启用、已授权外部AI的网站逐个排队检索？`))return;b.disabled=true;try{const r=await api('/web/runs/group',{method:'POST',body:{category:webFilter.category}});toast(`已排队 ${r.queued} 个检索任务，将依次执行`);await render();}catch(error){toast(error.message);b.disabled=false;}});
  $$('[data-web-page^="sources:"]').forEach(b=>b.onclick=()=>{webFilter.page=Number(b.dataset.webPage.split(':')[1]);render();});
  $$('[data-web-edit]').forEach(b=>b.onclick=()=>{openEditor();const s=webSources.find(s=>s.id===Number(b.dataset.webEdit));for(const key of ['name','url','keywords','max_pages','interval_hours','auto_import','category'])form.elements[key].value=s[key]??'';for(const key of ['allow_external','auto_analyze'])form.elements[key].checked=!!s[key];form.elements.source_id.value=s.id;$('#web-editor-title').textContent='编辑网站';form.scrollIntoView({block:'start',behavior:'smooth'});form.elements.name.focus();});
  form.onsubmit=async e=>{e.preventDefault();const f=new FormData(form),id=f.get('source_id'),b=$('[type=submit]',form);b.disabled=true;try{await api('/web/sources'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{name:f.get('name'),url:f.get('url'),category:f.get('category')||'',keywords:f.get('keywords'),max_pages:Number(f.get('max_pages')),interval_hours:Number(f.get('interval_hours')),auto_import:f.get('auto_import'),auto_analyze:f.has('auto_analyze'),allow_external:f.has('allow_external')}});toast('网站配置已保存');webEditorOpen=false;await render();}catch(error){$('#web-source-feedback').innerHTML=errorBox(error.message);b.disabled=false;}};
  $$('[data-web-run]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await api('/web/runs',{method:'POST',body:{source_id:Number(b.dataset.webRun)}});webSelectedRun=r.id;await render();}catch(error){toast(error.message);b.disabled=false;}});
  $$('[data-web-toggle]').forEach(b=>b.onclick=async()=>{try{await api('/web/sources/'+b.dataset.webToggle+'/toggle',{method:'POST',body:{enabled:b.dataset.enabled==='1'}});toast(b.dataset.enabled==='1'?'网站已启用':'网站已停用，不再参与定时和分组检索');await render();}catch(error){toast(error.message);}});
  $$('[data-web-delete]').forEach(b=>b.onclick=async()=>{const s=webSources.find(s=>s.id===Number(b.dataset.webDelete));if(!confirm(`删除网站“${s?.name||''}”？已有的检索记录和入库资料会保留。`))return;try{await api('/web/sources/'+b.dataset.webDelete,{method:'DELETE'});toast('网站已删除');await render();}catch(error){toast(error.message);}});
  $$('[data-web-pause]').forEach(b=>b.onclick=async()=>{try{await api('/web/sources/'+b.dataset.webPause+'/pause',{method:'POST'});toast('定时检索已暂停，当前任务如需停止请点击取消');await render();}catch(error){toast(error.message);}});
  bindWebRuns();
  clearTimeout(webRunsPoll);if($('#web-runs-active'))webRunsPoll=setTimeout(refreshWebRuns,5000);
  if(webSelectedRun)showWebRun(webSelectedRun);
}
