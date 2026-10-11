'use strict';
// Workspace composition keeps the existing routes, API and full-detail links intact.
let previewRequest=0;
const previewDrafts=new Map();
const mobileWorkspace=window.matchMedia('(max-width:700px)');
function sizeInspection(){
  const panel=$('.inspection-panel');if(!panel||panel.hidden)return;
  panel.style.setProperty('--inspection-height',`${Math.max(360,innerHeight-Math.max(20,panel.getBoundingClientRect().top)-20)}px`);
}
window.addEventListener('resize',sizeInspection);
function syncNavigation(){
  const toggle=$('#toggle-navigation');if(!toggle)return;
  const expanded=mobileWorkspace.matches?document.body.classList.contains('mobile-navigation-open'):!document.body.classList.contains('navigation-collapsed');
  toggle.setAttribute('aria-expanded',String(expanded));
  toggle.setAttribute('aria-label',mobileWorkspace.matches?(expanded?'关闭菜单':'打开菜单'):(expanded?'收起导航':'展开导航'));
  $$('[data-responsive-details]').forEach(details=>{details.open=!mobileWorkspace.matches;});
}
mobileWorkspace.addEventListener('change',syncNavigation);
function composeWorkspace(route,html){
  const root=document.createElement('div');root.innerHTML=html;
  root.className=`workspace-page page-${route}`;
  if(route==='overview'){
    const board=document.createElement('div');board.className='analysis-board';
    const left=document.createElement('div');left.className='analysis-primary';
    const right=document.createElement('div');right.className='analysis-rail';
    const network=root.querySelector('.network-panel');
    root.querySelector('.situation-grid').before(root.querySelector('.stats'));
    const heading=network.querySelector('.panel-heading');
    heading.querySelector('small').remove();
    heading.insertAdjacentHTML('beforeend','<div class="chart-switch" role="group" aria-label="风险分布展示方式"><button type="button" data-chart-view="network" aria-pressed="true">分布图</button><button type="button" data-chart-view="rank" aria-pressed="false">分类排行</button></div>');
    const ranks=document.createElement('div');ranks.className='category-ranking';ranks.hidden=true;
    const categories=[...network.querySelectorAll('.network-mobile-list a')];
    const counts=categories.map(a=>Number(a.querySelector('strong').firstChild.textContent));
    const max=Math.max(1,...counts);
    ranks.innerHTML=categories.map((a,i)=>`<a class="rank-row" href="${esc(a.getAttribute('href'))}"><span>${esc(a.querySelector('span').textContent)}</span><strong>${counts[i]} <small>条</small></strong><progress class="rank-track" value="${counts[i]}" max="${max}" aria-label="${esc(a.querySelector('span').textContent)}：${counts[i]}条"></progress></a>`).join('')||'<p class="muted">完成分析后展示分类排行。</p>';
    const footnote=network.querySelector('.chart-footnote');
    if(footnote)footnote.before(ranks);
    else heading.querySelector('.chart-switch').remove();
    left.append(network,root.querySelector('.events-panel'));
    right.append(root.querySelector('.review-panel'),root.querySelector('.severity-panel'));
    board.append(left,right);root.querySelector('.situation-grid').before(board);
    root.querySelector('.situation-grid').remove();root.querySelector('.overview-grid').remove();
  }
  if(route==='event'){
    const grid=root.querySelector('.detail-grid');
    const columns=[...grid.children];
    const [summary,review]=[...columns[0].children];
    const [evidence,record]=[...columns[1].children];
    summary.classList.add('detail-summary');evidence.classList.add('detail-evidence');review.classList.add('detail-review');record.classList.add('detail-record');
    grid.replaceChildren(summary,evidence,review,record);
  }
  if(route==='events'){
    const panel=root.querySelector('.panel');panel.classList.add('event-results');
    const form=panel.querySelector('form');panel.before(form);
    form.classList.add('workspace-filters');
    const advanced=document.createElement('details');advanced.className='advanced-filters';advanced.dataset.responsiveDetails='';advanced.open=!mobileWorkspace.matches;
    const labels=[...form.querySelectorAll('label:not(.search-field)')];
    const selected=labels.map(label=>label.querySelector('input,select')).filter(control=>control.value);
    advanced.innerHTML=`<summary>筛选条件${selected.length?` · ${selected.length} 项已选`:''}</summary><div class="advanced-fields"></div>`;
    labels.forEach(label=>advanced.querySelector('div').append(label));form.querySelector('.search-field').after(advanced);
    const actions=root.querySelector('.page-heading>.actions');
    const more=document.createElement('details');more.className='event-more-actions';more.dataset.responsiveDetails='';more.open=!mobileWorkspace.matches;
    more.innerHTML='<summary>更多操作</summary><div></div>';
    [...actions.children].filter(a=>!a.getAttribute('href')?.startsWith('#documents')).forEach(a=>more.querySelector('div').append(a));
    actions.prepend(more);actions.querySelector('a[href="#documents"]')?.classList.replace('primary','secondary');
    const layout=document.createElement('div');layout.className='verification-workspace';
    panel.before(layout);layout.append(panel);
    panel.querySelectorAll('tbody tr').forEach(row=>{
      const link=row.querySelector('.event-link');const id=link.getAttribute('href').split('/')[1];
      row.dataset.previewRow=id;
      row.querySelector('.source-line').insertAdjacentHTML('afterend',`<button type="button" class="preview-button" data-preview="${esc(id)}" aria-label="就地核验：${esc(link.textContent)}" aria-pressed="false">就地核验 →</button>`);
    });
    layout.insertAdjacentHTML('beforeend','<aside class="inspection-panel" aria-label="事件核验面板" hidden></aside>');
  }
  if(route==='documents'||route==='knowledge'){
    const tools=root.querySelector('.split');const list=[...root.children].find(n=>n.matches('section.panel'));
    if(tools&&list){
      const layout=document.createElement('div');layout.className='library-workbench';tools.before(layout);
      list.classList.add('library-list');tools.classList.add('library-tools');layout.append(list,tools);
      tools.querySelectorAll('li').forEach(li=>{li.textContent=li.textContent.replace('在下方资料列表启动分析','在资料列表选择内容并启动分析');});
      const results=root.querySelector('#knowledge-results');if(results)list.after(results);
    }
  }
  refineComponents(root);
  return root.outerHTML;
}
function refineComponents(root){
  root.querySelectorAll('table').forEach(table=>{
    table.classList.add('responsive-table');table.setAttribute('role','table');
    const labels=[...table.querySelectorAll('thead th')].map(th=>th.textContent.trim());
    table.querySelectorAll('tbody tr').forEach(row=>{
      row.setAttribute('role','row');
      [...row.cells].forEach((cell,i)=>{cell.dataset.label=labels[i]||'选择资料';cell.setAttribute('role','cell');});
      const title=row.querySelector('.title-cell')||row.cells[0];title.classList.add('mobile-row-title');
    });
  });
  // Enhance visual affordances without changing form names or business handlers.
  const actions=[['导出','download'],['下载','download'],['打印','print'],['保存','save'],['导入','upload'],['分析','analysis'],['查询','search'],['检索','search'],['刷新','refresh'],['更新','refresh'],['重置','refresh'],['收起','close'],['关闭','close']];
  root.querySelectorAll('button.primary,button.secondary,a.primary,a.secondary,button.text-button').forEach(button=>{
    if(button.querySelector('svg'))return;
    const label=button.textContent.trim();const match=actions.find(([word])=>label.startsWith(word));
    if(match)button.insertAdjacentHTML('afterbegin',icon(match[1]));
  });
  root.querySelectorAll('.panel-heading h2').forEach(title=>{
    const value=title.textContent;
    const name=/复核|规则/.test(value)?'check':/资料|导入|参考/.test(value)?'documents':/任务|记录|运行/.test(value)?'jobs':/模型|连接/.test(value)?'server':'overview';
    if(!title.querySelector('svg'))title.insertAdjacentHTML('afterbegin',icon(name));
  });
  root.querySelectorAll('.filters input[name="q"]').forEach(input=>{
    const wrapper=document.createElement('span');wrapper.className='search-control';
    input.before(wrapper);wrapper.append(input);wrapper.insertAdjacentHTML('afterbegin',icon('search'));
  });
  root.querySelectorAll('label.field:has([required])').forEach(label=>label.classList.add('required-field'));
  root.querySelectorAll('.library-list .title-cell').forEach(cell=>{
    const wrap=document.createElement('div');wrap.className='document-cell';
    const content=document.createElement('div');content.className='document-cell-content';
    while(cell.firstChild)content.append(cell.firstChild);
    wrap.innerHTML=`<span class="document-glyph" aria-hidden="true">${icon('documents')}</span>`;
    wrap.append(content);cell.append(wrap);
  });
  root.querySelectorAll('.upload-area').forEach(area=>{
    area.insertAdjacentHTML('afterbegin',`<span class="upload-glyph" aria-hidden="true">${icon('upload')}</span>`);
    const input=area.querySelector('input[type=file]');
    if(input){input.classList.add('file-native');input.setAttribute('aria-label','选择导入文件');area.insertAdjacentHTML('beforeend','<span class="file-picker-label">浏览本地文件</span><span class="file-selection" aria-live="polite">尚未选择文件</span>');}
  });
  root.querySelectorAll('.inspection-symbol').forEach(e=>{e.setAttribute('aria-hidden','true');e.innerHTML=icon('source');});
  root.querySelectorAll('.preview-button').forEach(b=>{b.innerHTML=icon('source')+'就地核验'+icon('arrow');});
}
async function openInspection(id){
  const panel=$('.inspection-panel');if(!panel)return;
  const request=++previewRequest;
  panel.hidden=false;panel.closest('.verification-workspace').classList.add('has-inspection');
  sizeInspection();
  panel.innerHTML='<div class="loading" role="status">正在读取事件与证据…</div>';
  $$('[data-preview]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.preview===id)));
  $$('[data-preview-row]').forEach(r=>r.classList.toggle('selected-event',r.dataset.previewRow===id));
  try{
    const e=await api('/events/'+encodeURIComponent(id));
    if(request!==previewRequest||!panel.isConnected)return;
    const draft=previewDrafts.get(id);
    panel.innerHTML=`<div class="inspection-top"><span>事件核验 <small>#${e.id}</small></span><button class="text-button" data-close-inspection>收起</button></div><div class="inspection-body"><div class="metadata">${badge(e.level)}${badge(e.review_status)}${demoTag(e.demo)}</div><h2>${esc(e.title)}</h2><p class="inspection-meta">${esc(e.category)} · ${esc(e.date||'日期未注明')}<br>${esc(e.source||'来源未填写')}</p>${!e.is_latest?'<p class="notice-inline">历史分析版本，请核对最新结果。</p>':''}${e.result.partial_context?'<p class="notice-inline">长资料分段分析，跨段关联需人工核验。</p>':''}<div class="inspection-sections">${[['风险摘要',e.summary],['潜在影响',e.impact],['应对建议',e.recommendation]].map(([label,value])=>`<section><h3>${label}</h3><p>${esc(value)}</p></section>`).join('')}</div><h3 class="evidence-heading">引用依据 <small>${e.evidence.length} 条</small></h3>${e.evidence.map((r,i)=>`<article class="inspection-evidence"><small>引用 ${i+1} · ${esc(r.reference)}</small><h3>${esc(r.title)}</h3><blockquote>${esc(r.quote)}</blockquote><p>${esc(r.reason)}</p><small>${esc(r.locator)}</small>${sourceButton(r.document_id,'定位原文',r.quote)}</article>`).join('')||'<p class="muted">暂无引用依据，请进入完整详情核查。</p>'}<form id="inspection-review"><h3>记录业务复核</h3><label class="field">复核结论<select name="status">${['pending','accepted','needs_change'].map(s=>`<option value="${s}" ${(draft?.status||e.review_status)===s?'selected':''}>${statuses[s]}</option>`).join('')}</select></label><label class="field">复核意见<textarea name="note" rows="3" maxlength="2000" placeholder="记录判断与需要补充的资料">${esc(draft?.note??e.review_note)}</textarea></label><div class="form-actions"><button class="primary" type="submit">保存复核</button><a href="#event/${e.id}">完整详情与历史</a></div><p class="draft-hint">未保存意见在当前页面会话内暂存。</p><div id="inspection-feedback" role="status"></div></form></div>`;
    $$('[data-source]',panel).forEach(b=>b.onclick=()=>showSource(b.dataset.source,b.dataset.quote));
    $('[data-close-inspection]',panel).onclick=()=>{++previewRequest;panel.hidden=true;panel.closest('.verification-workspace').classList.remove('has-inspection');panel.innerHTML='';$$('[data-preview]').forEach(b=>b.setAttribute('aria-pressed','false'));$$('.selected-event').forEach(r=>r.classList.remove('selected-event'));$(`[data-preview="${id}"]`)?.focus();};
    const form=$('#inspection-review');
    const sections=$('.inspection-sections',panel);sections.id='inspection-judgment';
    $('.evidence-heading',panel).id='inspection-evidence';
    $('.inspection-top',panel).insertAdjacentHTML('afterend','<nav class="inspection-jumps" aria-label="核验内容定位"><button type="button" data-inspection-target="inspection-judgment">判断</button><button type="button" data-inspection-target="inspection-evidence">依据</button><button type="button" data-inspection-target="inspection-review">复核</button></nav>');
    $$('[data-inspection-target]',panel).forEach(button=>button.onclick=()=>$('#'+button.dataset.inspectionTarget,panel).scrollIntoView({block:'start'}));
    const footer=document.createElement('div');footer.className='inspection-savebar';
    const save=$('[type=submit]',form);save.setAttribute('form','inspection-review');
    footer.append($('#inspection-feedback',form),$('.form-actions',form));panel.append(footer);
    footer.querySelector('.form-actions').insertAdjacentHTML('beforeend','<button type="button" class="secondary" data-next-review>下一条待复核</button>');
    $('[data-next-review]',footer).onclick=()=>{const row=$$('[data-preview-row]').find(row=>row.dataset.previewRow!==String(id)&&row.querySelector('.badge.pending'));if(row)openInspection(row.dataset.previewRow);else toast('当前列表没有其他待复核事件。');};
    form.oninput=()=>previewDrafts.set(id,Object.fromEntries(new FormData(form)));
    form.onsubmit=async event=>{
      event.preventDefault();const button=save;button.disabled=true;
      const values=Object.fromEntries(new FormData(form));
      $$('input,select,textarea',form).forEach(control=>control.disabled=true);
      try{
        await api(`/events/${e.id}/review`,{method:'PUT',body:values});previewDrafts.delete(id);
        if(!form.isConnected)return;
        $('#inspection-feedback',panel).innerHTML='<div class="success">复核已保存。</div>';
        const row=$(`[data-preview-row="${id}"]`);if(row)row.cells[3].innerHTML=badge(values.status);
        const meta=$('.metadata',panel);meta.innerHTML=badge(e.level)+badge(values.status)+demoTag(e.demo);
      }catch(err){if(form.isConnected)$('#inspection-feedback',panel).innerHTML=errorBox(err.message);}
      finally{if(button.isConnected){button.disabled=false;$$('input,select,textarea',form).forEach(control=>control.disabled=false);}}
    };
    if(matchMedia('(max-width: 1100px)').matches)panel.scrollIntoView({block:'start'});
  }catch(err){if(request===previewRequest&&panel.isConnected)panel.innerHTML=errorBox(err.message)+'<button class="secondary" data-retry-inspection>重新读取</button>';const retry=$('[data-retry-inspection]',panel);if(retry)retry.onclick=()=>openInspection(id);}
}
function bindWorkspace(){
  ++previewRequest;
  const file=$('.file-native');
  if(file)file.addEventListener('change',()=>{
    const selected=file.files[0];const area=file.closest('.upload-area');
    area.classList.toggle('has-file',Boolean(selected));
    $('.file-selection',area).textContent=selected?`${selected.name} · ${selected.size<1048576?Math.ceil(selected.size/1024)+' KB':(selected.size/1048576).toFixed(1)+' MB'}`:'尚未选择文件';
    $('.file-picker-label',area).textContent=selected?'重新选择文件':'浏览本地文件';
  });
  $$('[data-preview]').forEach(b=>b.onclick=()=>openInspection(b.dataset.preview));
  $$('[data-chart-view]').forEach(b=>b.onclick=()=>{
    const rank=b.dataset.chartView==='rank';
    $('.signal-canvas').hidden=rank;$('.category-ranking').hidden=!rank;
    $$('[data-chart-view]').forEach(t=>t.setAttribute('aria-pressed',String(t===b)));
  });
  const toggle=$('#toggle-navigation');
  toggle.onclick=()=>{
    if(window.matchMedia('(max-width:700px)').matches){
      const open=document.body.classList.toggle('mobile-navigation-open');
      toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'关闭菜单':'打开菜单');return;
    }
    const collapsed=document.body.classList.toggle('navigation-collapsed');
    toggle.setAttribute('aria-expanded',String(!collapsed));
    toggle.setAttribute('aria-label',collapsed?'展开导航':'收起导航');
  };
  syncNavigation();
  $$('[data-nav]').forEach(a=>a.addEventListener('click',()=>{if(mobileWorkspace.matches){document.body.classList.remove('mobile-navigation-open');syncNavigation();}}));
}
