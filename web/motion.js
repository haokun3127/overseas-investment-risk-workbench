'use strict';
// Deck sizing only. Entrance motion is intentionally not played.
(() => {
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const DECK_ITEMS = '.page-heading,.scope-strip,.scope-bar,.library-summary,.collection-steps,.back-link,.detail-title,.metadata';
  let deckObserver = null;
  let deckFrame = 0;

  function reduced() {
    return reducedQuery.matches;
  }

  // Layout offset, unaffected by any transform still on the node.
  function offsetWithin(node, ancestor) {
    let top = 0;
    let current = node;
    while (current && current !== ancestor) {
      top += current.offsetTop;
      current = current.offsetParent;
    }
    return top;
  }

  function syncDeck() {
    const body = document.querySelector('.app-body');
    const page = document.querySelector('#main .workspace-page');
    if (!body || !page) {
      return;
    }
    const items = [];
    Array.from(page.children).some((child) => {
      if (!child.matches(DECK_ITEMS)) {
        return true;
      }
      items.push(child);
      return false;
    });
    page.querySelectorAll('.in-deck').forEach((node) => node.classList.remove('in-deck'));
    if (page.classList.contains('page-overview')) {
      body.style.setProperty('--deck-h', '0px');
      return;
    }
    items.forEach((node) => node.classList.add('in-deck'));
    const last = items.at(-1);
    if (!last) {
      return;
    }
    const overview = page.classList.contains('page-overview');
    const sheet = overview ? page.querySelector(':scope > .kpi-strip') : null;
    if (sheet) {
      // The deck's fade is centred on the KPI sheet so the sheet reads as resting on the edge, not cut by it.
      const fade = parseFloat(getComputedStyle(body).getPropertyValue('--deck-fade')) || 72;
      const middle = offsetWithin(sheet, body) + (sheet.offsetHeight / 2);
      body.style.setProperty('--deck-h', `${Math.round(middle + (fade / 2))}px`);
      return;
    }
    const mobile = window.matchMedia('(max-width:700px)').matches;
    let extra = overview ? 84 : 60;
    if (mobile) {
      extra = overview ? 64 : 44;
    }
    const bottom = last.getBoundingClientRect().bottom - body.getBoundingClientRect().top;
    body.style.setProperty('--deck-h', `${Math.round(bottom + extra)}px`);
  }

  function scheduleDeck() {
    cancelAnimationFrame(deckFrame);
    deckFrame = requestAnimationFrame(syncDeck);
  }

  function watchDeck() {
    if (deckObserver || !('ResizeObserver' in window)) {
      return;
    }
    const main = document.getElementById('main');
    if (!main) {
      return;
    }
    deckObserver = new ResizeObserver(scheduleDeck);
    deckObserver.observe(main);
    window.addEventListener('resize', scheduleDeck, { passive: true });
  }

  function applyShares(root) {
    root.querySelectorAll('[data-share]').forEach((node) => {
      const value = Math.max(0, Math.min(1, Number(node.dataset.share) || 0));
      node.style.setProperty('--share', value.toFixed(4));
    });
  }

  function spotlight(node) {
    if (node.dataset.spotlight === 'on' || !window.matchMedia('(pointer:fine)').matches) {
      return;
    }
    node.dataset.spotlight = 'on';
    let pending = null;
    node.addEventListener('pointermove', (event) => {
      if (pending) {
        pending = event;
        return;
      }
      pending = event;
      requestAnimationFrame(() => {
        const rect = node.getBoundingClientRect();
        node.style.setProperty('--mx', `${Math.round(pending.clientX - rect.left)}px`);
        node.style.setProperty('--my', `${Math.round(pending.clientY - rect.top)}px`);
        pending = null;
      });
    }, { passive: true });
  }

  function enter(route) {
    const main = document.getElementById('main');
    const page = main?.querySelector('.workspace-page');
    document.body.dataset.route = route;
    watchDeck();
    if (!page) {
      return;
    }
    syncDeck();
    applyShares(page);
  }

  function topbarSentinel() {
    const sentinel = document.querySelector('.topbar-sentinel');
    if (!sentinel || !('IntersectionObserver' in window)) {
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      document.body.classList.toggle('is-scrolled', !entry.isIntersecting);
    });
    observer.observe(sentinel);
  }

  function leave() {
    const main = document.getElementById('main');
    if (main) {
      delete main.dataset.revealed;
    }
  }

  window.Motion = { reduced, enter, leave, spotlight, syncDeck, topbarSentinel };
  topbarSentinel();
})();
