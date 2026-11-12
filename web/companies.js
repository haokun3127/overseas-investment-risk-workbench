'use strict';
let companyData={items:[],active_id:null,scoped:false};
let companyMenuDismissBound=false;
const companyLabels={name:'公司名称',industry:'所属行业',business:'主营业务与产品',location:'印尼投资地区',stage:'投资阶段',investment:'投资规模',entity:'当地实体与股权结构',workforce:'员工与用工情况',supply_chain:'供应链与进出口',licenses:'许可与合规情况',concerns:'重点关注风险',notes:'补充说明'};
async function loadCompanies() {
  companyData = await api('/companies');
  const active = companyData.items.find((c) => c.id === companyData.active_id);
  state.company = active || (companyData.scoped ? companyData.items[0] : null) || null;
}
function companyPanel(options = {}) {
 const c=state.company;
 const scoped=Boolean(companyData.scoped);
 const compact=Boolean(options.compact);
 const actionsHtml=scoped
   ? (c?`<button class="secondary small" id="company-edit">修改本公司信息</button><button class="primary small" id="company-sync">同步至知识库</button>`:'')
   : `<label class="field">当前公司<select id="company-select" aria-label="当前公司"><option value="">全部企业</option>${companyData.items.map(i=>`<option value="${i.id}" ${i.id===c?.id?'selected':''}>${esc(i.name)}</option>`).join('')}</select></label><button class="secondary small" id="company-new">新增公司</button>${c?'<button class="secondary small" id="company-edit">修改信息</button><button class="primary small" id="company-sync">放入知识库</button>':''}`;
 const noteHtml=scoped
   ? '<p class="form-note">当前为企业专属工作区：您仅能查看和维护本公司信息、本公司导入的资料、分析任务及风险预警结果；平台公共法律法规知识库已自动为您挂载。</p>'
   : '<p class="form-note">选择企业后，风险总览与风险事件显示该企业的数据；选择全部企业可查看汇总。</p>';
 if (compact) {
   const emptyCopy = companyData.items.length
     ? '当前查看全部企业；新增资料前请选择所属企业。'
     : '还没有公司档案。先新增公司，填写行业、地区、投资阶段和重点关注风险。';
   const summary = c
     ? `${esc(c.name)} · ${esc(c.industry || '行业待补充')} · ${c.document_id ? '已入知识库' : '尚未放入知识库'}`
     : emptyCopy;
   const compactControls = scoped
     ? `<div class="company-current-static"><span>本公司</span><strong>${esc(c?.name||'尚未创建公司档案')}</strong></div>${c?`<details class="company-admin-menu"><summary>管理公司${icon('arrow')}</summary><div><button class="text-button" type="button" id="company-edit">修改信息</button><button class="text-button" type="button" id="company-sync">放入知识库</button></div></details>`:''}`
     : `<label class="company-picker"><span>当前公司</span><select id="company-select" aria-label="当前公司"><option value="">全部企业</option>${companyData.items.map(i=>`<option value="${i.id}" ${i.id===c?.id?'selected':''}>${esc(i.name)}</option>`).join('')}</select></label><details class="company-admin-menu"><summary>管理公司${icon('arrow')}</summary><div><button class="text-button" type="button" id="company-new">新增公司</button>${c?'<button class="text-button" type="button" id="company-edit">修改信息</button><button class="text-button" type="button" id="company-sync">放入知识库</button>':''}</div></details>`;
   return `<section class="panel company-panel is-compact">
     <div class="company-compact-row">
       <div class="company-compact-title">
         <span class="company-compact-icon" aria-hidden="true">${icon('overview')}</span>
         <div><h2>${scoped?'本公司信息档案':'企业范围与档案'}</h2><p>${scoped?'维护贵司在印尼的投资与经营背景，用于精准风险研判':'切换企业查看对应风险，并维护企业档案'}</p></div>
       </div>
       <div class="company-compact-controls">${compactControls}</div>
     </div>
     <p class="company-compact-note">${summary}</p>
   </section>`;
 }
 return `<section class="panel company-panel"><div class="panel-heading"><div><h2>${scoped?'本公司信息档案':'企业范围与档案'}</h2><small>${scoped?'维护贵司在印尼的投资与经营背景，用于精准风险研判':'切换企业查看对应风险，并维护企业档案'}</small></div><div class="actions">${actionsHtml}</div></div><div class="panel-content">${c?`<div class="company-summary">${Object.entries(companyLabels).map(([k,l])=>`<div><span>${l}</span><p>${esc(c[k]||'待补充')}</p></div>`).join('')}</div><p class="form-note">${c.document_id?'已入知识库 · 修改后自动同步同一条档案':'尚未放入知识库'} ｜ 更新：${when(c.updated_at)}</p>`:`<p class="muted">${companyData.items.length?'当前查看全部企业；新增资料前请选择所属企业。':'还没有公司档案。先新增公司，填写行业、地区、投资阶段和重点关注风险。'}</p>`}${noteHtml}</div></section>`;
}
const companyGroups = [
  ['01', '基本信息', '名称、行业与投资概况', ['name', 'industry', 'location', 'stage', 'investment']],
  ['02', '经营与结构', '业务、实体、用工与供应链', ['business', 'entity', 'workforce', 'supply_chain']],
  ['03', '合规与关注', '许可现状与重点风险', ['licenses', 'concerns', 'notes']],
];
const companyTextareas = ['business', 'entity', 'workforce', 'supply_chain', 'licenses', 'concerns', 'notes'];
const companyWide = ['business', 'supply_chain', 'licenses', 'concerns', 'notes'];
function companyField(c, key) {
  const label = companyLabels[key];
  const value = esc(c[key] || '');
  let control = '';
  if (companyTextareas.includes(key)) {
    control = `<textarea name="${key}" rows="2" maxlength="${['entity', 'workforce'].includes(key) ? 2000 : 3000}">${value}</textarea>`;
  } else {
    let max = 500;
    if (key === 'name') {
      max = 150;
    } else if (key === 'industry' || key === 'stage') {
      max = 200;
    }
    control = `<input name="${key}" value="${value}" maxlength="${max}" ${key === 'name' ? 'required autofocus' : ''}>`;
  }
  const mark = key === 'name' ? '<span class="req-mark" aria-hidden="true">*</span>' : '';
  return `<label class="field ${companyWide.includes(key) ? 'full' : ''}"><span>${label}${mark}</span>${control}</label>`;
}
function editCompany(c={}){
 const dialog=$('#company-dialog');
 const title = c.id ? '修改公司信息' : '新增公司';
 const groups = companyGroups.map(([index, name, hint, keys]) => `<fieldset class="dossier-group"><legend><span class="dossier-index" aria-hidden="true">${index}</span>${name}<small>${hint}</small></legend>`
   + `<div class="form-grid">${keys.map((key) => companyField(c, key)).join('')}</div></fieldset>`).join('');
 $('#company-editor').innerHTML = `<header class="dialog-head"><div><p class="dialog-eyebrow"><span class="label-dot" aria-hidden="true"></span>COMPANY DOSSIER · 公司档案</p>`
   + `<h2 id="company-dialog-title">${title}</h2><p class="dialog-sub">${c.id ? `${esc(c.name || '')} · 更新于 ${when(c.updated_at)}` : '填写在印尼的投资与经营背景，用于风险研判'}</p></div>`
   + `<button type="button" class="dialog-close" id="company-close" aria-label="关闭">${icon('close')}<span>关闭</span></button></header>`
   + `<form id="company-form" class="dialog-form"><div class="dialog-scroll">${groups}`
   + `<div id="company-error" role="alert"></div></div>`
   + '<div class="dialog-foot"><span class="dialog-foot-note">带 * 为必填 · 保存后用于此后提交的分析</span><button type="button" class="secondary" data-company-cancel>取消</button><button class="primary" type="submit">保存公司信息</button></div></form>';
 $('#company-close').onclick=()=>dialog.close();
 $('[data-company-cancel]').onclick = () => dialog.close();
 $('#company-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=$('[type=submit]',f);b.disabled=true;const values=new FormData(f);const body=Object.fromEntries(values);try{await api('/companies'+(c.id?'/'+c.id:''),{method:c.id?'PUT':'POST',body});dialog.close();toast('公司信息已保存'+(c.document_id?'，知识库已同步':''));await render();}catch(err){$('#company-error').textContent=err.message;b.disabled=false;}};
 dialog.showModal();
}
function bindCompanies(){
 if(state.auth?.role==='admin'&&$('#company-new')&&!$('#company-accounts')){
   const button=document.createElement('button');button.id='company-accounts';button.type='button';
   button.className='text-button';button.textContent='企业账号';button.onclick=openCompanyAccounts;
   $('#company-new').parentElement.append(button);
 }
 if(!companyMenuDismissBound){
   const dismissCompanyMenu=e=>{
     const menu=document.querySelector('.company-admin-menu[open]');
     if(!menu||(e.type==='pointerdown'&&menu.contains(e.target)))return;
     menu.open=false;
   };
   document.addEventListener('pointerdown',dismissCompanyMenu);
   document.addEventListener('keydown',e=>{if(e.key==='Escape')dismissCompanyMenu(e)});
   companyMenuDismissBound=true;
 }
 $('#company-new')?.addEventListener('click',()=>editCompany());
 $('#company-edit')?.addEventListener('click',()=>editCompany(state.company));
 $('#company-select')?.addEventListener('change',async e=>{try{await api(e.target.value?'/companies/'+e.target.value+'/activate':'/companies/active',{method:e.target.value?'POST':'DELETE'});await render();toast(e.target.value?'已切换企业范围':'已切换至全部企业');}catch(err){toast(err.message);}});
 $('#company-sync')?.addEventListener('click',async e=>{e.target.disabled=true;try{await api('/companies/'+state.company.id+'/knowledge',{method:'POST'});toast('公司档案已放入知识库');await render();}catch(err){toast(err.message);e.target.disabled=false;}});
}
async function openCompanyAccounts(){
 const dialog=$('#company-dialog');
 try{
   const data=await api('/company-users');
   $('#company-editor').innerHTML=`<header class="dialog-head"><h2 id="company-dialog-title">企业账号</h2><button type="button" class="secondary" id="accounts-close">关闭</button></header>
   <div class="dialog-scroll"><p>公司用户只能查看绑定企业的风险总览、事件及引用，不能维护知识库或修改事件。</p>
   <form id="company-account-form"><div class="form-grid"><label class="field full">所属企业<select name="company_id" required><option value="">请选择企业</option>${companyData.items.map(c=>`<option value="${c.id}" ${c.id===state.company?.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label>
   <label class="field">登录账号<input name="username" required minlength="3" maxlength="60" autocomplete="off"></label><label class="field">初始密码<input name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password"></label></div><button type="submit" class="primary">开通只读账号</button><div id="account-error" role="alert"></div></form>
   <h3>已开通账号</h3>${data.items.length?data.items.map(u=>`<p>${esc(u.username)} · ${esc(u.company_name)}</p>`).join(''):'<p>尚未开通公司账号。</p>'}</div>`;
   $('#accounts-close').onclick=()=>dialog.close();
   $('#company-account-form').onsubmit=async event=>{
     event.preventDefault();const form=event.currentTarget,button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;
     const body=Object.fromEntries(new FormData(form));body.company_id=Number(body.company_id);
     try{await api('/company-users',{method:'POST',body});form.reset();toast('企业只读账号已开通');await openCompanyAccounts();}
     catch(error){$('#account-error').innerHTML=errorBox(error.message);button.disabled=false;}
   };
   if(!dialog.open)dialog.showModal();
 }catch(error){toast(error.message);}
}
