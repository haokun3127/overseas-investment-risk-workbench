'use strict';
// Motion layer. Route entry uses Anime.js when it is loaded; quiet re-renders never replay it.
(() => {
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const DECK_ITEMS = '.page-heading,.scope-strip,.scope-bar,.library-summary,.collection-steps,.back-link,.detail-title,.metadata';
  const MAX_STAGGER = 8;
  let deckObserver = null;
  let deckFrame = 0;

  function reduced() {
    return reducedQuery.matches;
  }

  function easeOut(t) {
    return 1 - ((1 - t) ** 4);
  }

  // Layout offset, unaffected by the entrance transform still running on the node.
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

  function countUp(node) {
    const target = Number(node.dataset.count);
    if (!Number.isFinite(target)) {
      return;
    }
    node.style.setProperty('--digits', String(String(target).length));
    if (reduced() || target === 0) {
      node.textContent = String(target);
      return;
    }
    const start = performance.now();
    const duration = 900;
    // Assistive tech reads the final value from a hidden twin while the visible digits roll.
    const twin = document.createElement('span');
    twin.className = 'sr-only';
    twin.textContent = String(target);
    node.after(twin);
    node.setAttribute('aria-hidden', 'true');
    const finish = () => {
      node.textContent = String(target);
      node.removeAttribute('aria-hidden');
      twin.remove();
    };
    const frame = (now) => {
      if (!node.isConnected) {
        return;
      }
      const t = Math.min(1, (now - start) / duration);
      node.textContent = String(Math.round(target * easeOut(t)));
      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        finish();
      }
    };
    node.textContent = '0';
    requestAnimationFrame(frame);
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

  function clearMotion(nodes) {
    nodes.forEach((node) => {
      if (!node.isConnected) {
        return;
      }
      node.style.opacity = '';
      node.style.transform = '';
    });
  }

  function playAnime(engine, nodes, options) {
    if (!nodes.length) {
      return null;
    }
    return engine.animate(nodes, options);
  }

  function reveal(page) {
    const blocks = Array.from(page.children).filter((node) => !node.matches('[hidden]')).slice(0, MAX_STAGGER);
    const cards = Array.from(page.querySelectorAll('.kpi-strip .stat, .web-source-card, .collection-steps li, .kr-item')).filter((node) => !node.matches('[hidden]')).slice(0, 8);
    const engine = window.anime;
    if (blocks.length && engine && typeof engine.animate === 'function' && typeof engine.stagger === 'function') {
      try {
        const movers = blocks.concat(cards);
        const clear = () => clearMotion(movers);
        const anims = [
          playAnime(engine, blocks, {
            opacity: [0, 1],
            y: [22, 0],
            delay: engine.stagger(60, { from: 'first' }),
            duration: 680,
            ease: 'outCubic',
          }),
          playAnime(engine, cards, {
            opacity: [0, 1],
            y: [20, 0],
            scale: [0.96, 1],
            delay: engine.stagger(50, { start: 140 }),
            duration: 700,
            ease: 'outCubic',
          }),
        ].filter(Boolean);
        if (anims.length && typeof anims[0].then === 'function') {
          Promise.all(anims).then(clear);
        } else {
          setTimeout(clear, 1100);
        }
        return;
      } catch (_error) {
        clearMotion(blocks.concat(cards));
      }
    }
    blocks.forEach((node, index) => {
      node.animate(
        [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }],
        { duration: 360, delay: Math.min(320, index * 40), easing: 'cubic-bezier(.16,1,.3,1)', fill: 'backwards' },
      );
    });
  }

  function mountField(body) {
    if (body.querySelector(':scope > .kl-field')) {
      return;
    }
    const field = document.createElement('div');
    field.className = 'kl-field';
    field.setAttribute('aria-hidden', 'true');
    field.innerHTML = '<span class="kl-orb kl-orb-a"></span><span class="kl-orb kl-orb-b"></span><span class="kl-orb kl-orb-c"></span>';
    body.append(field);
  }

  function workspaceLight() {
    const body = document.querySelector('#shell .app-body');
    if (!body) {
      return;
    }
    mountField(body);
    if (body.dataset.light === 'on' || reduced() || !window.matchMedia('(pointer:fine)').matches) {
      return;
    }
    body.dataset.light = 'on';
    let pending = null;
    body.addEventListener('pointermove', (event) => {
      if (pending) {
        pending = event;
        return;
      }
      pending = event;
      requestAnimationFrame(() => {
        if (!pending || !body.isConnected) {
          pending = null;
          return;
        }
        const rect = body.getBoundingClientRect();
        body.style.setProperty('--lx', `${Math.round(pending.clientX - rect.left)}px`);
        body.style.setProperty('--ly', `${Math.round(pending.clientY - rect.top)}px`);
        pending = null;
      });
    }, { passive: true });
  }

  function enter(route, options = {}) {
    const main = document.getElementById('main');
    const page = main?.querySelector('.workspace-page');
    document.body.dataset.route = route;
    watchDeck();
    if (!page) {
      return;
    }
    syncDeck();
    applyShares(page);
    workspaceLight();
    const side = document.querySelector('#shell .sidebar');
    if (side) {
      spotlight(side);
    }
    page.querySelectorAll('.kpi-strip .stat, .panel, .workspace-filters, .collection-steps li, .primary, .secondary, .company-admin-menu>summary, .web-source-card, .kr-item, .upload-area, .kpi-strip').forEach(spotlight);
    const fresh = main.dataset.revealed !== route;
    main.dataset.revealed = route;
    if (!fresh || options.quiet || reduced()) {
      return;
    }
    const host = main.querySelector('.route-enter');
    host?.classList.add('is-revealing');
    setTimeout(() => host?.classList.remove('is-revealing'), 1500);
    reveal(page);
    page.querySelectorAll('[data-count]').forEach(countUp);
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

  window.Motion = { reduced, enter, leave, countUp, spotlight, syncDeck, topbarSentinel };
  topbarSentinel();
})();
