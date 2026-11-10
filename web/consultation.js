'use strict';

const consultation = {scope: '', turns: [], request: null};
const consultationExamples = [
  '印尼企业办理环境许可时，知识库有哪些政策依据？',
  '印尼并购反垄断申报要核对哪些条件？',
  '知识库里有哪些印尼劳资争议案例？',
];

function consultationScope() {
  return JSON.stringify([state.auth?.role, state.auth?.username, state.company?.id ?? null]);
}

function resetConsultation(scope = '') {
  consultation.request?.abort();
  Object.assign(consultation, {scope, turns: [], request: null});
}

function consultationPage() {
  const scope = consultationScope();
  if (consultation.scope !== scope) resetConsultation(scope);
  const company = state.company?.name;
  return heading('咨询问答', '向知识库提问，查看有原文依据的 AI 回答。', '<a class="secondary" href="#knowledge">打开知识库</a>') + `
    <section class="panel consultation-panel" aria-label="知识库咨询">
      <div class="panel-heading consultation-heading"><div><h2>知识库咨询</h2><small>${company ? esc(company) + '及公共资料' : '公共知识库'}
        ${state.auth?.role === 'admin' ? ' · <a href="#overview">在总览选择公司</a>' : ''}</small></div>
        <button type="button" class="secondary small" id="consultation-clear">新建问答</button></div>
      <div class="panel-content consultation-content">
        <div id="consultation-transcript" class="consultation-transcript" aria-live="polite"></div>
        <form id="consultation-form" class="consultation-form">
          <label class="field" for="consultation-question"><span>输入问题</span>
            <textarea id="consultation-question" name="question" rows="3" minlength="2" maxlength="500" required
              placeholder="可补充地区、行业、时间，或继续追问上一题"></textarea></label>
          <div class="consultation-actions"><small>问题和相关原文片段会交给已配置的 AI 模型。</small><button class="primary" type="submit">发送问题</button></div>
          <p id="consultation-status" role="status" aria-live="polite" class="consultation-status"></p>
          <div id="consultation-error" role="alert"></div>
        </form>
      </div>
    </section>`;
}

function consultationTurn(turn, turnIndex) {
  const answer = turn.answer;
  return `<article class="consultation-turn">
    <div class="consultation-question"><span>你的问题</span><p>${esc(turn.question)}</p></div>
    <div class="consultation-answer"><span>AI 回答</span>
      ${answer.status === 'insufficient' ? `<p>${esc(answer.message)}</p>` : answer.blocks.map(block =>
        `<p>${esc(block.text)} ${block.citations.map(number =>
          `<a class="consultation-marker" href="#consultation-source-${turnIndex}-${number}" data-consultation-marker="${turnIndex}-${number}" aria-label="引用 ${number}">[${number}]</a>`).join(' ')}</p>`).join('')}
      ${answer.sources.length ? `<details class="consultation-sources" open><summary>引用原文 · ${answer.sources.length} 条</summary>
        <ol>${answer.sources.map(source => `<li id="consultation-source-${turnIndex}-${source.number}" tabindex="-1">
          <div class="consultation-source-head"><strong>[${source.number}] ${esc(source.title)}</strong>
            <button type="button" class="text-button" data-consultation-source="${turnIndex}:${source.number}">查看原文</button></div>
          ${source.date || source.source ? `<small>${esc([source.date, source.source].filter(Boolean).join(' · '))}</small>` : ''}
          <blockquote>${esc(source.quote)}</blockquote></li>`).join('')}</ol></details>` : ''}
    </div></article>`;
}

function updateConsultation() {
  const transcript = $('#consultation-transcript');
  const form = $('#consultation-form');
  if (!transcript || !form || consultation.scope !== consultationScope()) return;
  transcript.innerHTML = consultation.turns.length ? consultation.turns.map(consultationTurn).join('') :
    `<div class="consultation-starter"><h3>想了解什么？</h3><p>可以咨询法规、风险案例或经营合规。找不到足够依据时，助手会直接说明。</p>
      <div class="consultation-examples">${consultationExamples.map((question, index) =>
        `<button type="button" class="secondary small" data-consultation-example="${index}">${esc(question)}</button>`).join('')}</div></div>`;
  $('#consultation-status').textContent = consultation.request ? '正在检索知识库并核对回答引用…' : '';
  $('[type=submit]', form).disabled = Boolean(consultation.request);
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
  $('#consultation-transcript').onclick = event => {
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
        question, company_id:state.company?.id ?? null,
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
