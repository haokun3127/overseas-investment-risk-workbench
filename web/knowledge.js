'use strict';
// Knowledge search reader: ranked list plus a reading pane (wide) or a full-screen dialog (narrow).
const krWide = window.matchMedia('(min-width:1180px)');
const kr = {
  data: null,
  groups: [],
  index: 0,
  request: 0,
  bodies: new Map(),
  hitCursor: -1,
  dialogBound: false,
};

function markRanges(text, terms) {
  const source = String(text || '');
  const ranges = [];
  const markers=Array.from(source.matchAll(/[ \t]*[〔［【\[]\s*S\d+\s*[〕］】\]]/g))
    .map(match=>[match.index,match.index+match[0].length]);
  (terms || []).filter(Boolean).forEach((term) => {
    const latin = /^[a-z0-9]+$/i.test(term);
    const pattern = latin
      ? new RegExp(`(?<![a-z0-9])${term}(?![a-z0-9])`, 'gi')
      : new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    Array.from(source.matchAll(pattern)).forEach((m) => {
      const end=m.index+m[0].length;
      if(!markers.some(([left,right])=>m.index<right&&end>left))ranges.push([m.index,end]);
    });
  });
  ranges.sort((a, b) => (a[0] - b[0]) || (b[1] - a[1]));
  let html = '';
  let cursor = 0;
  let count = 0;
  ranges.forEach(([start, end]) => {
    if (start < cursor) {
      return;
    }
    html += `${readingEsc(source.slice(cursor, start))}<mark class="kr-hit" data-hit="${count}" data-start="${start}">${readingEsc(source.slice(start, end))}</mark>`;
    cursor = end;
    count += 1;
  });
  return { html: html + readingEsc(source.slice(cursor)), count };
}

function groupHits(items) {
  const groups = [];
  const byKey = new Map();
  items.forEach((item, rank) => {
    const key = item.group_key || `doc:${item.document_id}`;
    const existing = byKey.get(key);
    if (existing) {
      existing.versions.push({ ...item, rank });
      return;
    }
    const group = { ...item, rank, versions: [] };
    byKey.set(key, group);
    groups.push(group);
  });
  return groups;
}

function krTerms(hit) {
  return hit.highlight_terms || [];
}

function krBasis(hit) {
  const matched = hit.matched || {};
  const parts = [];
  if (matched.title?.length) {
    parts.push('标题');
  }
  if (matched.zh_summary?.length) {
    parts.push('中文摘要（AI 生成，仅作检索辅助）');
  }
  if (matched.zh_keywords?.length) {
    parts.push('关键词（AI 生成）');
  }
  if (matched.body?.length) {
    parts.push('原文');
  }
  if (matched.expanded?.length) {
    parts.push(`扩展词：${matched.expanded.slice(0, 6).join('、')}`);
  }
  return parts.map((text) => `<span>${esc(text)}</span>`).join('');
}

function krWindowHtml(hit, window) {
  const before = window.start > 0 ? '…' : '';
  const after = window.end < (hit.characters || 0) ? '…' : '';
  return `${before}${markRanges(window.text.replace(/\s+/g, ' '), krTerms(hit)).html}${after}`;
}

function renderReaderList(data, groups) {
  const shown = groups.length;
  const head = `<header class="kr-head"><span class="kr-count">命中 ${data.total_documents} 份资料 · 显示前 ${Math.min(data.limit, data.items.length)} 份${shown < data.items.length ? `（合并为 ${shown} 组）` : ''} · 检索词“${esc(data.query)}”</span><button type="button" class="text-button" data-kr-collapse>收起</button></header>`;
  if (!groups.length) {
    return head + empty('没有匹配的资料', '可以用中文或资料原文的关键词检索；外文资料生成中文摘要后即可用中文检索。');
  }
  const items = groups.map((hit, i) => {
    const firstWindow = hit.hit_windows?.[0];
    const versions = hit.versions.length
      ? `<button type="button" class="text-button kr-versions" data-kr-versions="${i}" aria-expanded="false">另有 ${hit.versions.length} 个版本</button><div class="kr-version-list" hidden>${hit.versions.map((v) => `<button type="button" class="text-button" data-source="${v.document_id}">${esc(v.title)} · ${esc(dateLabel(v))}</button>`).join('')}</div>`
      : '';
    return `<li class="kr-item" role="option" id="kr-item-${i}" data-kr-index="${i}" aria-selected="false" tabindex="-1">`
      + `<span class="kr-rank">${String(hit.rank + 1).padStart(2, '0')}</span>`
      + `<h3 class="kr-title">${markRanges(hit.title, krTerms(hit)).html}</h3>`
      + `<div class="kr-meta"><span class="kr-tag">${esc(hit.kind_label || '资料')}</span><span>${esc(hit.source || '来源未填写')}</span><span>${esc(dateLabel(hit))}</span><span>入库 ${esc(when(hit.created_at))}</span></div>`
      + `<div class="kr-basis">${krBasis(hit)}</div>`
      + (firstWindow ? `<p class="kr-window">${krWindowHtml(hit, firstWindow)}</p>` : '')
      + versions
      + '</li>';
  }).join('');
  return `${head}<div class="kr-body"><ol class="kr-list" role="listbox" aria-label="检索结果">${items}</ol><article class="kr-pane" tabindex="-1" aria-live="polite"></article></div>`;
}

function renderReaderPane(hit, i, n, withBar = true) {
  const windows = hit.hit_windows || [];
  const rows = [
    ['知识分类', esc(hit.legal_metadata?.category_label || '未分类')],
    hit.section_type ? ['匹配段落', esc(legalSchema?.sections[hit.section_type] || '正文')] : null,
    ['法规效力', esc(hit.legal_metadata?.validity_label || '效力未确认')],
    ['来源类型', esc(hit.kind_label || '资料')],
    ['来源', esc(hit.source || '未填写')],
    ['资料日期（来源）', esc(dateLabel(hit))],
    hit.archived_at ? ['存档快照', esc(hit.archived_at)] : null,
    hit.fetched_at ? ['抓取', esc(when(hit.fetched_at))] : null,
    ['入库', esc(when(hit.created_at))],
    ['全文字数', `${Number(hit.characters || 0).toLocaleString('zh-CN')} 字符`],
    hit.url ? ['原始链接', `<a href="${esc(hit.url)}" target="_blank" rel="noopener noreferrer">${esc(hit.url)}</a>`] : null,
  ].filter(Boolean);
  const bar = withBar
    ? `<div class="kr-pane-bar"><span>第 ${i + 1} / ${n} 条</span><span class="actions"><button type="button" class="secondary small" data-kr-step="-1" ${i ? '' : 'disabled'}>上一条</button><button type="button" class="secondary small" data-kr-step="1" ${i < n - 1 ? '' : 'disabled'}>下一条</button></span></div>`
    : '';
  return bar
    + `<h3>${markRanges(hit.title, krTerms(hit)).html}</h3>`
    + `<dl class="kr-meta-grid">${rows.map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`).join('')}</dl>`
    + (hit.body_hit ? '' : '<p class="kr-notice">原文未直接出现检索词，命中来自标题、中文摘要或关键词（AI 生成，仅作检索辅助）。</p>')
    + (hit.zh_summary ? `<section><h4>中文摘要 <small>AI 生成，仅作检索辅助</small></h4><p class="kr-summary">${markRanges(hit.zh_summary, krTerms(hit)).html}</p><button type="button" class="text-button" data-kr-summary>展开</button></section>` : '')
    + (windows.length ? `<section><h4>原文命中片段（${windows.length}）</h4>${windows.map((w) => `<p class="kr-window">${krWindowHtml(hit, w)}</p><button type="button" class="text-button" data-kr-locate="${w.start}">在全文中定位</button>`).join('')}</section>` : '')
    + '<div class="kr-full-host"><button type="button" class="secondary small" data-kr-full>在全文中阅读</button></div>'
    + `<details class="kr-tech"><summary>技术详情</summary><p class="form-note">排序分数 ${esc(hit.score)}（BM25 加权，仅用于本次排序）· 匹配分段 ${esc(hit.locator)} · 资料编号 #${hit.document_id}</p></details>`
    + `<p><button type="button" class="text-button" data-source="${hit.document_id}">打开资料详情</button></p>`;
}

function krScroller(host) {
  return host.closest('.kr-dialog-body') || host.closest('.kr-pane');
}

function krShowHit(host, cursor) {
  const marks = Array.from(host.querySelectorAll('.kr-fulltext .kr-hit'));
  const counter = host.querySelector('[data-kr-count]');
  if (!marks.length) {
    return;
  }
  const next = (cursor + marks.length) % marks.length;
  marks.forEach((mark) => mark.classList.remove('is-current'));
  const mark = marks[next];
  mark.classList.add('is-current');
  host.querySelectorAll('.kr-tick').forEach((tick) => {
    tick.classList.toggle('is-current', Number(tick.dataset.krTick) === next);
  });
  kr.hitCursor = next;
  if (counter) {
    counter.textContent = `第 ${next + 1} / ${marks.length} 处`;
  }
  const scroller = krScroller(host);
  if (scroller) {
    const offset = mark.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
    scroller.scrollTop += offset - (scroller.clientHeight / 2);
  }
}

// One tick per hit, placed at its relative depth in the full text; the ↑/↓ buttons stay the keyboard path.
function renderHitMap(host) {
  const text = host.querySelector('.kr-fulltext');
  const marks = Array.from(host.querySelectorAll('.kr-fulltext .kr-hit'));
  if (!text || !marks.length) {
    return;
  }
  host.classList.add('has-hitmap');
  const map = document.createElement('div');
  map.className = 'kr-minimap';
  map.setAttribute('aria-hidden', 'true');
  map.innerHTML = marks.map((_mark, i) => `<span class="kr-tick" data-kr-tick="${i}"></span>`).join('');
  text.after(map);
  const top = text.getBoundingClientRect().top;
  const height = Math.max(1, text.scrollHeight);
  map.querySelectorAll('.kr-tick').forEach((tick, i) => {
    const y = (marks[i].getBoundingClientRect().top - top) / height;
    tick.style.setProperty('--y', Math.max(0, Math.min(1, y)).toFixed(4));
  });
  map.addEventListener('click', (event) => {
    const tick = event.target.closest('.kr-tick');
    if (tick) {
      krShowHit(host, Number(tick.dataset.krTick));
    }
  });
}

async function openFullText(hit, container, startAt = null) {
  const host = container.querySelector('.kr-full-host');
  if (!host) {
    return;
  }
  host.innerHTML = '<p class="loading" role="status">正在读取全文…</p>';
  try {
    if (!kr.bodies.has(hit.document_id)) {
      const doc = await api(`/documents/${hit.document_id}`);
      kr.bodies.set(hit.document_id, doc.body || '');
    }
    if (!host.isConnected) {
      return;
    }
    const marked = markRanges(kr.bodies.get(hit.document_id), krTerms(hit));
    host.innerHTML = `<div class="kr-hitnav"><span data-kr-count>${marked.count ? `第 1 / ${marked.count} 处` : '原文无直接命中'}</span><span class="actions"><button type="button" class="secondary small" data-kr-hit="-1" aria-label="上一处命中" ${marked.count ? '' : 'disabled'}>↑</button><button type="button" class="secondary small" data-kr-hit="1" aria-label="下一处命中" ${marked.count ? '' : 'disabled'}>↓</button></span></div><div class="kr-fulltext">${marked.html}</div>`;
    host.querySelectorAll('[data-kr-hit]').forEach((button) => {
      button.onclick = () => krShowHit(host, kr.hitCursor + Number(button.dataset.krHit));
    });
    renderHitMap(host);
    let cursor = 0;
    if (startAt !== null) {
      const marks = Array.from(host.querySelectorAll('.kr-fulltext .kr-hit'));
      const found = marks.findIndex((mark) => Number(mark.dataset.start) >= startAt);
      cursor = found < 0 ? 0 : found;
    }
    krShowHit(host, cursor);
  } catch (error) {
    if (host.isConnected) {
      host.innerHTML = errorBox(error.message);
    }
  }
}

function bindReaderPane(container, hit) {
  kr.hitCursor = -1;
  container.querySelectorAll('[data-kr-step]').forEach((button) => {
    button.onclick = () => moveHit(Number(button.dataset.krStep));
  });
  container.querySelector('[data-kr-full]')?.addEventListener('click', () => openFullText(hit, container));
  container.querySelectorAll('[data-kr-locate]').forEach((button) => {
    button.onclick = async () => {
      if (container.querySelector('.kr-fulltext')) {
        const marks = Array.from(container.querySelectorAll('.kr-fulltext .kr-hit'));
        const found = marks.findIndex((mark) => Number(mark.dataset.start) >= Number(button.dataset.krLocate));
        krShowHit(container, found < 0 ? 0 : found);
        return;
      }
      await openFullText(hit, container, Number(button.dataset.krLocate));
    };
  });
  const summaryToggle = container.querySelector('[data-kr-summary]');
  if (summaryToggle) {
    summaryToggle.onclick = () => {
      const summary = container.querySelector('.kr-summary');
      const expanded = summary.classList.toggle('is-expanded');
      summaryToggle.textContent = expanded ? '收起' : '展开';
    };
  }
  container.querySelectorAll('[data-source]').forEach((button) => {
    button.onclick = () => showSource(button.dataset.source);
  });
}

function krRememberIndex(i) {
  const [path, query = ''] = location.hash.slice(1).split('?');
  const params = new URLSearchParams(query);
  params.set('ki', String(i));
  const hash = `#${path}?${params}`;
  state.ki = i;
  state.routeKey = hash;
  history.replaceState(null, '', hash);
}

function selectHit(i, { focus = false, open = false } = {}) {
  const total = kr.groups.length;
  if (!total) {
    return;
  }
  const index = Math.max(0, Math.min(total - 1, i));
  kr.index = index;
  document.querySelectorAll('.kr-item').forEach((item) => {
    const selected = Number(item.dataset.krIndex) === index;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  const item = document.getElementById(`kr-item-${index}`);
  if (focus && item) {
    item.focus({ preventScroll: true });
    const rect = item.getBoundingClientRect();
    if (rect.bottom < 84 || rect.top > window.innerHeight) {
      item.scrollIntoView({ block: 'nearest' });
    }
  }
  krRememberIndex(index);
  const hit = kr.groups[index];
  if (krWide.matches) {
    const pane = document.querySelector('.kr-pane');
    if (pane) {
      pane.innerHTML = renderReaderPane(hit, index, total);
      pane.scrollTop = 0;
      bindReaderPane(pane, hit);
    }
  } else if (open || document.getElementById('kr-dialog')?.open) {
    openReaderDialog(index);
  }
}

function moveHit(step) {
  selectHit(kr.index + step, { focus: !document.getElementById('kr-dialog')?.open });
}

function openReaderDialog(i) {
  const dialog = document.getElementById('kr-dialog');
  const hit = kr.groups[i];
  if (!dialog || !hit) {
    return;
  }
  const body = document.getElementById('kr-dialog-body');
  document.getElementById('kr-dialog-title').textContent = `检索结果 · 第 ${i + 1} / ${kr.groups.length} 条`;
  body.innerHTML = renderReaderPane(hit, i, kr.groups.length, false);
  body.scrollTop = 0;
  bindReaderPane(body, hit);
  dialog.querySelector('[data-kr-prev]').disabled = i <= 0;
  dialog.querySelector('[data-kr-next]').disabled = i >= kr.groups.length - 1;
  if (!dialog.open) {
    dialog.showModal();
  }
}

function krReaderKeys(event) {
  if (event.target.closest('input,textarea,select') || event.metaKey || event.ctrlKey || event.altKey) {
    return;
  }
  const container = event.currentTarget;
  const fullOpen = Boolean(container.querySelector('.kr-fulltext .kr-hit'));
  if (event.key === 'j') {
    event.preventDefault();
    moveHit(1);
  } else if (event.key === 'k') {
    event.preventDefault();
    moveHit(-1);
  } else if (fullOpen && (event.key === 'n' || event.key === 'ArrowDown')) {
    event.preventDefault();
    krShowHit(container, kr.hitCursor + 1);
  } else if (fullOpen && (event.key === 'N' || event.key === 'ArrowUp')) {
    event.preventDefault();
    krShowHit(container, kr.hitCursor - 1);
  }
}

function bindReaderDialog() {
  if (kr.dialogBound) {
    return;
  }
  const dialog = document.getElementById('kr-dialog');
  if (!dialog) {
    return;
  }
  kr.dialogBound = true;
  dialog.querySelectorAll('[data-kr-close]').forEach((button) => {
    button.addEventListener('click', () => dialog.close());
  });
  dialog.querySelector('[data-kr-prev]').addEventListener('click', () => moveHit(-1));
  dialog.querySelector('[data-kr-next]').addEventListener('click', () => moveHit(1));
  document.getElementById('kr-dialog-body').addEventListener('keydown', krReaderKeys);
  dialog.addEventListener('close', () => {
    document.getElementById(`kr-item-${kr.index}`)?.focus({ preventScroll: true });
  });
}

async function runKnowledgeSearch(q, index = 0) {
  const target = document.getElementById('knowledge-results');
  const form = document.getElementById('knowledge-search');
  if (!target || !form) {
    return;
  }
  const request = kr.request + 1;
  kr.request = request;
  const button = form.querySelector('button[type=submit]');
  button.disabled = true;
  button.textContent = '正在检索…';
  target.innerHTML = '<p class="loading" role="status">正在匹配知识库资料…</p>';
  try {
    const params = new URLSearchParams(new FormData(form));
    params.set('q',q);
    const data = await api(`/knowledge/search?${params}`);
    if (request !== kr.request || !target.isConnected) {
      return;
    }
    kr.data = data;
    kr.groups = groupHits(data.items);
    target.innerHTML = renderReaderList(data, kr.groups);
    bindReaderList(target);
    if (kr.groups.length) {
      selectHit(Math.min(index, kr.groups.length - 1));
    }
  } catch (error) {
    if (request === kr.request && target.isConnected) {
      target.innerHTML = errorBox(error.message);
    }
  } finally {
    if (button.isConnected) {
      button.disabled = false;
      button.textContent = '检索内容';
    }
  }
}

function bindReaderList(target) {
  const list = target.querySelector('.kr-list');
  target.querySelector('[data-kr-collapse]')?.addEventListener('click', () => {
    kr.request += 1;
    target.innerHTML = '';
    state.kq = '';
    state.ki = 0;
    state.routeKey = '#knowledge';
    history.replaceState(null, '', '#knowledge');
  });
  if (!list) {
    return;
  }
  list.addEventListener('click', (event) => {
    if (event.target.closest('[data-source]')) {
      showSource(event.target.closest('[data-source]').dataset.source);
      return;
    }
    const toggle = event.target.closest('[data-kr-versions]');
    if (toggle) {
      const box = toggle.nextElementSibling;
      box.hidden = !box.hidden;
      toggle.setAttribute('aria-expanded', String(!box.hidden));
      return;
    }
    const item = event.target.closest('.kr-item');
    if (item) {
      selectHit(Number(item.dataset.krIndex), { focus: true, open: true });
    }
  });
  list.addEventListener('keydown', (event) => {
    if (event.target.closest('button')) {
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      selectHit(kr.index + (event.key === 'ArrowDown' ? 1 : -1), { focus: true });
    } else if ((event.key === 'Enter' || event.key === ' ') && !krWide.matches) {
      event.preventDefault();
      openReaderDialog(kr.index);
    }
  });
  target.querySelector('.kr-pane')?.addEventListener('keydown', krReaderKeys);
}

function bindKnowledgeReader() {
  bindReaderDialog();
  const form = document.getElementById('knowledge-search');
  if (!form) {
    return;
  }
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const q = String(new FormData(form).get('q') || '').trim();
    if (!q) {
      return;
    }
    const values = new FormData(form);
    const hash = `#knowledge?${new URLSearchParams({ kq: q, kcategory: values.get('category') || '', ksection: values.get('section') || '', kvalidity: values.get('validity') || '' })}`;
    if (location.hash === hash) {
      runKnowledgeSearch(q, 0);
    } else {
      location.hash = hash;
    }
  });
  if (state.kq) {
    form.elements.q.value = state.kq;
    runKnowledgeSearch(state.kq, state.ki);
  }
}

krWide.addEventListener('change', () => {
  if (!kr.groups.length || !document.querySelector('.kr-list')) {
    return;
  }
  const dialog = document.getElementById('kr-dialog');
  if (krWide.matches && dialog?.open) {
    dialog.close();
  }
  selectHit(kr.index);
});
