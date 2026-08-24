/* Resolves a page-relative asset path. The artifact bundle replaces this
   with a blob: URL lookup before this file runs; deployed it is identity. */
window.__ga = window.__ga || function (u) { return u; };

/* ============================================================
   GLOSS project page — interaction layer
   ============================================================ */

/* ---------- 3. Scroll-scrubbed pipeline figure ---------- */
(function () {
  const track = document.querySelector('.pipeline-track');
  const svg = document.querySelector('.pipeline-svg');
  const capEl = document.getElementById('pipeCaption');
  const dotsEl = document.getElementById('pipeDots');
  if (!track || !svg || !capEl) return;

  const CAPTIONS = [
    ['A · Global cameras', 'Sample viewpoints around the untextured mesh and render its geometry — normals and world positions.'],
    ['B · ControlNet views', 'An off-the-shelf diffusion model, conditioned on that geometry and LLM-written prompts, generates diverse single-view looks.'],
    ['C · De-lighting', 'Each view is converted to albedo and material maps, stripping the baked lighting.'],
    ['D · Back-projection', 'Albedo is projected back onto the surface, giving a partial texture and a mask of what is known.'],
    ['E · Local cameras', 'Close-up cameras are sampled inside the known region, weighted by surface area and visible pixels.'],
    ['F · Batch multi-attention', 'Local patches train as one attention context, so every patch can borrow from every other — the mechanism behind reference brushes.']
  ];

  const steps = [...svg.querySelectorAll('.pipe-step')];
  const flows = [...svg.querySelectorAll('.pipe-flow')];

  CAPTIONS.forEach(() => dotsEl.insertAdjacentHTML('beforeend', '<i></i>'));
  const dots = [...dotsEl.children];

  let current = -1;
  function render(idx) {
    if (idx === current) return;
    current = idx;
    steps.forEach((s, i) => s.classList.toggle('on', i <= idx));
    flows.forEach((f, i) => f.classList.toggle('on', i < idx));
    dots.forEach((d, i) => d.classList.toggle('on', i <= idx));
    const [title, body] = CAPTIONS[Math.max(0, idx)];
    capEl.innerHTML = '<b>' + title + '</b>' + body;
  }

  function onScroll() {
    const r = track.getBoundingClientRect();
    const total = r.height - window.innerHeight;
    if (total <= 0) { render(CAPTIONS.length - 1); return; }
    const p = Math.min(1, Math.max(0, -r.top / total));
    render(Math.min(CAPTIONS.length - 1, Math.floor(p * CAPTIONS.length)));
  }

  // Narrow screens drop the sticky track, so just show the finished figure.
  const mq = window.matchMedia('(max-width: 900px)');
  function bind() {
    window.removeEventListener('scroll', onScroll);
    if (mq.matches) { render(CAPTIONS.length - 1); }
    else { window.addEventListener('scroll', onScroll, { passive: true }); onScroll(); }
  }
  mq.addEventListener('change', bind);
  bind();
})();

/* ---------- 4. Play videos only while visible ---------- */
(function () {
  const vids = document.querySelectorAll('.video-card video');
  if (!vids.length || !('IntersectionObserver' in window)) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      const v = e.target;
      if (e.isIntersecting) {
        if (v.preload === 'none') v.preload = 'auto';
        v.play().catch(() => {});
      } else {
        v.pause();
      }
    });
  }, { threshold: 0.35 });

  vids.forEach((v) => io.observe(v));

  // Flipping [hidden] off does not make the observer re-deliver an entry, so a
  // revealed grid would sit paused. Re-observing forces a fresh initial record.
  window.__revealVideos = (root) => {
    // wait a frame: re-observing before layout runs measures the still-boxless
    // element and the observer reports it as not intersecting
    requestAnimationFrame(() => {
      root.querySelectorAll('video').forEach((v) => { io.unobserve(v); io.observe(v); });
    });
  };
})();

/* ---------- 5. Title: the five letters fly forward and assemble "GLOSS:" ----
   FLIP: each prefix letter is measured in its final slot, then offset onto the
   matching letter inside the sentence and released. Replays on a fixed cadence,
   continuously.                                                                */
(function () {
  const title = document.querySelector('.hero-title');
  if (!title) return;
  const letters = [...title.querySelectorAll('.gl-prefix i[data-src]')];
  const colon = title.querySelector('.gl-prefix .colon');
  if (!letters.length) return;

  const PERIOD = 9000;   // ms between replays
  const STAGGER = 90;
  const FLIGHT = 820;
  const LEAD = 260;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) { title.classList.add('static', 'assembled'); return; }

  function measure() {
    return letters.map((el) => {
      const src = document.getElementById(el.dataset.src);
      if (!src) return null;
      // clear any transform first, or we would measure the moved position
      el.style.transition = 'none';
      el.style.transform = 'none';
      const a = el.getBoundingClientRect(), b = src.getBoundingClientRect();
      return { el, dx: b.left - a.left, dy: b.top - a.top };
    }).filter(Boolean);
  }

  function play() {
    const moves = measure();
    title.classList.remove('assembled');
    moves.forEach((m) => {
      m.el.style.opacity = '0';
      m.el.style.transform = `translate(${m.dx}px, ${m.dy}px)`;
    });
    if (colon) { colon.style.transition = 'none'; colon.style.opacity = '0'; }

    requestAnimationFrame(() => {
      moves.forEach((m, i) => {
        const delay = LEAD + i * STAGGER;
        m.el.style.transition =
          `transform ${FLIGHT}ms cubic-bezier(.22,.72,.16,1) ${delay}ms, opacity 260ms ease ${delay}ms`;
        m.el.style.transform = 'translate(0, 0)';
        m.el.style.opacity = '1';
      });
      if (colon) {
        colon.style.transition = 'opacity 400ms ease ' + (LEAD + letters.length * STAGGER + 240) + 'ms';
        colon.style.opacity = '1';
      }
      setTimeout(() => title.classList.add('assembled'),
                 LEAD + (letters.length - 1) * STAGGER + FLIGHT * 0.55);
    });
  }

  (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => {
    requestAnimationFrame(() => {
      play();
      setInterval(play, PERIOD);   // runs continuously, on screen or not
      // a resize changes every measured position, so restart cleanly
      // Only a WIDTH change moves the letters. On a phone, scrolling
      // slides the URL bar away, which fires resize on every scroll with
      // an unchanged width - replaying on that restarted the assembly
      // mid-scroll, so the animation never appeared to finish.
      let rt, lastW = window.innerWidth;
      window.addEventListener('resize', () => {
        if (window.innerWidth === lastW) return;
        lastW = window.innerWidth;
        clearTimeout(rt);
        rt = setTimeout(play, 220);
      });
    });
  });
})();

/* ---------- 8. Creature chooser: one subsection, two authoring sessions ----
   A step control rather than tabs: either arrow moves to the other session and
   the name between them updates. Both grids stay in the DOM so the visibility
   observer above keeps owning playback; switching only flips [hidden].       */
(function () {
  const seg = document.getElementById('creaturePick');
  if (!seg) return;
  const grids = [...document.querySelectorAll('.video-grid[data-creature]')];
  const btns = [...seg.querySelectorAll('button[data-creature]')];
  if (!grids.length || !btns.length) return;

  const order = btns.map((b) => b.dataset.creature);
  let at = Math.max(0, order.indexOf('sea'));

  function show(i) {
    at = (i + order.length) % order.length;          // wraps, so arrow keys loop
    const want = order[at];
    btns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.creature === want)));
    grids.forEach((g) => {
      const on = g.dataset.creature === want;
      g.hidden = !on;
      // the observer pauses on the next tick anyway; stop the outgoing set now
      if (!on) g.querySelectorAll('video').forEach((v) => v.pause());
      else if (window.__revealVideos) window.__revealVideos(g);
    });
  }

  seg.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-creature]');
    if (!btn) return;
    show(order.indexOf(btn.dataset.creature));
  });

  // arrow keys still step through the list once the control has focus
  seg.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { show(at - 1); btns[at].focus(); e.preventDefault(); }
    if (e.key === 'ArrowRight') { show(at + 1); btns[at].focus(); e.preventDefault(); }
  });

  show(at);
})();

/* ---------- 4.4 · all seven methods in one row ----------
   The deck already ships each comparison as one video holding the reference
   and the six methods side by side, so the row IS the file: showing it whole
   keeps every method on the same frame of the same turntable, and the legend
   below only has to name the columns the video already has. */
(function () {
  const root = document.getElementById('autoCmp');
  const vid = document.getElementById('cmpStrip');
  if (!root || !vid) return;
  const shapes = [...root.querySelectorAll('.cmp-shape button')];
  let live = false;

  function load(i) {
    shapes.forEach((b, j) => b.classList.toggle('on', j === i));
    vid.src = window.__ga(shapes[i].dataset.src);
    if (live) vid.play().catch(() => {});
  }
  shapes.forEach((b, i) => b.addEventListener('click', () => load(i)));

  new IntersectionObserver((es) => {
    live = es[0].isIntersecting;
    if (live) vid.play().catch(() => {}); else vid.pause();
  }, { rootMargin: '200px' }).observe(root);

  load(0);
})();

/* ---------- 4.x · play the gallery clips only while they are on screen ----------
   The .video-card observer above does not reach these: the completion gallery
   and the finetune strips are their own shapes, and section 4 carries more
   clips than the rest of the page put together. */
(function () {
  const vids = [...document.querySelectorAll('.auto-cell video, .ft-strip video, .blend-cell video')];
  if (!vids.length || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver(es => {
    for (const e of es) {
      const v = e.target;
      if (e.isIntersecting) v.play().catch(() => {}); else v.pause();
    }
  }, { rootMargin: '150px' });
  vids.forEach(v => io.observe(v));
})();

/* ---------- 4.2 / 4.3 · step one object through its results ----------
   Every result for an object is in the DOM; the arrows move which one is
   shown, along with its own reference row and the dot that reports position.
   Only the visible result plays, so a cell costs one decode rather than N. */
(function () {
  const cells = [...document.querySelectorAll('.pbr-cell')];
  if (!cells.length) return;

  cells.forEach((cell) => {
    const vids = [...cell.querySelectorAll('.pbr-stage video')];
    const refs = [...cell.querySelectorAll('.pbr-refs')];
    const dots = [...cell.querySelectorAll('.pbr-dots i')];
    if (vids.length < 2) return;
    let cur = 0;

    function show(next) {
      cur = (next + vids.length) % vids.length;
      vids.forEach((v, i) => {
        v.classList.toggle('on', i === cur);
        if (i === cur) { if (cell.dataset.live === '1') v.play().catch(() => {}); }
        else v.pause();
      });
      refs.forEach((r, i) => r.classList.toggle('on', i === cur));
      dots.forEach((d, i) => d.classList.toggle('on', i === cur));
    }
    cell.querySelectorAll('.pbr-arrow').forEach((b) =>
      b.addEventListener('click', () => show(cur + (+b.dataset.step))));
    cell._show = show;
    cell._cur = () => cur;
  });

  /* decode only what is on screen — section 4 holds far more clips than the
     rest of the page put together */
  const io = new IntersectionObserver((es) => {
    for (const e of es) {
      const cell = e.target;
      cell.dataset.live = e.isIntersecting ? '1' : '0';
      const on = cell.querySelector('.pbr-stage video.on');
      if (!on) continue;
      if (e.isIntersecting) on.play().catch(() => {}); else on.pause();
    }
  }, { rootMargin: '150px' });
  cells.forEach((c) => io.observe(c));
})();

/* ---------- 4.4 · pick the shape by name ----------
   Seven slides, each five fills of one shape. The names are the control, so
   there is no hunting through arrows to reach the shape you want. Only the
   visible slide plays: twenty-three clips decoding at once would stall. */
(function () {
  const root = document.getElementById('autoSwap');
  if (!root) return;
  const slides = [...root.querySelectorAll('.as-slide')];
  const picks = [...root.querySelectorAll('.as-pick button')];
  let cur = 0, live = false;

  function show(next) {
    cur = (next + slides.length) % slides.length;
    slides.forEach((s, i) => {
      const on = i === cur;
      s.classList.toggle('on', on);
      s.querySelectorAll('video').forEach((v) => {
        if (on && live) v.play().catch(() => {}); else v.pause();
      });
    });
    picks.forEach((b, i) => b.classList.toggle('on', i === cur));
  }
  picks.forEach((b, i) => b.addEventListener('click', () => show(i)));

  new IntersectionObserver((es) => {
    live = es[0].isIntersecting;
    show(cur);
  }, { rootMargin: '150px' }).observe(root);
})();


/* ---------- 10. TL;DR: sweep the strike across the old claims ---------------
   The words are static — only the rule is animated, so the reader watches the
   old idea being crossed out instead of watching text type itself.          */
(function () {
  const swaps = document.querySelector('.tldr-swaps');
  if (!swaps) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    swaps.classList.add('struck');
    return;
  }
  const PERIOD = 7000;
  const strike = () => {
    swaps.classList.remove('struck');
    // let the reset paint before drawing again, or the browser coalesces both
    requestAnimationFrame(() => requestAnimationFrame(() => swaps.classList.add('struck')));
  };
  let timer = null;
  const start = () => { if (!timer) { strike(); timer = setInterval(strike, PERIOD); } };
  const stop = () => { clearInterval(timer); timer = null; };
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop()),
      { threshold: 0.4 }).observe(swaps);
  } else { start(); }
})();

/* ---------------------------------------------------------------------------
   Autoplay, on phones
   ---------------------------------------------------------------------------
   Every clip here is muted, looping and playsinline, which is the combination
   iOS accepts without a gesture - but it accepts it only when the device is
   not in Low Power Mode. In Low Power Mode Safari refuses the play() outright
   and the poster sits there, which is what "the videos don't autoplay" looks
   like in practice. There is no way to detect that state, and no way to
   override it; the one thing that does lift it is a real user gesture.

   So: kick the hero once on load, and arm a one-shot listener that retries
   every visible clip on the first touch, click or scroll. On a device that was
   already autoplaying this changes nothing - play() on a playing video is a
   no-op. On a device that refused, the page starts moving the moment the
   reader does.
   --------------------------------------------------------------------------- */
(function () {
  const kick = (v) => { if (v && v.paused) v.play().catch(() => {}); };
  const inView = (v) => {
    const r = v.getBoundingClientRect();
    return r.top < innerHeight && r.bottom > 0 && r.width > 0;
  };
  const retryVisible = () => {
    document.querySelectorAll('video').forEach((v) => {
      // don't fight the section controls: they park clips on purpose by
      // marking the cell they belong to as not live
      const cell = v.closest('[data-live]');
      if (cell && cell.dataset.live === '0') return;
      if (inView(v)) kick(v);
    });
  };

  const hero = document.querySelector('.hero-bg');
  if (hero) {
    kick(hero);
    hero.addEventListener('loadeddata', () => kick(hero), { once: true });
  }

  let armed = true;
  const unlock = () => {
    if (!armed) return;
    armed = false;
    retryVisible();
    ['touchstart', 'pointerdown', 'click', 'scroll'].forEach((e) =>
      window.removeEventListener(e, unlock)
    );
  };
  ['touchstart', 'pointerdown', 'click', 'scroll'].forEach((e) =>
    window.addEventListener(e, unlock, { passive: true })
  );

  // returning to the tab suspends and does not always resume playback
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) retryVisible();
  });
})();
