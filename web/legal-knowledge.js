'use strict';
let legalSchema = null;
async function ensureLegalSchema() {
  if (!legalSchema) legalSchema = await api('/knowledge/schema');
  return legalSchema;
}
function legalOptions(group, value = '', all = '') {
  return (all ? `<option value="">${esc(all)}</option>` : '') + Object.entries(legalSchema?.[group] || {}).map(([key, label]) =>
    `<option value="${esc(key)}" ${key === value ? 'selected' : ''}>${esc(label)}</option>`).join('');
}
function legalImportFields() {
  return `<div class="form-grid legal-fields"><label class="field">知识分类<select name="legal_category">${legalOptions('categories', 'unclassified')}</select></label>
    <label class="field">适用国家／地区<input name="legal_jurisdiction" maxlength="300" placeholder="如：印度尼西亚"></label></div>`;
}
function takeLegalImport(values) {
  const metadata = {category: values.get('legal_category') || 'unclassified', jurisdiction: values.get('legal_jurisdiction') || ''};
  values.delete('legal_category'); values.delete('legal_jurisdiction');
  return metadata;
}
function legalListFilters() {
  return `<label>知识分类<select name="category">${legalOptions('categories', state.filter.category || '', '全部分类')}</select></label>
    <label>法规效力<select name="validity">${legalOptions('validity', state.filter.validity || '', '全部效力状态')}</select></label>`;
}
function legalSearchFilters() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  return `<label class="field">知识分类<select name="category">${legalOptions('categories', params.get('kcategory') || '', '全部分类')}</select></label>
    <label class="field">检索段落<select name="section">${legalOptions('sections', params.get('ksection') || '', '全部段落')}</select></label>
    <label class="field">法规效力<select name="validity">${legalOptions('validity', params.get('kvalidity') || '', '全部效力状态')}</select></label>`;
}
function legalMetadataHtml(doc) {
  if (doc.kind !== 'knowledge') return '';
  const m = doc.legal_metadata;
  if (!m) return '';
  const types = [...new Set((doc.chunks || []).map(c => c.section_type).filter(type => type && type !== 'general'))];
  const summary = `<p>${esc(m.category_label)}${m.jurisdiction ? ' · ' + esc(m.jurisdiction) : ''} · ${esc(m.validity_label)}</p>
    ${types.length ? `<p>已识别段落：${types.map(type => esc(legalSchema.sections[type])).join('、')}</p>` : ''}
    <p class="form-note">${esc(m.verification_label)}${m.verified_on ? ' · ' + esc(m.verified_on) : ''}</p>`;
  const details = `<dl class="detail-meta-grid">${[['文号', m.document_no], ['发布机构', m.issuer], ['生效日期', m.effective_from], ['失效日期', m.effective_to], ['核验说明', m.verification_note]].filter(([,v]) => v).map(([k,v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`;
  const links = (m.verification_urls || []).map((url, i) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">核验来源 ${i + 1}</a>`).join(' · ');
  const input = (label, name, value, type='text') => `<label class="field">${label}<input type="${type}" name="${name}" value="${esc(value || '')}" ${type === 'text' ? 'maxlength="300"' : ''}></label>`;
  const editor = doc.editable && !doc.quarantined_at ? `<details class="legal-editor"><summary>维护分类与法规效力</summary><form id="legal-metadata-form" class="form-grid">
    <label class="field">知识分类<select name="category">${legalOptions('categories', m.category)}</select></label>
    ${input('适用国家／地区','jurisdiction',m.jurisdiction)}${input('文号','document_no',m.document_no)}${input('发布机构','issuer',m.issuer)}
    <label class="field">效力状态<select name="validity">${legalOptions('validity',m.validity)}</select></label>
    <label class="field">交叉核验<select name="corroboration">${Object.entries({unreviewed:'尚未核验',single:'仅有单一来源',confirmed:'人工确认独立来源交叉印证'}).map(([key,label])=>`<option value="${key}" ${m.corroboration===key?'selected':''}>${label}</option>`).join('')}</select></label>
    ${input('生效日期','effective_from',m.effective_from,'date')}${input('失效日期','effective_to',m.effective_to,'date')}${input('人工核验日期','verified_on',m.verified_on,'date')}
    <label class="field full">核验依据说明<textarea name="verification_note" rows="3" maxlength="3000">${esc(m.verification_note || '')}</textarea></label>
    <label class="field full">核验来源网址（每行一个）<textarea name="verification_urls" rows="3">${esc((m.verification_urls || []).join('\n'))}</textarea></label>
    <p class="form-note full">确认效力须填写核验日期、说明和来源。多个链接不自动代表已完成独立来源交叉验证。</p>
    <div class="form-actions full"><button type="submit" class="primary small">保存分类与核验记录</button></div><div id="legal-metadata-error" class="full" role="alert"></div>
    </form></details>` : '';
  return `<section class="legal-metadata"><h3>分类与法律资料信息</h3>${summary}${details}<div class="actions">${links}</div>${editor}</section>`;
}
function bindLegalMetadata(doc) {
  const form = document.getElementById('legal-metadata-form');
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('[type=submit]');
    if (button.disabled) return;
    button.disabled = true;
    const values = Object.fromEntries(new FormData(form));
    values.verification_urls = values.verification_urls.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
    try {
      const result = await api(`/documents/${doc.id}/legal-metadata`, {method:'PUT', body:{revision:doc.legal_metadata.revision, metadata:values}});
      doc.legal_metadata.revision = result.revision;
      kr.bodies.delete(doc.id);
      toast('分类与核验记录已保存');
      await render({quiet:true});
      await showSource(doc.id);
    } catch (error) {
      if (form.isConnected) document.getElementById('legal-metadata-error').innerHTML = errorBox(error.message);
    } finally { if (button.isConnected) button.disabled = false; }
  });
}
function documentMetadataEditor(doc) {
  if(state.auth?.role!=='admin'||doc.kind!=='knowledge'||doc.quarantined_at||doc.kind_label==='公司档案')return '';
  return `<details class="legal-editor"><summary>修改标题、日期与来源</summary><form id="document-metadata-form" class="form-grid">
    <label class="field full">资料标题<input name="title" required maxlength="240" value="${esc(doc.title)}"></label>
    <label class="field">资料发布日期<input name="date" type="date" value="${esc(doc.date||'')}"></label>
    <label class="field">信息来源<input name="source" maxlength="300" value="${esc(doc.source||'')}"></label>
    <label class="field full">原文网址<input name="url" type="url" maxlength="2000" value="${esc(doc.url||'')}"></label>
    <label class="field full">修改原因<textarea name="reason" required rows="2" maxlength="2000" placeholder="说明修正依据；未取得发布日期时请留空"></textarea></label>
    <div class="form-actions full"><button class="primary small" type="submit">保存资料信息</button></div><div id="document-metadata-error" class="full" role="alert"></div>
    </form></details><details id="document-metadata-history"><summary>资料信息修改记录</summary><div class="panel-content"></div></details>`;
}
function bindDocumentMetadata(doc) {
  const form=$('#document-metadata-form');
  form?.addEventListener('submit',async event=>{
    event.preventDefault();const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;
    try{
      await api(`/documents/${doc.id}/metadata`,{method:'PUT',body:{...Object.fromEntries(new FormData(form)),revision:doc.legal_metadata.revision}});
      kr.bodies.delete(doc.id);toast('资料信息已保存');await render({quiet:true});await showSource(doc.id);
    }catch(error){if(form.isConnected)$('#document-metadata-error').innerHTML=errorBox(error.message);}
    finally{if(button.isConnected)button.disabled=false;}
  });
  const history=$('#document-metadata-history');
  history?.addEventListener('toggle',async()=>{
    if(!history.open||history.dataset.loaded)return;
    try{
      const result=await api(`/documents/${doc.id}/metadata-history`);
      history.querySelector('div').innerHTML=result.items.map(item=>`<article><p>${when(item.created_at)} · ${esc(item.actor)}<br>${esc(item.reason)}</p><dl class="detail-meta-grid">${[['title','标题'],['date','资料日期'],['source','信息来源'],['url','原文网址']].filter(([key])=>item.before[key]!==item.after[key]).map(([key,label])=>`<div><dt>${label}</dt><dd>${esc(item.before[key]||'未填写')} → ${esc(item.after[key]||'未填写')}</dd></div>`).join('')}</dl></article>`).join('')||'<p>暂无资料信息修改记录。</p>';
      history.dataset.loaded='true';
    }catch(error){history.querySelector('div').innerHTML=errorBox(error.message);}
  });
}
