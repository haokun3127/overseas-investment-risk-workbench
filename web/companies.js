'use strict';
let companyData={items:[],active_id:null};
const companyLabels={name:'公司名称',industry:'所属行业',business:'主营业务与产品',location:'印尼投资地区',stage:'投资阶段',investment:'投资规模',entity:'当地实体与股权结构',workforce:'员工与用工情况',supply_chain:'供应链与进出口',licenses:'许可与合规情况',concerns:'重点关注风险',notes:'补充说明'};
async function loadCompanies(){companyData=await api('/companies');state.company=companyData.items.find(c=>c.id===companyData.active_id)||null;}
function companyPanel(){
 const c=state.company;
 return `<section class="panel company-panel"><div class="panel-heading"><div><h2>公司信息情况预览</h2><small>选择服务公司，维护其在印尼的投资与经营背景</small></div><div class="actions"><label class="field">当前公司<select id="company-select" aria-label="当前公司"><option value="">请选择公司</option>${companyData.items.map(i=>`<option value="${i.id}" ${i.id===c?.id?'selected':''}>${esc(i.name)}</option>`).join('')}</select></label><button class="secondary small" id="company-new">新增公司</button>${c?'<button class="secondary small" id="company-edit">修改信息</button><button class="primary small" id="company-sync">放入知识库</button>':''}</div></div><div class="panel-content">${c?`<div class="company-summary">${Object.entries(companyLabels).map(([k,l])=>`<div><span>${l}</span><p>${esc(c[k]||'待补充')}</p></div>`).join('')}</div><p class="form-note">${c.document_id?'已入知识库 · 修改后自动同步同一条档案':'尚未放入知识库'} ｜ ${c.allow_external?'已允许外部 AI 使用公司背景':'未授权 AI 使用，仅保存和查看'} ｜ 更新：${when(c.updated_at)}</p>`:'<p class="muted">还没有公司档案。先新增公司，填写行业、地区、投资阶段和重点关注风险。</p>'}<p class="form-note">公司切换影响新分析的业务背景；下方事件统计仍为工作台全部资料。</p></div></section>`;
}
function editCompany(c={}){
 const dialog=$('#company-dialog');
 $('#company-editor').innerHTML=`<div class="panel-heading"><h2>${c.id?'修改公司信息':'新增公司'}</h2><button type="button" class="secondary small" id="company-close">关闭</button></div><form id="company-form" class="panel-content"><div class="form-grid">${Object.entries(companyLabels).map(([k,l])=>`<label class="field ${['business','supply_chain','licenses','concerns','notes'].includes(k)?'full':''}">${l}${['business','entity','workforce','supply_chain','licenses','concerns','notes'].includes(k)?`<textarea name="${k}" rows="2" maxlength="${['entity','workforce'].includes(k)?2000:3000}">${esc(c[k]||'')}</textarea>`:`<input name="${k}" value="${esc(c[k]||'')}" maxlength="${k==='name'?150:k==='industry'||k==='stage'?200:500}" ${k==='name'?'required':''}>`}</label>`).join('')}</div><label class="check-field"><input type="checkbox" name="allow_external" ${c.allow_external?'checked':''}><span>允许已配置的外部 AI 服务使用此公司的背景信息。</span></label><div id="company-error" role="alert"></div><div class="form-actions"><button class="primary" type="submit">保存公司信息</button></div></form>`;
 $('#company-close').onclick=()=>dialog.close();
 $('#company-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=$('[type=submit]',f);b.disabled=true;const values=new FormData(f);const body=Object.fromEntries(values);body.allow_external=values.has('allow_external');try{await api('/companies'+(c.id?'/'+c.id:''),{method:c.id?'PUT':'POST',body});dialog.close();toast('公司信息已保存'+(c.document_id?'，知识库已同步':''));await render();}catch(err){$('#company-error').textContent=err.message;b.disabled=false;}};
 dialog.showModal();
}
function bindCompanies(){
 $('#company-new')?.addEventListener('click',()=>editCompany());
 $('#company-edit')?.addEventListener('click',()=>editCompany(state.company));
 $('#company-select')?.addEventListener('change',async e=>{if(!e.target.value)return;try{await api('/companies/'+e.target.value+'/activate',{method:'POST'});await render();toast('已切换公司，后续新分析使用该公司背景');}catch(err){toast(err.message);}});
 $('#company-sync')?.addEventListener('click',async e=>{e.target.disabled=true;try{await api('/companies/'+state.company.id+'/knowledge',{method:'POST'});toast('公司档案已放入知识库');await render();}catch(err){toast(err.message);e.target.disabled=false;}});
}
