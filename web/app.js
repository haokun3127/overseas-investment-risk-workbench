'use strict';
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Reading copies omit preparation markers; API bodies, quotes and data-quote
// attributes retain the original text used for source verification.
function readingText(value) {
  return String(value ?? '').replace(/[ \t]*[〔［【\[]\s*S\d+\s*[〕］】\]]/g,'');
}
const readingEsc = value => esc(readingText(value));

const RISK_TREE = [
  ['政治风险', [['政治稳定', ['政权更迭', '军事政变', '战争及内乱']], ['政府行为风险', ['政府征收和国有化风险', '汇兑限制', '政府腐败']], ['政府违约风险', ['中止/终止特许经营权', '财政偿债能力不足', '东道国违反合同风险']], ['国际关系风险', ['东道国被其他国家或国际组织制裁风险', '对华友好度', '地缘政治与大国博弈']]]],
  ['法律风险', [['法律环境风险', ['法律政策变动', '法律透明度', '法律制度健全性']], ['外资管理风险', ['准入审批限制风险', '安全审查风险', '反垄断审查风险']], ['执法风险', ['执法效率', '执法力度']], ['司法风险', ['司法公平', '司法效率', '执行风险']], ['合规风险', ['腐败风险', '人权风险', '违反东道国其他法律被处罚', '与被制裁企业交易', '跨境数据流动']], ['合同风险', ['合同执行风险', '法律救济与适用风险']], ['知识产权风险', ['知识产权保护风险', '知识产权纠纷风险']]]],
  ['社会风险', [['劳工风险', ['劳工组织维权风险', '劳工诉讼风险', '聘用当地或外籍员工要求']], ['环境保护风险', ['环保抗议风险', '环保诉讼风险', '环境行政审查风险']], ['宗教文化风险', ['宗教冲突风险', '文化冲突风险']], ['社会治安风险', ['社会动乱风险', '刑事犯罪风险']], ['重大公共卫生风险', ['人员流动性限制', '经济贸易限制', '其他限制性措施']]]],
];
function placeOf(category) {
  for (const [family, groups] of RISK_TREE) {
    for (const [group, items] of groups) {
      if (items.includes(category)) return { family, group };
    }
  }
  return { family: '', group: '' };
}
function familyOf(category) {
  return placeOf(category).family;
}
function riskPath(category) {
  const place = placeOf(category);
  if (!place.family) return '';
  return `${place.family} › ${place.group}`;
}
function riskTreeRow(level, label, name, countText, href) {
  const inner = `<span class="risk-level-tag">${label}</span><span class="risk-tree-name">${esc(name)}</span><span class="risk-tree-count">${countText}</span>`;
  if (href) return `<a class="risk-tree-row lv${level}" href="${href}">${inner}</a>`;
  return `<div class="risk-tree-row lv${level}">${inner}</div>`;
}
function riskTreeOverview(categories) {
  const counts = Object.fromEntries((categories || []).map((item) => [item.category, Number(item.count) || 0]));
  const seen = new Set();
  let hitGroups = 0;
  let hitLeaves = 0;
  let total = 0;
  const rows = [];
  RISK_TREE.forEach(([family, groups]) => {
    const blocks = [];
    let familyCount = 0;
    groups.forEach(([group, items]) => {
      const leaves = items.filter((name) => counts[name]).map((name) => {
        seen.add(name);
        return { name, count: counts[name] };
      });
      if (!leaves.length) return;
      const groupCount = leaves.reduce((sum, item) => sum + item.count, 0);
      familyCount += groupCount;
      total += groupCount;
      hitGroups += 1;
      hitLeaves += leaves.length;
      blocks.push({ group, groupCount, leaves });
    });
    if (!familyCount) {
      rows.push(`<div class="risk-tree-row lv1 is-empty"><span class="risk-level-tag">一级</span><span class="risk-tree-name">${esc(family)}</span><span class="risk-tree-count">0 条 · 暂无事件</span></div>`);
      return;
    }
    rows.push(riskTreeRow(1, '一级', family, `${familyCount} 条`));
    blocks.forEach((block) => {
      rows.push(riskTreeRow(2, '二级', block.group, `${block.groupCount} 条`));
      block.leaves.forEach((leaf) => {
        rows.push(riskTreeRow(3, '三级', leaf.name, `${leaf.count} 条`, eventHref({ category: leaf.name })));
      });
    });
  });
  const extra = Object.entries(counts).filter(([name, count]) => count && !seen.has(name));
  if (extra.length) {
    const extraCount = extra.reduce((sum, [, count]) => sum + count, 0);
    total += extraCount;
    hitLeaves += extra.length;
    rows.push(riskTreeRow(1, '一级', '未归类', `${extraCount} 条`));
    extra.forEach(([name, count]) => {
      rows.push(riskTreeRow(3, '三级', name, `${count} 条`, eventHref({ category: name })));
    });
  }
  const summary = `${RISK_TREE.length} 个一级 · 命中 ${hitGroups} 个二级 · ${hitLeaves} 个三级 · 共 ${total} 条`;
  return { summary, html: `<div class="risk-tree">${rows.join('')}</div>` };
}
function familyOptions() {
  const selected = state.filter.family || '';
  const items = RISK_TREE.map(([name]) => `<option value="${esc(name)}" ${selected === name ? 'selected' : ''}>${esc(name)}</option>`).join('');
  return `<option value="">全部一级</option>${items}`;
}
function categoryOptions(counts = {}) {
  const known = new Set(RISK_TREE.flatMap(([, groups]) => groups.flatMap(([, items]) => items)));
  const selected = state.filter.category || '';
  const family = state.filter.family || '';
  const extra = [...new Set([...(state.config?.rules?.categories || []), selected].filter((name) => name && !known.has(name)))];
  const option = (name) => `<option value="${esc(name)}" ${selected === name ? 'selected' : ''}>${esc(name)}（${Number(counts[name] || 0)}）</option>`;
  const trees = family ? RISK_TREE.filter(([name]) => name === family) : RISK_TREE;
  const groups = trees.map(([fam, groups]) => groups.map(([group, items]) => `<optgroup label="${esc(`${fam} · ${group}`)}">${items.map(option).join('')}</optgroup>`).join('')).join('');
  const legacy = !family && extra.length ? `<optgroup label="此前分类">${extra.map(option).join('')}</optgroup>` : '';
  return `<option value="">全部类型</option>${groups}${legacy}`;
}
const names = {overview:'风险总览',events:'风险事件',documents:'资料与分析',evidence:'待补证',updates:'网站更新待办',websites:'网站检索',knowledge:'知识库',consultation:'咨询问答',jobs:'资料与分析',settings:'模型与规则',report:'风险简报',countermeasures:'分级对策库'};
const levels = {
  lv1: '红色风险',
  lv2: '黄色风险',
  lv3: '蓝色风险',
};
const legacyLevels = {
  lv4: '灰色预警（旧标准）',
  lv5: '绿色预警（旧标准）',
  red: '高风险（旧标准）',
  orange: '中风险（旧标准）',
  yellow: '一般关注（旧标准）',
};
const levelLabels = { ...levels, ...legacyLevels, non_risk:'绿色 · 无风险' };
const levelOrder = [...Object.keys(levels), ...Object.keys(legacyLevels)];
const levelRank = (level) => (levelOrder.includes(level) ? levelOrder.indexOf(level) : levelOrder.length);
const statuses = {pending:'待复核',accepted:'已认可',needs_change:'需修正',queued:'排队中',running:'分析中',completed:'已完成',failed:'失败',cancelled:'已取消',risk:'发现风险',non_risk:'未发现风险',insufficient:'证据不足'};
const state = {config:null,scope:'all',page:1,route:'overview',importMode:'file',filter:{},renderId:0,renderAbort:null,renderSignal:null,kq:'',ki:0};
let toastTimer;
function toast(message){$('#notice').textContent=message;$('#notice').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#notice').hidden=true,4500);}
const API_TIMEOUT_MS=30000;
function apiSignal(extra, timeoutMs){
  const timeout=AbortSignal.timeout(timeoutMs);
  const parts=[timeout];
  if(extra)parts.push(extra);
  else if(state.renderSignal)parts.push(state.renderSignal);
  return parts.length===1?parts[0]:AbortSignal.any(parts);
}
async function api(path, {timeoutMs=API_TIMEOUT_MS,...options}={}){
  const headers={'X-Requested-With':'risk-workbench',...(options.headers||{})};
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  let response;
  try{response=await fetch('api'+path,{...options,headers,signal:apiSignal(options.signal,timeoutMs)});}
  catch(e){
    if(e.name==='AbortError')throw e;
    throw new Error(e.name==='TimeoutError'?'请求超时。操作可能已被接收，请刷新列表确认后再重试。':'无法连接本地服务，请检查服务是否启动，再重试。');
  }
  const data=await response.json().catch(()=>({detail:'服务响应无法读取。'}));
  if(!response.ok){
    if(response.status===401 && !path.startsWith('/auth/')){
      const main=$('#main');
      if(main?.querySelector('.loading'))main.innerHTML='';
      await boot();
    }
    const detail=Array.isArray(data.detail)?'输入内容格式不正确，请检查必填字段和长度。':data.detail;
    const error=new Error(detail||'请求失败，请稍后重试。');
    error.status=response.status;
    throw error;
  }
  return presentationData(data);
}
function badge(value){return `<span class="badge ${esc(value)}">${esc(levelLabels[value]||statuses[value]||value||'未分析')}</span>`;}

// Demo records are shown as they are, labelled, so they are never mistaken for real business data.
function presentationData(value){return value;}

// Analysis is refused until the client's classification rules are confirmed: say so where work starts.
function rulesAlert(){return state.config?.rules?.confirmed?'':'<div class="setup-alert" role="alert"><div><strong>风险分类分级规则尚未确认</strong><span>规则确认前，所有风险分析都无法启动，网站检索结果也不能“保存后分析”。资料导入、网站检索和知识库不受影响。</span></div><a class="primary small" href="#settings">去确认规则</a></div>';}
function demoTag(demo){return demo?'<span class="badge demo-tag" title="内置虚构演示数据，不是真实风险">演示</span>':'';}
function when(date){return date?new Date(date).toLocaleString('zh-CN',{hour12:false}):'—';}
function errorBox(message){return `<div class="error" role="alert">${esc(message)}</div>`;}
function icon(name){return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;}
const eyebrows={风险事件:'RISK LEDGER · 逐条核验',资料与分析:'INTAKE · 资料研判',知识库:'ARCHIVE · 法规与案例',网站检索:'WATCH · 公开来源采集',风险简报:'BRIEFING · 对外简报',模型与规则:'CONFIG · 模型与规则',分析任务:'QUEUE · 后台任务'};
function stamp(){return new Date().toLocaleString('zh-CN',{hour12:false,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
function heading(title,subtitle,actions='',showEyebrow=false){
  const eyebrow=title==='风险总览'?`INDONESIA · 海外投资风险研判 · 页面刷新 ${stamp()}`:(eyebrows[title]||'WORKBENCH');
  return `<div class="page-heading"><div>${showEyebrow?`<div class="page-eyebrow"><span class="label-dot" aria-hidden="true"></span>${eyebrow}</div>`:''}<h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${actions}</div></div>`;
}
function scopeValue(){return ['all','real','demo'].includes(state.scope)?state.scope:'all';}
function eventHref(filter={}){return '#events?'+new URLSearchParams({...filter,demo:scopeValue()});}
function openEvents(filter={}){const target=eventHref(filter);if(location.hash===target)render();else location.hash=target;}
function severityChart(stats,count){
  let offset=0;
  const legendLevels=[...Object.keys(levels),...Object.keys(legacyLevels).filter(v=>count[v])];
  const ringLevels=legendLevels.filter((level) => count[level]);
  const segments=ringLevels.map((level) => {
    const amount=count[level]||0,percent=stats.total?amount/stats.total*100:0;
    const segment=percent?`<circle class="ring-segment ${level}" cx="92" cy="92" r="70" pathLength="100" stroke-dasharray="${percent} ${100-percent}" stroke-dashoffset="${-offset}"/>`:'';
    offset+=percent;return segment;
  }).join('');
  return `<div class="severity-chart"><svg viewBox="0 0 184 184" class="severity-ring" role="img" aria-label="${legendLevels.map((v)=>`${levelLabels[v]}${count[v]||0}条`).join('，')}"><circle class="ring-track" cx="92" cy="92" r="70"/>${segments}<circle class="ring-inner" cx="92" cy="92" r="53"/><text x="92" y="94" class="ring-total">${stats.total}</text><text x="92" y="117" class="ring-caption">风险事件</text></svg><div class="severity-legend">${legendLevels.map((v)=>`<a href="${eventHref({level:v})}" class="legend-row"><span class="dot ${v}"></span><span>${levelLabels[v]}</span><strong>${count[v]||0}<small> 条</small></strong></a>`).join('')}</div></div>`;
}
function categoryNetwork(stats){
  if(!stats.categories.length)return empty('等待第一条风险信号','完成分析后，这里会展示风险类型及对应事件。','<a class="secondary" href="#documents">导入资料</a>');
  // Reserve the lower-right node for the actual "other" category, regardless of count.
  const other=stats.categories.find(c=>['其他','对不上'].includes(c.category));
  const nodes=other?[...stats.categories.filter(c=>c!==other).slice(0,5),other]:stats.categories.slice(0,6);
  const mobilePositions=nodes.map((c,i)=>({x:c===other||i%2?188:8,y:154+Math.floor(i/2)*66}));
  const mobileGraph=`<svg class="signal-network-mobile" viewBox="0 0 360 ${174+Math.ceil(nodes.length/2)*66}" role="group" aria-label="风险类型分布，点击类型查看事件"><circle class="network-core" cx="180" cy="65" r="57"/><text x="180" y="58" class="network-total">${stats.total}</text><text x="180" y="82" class="network-caption">已识别风险</text><path class="network-link" d="M180 122 V${mobilePositions.at(-1).y+27}"/>${nodes.map((c,i)=>{const p=mobilePositions[i];return `<path class="network-link" d="M180 ${p.y+27} H${p.x<180?p.x+164:p.x}"/><a href="${eventHref({category:c.category})}" aria-label="${esc(c.category)} ${c.count} 条风险事件"><rect class="network-focus" x="${p.x-4}" y="${p.y-4}" width="172" height="64" rx="11"/><rect class="network-node" x="${p.x}" y="${p.y}" width="164" height="56" rx="8"/><text class="network-label" x="${p.x+12}" y="${p.y+23}">${esc(c.category.length>9?c.category.slice(0,8)+'…':c.category)}</text><text class="network-count" x="${p.x+12}" y="${p.y+43}">${c.count} 条风险事件</text></a>`;}).join('')}</svg>`;
  const rows=Math.ceil(nodes.length/2),step=rows===2?118:86;
  const positions=nodes.map((c,i)=>({x:c===other||i%2?425:15,y:100+(Math.floor(i/2)-(rows-1)/2)*step}));
  const links=positions.map(p=>`<path class="network-link" pathLength="1" d="M300 127 C${p.x<300?220:380} 127 ${p.x<300?225:375} ${p.y+27} ${p.x<300?p.x+160:p.x} ${p.y+27}"/>`).join('');
  return `<div class="signal-canvas"><svg class="signal-network" viewBox="0 0 600 252" role="group" aria-label="风险类型与事件数量，点击类型筛选事件"><defs><pattern id="signal-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7"/></pattern><radialGradient id="core-glow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#7ee8dc" stop-opacity=".42"/><stop offset=".55" stop-color="#0f8a86" stop-opacity=".16"/><stop offset="1" stop-color="#0a1322" stop-opacity="0"/></radialGradient><linearGradient id="core-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d3a55"/><stop offset="1" stop-color="#0d1a2e"/></linearGradient></defs><rect class="network-grid" width="600" height="252" fill="url(#signal-grid)"/><circle class="network-halo" cx="300" cy="127" r="124" fill="url(#core-glow)"/><ellipse class="network-orbit" cx="300" cy="127" rx="101" ry="101"/><ellipse class="network-orbit" cx="300" cy="127" rx="80" ry="80"/>${links}<circle class="network-core" cx="300" cy="127" r="60"/><text x="300" y="117" class="network-total">${stats.total}</text><text x="300" y="142" class="network-caption">已识别风险</text><text x="300" y="159" class="network-unit">当前数据范围</text>${nodes.map((c,i)=>{const p=positions[i];return `<a href="${eventHref({category:c.category})}" aria-label="${esc(c.category)} ${c.count} 条风险事件"><rect class="network-focus" x="${p.x-5}" y="${p.y-5}" width="170" height="64" rx="12"/><rect class="network-node" x="${p.x}" y="${p.y}" width="160" height="54" rx="8"/><circle class="network-port" cx="${p.x<300?p.x+160:p.x}" cy="${p.y+27}" r="3"/><text class="network-label" x="${p.x+14}" y="${p.y+23}">${esc(c.category.length>9?c.category.slice(0,8)+'…':c.category)}</text><text class="network-count" x="${p.x+14}" y="${p.y+42}">${c.count} 条风险事件</text></a>`;}).join('')}</svg>${mobileGraph}<div class="network-mobile-list">${stats.categories.map(c=>`<a href="${eventHref({category:c.category})}"><span>${esc(c.category)}</span><strong>${c.count}<small> 条</small></strong></a>`).join('')}</div></div><div class="chart-footnote"><span>${stats.categories.length} 个风险类型${stats.categories.length>6?' · 图示数量最多的6类':''}</span><a href="${eventHref()}">查看分类事件 ${icon('arrow')}</a></div>`;
}
function sourceButton(id,label='查看原文',quote=''){return `<button class="text-button source-action" data-source="${id}" data-quote="${esc(quote)}">${icon('source')}${label}</button>`;}
function empty(title,description,actions=''){return `<div class="empty"><span class="empty-symbol" aria-hidden="true">${icon('documents')}</span><h2>${title}</h2><p>${description}</p><div class="actions">${actions}</div></div>`;}
function scope(){
  if(state.auth?.role==='company'){
    return `<div class="scope-bar"><span class="muted">统计范围：本公司 · ${esc(state.company?.name||state.auth.company_name||'未命名公司')}</span></div>`;
  }
  const count=state.overviewScope?.company_count;
  const label=state.company?esc(state.company.name):`全部公司${count!=null?`（${count} 家）`:''}`;
  return `<div class="scope-bar"><span class="muted">统计范围：${label}</span></div>`;
}
// Overview keeps scope and company background in one compact strip; the full company panel lives in its popover.
function scopeStrip(withDemo) {
  const company = state.auth?.role === 'company';
  const count = state.overviewScope?.company_count;
  const scopeText = company
    ? `本公司 · ${esc(state.company?.name || state.auth.company_name || '未命名公司')}`
    : state.company?esc(state.company.name):`全部公司${count != null ? `（${count} 家）` : ''}`;
  const background = '';
  const pickerLabel = company ? '本公司档案' : (state.company ? '更换公司' : '选择公司');
  const demo = withDemo
    ? `<details class="scope-picker scope-demo"><summary><span class="scope-demo-dot" aria-hidden="true"></span>含演示数据</summary><div class="scope-popover scope-tip">${demonstration()}</div></details>`
    : '';
  return `<div class="scope-strip" role="group" aria-label="统计范围与分析背景"><span class="scope-item"><span class="scope-key">统计范围</span><strong>${scopeText}</strong></span>${background}`
    + `<details class="scope-picker"><summary>${pickerLabel}<svg class="icon" aria-hidden="true"><use href="#i-arrow"/></svg></summary><div class="scope-popover" data-company-host></div></details>${demo}</div>`;
}
function kpiCell({ level = '', href, label, value, note, share, shareLabel }) {
  const dot = level ? `<span class="dot ${level}"></span>` : `${icon('source')}`;
  return `<a class="stat ${level || 'total-stat'}" href="${href}"><div class="stat-label">${dot}<span>${label}</span><span class="stat-share-label">${shareLabel}</span></div>`
    + `<div class="stat-number"><span class="stat-value" data-count="${value}">${value}</span><span>条</span></div><small>${note}</small>`
    + `<span class="stat-share" aria-hidden="true"><span data-share="${share}"></span></span></a>`;
}
function dateLabel(item={}){
  const source=item.date_source||'';
  const value=item.date||'';
  if(!value){
    if(item.date_note)return item.date_note;
    if(item.source==='公司信息档案'||String(item.title||'').startsWith('公司档案'))return '公司档案无独立发布日期';
    return item.url||item.method||source==='publication'?'原文未标明发布日期':'资料日期未标注';
  }
  if(source==='legacy')return `资料日期 ${value}（历史数据，来源未核实）`;
  if(source==='provided')return `资料日期 ${value}（录入）`;
  if(source==='feed')return `发布日期 ${value}（RSS）`;
  if(source==='api')return `发布日期 ${value}（官方接口）`;
  if(source==='page_meta')return `发布日期 ${value}（页面元数据）`;
  if(source==='page_text')return `发布日期 ${value}（正文）`;
  if(source==='document_text')return `资料日期 ${value}（正文）`;
  if(source==='document_signature')return `落款日期 ${value}（原文）`;
  if(source==='document_dispatch')return `送达日期 ${value}（原文）`;
  if(source==='disclosure_path')return `披露日期 ${value}（官方披露路径）`;
  if(source==='publication')return `发布日期 ${value}（原文）`;
  if(source==='archive')return `存档日期 ${value}（网页存档）`;
  return `资料日期 ${value}（来源未注明）`;
}
function dateStamp(item = {}) {
  const label = dateLabel(item);
  if (!item.date) {
    return `<span class="date-stamp is-empty">${esc(label)}</span>`;
  }
  const [, kind = '', source = ''] = label.match(/^(\S+)\s\S+?(?:（(.+)）)?$/) || [];
  return `<span class="date-stamp" title="${esc(label)}"><time datetime="${esc(item.date)}">${esc(item.date)}</time>`
    + `<small>${esc(kind)}${source ? ` · ${esc(source)}` : ''}</small></span>`;
}
function evidenceLabel(r) {
  return String(r.reference || '').startsWith('K') ? `知识库：${r.title || '参考资料'}` : '输入资料片段';
}
function updateIdentity() {
  $$('[data-nav]').forEach(a=>{if(!['overview','events'].includes(a.dataset.nav))a.hidden=state.auth?.role==='company';});
  const userMark = $('.user-mark');
  if (!userMark || state.auth?.role !== 'admin') {
    return;
  }
  const background = state.company?.name || '全部企业';
  userMark.textContent = '系统管理员';
  userMark.title = `当前登录身份：系统管理员；当前企业范围：${background}`;
  const workspaceLabel=$('#workspace-label');
  if(workspaceLabel)workspaceLabel.innerHTML=`管理员<small>${esc(background)}</small>`;
}
function demonstration(){return '<p class="demo-note" role="note">当前结果包含标有“演示”的内置虚构数据，不是真实风险。风险简报默认不纳入演示数据；不再需要时可在<a href="#settings">模型与规则</a>中一键清除。</p>';}
function pagination(data){return `<div class="pagination"><span>共 ${data.total} 条 · 第 ${data.page} / ${Math.max(1,Math.ceil(data.total/data.page_size))} 页</span><div class="actions"><button class="secondary small" data-page="${data.page-1}" ${data.page<=1?'disabled':''}>上一页</button><button class="secondary small" data-page="${data.page+1}" ${data.page*data.page_size>=data.total?'disabled':''}>下一页</button></div></div>`;}
function tableEvents(items, compact = false) {
  const typeHead = compact ? '' : '<th>风险类型</th>';
  const rows = items.map((event) => {
    const path = riskPath(event.category);
    const underTitle = compact && path ? `<span class="risk-path">${esc(path)} › ${esc(event.category)}</span>` : '';
    const typeCell = compact ? '' : `<td class="risk-type-cell"><span class="risk-leaf">${esc(event.category)}</span>${path ? `<span class="risk-path">${esc(path)}</span>` : ''}</td>`;
    return `<tr><td class="title-cell"><a class="event-link" href="#event/${event.id}">${esc(event.title)}</a>${demoTag(event.demo)}<span class="source-line">${esc(event.source || '来源未填写')}</span>${underTitle}</td><td>${badge(event.level)}</td>${typeCell}<td>${badge(event.review_status)}</td><td class="date-cell">${dateStamp(event)}</td></tr>`;
  }).join('');
  return `<div class="table-wrap"><table><thead><tr><th>风险事件</th><th>等级</th>${typeHead}<th>复核状态</th><th>资料日期（来源）</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
const authCopy = {
  company: { sub: '登录后仅显示贵司的资料、任务与风险事件。', submit: '登录企业工作区' },
  admin: { sub: '管理全部公司、全局网站来源、规则与模型配置。', submit: '以管理员身份登录' },
};
function loginRole() {
  try {
    return localStorage.getItem('loginRole') === 'admin' ? 'admin' : 'company';
  } catch (_error) {
    return 'company';
  }
}
function rememberLoginRole(role) {
  try {
    localStorage.setItem('loginRole', role);
  } catch (_error) {
    // 存储不可用时只影响下次默认身份
  }
}
function renderAuthShell() {
  const host = $('#auth');
  host.hidden = false;
  const existing = $('.auth-panel', host);
  if (existing) {
    $('.auth-split', host).classList.remove('is-entering');
    return existing;
  }
  const fact = (no, text) => `<li><span class="auth-fact-no">${no}</span><span>${text}</span></li>`;
  host.innerHTML = '<div class="auth-split is-entering">' +
    '<aside class="auth-brand-panel" aria-label="产品说明" data-stage="static">' +
    '<div class="auth-stage-field" aria-hidden="true"><span class="auth-lamp"></span><span class="auth-iso"></span></div>' +
    `<div class="auth-logo"><span class="auth-logo-mark">${icon('mark')}</span><span class="auth-logo-word">海外投资风险分析工作台</span></div>` +
    '<div class="auth-pitch">' +
    '<h2 class="auth-headline"><span class="auth-line"><span>从风险信号</span></span><span class="auth-line"><span class="auth-gild">到判断依据</span></span></h2>' +
    '<p class="auth-lede">查看企业风险、核验原文依据并记录复核结果，让每一次分析可追溯。</p>' +
    `<ul class="auth-facts">${fact('01', '每条风险都能追溯到原文')}${fact('02', '分析结论需经业务复核')}${fact('03', '资料与结果保存在工作台服务器')}</ul></div>` +
    '</aside>' +
    '<div class="auth-main"><section class="auth-panel" aria-labelledby="auth-title"></section></div></div>';
  const split = $('.auth-split', host);
  setTimeout(() => split.classList.remove('is-entering'), 1200);
  document.body.dataset.route = 'auth';
  window.Stage?.mount($('.auth-brand-panel', host));
  window.Motion?.spotlight($('.auth-panel', host));
  return $('.auth-panel', host);
}
function passwordField({ id, name, label, minlength, autocomplete, className = '' }) {
  return `<div class="field${className ? ` ${className}` : ''}"><label for="${id}">${label}</label>` +
    `<span class="auth-password"><input id="${id}" type="password" name="${name}" minlength="${minlength}" maxlength="128" autocomplete="${autocomplete}" aria-describedby="${id}-caps" required>` +
    `<button type="button" class="auth-reveal" aria-controls="${id}" aria-pressed="false" aria-label="显示密码">${icon('eye')}</button></span>` +
    `<p class="auth-caps" id="${id}-caps" hidden>大写锁定已开启</p></div>`;
}
function authTabs(isRegister) {
  return '<p class="form-note">公司账号由管理员开通并绑定所属企业。</p>';
}
function loginFormHtml(role) {
  const admin = role === 'admin';
  return '<form id="login-form">' +
    '<div class="auth-role auth-rise" role="group" aria-label="登录身份">' +
    `<button type="button" data-login-role="company" aria-pressed="${!admin}">企业账号</button>` +
    `<button type="button" data-login-role="admin" aria-pressed="${admin}">系统管理员</button></div>` +
    `<label class="field auth-rise" data-username-field${admin ? ' hidden' : ''}>企业登录账号<input name="username" maxlength="60" placeholder="输入企业账号" autocomplete="username" required${admin ? ' disabled' : ''}></label>` +
    passwordField({ id: 'auth-password', name: 'password', label: '登录密码', minlength: 8, autocomplete: 'current-password', className: 'auth-rise' }) +
    '<div id="auth-error" role="alert"></div>' +
    `<button class="primary auth-submit auth-rise" type="submit">${authCopy[role].submit}</button></form>` +
    '<p class="auth-note auth-rise">登录有效期为8小时；不同企业账号之间资料、任务与风险事件严格隔离。</p>';
}
function setupFormHtml() {
  return '<form id="login-form">' +
    passwordField({ id: 'auth-password', name: 'password', label: '设置密码（至少10位）', minlength: 10, autocomplete: 'new-password', className: 'auth-rise' }) +
    passwordField({ id: 'auth-confirm', name: 'confirm', label: '再次输入密码', minlength: 10, autocomplete: 'new-password', className: 'auth-rise' }) +
    '<div id="auth-error" role="alert"></div>' +
    '<button class="primary auth-submit auth-rise" type="submit">创建管理员并进入</button></form>' +
    '<p class="auth-note auth-rise">首次设置需在服务器本机完成。</p>';
}
function registerFormHtml() {
  return '<form id="register-form">' +
    '<fieldset class="auth-rise"><legend>账号与公司</legend><div class="auth-grid">' +
    '<label class="field">登录账号 *<input name="username" minlength="3" maxlength="60" placeholder="例如：hualan_id" autocomplete="username" required></label>' +
    '<label class="field">公司名称 *<input name="name" maxlength="150" placeholder="例如：华澜精密制造（印尼）有限公司" required></label>' +
    passwordField({ id: 'auth-register-password', name: 'password', label: '设置密码（至少8位）*', minlength: 8, autocomplete: 'new-password' }) +
    passwordField({ id: 'auth-register-confirm', name: 'confirm', label: '确认密码 *', minlength: 8, autocomplete: 'new-password' }) +
    '</div></fieldset>' +
    '<fieldset class="auth-rise"><legend>业务背景 <small>（选填，登录后可在公司档案中修改）</small></legend><div class="auth-grid">' +
    '<label class="field">所属行业<input name="industry" maxlength="200" placeholder="例如：汽车零部件 / 新能源矿业"></label>' +
    '<label class="field">印尼投资地区<input name="location" maxlength="500" placeholder="例如：西爪哇省勿加泗县芝卡朗工业区"></label>' +
    '<label class="field full">主营业务与产品<textarea name="business" rows="2" maxlength="3000" placeholder="简述在印尼的主营业务、核心产品或项目阶段"></textarea></label>' +
    '<label class="field full">重点关注风险<textarea name="concerns" rows="2" maxlength="3000" placeholder="例如：外籍劳工RPTKA合规、进口模具钢清关、本地化率TKDN要求"></textarea></label>' +
    '</div></fieldset>' +
    '' +
    '<div id="auth-error" role="alert"></div>' +
    '<button class="primary auth-submit auth-rise" type="submit">注册并进入工作台</button></form>' +
    '<p class="auth-note auth-rise">登录有效期为8小时；不同企业账号之间资料、任务与风险事件严格隔离。</p>';
}
function focusFirstAuthField(panel) {
  const field = $$('input:not([type=checkbox]):not(:disabled)', panel).find((input) => input.offsetParent !== null);
  if (field) {
    field.focus();
  }
}
function showAuthError(message) {
  $('#auth-error').innerHTML = `<div class="error">${esc(message)}</div>`;
}
function setAuthBusy(form, busy, busyLabel) {
  const button = $('button[type=submit]', form);
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyLabel;
  } else if (button.dataset.label) {
    button.textContent = button.dataset.label;
  }
  button.disabled = busy;
  form.setAttribute('aria-busy', String(busy));
}
function bindPasswordAids(panel) {
  $$('.auth-reveal', panel).forEach((button) => {
    button.onclick = () => {
      const input = $(`#${button.getAttribute('aria-controls')}`);
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(show));
      button.setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
      button.innerHTML = icon(show ? 'eye-off' : 'eye');
    };
  });
  $$('.auth-password input', panel).forEach((input) => {
    const hint = $(`#${input.id}-caps`);
    const sync = (event) => {
      if (typeof event.getModifierState === 'function') {
        hint.hidden = !event.getModifierState('CapsLock');
      }
    };
    input.addEventListener('keydown', sync);
    input.addEventListener('keyup', sync);
    input.addEventListener('blur', () => {
      hint.hidden = true;
    });
  });
}
function applyLoginRole(panel, role) {
  const admin = role === 'admin';
  const field = $('[data-username-field]', panel);
  const input = $('input[name=username]', field);
  field.hidden = admin;
  input.disabled = admin;
  $$('[data-login-role]', panel).forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.loginRole === role));
  });
  $('.auth-sub', panel).textContent = authCopy[role].sub;
  $('#login-form button[type=submit]').textContent = authCopy[role].submit;
}
function renderAuthPanel(auth, options = {}) {
  const panel = renderAuthShell();
  const isRegister = false; // Enterprise accounts are provisioned by the administrator.
  const role = loginRole();
  let html = '';
  if (!auth.initialized) {
    html = '<h1 id="auth-title" class="auth-rise">设置本地管理员</h1><p class="auth-sub auth-rise">首次使用请设置管理员密码。资料和分析结果保存在当前服务器。</p>' + setupFormHtml();
  } else if (isRegister) {
    html = `${authTabs(true)}<h1 id="auth-title" class="auth-rise">注册企业账号</h1><p class="auth-sub auth-rise">注册后自动创建贵司专属档案并同步知识库；登录后仅显示贵司自己的信息与相关风险内容。</p>${registerFormHtml()}`;
  } else {
    html = `${authTabs(false)}<h1 id="auth-title" class="auth-rise">登录工作台</h1><p class="auth-sub auth-rise">${authCopy[role].sub}</p>${loginFormHtml(role)}`;
  }
  panel.classList.toggle('is-register', isRegister);
  panel.innerHTML = html;
  $$('.auth-rise', panel).forEach((node, index) => node.style.setProperty('--rise', String(index)));
  bindPasswordAids(panel);
  $$('[data-auth-mode]', panel).forEach((tab) => {
    tab.onclick = () => {
      if (tab.getAttribute('aria-selected') === 'true') {
        return;
      }
      state.authMode = tab.dataset.authMode;
      renderAuthPanel(auth, { focus: 'field' });
    };
    tab.onkeydown = (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
        return;
      }
      event.preventDefault();
      const tabs = $$('[data-auth-mode]', panel);
      const next = tabs[(tabs.indexOf(tab) + 1) % tabs.length];
      const target = event.key === 'Home' ? tabs[0] : (event.key === 'End' ? tabs.at(-1) : next);
      state.authMode = target.dataset.authMode;
      renderAuthPanel(auth, { focus: 'tab' });
    };
  });
  $$('[data-login-role]', panel).forEach((button) => {
    button.onclick = () => {
      const { loginRole: next } = button.dataset;
      rememberLoginRole(next);
      applyLoginRole(panel, next);
      $('#auth-error').innerHTML = '';
      focusFirstAuthField(panel);
    };
  });
  if (options.focus === 'tab') {
    $('[data-auth-mode][aria-selected=true]', panel).focus();
  } else if (options.focus === 'field' || (options.focus === 'initial' && matchMedia('(pointer:fine)').matches)) {
    focusFirstAuthField(panel);
  }
  const loginForm = $('#login-form');
  if (loginForm) {
    loginForm.onsubmit = async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const values = new FormData(form);
      if (!auth.initialized && values.get('password') !== values.get('confirm')) {
        showAuthError('两次输入的密码不一致。');
        return;
      }
      $('#auth-error').innerHTML = '';
      setAuthBusy(form, true, auth.initialized ? '正在登录…' : '正在创建…');
      try {
        const payload = auth.initialized
          ? { username: (values.get('username') || '').trim(), password: values.get('password') }
          : { password: values.get('password') };
        await api(auth.initialized ? '/auth/login' : '/auth/setup', { method: 'POST', body: payload });
        await boot();
      } catch (e) {
        if (form.isConnected) {
          setAuthBusy(form, false);
          showAuthError(e.message);
        }
      }
    };
  }
  const registerForm = $('#register-form');
  if (registerForm) {
    registerForm.onsubmit = async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const values = new FormData(form);
      if (values.get('password') !== values.get('confirm')) {
        showAuthError('两次输入的密码不一致。');
        return;
      }
      $('#auth-error').innerHTML = '';
      setAuthBusy(form, true, '正在注册…');
      const body = Object.fromEntries(values);
      delete body.confirm;
      try {
        const res = await api('/auth/register', { method: 'POST', body });
        state.authMode = 'login';
        toast(`企业账号已注册并登录：${res.company_name || body.name}`);
        await boot();
      } catch (e) {
        if (form.isConnected) {
          setAuthBusy(form, false);
          showAuthError(e.message);
        }
      }
    };
  }
}
function renderAuthFailure(error) {
  $('#shell').hidden = true;
  const panel = renderAuthShell();
  panel.classList.remove('is-register');
  panel.innerHTML = '<h1 id="auth-title" class="auth-rise">暂时无法连接服务</h1>' +
    '<p class="auth-sub auth-rise">请检查后端是否启动，再刷新页面。</p>' +
    `<div class="auth-rise">${errorBox(error.message)}</div>` +
    '<button type="button" class="primary auth-submit auth-rise" id="auth-retry">重新连接</button>';
  $$('.auth-rise', panel).forEach((node, index) => node.style.setProperty('--rise', String(index)));
  $('#auth-retry').onclick = async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = '正在连接…';
    await boot().catch(renderAuthFailure);
  };
}
async function boot(){
  const auth=await api('/auth/status');
  state.auth=auth;
  $('#auth').hidden=auth.authenticated;$('#shell').hidden=!auth.authenticated;
  if(!auth.authenticated){
    workDrafts.clear();
    resetConsultation();
    document.body.classList.remove('mobile-navigation-open');
    window.Motion?.leave();
    renderAuthPanel(auth,{focus:'initial'});
    return;
  }
  window.Stage?.unmount();
  $('#auth').replaceChildren();
  document.body.dataset.role=auth.role||'';
  const workspaceLabel=$('#workspace-label');
  if(workspaceLabel){
    workspaceLabel.innerHTML=auth.company_id
      ? `${esc(auth.company_name||'企业')}<small>企业专属工作区</small>`
      : '管理员<small>全部公司</small>';
  }
  const userMark=$('.user-mark');
  if(userMark){
    userMark.textContent=auth.company_id?`企业 · ${auth.company_name||auth.username}`:'管理员 · 背景：未选择';
    userMark.title=auth.company_id?`当前登录企业：${auth.company_name}（账号：${auth.username}）`:'当前登录身份：系统管理员';
  }
  state.config=await api('/settings');
  $('#model-status').textContent=modelStatusText();
  $('#model-status').title=state.config.last_success?'最近成功分析：'+when(state.config.last_success.created_at)+'；不代表实时连接探测':'';
  $('#mode-label').textContent='外部 API 模式';
  await render();
}
async function render(options={}){
  if($('#shell').hidden)return;
  const previousScroll=window.scrollY;
  const routeChanged=state.routeKey!==location.hash;
  state.renderAbort?.abort();
  const ac=new AbortController();
  state.renderAbort=ac;
  state.renderSignal=ac.signal;
  const renderId=++state.renderId;
  const [routePath,routeSearch='']=location.hash.slice(1).split('?');
  const parts=routePath.split('/');
  const rawRoute=parts[0]||'overview',id=parts[1];
  const route=rawRoute==='jobs'?'documents':rawRoute;
  if(['report','countermeasures'].includes(route)||(state.auth?.role==='company'&&!['overview','events','event'].includes(route))){location.hash='#overview';return;}
  if(state.route!==route||state.routeKey!==location.hash){
    state.filter={};state.page=1;
    if(['events','documents','knowledge','jobs','report','evidence','updates'].includes(route)){
      const params=new URLSearchParams(routeSearch);
      for(const key of ['q','level','category','validity','review','date_from','date_to','status','policy','sort','change','family'])if(params.has(key))state.filter[key]=params.get(key);
      state.page=Math.max(1,parseInt(params.get('page'),10)||1);
      if(['all','real','demo'].includes(params.get('demo')))state.scope=params.get('demo');
      else if(params.has('demo'))state.scope='all';
      state.kq=params.get('kq')||'';
      state.ki=Math.max(0,parseInt(params.get('ki'),10)||0);
    }
  }
  if(routeChanged&&route==='websites'){webFilter.status=new URLSearchParams(routeSearch).get('status')||'';webFilter.page=1;}
  state.routeKey=location.hash;
  state.route=route;
  document.body.dataset.route = route;
  const active=route==='event'?'events':route;
  $$('[data-nav]').forEach(a=>{a.classList.toggle('active',a.dataset.nav===active);if(a.dataset.nav===active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#breadcrumb').innerHTML=`<span class="crumb-root">工作台 / </span><span class="crumb-page">${names[active]||'风险详情'}</span>`;
  if(!options.quiet)$('#main').innerHTML='<div class="loading" role="status">正在加载…</div>';
  try{
    await loadCompanies();
    updateIdentity();
    $('#breadcrumb').innerHTML=`<span class="crumb-root">工作台 / </span><span class="crumb-page">${names[active]||'风险详情'}</span>${state.company?`<span class="crumb-company"> / 当前公司：${esc(state.company.name)}</span>`:''}`;
    let html='';
    if(['websites','updates'].includes(route)&&state.auth?.role==='company'){
      html=empty('该功能仅管理员可用','网站采集和管理是平台级功能，企业账号可继续使用知识库检索和本公司资料。','<a class="secondary" href="#knowledge">进入知识库</a>');
    }
    else if(route==='overview')html=await overview();
    else if(route==='events')html=await eventList();
    else if(route==='event')html=await eventDetail(id);
    else if(route==='event-new')html=meetingCreate();
    else if(route==='documents'||route==='knowledge')html=await documents(route==='knowledge');
    else if(route==='consultation')html=consultationPage();
    else if(route==='drafting')html=await meetingDrafting();
    else if(route==='jobs')html=await jobsPage();
    else if(route==='websites')html=await websitePage();
    else if(route==='evidence')html=await evidencePage(id);
    else if(route==='updates')html=await updatesPage();
    else if(route==='settings')html=await settings();
    else if(route==='report')html=await reportView();
    else if(route==='countermeasures')html=await countermeasurePage(new URLSearchParams(routeSearch).get('level'));
    else html=empty('页面不存在','请从左侧导航选择工作区。','<a href="#overview" class="primary">返回总览</a>');
    if(renderId!==state.renderId)return;
    html=await enhanceView(route,html);
    html=meetingView(route,html);
    if(route==='overview'){const host=document.createElement('div');host.innerHTML=html;host.querySelector('[data-company-host]').innerHTML=companyContext();html=host.innerHTML;}
    if(renderId!==state.renderId)return;
    $('#main').innerHTML=`<div class="route-enter">${composeWorkspace(route,html)}</div>`;bind();bindFeatures();bindWorkflows();bindKnowledgeReader();bindWorkspace();bindWebsite();bindCompanies();
    window.Motion?.enter(route,{quiet:options.quiet});
    if(options.quiet)window.scrollTo(0,previousScroll);
    else if(routeChanged)window.scrollTo({top:0,behavior:'instant'});
    bindOperations();
    bindEvidence();bindFollowups();bindConsultation();bindMeeting();bindDrafting();
  }catch(e){
    if(renderId!==state.renderId||e.name==='AbortError'||e.status===401)return;
    $('#main').innerHTML=errorBox(e.message)+'<button class="secondary" id="retry-page">重新加载</button>';
    $('#retry-page')?.addEventListener('click',render);
  }finally{
    if(state.renderSignal===ac.signal)state.renderSignal=null;
  }
}
// Empty overview: the map slot becomes a standby card whose single action follows the workspace's real state.
function signalStandby(stats,workspace){
  const pending=stats.documents?Math.min(workspace?.unanalyzed||0,stats.documents):0;
  let title='导入第一批资料，点亮风险信号';
  let copy='上传政策、新闻或项目资料后，系统会结合企业背景与知识库识别风险，并在这里绘出风险类型分布。';
  let action=`<a class="primary" href="#documents">${icon('upload')}导入资料</a>`;
  if(pending){
    title=`${pending} 份资料已入库，等待分析`;
    copy='启动分析后，风险类型、等级构成与复核待办会在这里展开。每条判断都可回溯到原文。';
    action=`<a class="primary" href="#documents?status=unanalysed">分析 ${pending} 份待分析资料${icon('arrow')}</a>`;
  }else if(stats.documents){
    title=`已分析 ${stats.documents} 份资料，未识别到风险`;
    copy='当前范围内没有风险事件。可以继续导入资料，或复查已分析资料的结论。';
    action=`<a class="secondary" href="#documents">查看资料${icon('arrow')}</a>`;
  }
  const network = `<div class="standby-network" aria-hidden="true">
    <svg viewBox="0 0 360 240">
      <ellipse class="standby-ring" cx="180" cy="120" rx="104" ry="74"/>
      <ellipse class="standby-ring ring-inner" cx="180" cy="120" rx="58" ry="40"/>
      <path class="standby-link" pathLength="1" d="M180 120 Q132 78 72 70"/>
      <path class="standby-link" pathLength="1" d="M180 120 Q238 66 294 66"/>
      <path class="standby-link" pathLength="1" d="M180 120 Q125 166 84 181"/>
      <path class="standby-link" pathLength="1" d="M180 120 Q240 166 286 181"/>
      <path class="standby-link is-faint" pathLength="1" d="M180 120 V45"/>
      <path class="standby-link is-faint" pathLength="1" d="M180 120 V202"/>
      <circle class="standby-node" cx="72" cy="70" r="6"/>
      <circle class="standby-node" cx="294" cy="66" r="5"/>
      <circle class="standby-node" cx="84" cy="181" r="5"/>
      <circle class="standby-node" cx="286" cy="181" r="6"/>
      <circle class="standby-node node-brass" cx="180" cy="45" r="4"/>
      <circle class="standby-node node-faint" cx="180" cy="202" r="4"/>
      <circle class="standby-core" cx="180" cy="120" r="13"/>
      <circle class="standby-core-dot" cx="180" cy="120" r="3"/>
    </svg>
  </div>`;
  return `<div class="signal-standby"><div class="standby-copy"><p class="standby-kicker"><span class="label-dot" aria-hidden="true"></span>SIGNAL MAP · STANDBY</p><h2>${title}</h2><p>${copy}</p><div class="actions">${action}</div></div>${network}</div>`;
}
async function overview(){
  const [stats,data,workspace]=await Promise.all([api(`/overview?demo=${scopeValue()}`),api(`/events?demo=${scopeValue()}`),state.auth?.role==='admin'?api('/workspace').catch(()=>null):null]);
  state.overviewScope=stats.scope||null;
  state.overviewDecisions=stats.decisions||[];
  state.overviewGaps=stats.evidence_gaps||[];
  state.overviewWorkspace=workspace;
  state.collectionHealth=null;
  const isEmpty=stats.total===0;
  const pending=Math.min(workspace?.unanalyzed||0,stats.documents||0);
  const count=Object.fromEntries(stats.levels.map(v=>[v.level,v.count]));
  const recent=data.items.slice(0,6);
  const decisions=Object.fromEntries((stats.decisions||[]).map(r=>[r.decision,r.count]));
  const primary = pending
    ? `<a class="primary" href="#documents?status=unanalysed">${icon('analysis')}分析 ${pending} 份资料</a>`
    : stats.documents
      ? `<a class="secondary" href="#documents">${icon('documents')}查看资料</a>`
      : `<a class="primary" href="#documents">${icon('upload')}导入资料</a>`;
  const composition=`<section class="panel overview-composition" aria-label="风险等级构成"><div class="panel-heading"><h2>风险等级构成</h2><span class="composition-total">已识别 <strong>${stats.total}</strong> 条风险事件</span></div><div class="risk-composition-body"><div class="risk-composition-bar" aria-hidden="true">${['lv1','lv2','lv3'].map(v=>`<span class="${v}" data-weight="${count[v]||0}"></span>`).join('')}</div><div class="risk-composition-levels">${['lv1','lv2','lv3'].map(v=>`<a href="${eventHref({level:v})}"><span class="composition-level-name"><span class="dot ${v}"></span>${levelLabels[v]}</span><span class="composition-level-value">${count[v]||0}<small>条</small></span><span class="composition-level-share">${stats.total?Math.round((count[v]||0)/stats.total*100):0}%</span></a>`).join('')}</div></div><div class="composition-footer"><small>仅统计各资料的最新分析版本 · 点击等级查看事件</small><span class="composition-green"><span class="dot non_risk"></span>绿色 · 无风险 <strong>${decisions.non_risk||0}</strong> 份资料<small>不计入风险事件</small></span></div></section>`;
  const board = isEmpty
    ? `<section class="panel network-panel is-standby" aria-label="风险类型分布">${signalStandby(stats,workspace)}</section>`
    : `<section class="panel network-panel"><div class="panel-heading"><h2>${icon('overview')}风险类型分布</h2><small>基于当前资料</small></div>${categoryNetwork(stats)}</section>`;
  return heading('风险总览','从风险信号到判断依据，让每一次分析可核验。',`<button class="secondary icon-button" data-refresh aria-label="刷新总览">${icon('refresh')}</button><a class="secondary" href="#events">查看全部事件</a>${primary}`)
    +'<div data-company-host></div>'
    +overviewScope()
    +rulesAlert()
    +(state.scope!=='real'&&recent.some(e=>e.demo)?demonstration():'')
    +composition
    +`<div class="analysis-board overview-bento${isEmpty?' is-empty':''}">${board}</div>`
    +`<section class="panel events-panel"><div class="panel-heading"><h2>${icon('risk')}最新风险事件</h2><a class="panel-link" href="${eventHref()}">全部事件 ${icon('arrow')}</a></div>${recent.length?tableEvents(recent,true):`<p class="events-empty">${icon('risk')}<span><strong>暂无风险事件</strong><span>分析完成后，最新 6 条会显示在这里</span></span><a class="text-button" href="#documents">查看资料队列${icon('arrow')}</a></p>`}</section>`;
}
async function eventList(){
  state.eventListReturn={href:location.hash||'#events',scope:JSON.stringify([state.auth?.username,state.company?.id||null])};
  if (state.filter.family && state.filter.category && familyOf(state.filter.category) !== state.filter.family) {
    delete state.filter.category;
  }
  const query=new URLSearchParams({...state.filter,page:state.page,demo:scopeValue()});
  query.delete('family');
  let counts = {};
  try {
    const overview = await api('/overview?' + new URLSearchParams({ demo: scopeValue() }));
    counts = Object.fromEntries((overview.categories || []).map((item) => [item.category, item.count]));
  } catch (_error) {
    counts = {};
  }
  const data=await api('/events?'+query);
return heading('风险事件','逐条核验风险判断，查看来源并记录业务复核意见。','<a href="#documents" class="primary">导入新资料</a>')+scope()+`<section class="panel"><form class="filters" id="event-filter"><label class="search-field">搜索事件<input name="q" placeholder="输入事件标题或摘要" value="${esc(state.filter.q||'')}"></label><label>风险等级<select name="level"><option value="">全部等级</option>${Object.entries(levels).map(([v,l])=>`<option value="${v}" ${state.filter.level===v?'selected':''}>${l}</option>`).join('')}</select></label><label>复核状态<select name="review"><option value="">全部状态</option>${['pending','accepted','needs_change'].map(v=>`<option value="${v}" ${state.filter.review===v?'selected':''}>${statuses[v]}</option>`).join('')}</select></label><label>一级风险<select name="family">${familyOptions()}</select></label><label>风险类型<select name="category">${categoryOptions(counts)}</select></label><label>开始日期<input type="date" name="date_from" value="${esc(state.filter.date_from||'')}"></label><label>结束日期<input type="date" name="date_to" value="${esc(state.filter.date_to||'')}"></label><button class="secondary small" type="submit">查询</button><button class="text-button" type="button" id="clear-filter">重置</button></form>${data.items.length?tableEvents(data.items):empty('没有符合条件的风险事件','尝试调整筛选条件，或在资料页导入并分析新资料。')}${pagination(data)}</section>`;
}
async function eventDetail(id){
  const e=await api('/events/'+encodeURIComponent(id));
  state.currentEvent=e;
  return `<a class="back-link" href="#events">返回风险事件</a><h1 class="detail-title">${esc(e.title)}</h1><div class="metadata">${badge(e.level)}<span>${esc(e.category)}</span><span>${esc(dateLabel(e))}</span><span>${esc(e.source||'来源未填写')}</span>${demoTag(e.demo)}</div>`+
    (e.quarantined_at?'<div class="notice-inline">来源资料已隔离，本事件不计入统计、列表和简报。原因：'+esc(e.quarantine_reason||'未填写')+'</div>':'')+
    (!e.is_latest?'<div class="notice-inline">这是历史版本，最新分析结果请从风险列表查看。</div>':'')+
    (e.result.partial_context?'<div class="notice-inline">这份长资料已分段分析。跨段关联及事件重复需人工核验。</div>':'')+
    `<div class="detail-grid"><div><section class="panel">${[['事件摘要',e.summary],['潜在影响',e.impact],['初步应对建议',e.recommendation]].map(([title,text])=>`<section class="detail-section"><h2>${title}</h2><p>${esc(text)}</p></section>`).join('')}</section><section class="panel"><div class="panel-heading"><h2>业务复核</h2>${badge(e.review_status)}</div><form id="review-form" class="panel-content review-form" data-id="${e.id}"><div class="form-grid"><label class="field">复核结论<select name="status">${['pending','accepted','needs_change'].map(v=>`<option value="${v}" ${e.review_status===v?'selected':''}>${statuses[v]}</option>`).join('')}</select></label><label class="field full">复核意见<textarea name="note" rows="3" maxlength="2000" placeholder="记录判断分歧、需要补充的资料或修正建议">${esc(e.review_note)}</textarea></label></div><div class="form-actions"><button class="primary" type="submit">保存复核意见</button><small>${e.reviewed_at?'上次保存 '+when(e.reviewed_at):'尚未记录复核意见'}</small></div><div id="review-error"></div></form></section></div><div><section class="panel"><div class="panel-heading"><h2>判断依据与来源</h2><small>${e.evidence.length} 条引用</small></div>${e.evidence.map((r,i)=>`<article class="evidence"><span class="ref">引用 ${i+1} · ${esc(evidenceLabel(r))}</span><h3>${esc(r.title)}</h3><blockquote>${readingEsc(r.quote)}</blockquote><p>${esc(r.reason)}</p><small>${esc(r.locator)}</small><br>${sourceButton(r.document_id,'定位原文',r.quote)}</article>`).join('')}</section><section class="panel"><div class="panel-heading"><h2>分析记录</h2></div><div class="panel-content"><dl class="definition"><dt>分析版本</dt><dd>v${e.version}</dd><dt>模型</dt><dd>${esc(e.model)}</dd><dt>运行模式</dt><dd>${e.mode==='demo'?'演示数据（未调用模型）':e.mode==='local'?'本地模型':'外部 API'}</dd><dt>规则版本</dt><dd>${esc(e.rules.version)}</dd><dt>分析时间</dt><dd>${when(e.created_at)}</dd><dt>处理耗时</dt><dd>${e.duration_ms?e.duration_ms/1000+' 秒':'—'}</dd></dl><div class="form-actions">${sourceButton(e.document_id,'查看输入资料')}</div></div></section></div></div>`;
}
function importForm(knowledge){
  return `<div class="tabs"><button data-import-mode="file" class="${state.importMode==='file'?'selected':''}">上传文件</button><button data-import-mode="manual" class="${state.importMode==='manual'?'selected':''}">手动录入</button></div><form id="import-form" data-kind="${knowledge?'knowledge':'event'}">${knowledge?legalImportFields():''}${state.importMode==='file'?`<label class="upload-area"><strong>选择需要导入的资料</strong><br><small>Excel / CSV / Word / PDF / TXT / Markdown · 最大10MB</small><br><input type="file" name="file" accept=".csv,.xlsx,.docx,.pdf,.txt,.md" required></label>`:`<div class="form-grid"><label class="field full">标题<input name="title" maxlength="240" required placeholder="输入资料标题"></label><label class="field">资料日期<input type="date" name="date"></label><label class="field">信息来源<input name="source" maxlength="300" placeholder="发布机构或资料出处"></label><label class="field full">原始链接<input name="url" type="url" placeholder="https://"></label><label class="field full">正文<textarea name="body" rows="7" maxlength="60000" required placeholder="粘贴完整正文，保留有助于核验的上下文"></textarea></label></div>`}<div class="form-actions"><button class="primary" type="submit">${knowledge?'导入知识库':'保存并核对资料'}</button>${state.importMode==='file'?'<a href="api/template" class="text-button">下载表格模板</a>':''}</div><div id="import-result" aria-live="polite"></div></form>`;
}
function renderDocAnalysisStatus(d){
  const st=['queued','running','failed'].includes(d.job_status)?d.job_status:(d.decision||d.job_status);
  let html=badge(st);
  if(d.decision==='insufficient'&&d.analysis_id)html+=`<a class="source-line" href="#evidence/${d.analysis_id}">补充证据 ${icon('arrow')}</a>`;
  if(d.job_status==='queued'||d.job_status==='running'){
    html+=`<div class="source-line nowrap">任务 #${d.job_id} · ${d.job_progress||0} / ${d.job_total||'—'} 段</div><progress class="job-progress" value="${d.job_progress||0}" max="${d.job_total||1}" aria-label="任务进度"></progress>`;
  }else if(d.job_status==='failed'&&d.job_error){
    html+=`<div class="source-line job-error">${esc(d.job_error)}</div>`;
  }
  return html;
}
function docProgressCellHtml(d) {
  return `${renderDocAnalysisStatus(d)}<span class="source-line nowrap">全文 ${d.characters.toLocaleString('zh-CN')} 字符</span>`;
}
function docDeleteHtml(d, knowledge) {
  if (d.quarantined_at) {
    return '';
  }
  if (d.editable) {
    return `<button class="text-button danger" data-delete-doc="${d.id}" data-title="${esc(d.title)}">删除</button>`;
  }
  return knowledge ? '<span class="web-tag">公共资料 · 只读</span>' : '';
}
function docSelectHtml(d) {
  const disabled = d.demo
    ? 'disabled title="演示数据，不能进入真实分析"'
    : d.quarantined_at ? 'disabled title="资料已隔离，不能进入分析"' : '';
  return `<input type="checkbox" name="doc-select" value="${d.id}" aria-label="选择 ${esc(d.title)}" ${disabled}>`;
}
function quarantineTag(d) {
  return d.quarantined_at ? `<span class="badge quarantine-tag" title="${esc(d.quarantine_reason || '待核实')}">已隔离</span>` : '';
}
async function documents(knowledge){
  if(knowledge) await ensureLegalSchema();
  // This retired list filter must not keep silently filtering bookmarked URLs.
  delete state.filter.policy;
  const kind=knowledge?'knowledge':'event';
  const data=await api('/documents?'+new URLSearchParams({...state.filter,kind,page:state.page}));
  const rows=data.items.map(d=>{
    const summary=d.zh_state==='done'
      ? `<div class="zh-summary-clamp">${esc(d.zh_summary)}</div>${d.zh_keywords?`<div class="zh-kw-line"><strong>关键词：</strong>${esc(d.zh_keywords)}</div>`:''}<button type="button" class="text-button" data-zh-expand>展开</button>`
      : `<span class="zh-state">${d.demo?'演示资料不生成摘要':d.zh_state==='failed'?'摘要生成失败':'摘要待生成'}</span>`;
    const actions=knowledge
      ? `${sourceButton(d.id,'查看详细')}${docDeleteHtml(d,true)}`
      : `${sourceButton(d.id,d.decision?'查看详细与结果':'查看详细')}<span data-job-actions>${docJobActionsHtml(d)}</span>${docDeleteHtml(d,false)}`;
    return `<tr data-doc-id="${d.id}">
      ${knowledge?'':`<td>${docSelectHtml(d)}</td>`}
      <td class="title-cell">${esc(d.title)}${demoTag(d.demo)}${quarantineTag(d)}<span class="source-line">${knowledge?esc(d.legal_metadata?.category_label||'未分类')+' · ':''}${esc(d.kind_label||'')}${d.kind_label?' · ':''}${esc(d.source||'来源未填写')}</span>${knowledge?`<span class="source-line">${esc(d.legal_metadata?.validity_label||'效力未确认')}</span>`:''}</td>
      <td class="date-cell">${dateStamp(d)}</td>
      <td class="${knowledge?'zh-cell':''}" ${knowledge?'':`data-progress-cell`}>${knowledge?summary:docProgressCellHtml(d)}</td>
      <td><div class="document-actions">${actions}</div></td>
    </tr>`;
  }).join('');
  return heading(knowledge?'知识库':'资料与分析',knowledge?'保存政策、案例与业务资料，为风险分析提供可追溯的参考依据。':'上传或录入待研判资料，一键结合企业背景与知识库法规完成风险分析。')+
    `<div class="split"><section class="panel"><div class="panel-heading"><h2>${knowledge?'添加参考资料':'导入并分析资料'}</h2></div><div class="panel-content">${importForm(knowledge)}</div></section><section class="panel"><div class="panel-heading"><h2>${knowledge?'检索与使用说明':'导入与分析说明'}</h2></div><div class="panel-content form-note">${knowledge?'<p>资料入库后，由已配置的模型自动生成中文摘要和中文关键词，外文法规也可以用中文检索。检索在服务端完成，结果都能追溯原文。</p><p>风险分析使用当前公司及公共知识库中相关的参考资料，引用的是原文片段，并随分析版本保存。</p>':'<ul><li>上传或录入后自动进入后台风险分析，并实时刷新进度。</li><li>分析时自动挂载贵司档案背景与知识库中最相关的印尼法规原文。</li><li>每条记录至少包含标题和正文；单条最多60000字符。</li><li>下方列表可直接查看分段分析进度、失败原因、取消排队或重新分析。</li></ul>'}<p>模型状态：<strong>${modelStatusText()}</strong><br>分类规则：${state.config.rules.confirmed?'已确认':'待确认'}</p><a href="#settings">查看模型与规则设置</a></div></section></div>`+
    (knowledge?'<section class="panel knowledge-search-panel"><div class="panel-heading"><h2>知识库检索</h2><small>中文、印尼文和英文关键词均可</small></div><form id="knowledge-search" class="knowledge-search-bar legal-search"><label class="field">内容检索<input name="q" value="'+esc(state.kq||'')+'" required placeholder="检索资料标题、摘要和正文"></label>'+legalSearchFilters()+'<button class="primary small" type="submit">检索内容</button></form><section id="knowledge-results" class="kr" aria-live="polite"></section></section>':'')+
    `<section class="panel"><div class="panel-heading"><h2>${knowledge?'参考资料':'资料与分析任务列表'} <small>${data.total} 条</small></h2>${knowledge?'':'<div class="actions"><button class="secondary small" data-refresh>刷新进度</button><button class="primary small" id="analyze-selected">分析所选资料</button></div>'}</div><form class="filters" id="document-filter"><label class="search-field">搜索资料<input name="q" value="${esc(state.filter.q||'')}" placeholder="按标题搜索"></label>${knowledge?legalListFilters():''}<button class="secondary small">查询</button></form><p id="list-stale" hidden>列表有新增或删除，<button type="button" class="text-button" data-refresh>点击刷新</button></p>${data.items.length?`<div class="table-wrap"><table><thead><tr>${knowledge?'':'<th><input type="checkbox" id="select-all" aria-label="选择当前页可分析资料"></th>'}<th>资料标题</th><th>日期（来源）</th><th>${knowledge?'中文摘要':'分析进度与结论'}</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table></div>`:empty(knowledge?'没有符合条件的参考资料':'暂无待分析资料',knowledge?'可以调整分类或效力筛选，或导入新的资料。':'在上方上传文件或手动录入，核对正文与企业范围后确认分析。')}${pagination(data)}</section>`;
}
function docJobActionsHtml(d){
  if(d.demo||d.quarantined_at)return '';
  if(d.job_status==='queued')return `<button class="secondary small" data-cancel-job="${d.job_id}">取消排队</button>`;
  if(d.job_status==='running')return '<span class="muted nowrap">分析中…</span>';
  return `<button class="secondary small" data-analyze="${d.id}">${d.decision||d.job_status==='failed'?'重新分析':'分析'}</button>`;
}
async function jobs(){
  const data=await api('/jobs');
  return heading('分析任务','后台逐条处理资料。失败任务不会覆盖已有分析结果。','<button class="secondary" data-refresh>刷新状态</button><a class="primary" href="#documents">选择资料</a>')+
    `<section class="panel"><div class="panel-heading"><h2>最近100条任务</h2><small>排队与运行中的任务每4秒更新</small></div>${data.items.length?`<div class="table-wrap"><table><thead><tr><th>任务与资料</th><th>状态</th><th>处理进度</th><th>提交时间</th><th>结果与操作</th></tr></thead><tbody>${data.items.map(j=>`<tr><td class="title-cell">${esc(j.title)}<span class="source-line">任务 #${j.id}</span></td><td>${badge(j.status)}</td><td class="nowrap">${j.progress} / ${j.total||'—'} 个片段<progress class="job-progress" value="${j.progress}" max="${j.total||1}" aria-label="任务进度"></progress></td><td class="nowrap">${when(j.created_at)}</td><td>${j.error?`<p>${esc(j.error)}</p>`:''}${j.status==='failed'?`<button class="secondary small" data-analyze="${j.document_id}">重试分析</button>`:j.status==='completed'?sourceButton(j.document_id,'查看分析记录'):'等待处理'}</td></tr>`).join('')}</tbody></table></div>`:empty('还没有分析任务','在资料页选择一条或多条资料，启动后台分析。','<a class="primary" href="#documents">进入资料页</a>')}</section>`;
}
async function settings(){
  state.config=await api('/settings');const c=state.config;
  return heading('模型与规则','通过外部模型 API 完成风险分析和网站相关性筛选。')+`<div class="settings-grid"><section class="panel"><div class="panel-heading"><h2>模型连接</h2><span class="status-chip">${c.configured?'已填写配置':'等待配置'}</span></div><div class="panel-content"><dl class="definition"><dt>运行模式</dt><dd>${'外部 API'}</dd><dt>模型名称</dt><dd>${esc(c.model||'未设置')}</dd><dt>服务地址</dt><dd>${esc(c.base_url||'未设置')}</dd><dt>推理强度</dt><dd>${esc(c.reasoning_effort||'模型默认')}</dd><dt>接口协议</dt><dd>${c.wire_api==='responses'?'Responses':'Chat Completions'}</dd><dt>响应存储</dt><dd>${c.store_responses?'开启':'关闭'}</dd><dt>知识库检索</dt><dd>${esc(c.retrieval)}</dd></dl><h3>API 使用说明</h3><p class="form-note">模型连接由服务端统一配置，API 密钥不会返回浏览器。支持 Responses 与 Chat Completions 协议，可设置推理强度和响应存储。</p><p class="form-note">资料录入后即可用于模型分析；风险分析结合正文、相关知识片段和公司背景，网站检索按配置筛选公开网页。</p><p class="form-note">连接异常时任务会提示失败，可在恢复后重试。配置已填写不代表实时连接正常，请使用连接检查验证。</p></div></section><section class="panel"><div class="panel-heading"><h2>风险分类分级规则</h2><span class="status-chip">${c.rules.confirmed?'已保存':'待确认'}</span></div><form class="panel-content" id="rules-form"><p class="form-note">可根据公司经营情况修改分类、等级定义和版本，再勾选确认。历史分析保留当时使用的规则。</p><label class="field">规则内容（JSON）<textarea name="rules" class="rules-editor" spellcheck="false">${esc(JSON.stringify(c.rules,null,2))}</textarea></label><label class="check-field"><input type="checkbox" name="confirmed" ${c.rules.confirmed?'checked':''}><span>我确认这份规则适用于当前分析用途。</span></label><button class="primary" type="submit">保存规则</button><div id="rules-error"></div></form></section></div>`;
}
function sourceDateRows(d) {
  const rows = [['资料日期（来源）', esc(dateLabel(d))]];
  if (d.archived_at) {
    rows.push(['存档快照', esc(d.archived_at)]);
  }
  if (d.fetched_at) {
    rows.push(['收录时间', esc(when(d.fetched_at))]);
  }
  if (d.date_source === 'removed' && d.date_legacy) {
    rows.push(['已移除的旧日期', `${esc(d.date_legacy)}（无法证明是发布日期，仅保留核对）`]);
  }
  rows.push(['入库时间', esc(when(d.created_at))]);
  return rows.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('');
}
async function showSource(id, quote = '') {
  const sourceRequest = (state.sourceRequest || 0) + 1;
  state.sourceRequest = sourceRequest;
  const dialog = $('#source-dialog');
  $('#source-title').textContent = '原始资料';
  $('#source-content').innerHTML = '<div class="loading">正在读取原文…</div>';
  if (!dialog.open) {
    dialog.showModal();
  }
  try {
    const d = await api(`/documents/${id}`);
    if (sourceRequest !== state.sourceRequest || !dialog.open) {
      return;
    }
    const at = quote ? d.body.indexOf(quote) : -1;
    const text = at >= 0
      ? `${readingEsc(d.body.slice(0, at))}<mark id="source-quote">${readingEsc(quote)}</mark>${readingEsc(d.body.slice(at + quote.length))}`
      : readingEsc(d.body);
    const quoteTools = !quote ? '' : at >= 0
      ? '<button type="button" class="secondary small" id="jump-quote">跳到引用位置</button>'
      : '<p class="notice-inline" role="note">原文已变化，未能定位该引用片段，请人工核对。</p>';
    const kwHtml = d.zh_keywords ? d.zh_keywords.split(/[、,，;；]+/).filter(Boolean).map((k) => `<span class="kw-chip">${esc(k.trim())}</span>`).join('') : '';
    const zhBlock = (d.zh_summary || d.zh_keywords) ? `<section class="detail-zh-card"><h3>中文摘要与检索关键词 <small>AI 生成，仅作检索辅助</small></h3>${d.zh_summary ? `<p class="detail-zh-summary">${esc(d.zh_summary)}</p>` : ''}${kwHtml ? `<div class="detail-zh-keywords">${kwHtml}</div>` : ''}</section>` : '';
    const metaGrid = `<dl class="detail-meta-grid"><div><dt>资料编号</dt><dd>#${d.id}（${d.kind === 'knowledge' ? '知识库法规/参考资料' : d.kind === 'supplement' ? '关联补充材料' : '待分析业务资料'}${d.kind_label ? ` · ${esc(d.kind_label)}` : ''}）</dd></div>${sourceDateRows(d)}<div><dt>信息来源</dt><dd>${esc(d.source || '未填写')}</dd></div><div><dt>正文规模</dt><dd>${(d.body?.length || 0).toLocaleString('zh-CN')} 字符 · 共 ${d.chunks?.length || 1} 个检索分段</dd></div></dl>`;
    const quarantine = d.quarantined_at ? `<div class="notice-inline" role="note">资料已隔离，不计入统计、列表和简报，也不能进入分析。原因：${esc(d.quarantine_reason || '未填写')}</div>` : '';
    const analyses = d.kind === 'event' || d.analyses?.length
      ? `<h3>分析记录</h3>${d.analyses.length ? d.analyses.map((a) => `<p class="form-note">v${a.version} · ${badge(a.decision)} · ${esc(a.model)} · ${when(a.created_at)} · 规则 ${esc(a.rule_version)}${a.result.rules_snapshot_origin==='upgrade'?'（升级时固定）':''}${a.result.supplement_document_ids?.length?` · 补证材料 ${a.result.supplement_document_ids.map(id=>'#'+id).join('、')}`:''}${a.decision==='insufficient'?` · <a href="#evidence/${a.id}" data-history>进入补证</a>`:''}<br>${esc(a.result.reason || a.result.parts?.map((p) => p.reason).join('；') || '查看风险列表中的分析结果。')}</p>`).join('') : '<p class="muted">尚无分析记录。</p>'}`
      : '';
    $('#source-title').textContent = d.kind === 'knowledge' ? '知识库资料详情' : d.kind === 'supplement' ? '补充材料详情' : '业务资料与分析详情';
    await ensureLegalSchema();
    if(sourceRequest !== state.sourceRequest || !dialog.open) return;
    $('#source-content').innerHTML = `<h2>${esc(d.title)}${demoTag(d.demo)}${quarantineTag(d)}</h2>${quarantine}${metaGrid}<div class="actions source-actions">${quoteTools}${d.filename ? `<a class="secondary small" href="api/documents/${d.id}/file">下载原始快照/附件</a>` : ''}${d.url ? `<a class="secondary small" href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">打开原始网页链接 ↗</a>` : ''}</div>${legalMetadataHtml(d)}${zhBlock}<h3>原始全文（${(d.body?.length || 0).toLocaleString('zh-CN')} 字符）</h3><div class="source-body">${text}</div>${analyses}`;
    $('#source-content .source-actions').insertAdjacentHTML('afterend',documentMetadataEditor(d));
    bindLegalMetadata(d);
    bindDocumentMetadata(d);
    $$('[data-history]',dialog).forEach(link=>link.onclick=()=>dialog.close());
    const history = d.analyses.filter((a) => a.events?.length);
    if (history.length) {
      $('#source-content').insertAdjacentHTML('beforeend', `<h3>各版本风险事件</h3>${history.map((a) => `<div class="version-links"><small>v${a.version}</small>${a.events.map((e) => `<a href="#event/${e.id}" data-history>${esc(e.title)}</a>`).join('')}</div>`).join('')}`);
      $$('[data-history]', dialog).forEach((a) => {
        a.onclick = () => dialog.close();
      });
    }
    $('#jump-quote')?.addEventListener('click', () => $('#source-quote')?.scrollIntoView({ block: 'start' }));
    dialog.scrollTop = 0;
    $('#source-content').scrollTop = 0;
  } catch (e) {
    if (sourceRequest === state.sourceRequest && dialog.open) {
      $('#source-content').innerHTML = errorBox(e.message);
    }
  }
}
async function analyze(ids,button){
  if(!ids.length){toast('请先选择需要分析的资料。');return;}
  if(button)button.disabled=true;
  try{
    const result=await api('/jobs',{method:'POST',body:{document_ids:ids}});
    toast(`已启动 ${result.items.length} 条资料的后台风险分析，当前列表将实时刷新进度。`);
    if(state.route==='documents')await render({quiet:true});else location.hash='#documents';
  }catch(e){toast(e.message);if(button)button.disabled=false;}
}
function bind(){
  $$('[data-scope]').forEach(b=>b.onclick=()=>{state.scope=b.dataset.scope;state.page=1;if(state.route==='event'||state.route==='events')openEvents(state.route==='event'?{}:state.filter);else render();});
  $$('[data-page]').forEach(b=>b.onclick=()=>{state.page=Number(b.dataset.page);navigateList();});
  $$('[data-source]').forEach(b=>b.onclick=()=>showSource(b.dataset.source,b.dataset.quote));
  $$('[data-analyze]').forEach(b=>b.onclick=()=>analyze([Number(b.dataset.analyze)],b));
  $$('[data-delete-doc]').forEach(b=>b.onclick=async()=>{if(!confirm(`删除资料“${b.dataset.title}”？
它的文本片段、中文摘要、分析结果和风险事件会一并删除，无法恢复。`))return;b.disabled=true;try{const r=await api('/documents/'+b.dataset.deleteDoc,{method:'DELETE'});toast(r.events?`已删除资料及 ${r.events} 条风险事件`:'资料已删除');await render({quiet:true});}catch(e){toast(e.message);b.disabled=false;}});
  $$('[data-refresh]').forEach(b=>b.onclick=()=>render({quiet:true}));
  $$('[data-zh-expand]').forEach((b) => {
    b.onclick = () => {
      const summary = b.parentElement.querySelector('.zh-summary-clamp');
      const expanded = summary.classList.toggle('is-expanded');
      b.textContent = expanded ? '收起' : '展开';
    };
  });
  $$('[data-demo]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const d=await api('/demo',{method:'POST'});toast(`已载入 ${d.added} 条虚构演示案例`);await render({quiet:true});}catch(e){toast(e.message);b.disabled=false;}});
  $('#event-filter')?.addEventListener('submit',e=>{e.preventDefault();state.filter=Object.fromEntries(new FormData(e.currentTarget));state.page=1;openEvents(state.filter);});
  $('#event-filter [name=family]')?.addEventListener('change',()=>{const form=$('#event-filter');state.filter=Object.fromEntries(new FormData(form));if(state.filter.category&&familyOf(state.filter.category)!==state.filter.family)delete state.filter.category;state.page=1;openEvents(state.filter);});
  $('#clear-filter')?.addEventListener('click',()=>{state.filter={};state.page=1;openEvents();});
  $('#document-filter')?.addEventListener('submit',e=>{e.preventDefault();state.filter=Object.fromEntries(new FormData(e.currentTarget));state.page=1;navigateList();});
  $$('[data-import-mode]').forEach(b=>b.onclick=()=>{state.importMode=b.dataset.importMode;render();});
  $('#select-all')?.addEventListener('change',e=>$$('[name=doc-select]:not(:disabled)').forEach(c=>c.checked=e.target.checked));
  $('#analyze-selected')?.addEventListener('click',e=>analyze($$('[name=doc-select]:checked').map(c=>Number(c.value)),e.currentTarget));
  $('#import-form')?.addEventListener('submit',async e=>{
    e.preventDefault();const form=e.currentTarget;const values=new FormData(form);const legalMetadata=takeLegalImport(values);const button=$('[type=submit]',form);button.disabled=true;$('#import-result').innerHTML='';
    try{
      let message;
      const confirmAnalysis=form.dataset.kind==='event';
      let analyzeIds=[];
      if(state.importMode==='file'){
        values.set('kind',form.dataset.kind);
        values.set('legal_metadata',JSON.stringify(legalMetadata));
        const result=await api('/import',{method:'POST',body:values});
        const failed=result.results.filter(r=>r.status==='failed');const dup=result.results.filter(r=>r.status==='duplicate');
        analyzeIds=result.results.filter(r=>r.id&&r.status==='created').map(r=>r.id);
        message=`导入完成：新增 ${result.created} 条，重复 ${dup.length} 条，失败 ${failed.length} 条。`;
        sessionStorage.setItem('importFeedback',JSON.stringify({route:state.route,message,failed}));
      }else{
        const record=Object.fromEntries(values);delete record.auto_analyze;record.kind=form.dataset.kind;record.legal_metadata=legalMetadata;
        const result=await api('/documents',{method:'POST',body:record});
        if(result.id&&result.created)analyzeIds=[result.id];
        message=result.created?'资料已保存。':'资料已存在，没有重复导入。';
        sessionStorage.setItem('importFeedback',JSON.stringify({route:state.route,message,failed:[]}));
      }
      if(confirmAnalysis&&analyzeIds.length){
        message+=' 请核对资料正文与企业范围后，确认提交分析。';
        if(analyzeIds.length>100)message+=' 本次先确认前100条，其余资料请在列表分批选择。';
        const fb=JSON.parse(sessionStorage.getItem('importFeedback')||'null');
        if(fb){fb.message=message;sessionStorage.setItem('importFeedback',JSON.stringify(fb));}
      }
      toast(message);await render({quiet:true});
      if(confirmAnalysis&&analyzeIds.length)await inspectAnalysis(analyzeIds.slice(0,100),$('#import-form [type=submit]'));
    }catch(error){$('#import-result').innerHTML=errorBox(error.message);button.disabled=false;}
  });
  let feedback=null;try{feedback=JSON.parse(sessionStorage.getItem('importFeedback')||'null');}catch{sessionStorage.removeItem('importFeedback');}
  if(feedback&&feedback.route===state.route&&$('#import-result')){$('#import-result').innerHTML=`<div class="success">${esc(feedback.message)}</div>${feedback.failed.length?'<ul class="result-list">'+feedback.failed.map(r=>`<li>第 ${r.row} 行：${esc(r.error)}</li>`).join('')+'</ul>':''}`;sessionStorage.removeItem('importFeedback');}
  $('#review-form')?.addEventListener('submit',async e=>{
    e.preventDefault();const form=e.currentTarget;const b=$('[type=submit]',form);b.disabled=true;
    try{await api(`/events/${form.dataset.id}/review`,{method:'PUT',body:Object.fromEntries(new FormData(form))});toast('复核意见已保存');await render({quiet:true});}catch(err){$('#review-error').innerHTML=errorBox(err.message);b.disabled=false;}
  });
}
$('#close-source').onclick=()=>$('#source-dialog').close();
$('#logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});await boot();}catch(e){toast(e.message);}};
window.addEventListener('hashchange',render);
document.addEventListener('click', (event) => {
  $$('.scope-picker[open]').forEach((picker) => {
    if (!picker.contains(event.target) && !event.target.closest('dialog')) {
      picker.open = false;
    }
  });
});
document.addEventListener('keydown', (event) => {
  const picker = $('.scope-picker[open]');
  if (event.key === 'Escape' && picker && !$('dialog[open]')) {
    event.preventDefault();
    picker.open = false;
    $('summary', picker).focus();
  }
});
let polling=false;
function bindDocumentRow(row) {
  $$('[data-analyze]', row).forEach((b) => {
    b.onclick = () => inspectAnalysis([Number(b.dataset.analyze)], b);
  });
  $$('[data-cancel-job]', row).forEach((b) => {
    b.onclick = () => cancelJob(b);
  });
  $$('[data-source]', row).forEach((b) => {
    b.onclick = () => showSource(b.dataset.source, b.dataset.quote);
  });
}
async function refreshDocumentProgress() {
  const { renderId } = state;
  const query = new URLSearchParams({ ...state.filter, kind: 'event', page: state.page });
  const data = await api(`/documents?${query}`);
  if (renderId !== state.renderId || state.route !== 'documents') {
    return;
  }
  data.items.forEach((d) => {
    const row = $(`tr[data-doc-id="${d.id}"]`);
    if (!row) {
      return;
    }
    const cell = $('[data-progress-cell]', row);
    if (cell) {
      cell.innerHTML = docProgressCellHtml(d);
    }
    const actions = $('[data-job-actions]', row);
    if (actions) {
      actions.innerHTML = docJobActionsHtml(d);
      refineComponents(actions);
      bindDocumentRow(actions);
    }
  });
  const shown = $$('tr[data-doc-id]').map((row) => row.dataset.docId).join(',');
  const fresh = data.items.map((d) => String(d.id)).join(',');
  const stale = $('#list-stale');
  if (stale) {
    stale.hidden = shown === fresh;
  }
}
setInterval(async () => {
  if ($('#shell').hidden || polling || document.hidden || state.auth?.role!=='admin') {
    return;
  }
  polling = true;
  try {
    const { active } = await api('/jobs/active');
    $('#job-count').textContent = active || '';
    if (state.route === 'documents' && (active || state.lastActive)) {
      await refreshDocumentProgress();
    }
    state.lastActive = active;
  } catch (_error) {
    // 轮询失败不打断用户；页面级错误由主动操作暴露
  } finally {
    polling = false;
  }
}, 4000);
boot().catch(renderAuthFailure);
