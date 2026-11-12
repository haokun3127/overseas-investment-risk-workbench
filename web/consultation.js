'use strict';

const consultation = {scope: '', turns: [], request: null};
const consultationExamples = [
  '印尼企业办理环境许可时，知识库有哪些政策依据？',
  '印尼并购反垄断申报要核对哪些条件？',
  '知识库里有哪些印尼劳资争议案例？',
];

function consultationScope() {
  return JSON.stringify([state.auth?.role, state.auth?.username]);
}

function resetConsultation(scope = '') {
  consultation.request?.abort();
  Object.assign(consultation, {scope, turns: [], request: null});
}

function consultationPage() {
  const scope = consultationScope();
  if (consultation.scope !== scope) resetConsultation(scope);
  return heading('咨询问答', '向知识库提问，查看有原文依据的 AI 回答。', '<a class="secondary" href="#knowledge">打开知识库</a>') + `
    <section class="panel consultation-panel" aria-label="知识库咨询">
      <div class="panel-heading consultation-heading"><div><h2>知识库咨询</h2><small>法规、案例与经营合规</small></div>
        <button type="button" class="secondary small" id="consultation-clear">新建问答</button></div>
      <div class="panel-content consultation-content">
        <div id="consultation-transcript" class="consultation-transcript" aria-live="polite"></div>
        <form id="consultation-form" class="consultation-form">
          <label class="field" for="consultation-question"><span>输入问题</span>
            <textarea id="consultation-question" name="question" rows="3" minlength="2" maxlength="500" required
              placeholder="可补充地区、行业、时间，或继续追问上一题"></textarea></label>
          <div class="consultation-actions"><label class="field consultation-mode">输出形式<select name="mode"><option value="answer">咨询问答</option><option value="report">咨询报告（四个模块）</option></select></label><button class="primary" type="submit">发送问题 ${icon('arrow')}</button></div>
          <small class="consultation-privacy">检索公共知识库，不带入企业私有资料；问题和相关原文片段会发送给已配置的 AI 模型。</small>
          <p id="consultation-status" role="status" aria-live="polite" class="consultation-status"></p>
          <div id="consultation-error" role="alert"></div>
        </form>
      </div>
    </section>`;
}

function consultationTurn(turn, turnIndex) {
  const answer = turn.answer;
  const gap=answer.explanation;
  const explanation=gap?`<section class="consultation-gap-section"><h4>资料缺口与补充建议</h4><dl class="consultation-gaps">${[['known_materials','已检索到'],['missing_facts','缺少事实'],['missing_basis','缺少依据'],['conflicts','待核实矛盾'],['affected','暂不能判断'],['needed','建议补充']].filter(([key])=>gap[key]?.length).map(([key,label])=>`<div><dt>${label}</dt><dd>${gap[key].map(text=>`<p>${readingEsc(text)}</p>`).join('')}</dd></div>`).join('')}</dl></section>`:'';
  const reportActions=answer.mode === 'report' && answer.blocks.length ? `${answer.report_id?`<a class="secondary small" href="api/consultation/reports/${Number(answer.report_id)}/docx">${icon('download')}下载 Word</a>`:''}<button type="button" class="secondary small" data-print-consultation="${turnIndex}">${icon('print')}打印／保存 PDF</button>` : '';
  return `<article class="consultation-turn">
    <div class="consultation-question"><span>${icon('consultation')}你的问题</span><p>${esc(turn.question)}</p></div>
    <div class="consultation-answer">
      <header class="consultation-answer-head"><h3>${answer.mode==='report'?'咨询报告':'咨询回答'}</h3><div class="consultation-answer-tools">${answer.sources.length?`<button type="button" class="text-button" data-consultation-references="${turnIndex}">${icon('source')}${answer.sources.length} 条引用</button>`:''}<button type="button" class="text-button" data-copy-consultation="${turnIndex}">复制回答</button></div></header>
      ${answer.status === 'insufficient' ? `<p class="consultation-limitation">${icon('risk')}<span>${esc(answer.message)}</span></p>${answer.blocks.length?'<h4 class="consultation-partial-title">已有依据支持的部分</h4>':''}` : ''}
      <div class="consultation-answer-body">${answer.blocks.map(block =>
        `<section class="consultation-block">${block.heading ? `<h4>${esc(block.heading)}</h4>` : ''}<p>${esc(block.text)} ${block.citations.map(number =>
          `<a class="consultation-marker" href="#consultation-source-${turnIndex}-${number}" data-consultation-marker="${turnIndex}-${number}" aria-label="引用 ${number}">[${number}]</a>`).join(' ')}</p></section>`).join('')}
      </div>${explanation}
      ${answer.missing_sections?.length ? `<div class="report-gaps"><strong>以下模块依据不足</strong><p>${answer.missing_sections.map(esc).join('、')}。请补充相应类别资料及核验记录后重新生成。</p></div>` : ''}
      ${answer.assessment_note ? `<p class="form-note">${esc(answer.assessment_note)}</p>` : ''}
      ${answer.sources.length ? `<details class="consultation-sources"><summary>依据与来源 <span>${answer.sources.length} 条引用</span></summary>
        <ol>${answer.sources.map(source => `<li id="consultation-source-${turnIndex}-${source.number}" tabindex="-1">
          <div class="consultation-source-head"><strong>[${source.number}] ${esc(source.title)}</strong>
            <button type="button" class="text-button" data-consultation-source="${turnIndex}:${source.number}">查看原文</button></div>
          ${source.date || source.source ? `<small>${esc([source.date, source.source].filter(Boolean).join(' · '))}</small>` : ''}
          <blockquote>${readingEsc(source.quote)}</blockquote></li>`).join('')}</ol></details>` : ''}
      ${reportActions?`<footer class="consultation-report-actions">${reportActions}</footer>`:''}
    </div></article>`;
}

function consultationCopyText(turn) {
  const answer=turn.answer,lines=['问题：'+turn.question,'',answer.mode==='report'?'咨询报告':'咨询回答'];
  if(answer.status==='insufficient')lines.push(answer.message);
  for(const block of answer.blocks){
    if(block.heading)lines.push('',block.heading);
    lines.push(block.text+' '+block.citations.map(n=>'['+n+']').join(' '));
  }
  const gap=answer.explanation;
  if(gap)for(const [key,label] of [['known_materials','已检索到'],['missing_facts','缺少事实'],['missing_basis','缺少依据'],['conflicts','待核实矛盾'],['affected','暂不能判断'],['needed','建议补充']])
    if(gap[key]?.length)lines.push('',label+'：'+gap[key].join('；'));
  if(answer.missing_sections?.length)lines.push('以下模块依据不足：'+answer.missing_sections.join('、'));
  if(answer.assessment_note)lines.push(answer.assessment_note);
  if(answer.sources.length)lines.push('','依据与来源');
  for(const source of answer.sources)lines.push('['+source.number+'] '+source.title,
    readingText(source.quote),[source.date,source.source,source.url].filter(Boolean).join(' · '));
  return lines.join('\n');
}

function updateConsultation() {
  const transcript = $('#consultation-transcript');
  const form = $('#consultation-form');
  if (!transcript || !form || consultation.scope !== consultationScope()) return;
  transcript.innerHTML = consultation.turns.length ? consultation.turns.map(consultationTurn).join('') :
    `<div class="consultation-starter"><h3>从一个具体问题开始</h3><p>描述你关心的事项，回答将附上可查阅的原文依据。</p>
      <div class="consultation-examples">${consultationExamples.map((question, index) =>
        `<button type="button" class="secondary small" data-consultation-example="${index}"><span>${esc(question)}</span>${icon('arrow')}</button>`).join('')}</div></div>`;
  form.closest('.consultation-panel').classList.toggle('has-conversation',Boolean(consultation.turns.length));
  const busy=Boolean(consultation.request);
  form.setAttribute('aria-busy',String(busy));
  transcript.setAttribute('aria-busy',String(busy));
  $('#consultation-status').textContent = busy ? '正在检索知识库并生成回答，请稍候…' : '';
  const submit=$('[type=submit]', form);
  submit.disabled=busy;
  submit.innerHTML=busy?'正在回答…':`发送问题 ${icon('arrow')}`;
}

function bindConsultation() {
  const form = $('#consultation-form');
  if (!form) return;
  const input = $('#consultation-question');
  const currentView = () => form.isConnected && consultation.scope === consultationScope();
  updateConsultation();
  $('#consultation-clear').onclick = () => {
    resetConsultation(consultationScope());
    input.value = '';
    $('#consultation-error').textContent = '';
    updateConsultation();
    input.focus();
  };
  $('#consultation-transcript').onclick = async event => {
    const copy=event.target.closest('[data-copy-consultation]');
    if(copy){
      const turn=consultation.turns[Number(copy.dataset.copyConsultation)];
      if(!turn||!currentView())return;
      copy.disabled=true;
      try{
        await navigator.clipboard.writeText(consultationCopyText(turn));
        toast('回答及引用来源已复制');
      }catch(_error){toast('未能访问剪贴板，请选中回答文字复制。');}
      finally{if(copy.isConnected)copy.disabled=false;}
      return;
    }
    const references=event.target.closest('[data-consultation-references]');
    if(references){
      const details=references.closest('.consultation-answer').querySelector('.consultation-sources');
      if(details){details.open=true;details.querySelector('summary').focus();details.scrollIntoView({block:'nearest'});}
      return;
    }
    const print = event.target.closest('[data-print-consultation]');
    if (print) {
      const article = print.closest('.consultation-turn');
      document.body.classList.add('print-consultation');
      article.classList.add('print-selected');
      const details=article.querySelector('.consultation-sources'),wasOpen=details?.open;
      if(details)details.open=true;
      const cleanup = () => { document.body.classList.remove('print-consultation'); article.classList.remove('print-selected'); if(details)details.open=wasOpen; };
      window.addEventListener('afterprint', cleanup, {once:true});
      window.print();
      return;
    }
    const example = event.target.closest('[data-consultation-example]');
    if (example) {
      input.value = consultationExamples[Number(example.dataset.consultationExample)];
      input.focus();
      return;
    }
    const marker = event.target.closest('[data-consultation-marker]');
    if (marker) {
      event.preventDefault();
      const source = document.getElementById('consultation-source-' + marker.dataset.consultationMarker);
      if (source) {
        source.closest('details').open = true;
        source.focus();
      }
      return;
    }
    const button = event.target.closest('[data-consultation-source]');
    if (!button || !currentView()) return;
    const [turn, number] = button.dataset.consultationSource.split(':').map(Number);
    const source = consultation.turns[turn]?.answer.sources.find(item => item.number === number);
    if (source) showSource(source.document_id, source.quote);
  };
  form.onsubmit = async event => {
    event.preventDefault();
    const question = input.value.trim();
    if (consultation.request || question.length < 2 || !currentView()) return;
    const request = new AbortController();
    const scope = consultation.scope;
    consultation.request = request;
    $('#consultation-error').textContent = '';
    updateConsultation();
    try {
      const answer = await api('/consultation', {method:'POST', timeoutMs:80000, signal:request.signal, body:{
        question, company_id:null, mode:form.elements.mode.value,
        previous_questions:consultation.turns.slice(-3).map(turn => turn.question),
      }});
      if (consultation.scope !== scope || consultation.request !== request || consultationScope() !== scope) return;
      consultation.turns = [...consultation.turns, {question, answer}].slice(-20);
      if (currentView() && input.value.trim() === question) input.value = '';
    } catch (error) {
      if (error.name !== 'AbortError' && currentView() && consultation.request === request) {
        $('#consultation-error').innerHTML = errorBox(error.message);
      }
    } finally {
      if (consultation.request === request) {
        consultation.request = null;
        updateConsultation();
      }
    }
  };
}
