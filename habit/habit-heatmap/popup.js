// Fenêtre de la barre d'outils : cocher vite ses habitudes et réafficher l'onglet sur un site masqué.
// Elle lit et écrit dans la même mémoire (storage.local) que le tiroir : tout reste synchronisé.

const api = typeof browser !== 'undefined' ? browser : chrome;
const KEYS = { tasks: 'habitHeatmapTasks', texts: 'habitHeatmapTexts', settings: 'habitHeatmapSettings' };

let tasks = [];
let settings = { theme: 'auto', hiddenSites: [] };
let title = 'Mes habitudes';
let site = null;

const pad = (n) => String(n).padStart(2, '0');
const dateKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const countOf = (t, k) => {
  const v = t.days?.[k];
  return Math.min(t.goal || 1, v === true ? 1 : Number(v) || 0);
};

function h(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'style') node.style.cssText = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

async function init() {
  const res = await api.storage.local.get(Object.values(KEYS));
  tasks = res[KEYS.tasks] || [];
  settings = { ...settings, ...(res[KEYS.settings] || {}) };
  title = res[KEYS.texts]?.title || title;
  try {
    const [tab] = await api.tabs.query({ active: true, currentWindow: true });
    const url = new URL(tab.url);
    if (url.protocol === 'http:' || url.protocol === 'https:') site = url.hostname;
  } catch { /* page interne de Firefox : pas de site */ }
  render();
}

function toggleToday(t) {
  const k = dateKey(new Date());
  const goal = t.goal || 1;
  const n = countOf(t, k);
  const next = n >= goal ? 0 : n + 1;
  t.days = t.days || {};
  if (next) t.days[k] = next; else delete t.days[k];
  api.storage.local.set({ [KEYS.tasks]: tasks });
  render();
}

function toggleSite() {
  const hidden = settings.hiddenSites.includes(site);
  settings.hiddenSites = hidden ? settings.hiddenSites.filter((s) => s !== site) : [...settings.hiddenSites, site];
  api.storage.local.set({ [KEYS.settings]: settings });
  render();
}

// Interrupteur général : afficher ou non l'onglet sur toutes les pages
function toggleEverywhere() {
  settings.showTab = settings.showTab === false; // false → true, et tout le reste → false
  api.storage.local.set({ [KEYS.settings]: settings });
  render();
}

function render() {
  document.documentElement.dataset.theme = settings.theme;
  const app = document.getElementById('app');
  app.textContent = '';
  const today = new Date();
  const k = dateKey(today);

  app.append(h('div', { class: 'head' },
    h('h1', {}, title),
    h('span', { class: 'date' }, today.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' }))));

  if (!tasks.length) {
    app.append(h('p', { class: 'empty' }, 'Ouvre l’onglet sur le bord droit de n’importe quelle page pour créer ta première habitude 🌱'));
  }

  for (const t of tasks) {
    const goal = t.goal || 1;
    const n = countOf(t, k);
    const done = n >= goal;

    // Les 7 derniers jours en petits carrés
    const week = h('div', { class: 'week' });
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const c = countOf(t, dateKey(d));
      week.append(h('i', { title: d.toLocaleDateString('fr-FR', { weekday: 'long' }),
        style: c ? `background:color-mix(in srgb, ${t.color} ${c >= goal ? 100 : 50}%, var(--empty))` : null }));
    }

    app.append(h('div', { class: 'habit', style: `--c:${t.color}` },
      h('span', { class: 'emoji' }, t.emoji || '✨'),
      h('div', { class: 'info' }, h('div', { class: 'name' }, t.name), week),
      h('button', { class: 'check' + (done ? ' done' : ''), title: done ? 'Annuler' : 'Marquer comme fait',
        onclick: () => toggleToday(t) }, done ? '✓' : goal > 1 ? `${n}/${goal}` : '+1')));
  }

  const everywhere = settings.showTab !== false;
  app.append(h('div', { class: 'site' },
    h('span', {}, 'Onglet sur toutes les pages'),
    h('button', { class: 'switch' + (everywhere ? ' on' : ''), role: 'switch', 'aria-checked': String(everywhere),
      'aria-label': 'Onglet sur toutes les pages', onclick: toggleEverywhere })));

  // Le réglage par site n'a de sens que si l'onglet est activé partout
  if (site && everywhere) {
    const visible = !settings.hiddenSites.includes(site);
    app.append(h('div', { class: 'site sub' },
      h('span', {}, `Visible sur ${site}`),
      h('button', { class: 'switch' + (visible ? ' on' : ''), role: 'switch', 'aria-checked': String(visible),
        'aria-label': `Visible sur ${site}`, onclick: toggleSite })));
  }

  if (!everywhere) {
    app.append(h('p', { class: 'hint' }, 'L’onglet est masqué partout. Tu peux toujours cocher tes habitudes ici.'));
  }

  if (everywhere) app.append(h('p', { class: 'hint' }, 'Raccourci sur une page : ', h('kbd', {}, 'Alt'), ' + ', h('kbd', {}, 'Maj'), ' + ', h('kbd', {}, 'H')));
}

init();
