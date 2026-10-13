// Habit Heatmap v2 — script injecté dans chaque page
// Un onglet à encoche collé au bord droit de l'écran fait glisser un tiroir
// contenant jusqu'à 3 habitudes, chacune avec son calendrier façon GitHub.

(() => {
  // On ne s'affiche que dans la page principale (pas dans les iframes type pubs ou vidéos intégrées)
  if (window.top !== window) return;
  if (document.getElementById('habit-heatmap-host')) return;

  const api = typeof browser !== 'undefined' ? browser : chrome;

  // =====================================================================
  // 1. RÉGLAGES DE BASE
  // =====================================================================
  const MAX_TASKS = 3;
  const KEYS = { tasks: 'habitHeatmapTasks', texts: 'habitHeatmapTexts', settings: 'habitHeatmapSettings' };
  const PALETTE = ['#2da44e', '#0969da', '#8250df', '#bf3989', '#cf222e', '#e16f24', '#d4a72c', '#1b7c83'];
  const EMOJIS = ['📚', '🏃', '💧', '🧘', '🎸', '✍️', '🍎', '💤', '🧹', '💻', '🎨', '🌱',
                  '🏋️', '🚲', '🎧', '📝', '🧠', '☀️', '🙏', '📵', '🥗', '🐶', '🎮', '❤️'];
  const RANGES = [['13', '3 mois'], ['26', '6 mois'], ['53', '1 an']];
  const MILESTONES = [3, 7, 14, 21, 30, 50, 100, 200, 365];

  const DEFAULT_SETTINGS = { theme: 'auto', weeks: 53, tabTop: 18, hiddenSites: [], celebrate: true, hideFullscreen: true, showTab: true };

  // Tous les textes affichés. Modifiables ici ou dans Réglages → Textes.
  const DEFAULT_TEXTS = {
    title: 'Mes habitudes',
    markToday: 'Marquer comme fait',
    doneToday: 'Fait aujourd’hui ✓',
    add: '+ Nouvelle habitude',
    newTask: 'Nouvelle habitude',
    streak: 'jours d’affilée',
    allDone: 'Journée parfaite ✨',
    empty: 'Choisis jusqu’à 3 habitudes et regarde ton calendrier se colorer jour après jour.',
  };
  const TEXT_FIELDS = [
    ['title', 'Titre'],
    ['markToday', 'Bouton « pas fait »'],
    ['doneToday', 'Bouton « fait »'],
    ['add', 'Bouton d’ajout'],
    ['newTask', 'Nom par défaut'],
    ['streak', 'Texte de série'],
    ['allDone', 'Tout est fait'],
    ['empty', 'Message vide'],
  ];

  // =====================================================================
  // 2. ÉTAT (tout ce que l'extension "sait" à un instant donné)
  // =====================================================================
  // task = { id, name, emoji, color, goal, days: { "2026-10-13": 2, ... }, createdAt }
  const state = {
    tasks: [],
    texts: { ...DEFAULT_TEXTS },
    settings: { ...DEFAULT_SETTINGS },
    open: false,
    view: 'habits', // 'habits' ou 'settings'
    editing: null,  // id de l'habitude en cours de personnalisation
  };

  // =====================================================================
  // 3. OUTILS : dates, statistiques
  // =====================================================================
  const pad = (n) => String(n).padStart(2, '0');
  const dateKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const todayKey = () => dateKey(new Date());
  const parseKey = (k) => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d); };
  const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

  const countOf = (t, k) => Math.min(t.goal, t.days[k] || 0);
  const isDone = (t, k) => countOf(t, k) >= t.goal;

  function calendarStart(weeks) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayIndex = (today.getDay() + 6) % 7; // lundi = 0 ... dimanche = 6
    const start = new Date(today);
    start.setDate(today.getDate() - (weeks - 1) * 7 - dayIndex);
    return { start, today };
  }

  // Série en cours (on tolère que ce ne soit pas encore fait aujourd'hui)
  function currentStreak(t) {
    const d = new Date();
    if (!isDone(t, dateKey(d))) d.setDate(d.getDate() - 1);
    let n = 0;
    while (isDone(t, dateKey(d))) { n++; d.setDate(d.getDate() - 1); }
    return n;
  }

  function bestStreak(t) {
    const keys = Object.keys(t.days).filter((k) => isDone(t, k)).sort();
    let best = 0, run = 0, prev = null;
    for (const k of keys) {
      const d = parseKey(k);
      run = prev && Math.round((d - prev) / 86400000) === 1 ? run + 1 : 1;
      best = Math.max(best, run);
      prev = d;
    }
    return best;
  }

  function rate30(t) {
    const d = new Date();
    let done = 0;
    for (let i = 0; i < 30; i++) { if (isDone(t, dateKey(d))) done++; d.setDate(d.getDate() - 1); }
    return Math.round((done / 30) * 100);
  }

  const totalDone = (t) => Object.keys(t.days).filter((k) => isDone(t, k)).length;

  // Remet d'aplomb une habitude (utile pour les données de la v1 ou un fichier importé)
  function normalizeTask(t) {
    const days = {};
    for (const [k, v] of Object.entries(t.days || {})) {
      const n = v === true ? 1 : Number(v) || 0;
      if (n > 0 && /^\d{4}-\d{2}-\d{2}$/.test(k)) days[k] = Math.min(10, n);
    }
    return {
      id: String(t.id || Date.now().toString(36) + Math.random().toString(36).slice(2, 6)),
      name: String(t.name || DEFAULT_TEXTS.newTask).slice(0, 40),
      emoji: typeof t.emoji === 'string' && t.emoji ? t.emoji : '✨',
      color: /^#[0-9a-f]{6}$/i.test(t.color) ? t.color : PALETTE[0],
      goal: clamp(Number(t.goal) || 1, 1, 10),
      days,
      createdAt: t.createdAt || Date.now(),
    };
  }

  function pickTexts(obj) {
    const out = { ...DEFAULT_TEXTS };
    for (const k of Object.keys(DEFAULT_TEXTS)) if (typeof obj?.[k] === 'string' && obj[k].trim()) out[k] = obj[k];
    return out;
  }

  // =====================================================================
  // 4. SAUVEGARDE (storage.local est partagé entre tous les onglets)
  // =====================================================================
  async function load() {
    const res = await api.storage.local.get(Object.values(KEYS));
    state.tasks = (res[KEYS.tasks] || []).map(normalizeTask);
    state.texts = pickTexts(res[KEYS.texts]);
    state.settings = { ...DEFAULT_SETTINGS, ...(res[KEYS.settings] || {}) };
    applySettings();
    render();
  }

  function saveTasks() { render(); api.storage.local.set({ [KEYS.tasks]: state.tasks }); }
  function saveTexts() { render(); api.storage.local.set({ [KEYS.texts]: state.texts }); }
  function saveSettings(patch) {
    Object.assign(state.settings, patch);
    applySettings();
    render();
    api.storage.local.set({ [KEYS.settings]: state.settings });
  }

  // Un autre onglet (ou le bouton de la barre d'outils) a changé quelque chose
  api.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    let changed = false;
    const sync = (key, value) => {
      if (JSON.stringify(value) !== JSON.stringify(state[key])) { state[key] = value; changed = true; }
    };
    if (changes[KEYS.tasks]) sync('tasks', (changes[KEYS.tasks].newValue || []).map(normalizeTask));
    if (changes[KEYS.texts]) sync('texts', pickTexts(changes[KEYS.texts].newValue));
    if (changes[KEYS.settings]) sync('settings', { ...DEFAULT_SETTINGS, ...(changes[KEYS.settings].newValue || {}) });
    if (!changed) return;
    applySettings();
    const active = root.activeElement;
    if (active && active.tagName === 'INPUT' && active.type === 'text') return; // on ne casse pas une saisie
    render();
  });

  // =====================================================================
  // 5. ACTIONS
  // =====================================================================
  const findTask = (id) => state.tasks.find((t) => t.id === id);

  function addTask() {
    if (state.tasks.length >= MAX_TASKS) return;
    const usedColors = state.tasks.map((t) => t.color);
    const usedEmojis = state.tasks.map((t) => t.emoji);
    const task = normalizeTask({
      name: state.texts.newTask,
      color: PALETTE.find((c) => !usedColors.includes(c)),
      emoji: EMOJIS.find((e) => !usedEmojis.includes(e)),
    });
    state.tasks.push(task);
    state.editing = task.id; // on ouvre directement la personnalisation
    saveTasks();
    requestAnimationFrame(() => {
      const input = panel.querySelector(`[data-name="${task.id}"]`);
      if (input) { input.focus(); input.select(); }
    });
  }

  function updateTask(id, changes) { Object.assign(findTask(id), changes); saveTasks(); }

  function removeTask(id) {
    state.tasks = state.tasks.filter((t) => t.id !== id);
    if (state.editing === id) state.editing = null;
    saveTasks();
  }

  function setCount(id, key, n) {
    const t = findTask(id);
    const wasDone = isDone(t, key);
    n = clamp(n, 0, t.goal);
    if (n) t.days[key] = n; else delete t.days[key];
    saveTasks();
    if (!wasDone && isDone(t, key) && key === todayKey()) celebrate(t);
  }

  // =====================================================================
  // 6. CÉLÉBRATIONS (confettis + petits messages)
  // =====================================================================
  function celebrate(t) {
    const k = todayKey();
    const allDone = state.tasks.length > 1 && state.tasks.every((x) => isDone(x, k));
    if (state.settings.celebrate) burst(t.id, allDone ? 44 : 18);
    const s = currentStreak(t);
    if (allDone) toast(state.texts.allDone);
    else if (MILESTONES.includes(s)) toast(`🔥 ${s} ${state.texts.streak} — ${t.name}`);
  }

  function burst(id, amount) {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const btn = panel.querySelector(`[data-today="${id}"]`);
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const colors = [...state.tasks.map((t) => t.color), '#ffd33d', '#ffffff'];
    for (let i = 0; i < amount; i++) {
      const p = h('i', { class: 'confetti', style: `left:${x}px;top:${y}px;background:${colors[i % colors.length]}` });
      fx.append(p);
      const angle = Math.random() * Math.PI * 2;
      const dist = 40 + Math.random() * (amount > 20 ? 140 : 80);
      const dx = Math.cos(angle) * dist, dy = Math.sin(angle) * dist - 40;
      p.animate([
        { transform: 'translate(-50%,-50%) scale(.6)', opacity: 1 },
        { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) rotate(${Math.random() * 360}deg)`, opacity: 1, offset: 0.55 },
        { transform: `translate(calc(-50% + ${dx * 1.15}px), calc(-50% + ${dy + 90}px)) rotate(${Math.random() * 720}deg)`, opacity: 0 },
      ], { duration: 900 + Math.random() * 600, easing: 'cubic-bezier(.2,.7,.3,1)' }).onfinish = () => p.remove();
    }
  }

  let toastTimer;
  function toast(message) {
    toastEl.textContent = message;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2800);
  }

  // =====================================================================
  // 7. SAUVEGARDE DANS UN FICHIER (exporter / importer)
  // =====================================================================
  function exportData() {
    const data = { app: 'habit-heatmap', version: 2, exportedAt: new Date().toISOString(),
                   tasks: state.tasks, texts: state.texts };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const a = h('a', { href: url, download: `habit-heatmap-${todayKey()}.json` });
    ui.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast('Sauvegarde téléchargée 💾');
  }

  async function importData(file) {
    try {
      const data = JSON.parse(await file.text());
      if (!Array.isArray(data.tasks)) throw new Error('format');
      if (!confirm('Remplacer tes habitudes actuelles par celles de ce fichier ?')) return;
      state.tasks = data.tasks.slice(0, MAX_TASKS).map(normalizeTask);
      if (data.texts) state.texts = pickTexts(data.texts);
      saveTasks();
      saveTexts();
      toast('Sauvegarde restaurée ✓');
    } catch {
      toast('Ce fichier n’est pas une sauvegarde valide');
    }
  }

  // =====================================================================
  // 8. PETIT OUTIL POUR FABRIQUER DES ÉLÉMENTS HTML
  // h('button', { class: 'x', onclick: fn }, 'texte') → <button class="x">texte</button>
  // Les textes passent toujours par createTextNode : impossible d'injecter du HTML.
  // =====================================================================
  function h(tag, props = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'style') node.style.cssText = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else if (k in node && !k.includes('-')) node[k] = v;
      else node.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }

  // =====================================================================
  // 9. LE STYLE (dans une bulle Shadow DOM : le CSS du site ne nous touche pas)
  // =====================================================================
  const DARK = '--bg:#0d1117;--bg2:#161b22;--fg:#e6edf3;--muted:#8d96a0;--empty:#21262d;--border:#30363d;--shadow:rgba(0,0,0,.55);';
  const CSS = `
    *{box-sizing:border-box;margin:0;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
    button,input{font:inherit;color:inherit}
    :focus-visible{outline:2px solid var(--accent);outline-offset:2px}

    .ui{display:contents;--bg:#fff;--bg2:#f6f8fa;--fg:#1f2328;--muted:#656d76;--empty:#ebedf0;--border:#d8dee4;
        --shadow:rgba(31,35,40,.18);--accent:#2da44e;--tab-w:28px}
    @media (prefers-color-scheme:dark){.ui[data-theme="auto"]{${DARK}}}
    .ui[data-theme="dark"]{${DARK}}

    /* ---- Tiroir : onglet + panneau collés. Fermé, on ne laisse dépasser que l'onglet ---- */
    .drawer{display:flex;align-items:flex-start;pointer-events:auto;
      transform:translateX(calc(100% - var(--tab-w)));transition:transform .38s cubic-bezier(.2,.8,.2,1);
      filter:drop-shadow(-4px 6px 14px var(--shadow))}
    .drawer.open{transform:none}

    /* ---- L'onglet, avec son encoche découpée par un masque ---- */
    .tab{flex:none;width:var(--tab-w);height:100px;margin-right:-1px;padding:10px 0;border:1px solid var(--border);
      border-right:0;border-radius:12px 0 0 12px;background:var(--bg);color:var(--fg);cursor:grab;touch-action:none;
      user-select:none;display:flex;flex-direction:column;align-items:center;justify-content:space-between;
      -webkit-mask:radial-gradient(circle 5px at 0 50%,transparent 97%,#000 100%);
              mask:radial-gradient(circle 5px at 0 50%,transparent 97%,#000 100%)}
    .tab:active{cursor:grabbing}
    .chevron{font-size:15px;line-height:1;color:var(--muted);transition:transform .38s}
    .drawer.open .chevron{transform:rotate(180deg)}
    .tab:hover .chevron{color:var(--fg)}
    .grip{display:grid;gap:2px;margin-left:5px}
    .grip i{width:9px;height:2px;border-radius:2px;background:var(--border)}
    .tab-count{font-size:10px;font-weight:700;color:var(--muted);writing-mode:vertical-rl;letter-spacing:.5px;min-height:20px}
    .tab.all-done .tab-count{color:var(--accent)}
    .tab.all-done .grip i{background:var(--accent)}

    /* ---- Panneau ---- */
    .panel{width:min(600px,calc(100vw - 44px));max-height:calc(100vh - 24px);overflow:auto;overscroll-behavior:contain;
      background:var(--bg);color:var(--fg);border:1px solid var(--border);border-right:0;border-radius:16px 0 0 16px;
      padding:14px;font-size:12.5px;line-height:1.35;scrollbar-width:thin;
      visibility:hidden;transition:visibility 0s .38s}
    .drawer.open .panel{visibility:visible;transition-delay:0s}

    .head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
    .titles{flex:1;min-width:0}
    h2{font-size:15px;font-weight:650;letter-spacing:-.01em}
    .date{font-size:11.5px;color:var(--muted);margin-top:1px}
    .ring{flex:none;width:40px;height:40px;border-radius:50%;display:grid;place-items:center;position:relative;
      background:conic-gradient(var(--accent) var(--p),var(--empty) 0);font-size:10.5px;font-weight:700}
    .ring::before{content:"";position:absolute;inset:4px;border-radius:50%;background:var(--bg)}
    .ring span{position:relative}
    .icon-btn{flex:none;border:1px solid transparent;background:none;color:var(--muted);cursor:pointer;font-size:14px;
      line-height:1;padding:6px 8px;border-radius:8px}
    .icon-btn:hover,.icon-btn.on{background:var(--bg2);border-color:var(--border);color:var(--fg)}

    /* ---- Carte d'une habitude ---- */
    .card{position:relative;background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:12px 12px 12px 15px;
      margin-bottom:10px;overflow:hidden}
    .card::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--c)}
    .card-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
    .emoji{flex:none;font-size:17px;width:32px;height:32px;display:grid;place-items:center;border-radius:9px;
      background:color-mix(in srgb,var(--c) 18%,transparent)}
    .name{flex:1;min-width:0;font-size:14px;font-weight:600;background:transparent;border:1px solid transparent;
      border-radius:6px;padding:3px 6px}
    .name:hover,.name:focus{border-color:var(--border);background:var(--bg);outline:none}
    .pill{flex:none;font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;
      background:color-mix(in srgb,var(--c) 16%,transparent)}

    .today-row{display:flex;gap:6px;margin-bottom:12px}
    .today{flex:1;display:flex;align-items:center;justify-content:space-between;gap:8px;cursor:pointer;
      padding:8px 12px;border-radius:9px;border:1.5px solid var(--c);font-weight:600;font-size:12.5px;
      background:linear-gradient(90deg,color-mix(in srgb,var(--c) 28%,transparent) var(--p),transparent var(--p));
      transition:transform .1s ease}
    .today:hover{box-shadow:inset 0 0 0 99px color-mix(in srgb,var(--c) 7%,transparent)}
    .today:active{transform:scale(.98)}
    .today.done{background:var(--c);color:#fff}
    .today-count{font-variant-numeric:tabular-nums;opacity:.85}
    .minus{border:1.5px solid var(--border);font-size:16px;padding:0 12px}

    /* ---- Le calendrier ---- */
    .scroller{overflow-x:auto;padding:3px 0 4px;scrollbar-width:thin}
    .cal{display:grid;grid-template-columns:auto auto;column-gap:5px;row-gap:3px;width:max-content}
    .months{grid-column:2;display:grid;grid-auto-flow:column;grid-auto-columns:calc(var(--cell) + var(--gap));
      font-size:9.5px;color:var(--muted);height:12px}
    .months span{white-space:nowrap}
    .wdays{grid-column:1;display:grid;grid-template-rows:repeat(7,var(--cell));gap:var(--gap);font-size:8.5px;
      color:var(--muted);line-height:var(--cell)}
    .grid{grid-column:2;display:grid;grid-template-rows:repeat(7,var(--cell));grid-auto-flow:column;
      grid-auto-columns:var(--cell);gap:var(--gap)}
    .cell{width:var(--cell);height:var(--cell);border-radius:max(2px,calc(var(--cell) / 4));background:var(--empty);
      cursor:pointer;transition:transform .12s}
    .cell:hover{transform:scale(1.4);position:relative;z-index:1}
    .cell.is-today{box-shadow:0 0 0 1.5px var(--fg)}
    .cell.future{visibility:hidden}

    .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px}
    .stat{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:6px 9px}
    .stat strong{display:block;font-size:14px;font-variant-numeric:tabular-nums}
    .stat span{font-size:10.5px;color:var(--muted)}

    /* ---- Personnalisation d'une habitude ---- */
    .editor{margin-top:12px;padding-top:12px;border-top:1px dashed var(--border);display:grid;gap:12px}
    .label{display:block;font-size:10.5px;font-weight:700;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
    .emoji-grid{display:grid;grid-template-columns:repeat(12,1fr);gap:3px}
    .emoji-opt{border:1px solid transparent;background:none;border-radius:7px;cursor:pointer;font-size:15px;padding:3px 0}
    .emoji-opt:hover{background:var(--bg)}
    .emoji-opt.on{background:var(--bg);border-color:var(--c)}
    .swatches{display:flex;gap:7px;flex-wrap:wrap;align-items:center}
    .swatch{width:22px;height:22px;border-radius:50%;background:var(--s);border:2px solid var(--bg2);
      box-shadow:0 0 0 1px var(--border);cursor:pointer;padding:0;position:relative}
    .swatch.on{box-shadow:0 0 0 2px var(--fg)}
    .swatch.custom{background:conic-gradient(#cf222e,#d4a72c,#2da44e,#0969da,#8250df,#cf222e);overflow:hidden}
    .swatch.custom input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
    .stepper{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--bg)}
    .stepper button{border:0;background:none;cursor:pointer;padding:4px 11px;font-size:15px}
    .stepper button:hover{background:var(--bg2)}
    .stepper span{min-width:62px;text-align:center;font-weight:600}
    .row-between{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;flex-wrap:wrap}
    .danger{border:1px solid transparent;background:none;color:#cf222e;cursor:pointer;padding:5px 8px;border-radius:7px;font-size:12px}
    .danger:hover{background:rgba(207,34,46,.1)}

    .add{width:100%;cursor:pointer;padding:10px;border-radius:12px;font-size:12.5px;font-weight:600;
      border:1.5px dashed var(--border);background:transparent;color:var(--muted)}
    .add:hover{color:var(--fg);border-color:var(--muted)}
    .empty{text-align:center;padding:16px 20px 18px;color:var(--muted)}
    .empty .big{font-size:30px;display:block;margin-bottom:8px}
    .foot{margin-top:10px;font-size:10.5px;color:var(--muted);text-align:center}
    kbd{font:inherit;font-size:10px;border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:0 4px;background:var(--bg2)}

    /* ---- Réglages ---- */
    .group{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:11px 12px;margin-bottom:10px;display:grid;gap:9px}
    .group h3{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
    .setting{display:flex;align-items:center;justify-content:space-between;gap:10px}
    .seg{display:inline-flex;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:2px}
    .seg button{border:0;background:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px;color:var(--muted)}
    .seg button.on{background:var(--fg);color:var(--bg)}
    .switch{flex:none;width:34px;height:20px;border-radius:999px;border:0;background:var(--border);position:relative;cursor:pointer;transition:background .2s}
    .switch::after{content:"";position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#fff;
      box-shadow:0 1px 2px rgba(0,0,0,.3);transition:transform .2s}
    .switch.on{background:var(--accent)}
    .switch.on::after{transform:translateX(14px)}
    .btns{display:flex;gap:6px;flex-wrap:wrap}
    .btn{border:1px solid var(--border);background:var(--bg);border-radius:8px;padding:6px 11px;cursor:pointer;font-size:12px;font-weight:600}
    .btn:hover{border-color:var(--muted)}
    .hint{font-size:11px;color:var(--muted)}
    .texts{display:grid;grid-template-columns:auto 1fr;gap:5px 10px;align-items:center}
    .texts label{font-size:11px;color:var(--muted)}
    .texts input{font-size:12px;padding:4px 7px;border:1px solid var(--border);border-radius:6px;background:var(--bg);min-width:0}

    /* ---- Couches flottantes : confettis, infobulle, message ---- */
    .fx{position:fixed;inset:0;pointer-events:none;overflow:hidden}
    .confetti{position:fixed;width:7px;height:10px;border-radius:2px}
    .tip{position:fixed;pointer-events:none;transform:translate(-50%,calc(-100% - 8px));background:var(--fg);color:var(--bg);
      font-size:11px;padding:4px 8px;border-radius:6px;white-space:nowrap;opacity:0;transition:opacity .1s}
    .tip.show{opacity:1}
    .toast{position:fixed;right:20px;bottom:20px;background:var(--fg);color:var(--bg);padding:10px 15px;border-radius:10px;
      font-size:12.5px;font-weight:600;box-shadow:0 8px 24px var(--shadow);transform:translateY(16px);opacity:0;
      transition:transform .25s,opacity .25s;pointer-events:none;max-width:320px}
    .toast.show{transform:none;opacity:1}

    @media (prefers-reduced-motion:reduce){*{transition:none!important}}
  `;

  // =====================================================================
  // 10. LA STRUCTURE FIXE (construite une seule fois, pour que les animations glissent bien)
  // =====================================================================
  const host = document.createElement('div');
  host.id = 'habit-heatmap-host';
  host.style.cssText = 'all:initial;display:block;position:fixed;right:0;top:18vh;z-index:2147483647;pointer-events:none;';
  const root = host.attachShadow({ mode: 'open' });
  root.append(h('style', {}, CSS));

  const tabCount = h('span', { class: 'tab-count' });
  const tab = h('button', { class: 'tab', title: 'Ouvrir / fermer (Alt+Maj+H) — glisse pour déplacer', 'aria-expanded': 'false' },
    h('span', { class: 'chevron' }, '‹'),
    h('span', { class: 'grip' }, h('i'), h('i'), h('i')),
    tabCount);
  const panel = h('div', { class: 'panel', inert: true });
  const drawer = h('div', { class: 'drawer' }, tab, panel);
  const fx = h('div', { class: 'fx' });
  const tip = h('div', { class: 'tip' });
  const toastEl = h('div', { class: 'toast', role: 'status' });
  const ui = h('div', { class: 'ui', 'data-theme': 'auto' }, drawer, fx, tip, toastEl);
  root.append(ui);
  document.documentElement.append(host);

  function setOpen(open) {
    state.open = open;
    drawer.classList.toggle('open', open);
    panel.inert = !open;
    tab.setAttribute('aria-expanded', String(open));
    if (open) afterRender();
    else hideTip();
  }

  // Est-ce qu'on est en plein écran ? Deux cas possibles :
  // 1) une vidéo (ou un élément de la page) est passée en plein écran → document.fullscreenElement
  // 2) toute la fenêtre de Firefox est en plein écran (F11, ou le bouton vert sur Mac)
  //    → la fenêtre fait exactement la taille de l'écran
  function isFullscreen() {
    if (document.fullscreenElement) return true;
    if (matchMedia('(display-mode: fullscreen)').matches) return true;
    return outerWidth >= screen.width && outerHeight >= screen.height;
  }

  // Applique les réglages qui ne dépendent pas du contenu : thème, position, visibilité
  function applySettings() {
    ui.dataset.theme = state.settings.theme;
    applyVisibility();
    placeTab();
  }

  function applyVisibility() {
    const globallyOff = state.settings.showTab === false;          // désactivé sur toutes les pages
    const siteHidden = state.settings.hiddenSites.includes(location.hostname); // désactivé sur ce site
    const fullscreenHidden = state.settings.hideFullscreen && isFullscreen();  // plein écran
    const hidden = globallyOff || siteHidden || fullscreenHidden;
    host.style.display = hidden ? 'none' : 'block';
    if (hidden && state.open) setOpen(false);
  }

  // On revérifie à chaque entrée/sortie de plein écran
  document.addEventListener('fullscreenchange', applyVisibility);
  matchMedia('(display-mode: fullscreen)').addEventListener('change', applyVisibility);

  function placeTab() {
    const top = clamp((state.settings.tabTop / 100) * innerHeight, 8, innerHeight - 110);
    host.style.top = top + 'px';
  }

  // Si le panneau dépasse en bas de l'écran, on le remonte (l'onglet, lui, reste où il est)
  function fitPanel() {
    panel.style.marginTop = '0px';
    const top = host.getBoundingClientRect().top;
    const overflow = top + panel.offsetHeight - (innerHeight - 12);
    if (overflow > 0) panel.style.marginTop = -Math.min(overflow, top - 12) + 'px';
  }

  function afterRender() {
    requestAnimationFrame(() => {
      fitPanel();
      panel.querySelectorAll('.scroller').forEach((sc) => (sc.scrollLeft = sc.scrollWidth));
    });
  }

  addEventListener('resize', () => { applyVisibility(); placeTab(); if (state.open) fitPanel(); });

  // ---- L'onglet : un clic ouvre/ferme, un glisser le déplace verticalement ----
  let drag = null;
  tab.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    drag = { y: e.clientY, top: host.getBoundingClientRect().top, moved: false };
    tab.setPointerCapture(e.pointerId);
  });
  tab.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dy = e.clientY - drag.y;
    if (Math.abs(dy) > 4) drag.moved = true;
    if (drag.moved) {
      host.style.top = clamp(drag.top + dy, 8, innerHeight - 110) + 'px';
      if (state.open) fitPanel();
    }
  });
  tab.addEventListener('pointerup', () => {
    if (!drag) return;
    const moved = drag.moved;
    drag = null;
    if (moved) saveSettings({ tabTop: Math.round((parseFloat(host.style.top) / innerHeight) * 1000) / 10 });
    else setOpen(!state.open);
  });
  tab.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(!state.open); }
  });

  // Empêche les raccourcis clavier du site (YouTube, Gmail...) de réagir quand tu tapes dans le tiroir
  ['keydown', 'keyup', 'keypress'].forEach((type) =>
    host.addEventListener(type, (e) => {
      if (type === 'keydown' && e.key === 'Escape' && state.open) setOpen(false);
      e.stopPropagation();
    })
  );

  // Raccourci global : Alt + Maj + H
  document.addEventListener('keydown', (e) => {
    if (e.altKey && e.shiftKey && e.code === 'KeyH' && host.style.display !== 'none') {
      e.preventDefault();
      setOpen(!state.open);
    }
  }, true);

  // Clic en dehors du tiroir = on le referme
  document.addEventListener('click', (e) => {
    if (state.open && !e.composedPath().includes(host)) setOpen(false);
  });

  // ---- Infobulle des cases du calendrier ----
  function showTip(cell, text) {
    const r = cell.getBoundingClientRect();
    tip.textContent = text;
    tip.style.left = r.left + r.width / 2 + 'px';
    tip.style.top = r.top + 'px';
    tip.classList.add('show');
  }
  function hideTip() { tip.classList.remove('show'); }

  // =====================================================================
  // 11. LES VUES
  // =====================================================================
  function render() {
    const k = todayKey();
    const done = state.tasks.filter((t) => isDone(t, k)).length;
    const n = state.tasks.length;
    tabCount.textContent = n ? `${done}/${n}` : '';
    tab.classList.toggle('all-done', n > 0 && done === n);

    hideTip();
    panel.textContent = '';
    panel.append(state.view === 'settings' ? settingsView() : habitsView());
    if (state.open) afterRender();
  }

  // ---------- Vue principale ----------
  function habitsView() {
    const T = state.texts;
    const k = todayKey();
    const n = state.tasks.length;
    const done = state.tasks.filter((t) => isDone(t, k)).length;
    const dateLabel = capitalize(new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' }));

    return h('div', {},
      h('header', { class: 'head' },
        h('div', { class: 'ring', style: `--p:${n ? (done / n) * 100 : 0}%`, title: 'Habitudes faites aujourd’hui' },
          h('span', {}, n ? `${done}/${n}` : '–')),
        h('div', { class: 'titles' },
          h('h2', {}, T.title),
          h('p', { class: 'date' }, n && done === n ? `${dateLabel} · ${T.allDone}` : dateLabel)),
        h('button', { class: 'icon-btn', title: 'Réglages', 'aria-label': 'Réglages',
          onclick: () => { state.view = 'settings'; render(); } }, '⚙')),

      n === 0 && h('div', { class: 'empty' }, h('span', { class: 'big' }, '🌱'), T.empty),
      state.tasks.map(taskCard),
      n < MAX_TASKS && h('button', { class: 'add', onclick: addTask }, T.add),
      h('p', { class: 'foot' }, h('kbd', {}, 'Alt'), ' + ', h('kbd', {}, 'Maj'), ' + ', h('kbd', {}, 'H'),
        ' pour ouvrir ou fermer · glisse l’onglet pour le déplacer'));
  }

  function taskCard(t) {
    const T = state.texts;
    const k = todayKey();
    const count = countOf(t, k);
    const done = count >= t.goal;
    const editing = state.editing === t.id;
    const streak = currentStreak(t);

    return h('section', { class: 'card', style: `--c:${t.color}` },
      h('div', { class: 'card-head' },
        h('span', { class: 'emoji', 'aria-hidden': 'true' }, t.emoji),
        h('input', { class: 'name', type: 'text', value: t.name, maxLength: 40, 'data-name': t.id,
          'aria-label': 'Nom de l’habitude', title: 'Clique pour renommer',
          onchange: (e) => updateTask(t.id, { name: e.target.value.trim() || T.newTask }),
          onkeydown: (e) => e.key === 'Enter' && e.target.blur() }),
        streak > 0 && h('span', { class: 'pill', title: `${streak} ${T.streak}` }, `🔥 ${streak}`),
        h('button', { class: 'icon-btn' + (editing ? ' on' : ''), title: 'Personnaliser', 'aria-label': 'Personnaliser',
          onclick: () => { state.editing = editing ? null : t.id; render(); } }, '✎')),

      h('div', { class: 'today-row' },
        h('button', { class: 'today' + (done ? ' done' : ''), 'data-today': t.id,
          style: `--p:${Math.round((count / t.goal) * 100)}%`,
          onclick: () => setCount(t.id, k, done ? 0 : count + 1) },
          h('span', {}, done ? T.doneToday : T.markToday),
          t.goal > 1 && h('span', { class: 'today-count' }, `${count}/${t.goal}`)),
        t.goal > 1 && count > 0 && !done && h('button', { class: 'icon-btn minus', title: 'Retirer une fois',
          onclick: () => setCount(t.id, k, count - 1) }, '−')),

      calendar(t),

      h('div', { class: 'stats' },
        stat(`${bestStreak(t)} j`, 'Meilleure série'),
        stat(`${rate30(t)} %`, '30 derniers jours'),
        stat(totalDone(t), 'Jours réussis')),

      editing && editor(t));
  }

  const stat = (value, label) => h('div', { class: 'stat' }, h('strong', {}, value), h('span', {}, label));

  function cellColor(t, n) {
    if (!n) return '';
    const ratio = Math.min(1, n / t.goal);
    const pct = ratio >= 1 ? 100 : ratio >= 0.66 ? 75 : ratio >= 0.33 ? 55 : 38;
    return `color-mix(in srgb, ${t.color} ${pct}%, var(--empty))`;
  }

  function calendar(t) {
    const W = state.settings.weeks;
    const { start, today } = calendarStart(W);
    const gap = W > 30 ? 2 : 3;
    const size = clamp(Math.floor((528 - gap * (W - 1)) / W), 7, W <= 13 ? 24 : 16);
    const tKey = dateKey(today);

    // Ligne des mois
    const months = h('div', { class: 'months' });
    let lastMonth = -1;
    for (let w = 0; w < W; w++) {
      const d = new Date(start);
      d.setDate(start.getDate() + w * 7);
      const label = d.getMonth() !== lastMonth && w > 0 ? d.toLocaleDateString('fr-FR', { month: 'short' }) : '';
      months.append(h('span', {}, label));
      lastMonth = d.getMonth();
    }

    // Les cases
    const grid = h('div', { class: 'grid' });
    for (let i = 0; i < W * 7; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      if (d > today) { grid.append(h('div', { class: 'cell future' })); continue; }
      const k = dateKey(d);
      const n = countOf(t, k);
      grid.append(h('div', { class: 'cell' + (k === tKey ? ' is-today' : ''), 'data-k': k, style: n ? `background:${cellColor(t, n)}` : null }));
    }

    // Un seul écouteur pour toutes les cases (plus léger que 371 écouteurs !)
    grid.addEventListener('click', (e) => {
      const k = e.target.dataset.k;
      if (k) setCount(t.id, k, (countOf(t, k) + 1) % (t.goal + 1));
    });
    grid.addEventListener('mouseover', (e) => {
      const k = e.target.dataset.k;
      if (!k) return;
      const n = countOf(t, k);
      const day = parseKey(k).toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
      const status = t.goal > 1 ? `${n}/${t.goal}` : n ? 'fait ✓' : 'pas fait';
      showTip(e.target, `${day} — ${status}`);
    });
    grid.addEventListener('mouseleave', hideTip);

    return h('div', { class: 'scroller' },
      h('div', { class: 'cal', style: `--cell:${size}px;--gap:${gap}px` },
        h('span'), months,
        h('div', { class: 'wdays' }, ['L', '', 'M', '', 'V', '', 'D'].map((x) => h('span', {}, x))),
        grid));
  }

  function editor(t) {
    return h('div', { class: 'editor' },
      h('div', {},
        h('span', { class: 'label' }, 'Icône'),
        h('div', { class: 'emoji-grid' }, EMOJIS.map((e) =>
          h('button', { class: 'emoji-opt' + (e === t.emoji ? ' on' : ''), title: e, onclick: () => updateTask(t.id, { emoji: e }) }, e)))),
      h('div', {},
        h('span', { class: 'label' }, 'Couleur'),
        h('div', { class: 'swatches' },
          PALETTE.map((c) => h('button', { class: 'swatch' + (c === t.color ? ' on' : ''), style: `--s:${c}`,
            'aria-label': `Couleur ${c}`, onclick: () => updateTask(t.id, { color: c }) })),
          h('label', { class: 'swatch custom' + (PALETTE.includes(t.color) ? '' : ' on'), title: 'Couleur personnalisée' },
            h('input', { type: 'color', value: t.color, onchange: (e) => updateTask(t.id, { color: e.target.value }) })))),
      h('div', { class: 'row-between' },
        h('div', {},
          h('span', { class: 'label' }, 'Objectif par jour'),
          h('div', { class: 'stepper' },
            h('button', { 'aria-label': 'Moins', onclick: () => updateTask(t.id, { goal: clamp(t.goal - 1, 1, 10) }) }, '−'),
            h('span', {}, `${t.goal} fois`),
            h('button', { 'aria-label': 'Plus', onclick: () => updateTask(t.id, { goal: clamp(t.goal + 1, 1, 10) }) }, '+'))),
        h('button', { class: 'danger', onclick: () => {
          if (confirm(`Supprimer « ${t.name} » et tout son historique ?`)) removeTask(t.id);
        } }, 'Supprimer cette habitude')));
  }

  // ---------- Vue Réglages ----------
  function settingsView() {
    const S = state.settings;
    const site = location.hostname;

    const seg = (options, current, onPick) => h('div', { class: 'seg' },
      options.map(([value, label]) => h('button', { class: String(current) === value ? 'on' : '', onclick: () => onPick(value) }, label)));
    const toggle = (on, onFlip) => h('button', { class: 'switch' + (on ? ' on' : ''), role: 'switch',
      'aria-checked': String(on), onclick: () => onFlip(!on) });
    const setting = (label, control) => h('div', { class: 'setting' }, h('span', {}, label), control);

    const fileInput = h('input', { type: 'file', accept: '.json,application/json', style: 'display:none',
      onchange: (e) => e.target.files[0] && importData(e.target.files[0]) });

    return h('div', {},
      h('header', { class: 'head' },
        h('button', { class: 'icon-btn', title: 'Retour', 'aria-label': 'Retour',
          onclick: () => { state.view = 'habits'; render(); } }, '←'),
        h('div', { class: 'titles' }, h('h2', {}, 'Réglages'))),

      h('div', { class: 'group' },
        h('h3', {}, 'Apparence'),
        setting('Thème', seg([['auto', 'Auto'], ['light', 'Clair'], ['dark', 'Sombre']], S.theme, (v) => saveSettings({ theme: v }))),
        setting('Période affichée', seg(RANGES, S.weeks, (v) => saveSettings({ weeks: Number(v) }))),
        setting('Confettis et félicitations', toggle(S.celebrate, (v) => saveSettings({ celebrate: v }))),
        setting('Disparaître en plein écran', toggle(S.hideFullscreen, (v) => saveSettings({ hideFullscreen: v })))),

      h('div', { class: 'group' },
        h('h3', {}, 'Affichage'),
        site && setting(`Afficher l’onglet sur ${site}`, toggle(true, () => {
          saveSettings({ hiddenSites: [...S.hiddenSites, site] });
        })),
        setting('Afficher l’onglet sur toutes les pages', toggle(true, () => {
          if (confirm('Masquer l’onglet sur toutes les pages ?\n\nTu pourras le réactiver en cliquant sur l’icône de l’extension dans la barre d’outils de Firefox.')) {
            saveSettings({ showTab: false });
          }
        })),
        h('p', { class: 'hint' }, 'Pour faire revenir l’onglet, clique sur l’icône de l’extension dans la barre d’outils de Firefox.')),

      h('div', { class: 'group' },
        h('h3', {}, 'Textes'),
        h('div', { class: 'texts' }, TEXT_FIELDS.map(([key, label]) => [
          h('label', { htmlFor: 'txt-' + key }, label),
          h('input', { id: 'txt-' + key, type: 'text', value: state.texts[key], placeholder: DEFAULT_TEXTS[key],
            onchange: (e) => { state.texts[key] = e.target.value.trim() || DEFAULT_TEXTS[key]; saveTexts(); },
            onkeydown: (e) => e.key === 'Enter' && e.target.blur() }),
        ])),
        h('div', { class: 'btns' },
          h('button', { class: 'btn', onclick: () => { state.texts = { ...DEFAULT_TEXTS }; saveTexts(); } }, 'Remettre les textes d’origine'))),

      h('div', { class: 'group' },
        h('h3', {}, 'Sauvegarde'),
        h('p', { class: 'hint' }, 'Tes données restent uniquement dans ton navigateur. Exporte-les de temps en temps pour ne rien perdre.'),
        h('div', { class: 'btns' },
          h('button', { class: 'btn', onclick: exportData }, '⬇ Exporter'),
          h('button', { class: 'btn', onclick: () => fileInput.click() }, '⬆ Importer'),
          fileInput)));
  }

  load();
})();
