/*
THESIS: Match the stored warning grade to traceable enterprise and state reference actions.
OWN-WORLD: Extend the existing ink, paper and tide workbench with its type, controls and risk badges.
STORY: Choose a grade, read the original actions by responsible party, and open the source document.
FIRST VIEWPORT: Five grade choices, the selected standard, then two plain role columns; no invented score.
FORM: A reference section inside the existing workspace, with a dedicated index and report appendix.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
*/
function countermeasureSourceHtml(source, print=false){
  if(!source)return '';
  const label=`《${source.title}》 · ${source.section} · ${source.version}`;
  return `<p class="cm-source">来源：${esc(label)}${print?'':`<a class="text-button" href="api/countermeasures/source">下载原文 ${icon('download')}</a>`}</p>`;
}

function countermeasureRolesHtml(reference){
  return `<div class="cm-roles">${[['enterprise','企业层面对策','结合本事件选择适用措施'],['state','国家层面对策','需由有权机构评估、协调']].map(([key,title,note])=>`<section class="cm-role" aria-label="${title}"><h3>${title}<span>${reference[key].length} 项</span></h3><p class="cm-role-note">${note}</p><ul>${reference[key].map(item=>`<li><span>${esc(item.text)}</span><small class="cm-locator">${esc(item.locator)}</small></li>`).join('')}</ul></section>`).join('')}</div>`;
}

function countermeasureEventHtml(reference){
  if(!reference)return '';
  if(reference.status!=='available')return `<section class="detail-section cm-event-reference"><h2>分级处置参考</h2><p>${esc(reference.message)}</p><a class="text-button" href="#countermeasures">查看分级对策库 ${icon('arrow')}</a></section>`;
  return `<section class="detail-section cm-event-reference"><div class="cm-section-heading"><h2>分级处置参考</h2>${badge(reference.level)}</div><p class="cm-intro">以下是该等级的原文可选对策，与上方模型建议分别展示。</p>${countermeasureRolesHtml(reference)}${countermeasureSourceHtml(reference.source)}<a class="text-button" href="#countermeasures?level=${encodeURIComponent(reference.level)}">查看完整分级标准 ${icon('arrow')}</a></section>`;
}

function countermeasureInlineLink(reference){
  if(reference?.status==='available')return `<p class="cm-inline-link"><a href="#countermeasures?level=${encodeURIComponent(reference.level)}">查看${esc(levelLabels[reference.level])}的原文对策 ${icon('arrow')}</a><small>企业与国家层面分列，供结合实际选择。</small></p>`;
  return reference?`<p class="cm-inline-link"><small>${esc(reference.message)}</small><a href="#countermeasures">查看分级对策库 ${icon('arrow')}</a></p>`:'';
}

async function countermeasurePage(requestedLevel){
  const library=await api('/countermeasures');
  const title=heading('分级对策库','按预警等级查阅原文中的可选对策，结合具体事件判断适用性。','',false);
  if(library.status!=='available')return title+`<section class="panel"><div class="panel-content">${empty('分级对策原文尚未就绪',esc(library.message),'<button class="secondary" data-refresh>重新读取</button>')}</div></section>`;
  const selected=requestedLevel?library.levels.find(item=>item.level===requestedLevel):library.levels[0];
  const navigation=`<nav class="cm-grade-nav" aria-label="选择预警等级">${library.levels.map(item=>`<a class="cm-grade-link ${selected?.level===item.level?'selected':''}" href="#countermeasures?level=${item.level}" ${selected?.level===item.level?'aria-current="page"':''}>${badge(item.level)}</a>`).join('')}</nav>`;
  if(!selected)return title+navigation+`<section class="panel"><div class="panel-content"><h2>请选择现行五级标准</h2><p>该链接的等级不属于当前五级标准，未自动换算。请在上方选择需要查看的等级。</p></div></section>`;
  return title+navigation+`<section class="panel cm-library-panel"><div class="panel-heading"><h2>${esc(selected.label)}处置参考</h2><span class="cm-original-label">原文参考</span></div><div class="panel-content"><div class="cm-standard"><h3>预警标准</h3><p>${esc(selected.standard)}</p><p class="cm-threshold">原文阈值：${esc(selected.threshold)}<small>这是文件中的标准区间，不是本事件计算得分。</small></p></div>${countermeasureRolesHtml(selected)}${countermeasureSourceHtml(library.source)}</div></section>`;
}

function countermeasureReportHtml(reference){
  if(!reference)return '';
  if(reference.status!=='available')return `<section class="cm-report-reference"><h2>分级处置参考</h2><p>${esc(reference.message)}</p></section>`;
  if(!reference.groups.length&&!reference.unsupported_levels.length)return '';
  return `<section class="cm-report-reference"><div class="brief-section-title"><h2>分级处置参考</h2><span>按本简报涉及的等级汇总</span></div><p class="cm-intro">以下为原文中的可选对策，与逐项事件中的模型建议分列，不代表全部措施均适用。</p>${reference.groups.map(item=>`<section class="cm-report-grade"><h3>${esc(item.label)}</h3>${countermeasureRolesHtml(item)}</section>`).join('')}${reference.unsupported_levels.length?'<p>部分历史记录使用旧标准，未自动套用五级对策；需先复核等级。</p>':''}${countermeasureSourceHtml(reference.source,true)}</section>`;
}
