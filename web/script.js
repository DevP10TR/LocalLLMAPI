/* ==========================================================================
   LocalLLMAPI — panel
   Bez zależności od zewnętrznego origin (wszystko same-origin), bez innerHTML
   na danych użytkownika (bez XSS), z adaptacyjnym pollingiem.
   ========================================================================== */
(() => {
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const PORT = 1000;

/* i18n.js wystawia window.t. Rozwiązujemy go leniwie przy wywołaniu, żeby
   kolejność wczytywania skryptów nie miała znaczenia. */
const t = (key, vars) => (window.t ? window.t(key, vars) : key);

/* ---------- pomocnicze ---------- */

/** Buduje element zamiast wstawiać HTML — dane użytkownika nigdy nie parsujemy.
 *  Helper celowo NIE ma trybu `html:`: dostep do innerHTML zostawiamy tylko
 *  dla statycznych ikon. */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    // nodeType zamiast `instanceof Node` — działa też dla węzłów z innego kontekstu
    node.append(c && c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

const icon = (name, cls = '') => el('i', { class: `ti ti-${name}${cls ? ' ' + cls : ''}` });

const nf = new Intl.NumberFormat('pl-PL');
const num = (n) => nf.format(Math.round(Number(n) || 0));
const dec = (n, d = 1) => (Number(n) || 0).toFixed(d);

function ago(ts) {
  if (!ts) return t('time_never');
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return t('time_now');
  if (s < 3600) return `${Math.floor(s / 60)} ${t('time_min')}`;
  if (s < 86400) return `${Math.floor(s / 3600)} ${t('time_h')}`;
  return `${Math.floor(s / 86400)} ${t('time_d')}`;
}

function uptime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600),
        m = Math.floor((sec % 3600) / 60);
  if (d) return `${d}${t('time_d')} ${h}${t('time_h')}`;
  if (h) return `${h}${t('time_h')} ${m}${t('time_min')}`;
  return `${m}${t('time_min')} ${sec % 60}s`;
}

const bytes = (b) => {
  if (!b) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(u.length - 1, Math.floor(Math.log(b) / Math.log(1024)));
  return `${(b / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
};

const fmtDT = (ts) => (ts ? new Date(ts * 1000).toLocaleString('pl-PL', {
  day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
}) : '—');

const maskKey = (k) => (!k ? '—' : k.length > 15 ? `${k.slice(0, 10)}…${k.slice(-3)}` : k);

/* ---------- fetch ---------- */
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body ? { 'Content-Type': 'application/json' } : {},
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* pusta body */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

/* Kopia do schowka z fallbackiem — clipboard API nie działa po http:// (brak
   secure context), a panel ma działać także po adresie LAN. */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* idziemy dalej */ }
  try {
    const ta = el('textarea', { style: 'position:fixed;top:-9999px;opacity:0' });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    return ok;
  } catch { return false; }
}

/* ---------- toasty ---------- */
const TOAST_ICON = { ok: 'circle-check', err: 'alert-circle', info: 'info-circle' };
function toast(message, kind = 'ok', ms = 3000) {
  const host = $('#toasts');
  const node = el('div', { class: `toast ${kind}` }, icon(TOAST_ICON[kind] || 'info-circle'), el('span', { text: message }));
  host.append(node);
  const kill = () => {
    node.classList.add('is-out');
    node.addEventListener('animationend', () => node.remove(), { once: true });
    setTimeout(() => node.remove(), 600);
  };
  const timer = setTimeout(kill, ms);
  node.addEventListener('click', () => { clearTimeout(timer); kill(); });
  while (host.children.length > 4) host.firstElementChild.remove();
  return node;
}

/* ---------- animowany licznik ---------- */
const counted = new WeakMap();
function countTo(node, value, { decimals = 0, suffix = '' } = {}) {
  const target = Number(value) || 0;
  const prev = counted.get(node);
  if (prev === target) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    node.textContent = target.toFixed(decimals) + suffix;
    counted.set(node, target);
    return;
  }
  const from = prev ?? 0;
  counted.set(node, target);
  const t0 = performance.now(), dur = 620;
  const step = (now) => {
    const p = Math.min(1, (now - t0) / dur);
    const eased = 1 - (1 - p) ** 3;
    node.textContent = (from + (target - from) * eased).toFixed(decimals) + suffix;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ---------- routing / nav ---------- */
let currentTab = 'home';

function showTab(name, push = true) {
  const panel = document.getElementById(name);
  if (!panel) return;
  currentTab = name;

  $$('.nav-item').forEach((n) => {
    const on = n.dataset.tab === name;
    n.classList.toggle('is-active', on);
    if (on) n.setAttribute('aria-current', 'page'); else n.removeAttribute('aria-current');
  });
  $$('.panel').forEach((p) => p.classList.toggle('is-active', p.id === name));

  const active = $(`.nav-item[data-tab="${name}"] span`);
  $('#page-title').textContent = active ? active.textContent : '';
  $('#page-sub').textContent = t(`sub_${name}`) || '';

  document.body.classList.remove('nav-open');
  $('#scroll').scrollTop = 0;
  if (push && location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);

  if (name === 'settings') { loadSlots(); loadLoadedModels(); }
  if (name === 'home') { loadStats(); }
  refresh(true);
}

document.addEventListener('click', (e) => {
  const nav = e.target.closest('.nav-item');
  if (nav) { e.preventDefault(); showTab(nav.dataset.tab); return; }
  const goto = e.target.closest('[data-goto]');
  if (goto) { showTab(goto.dataset.goto); }
});

$('#sidebar-open').addEventListener('click', () => document.body.classList.add('nav-open'));
$('#sidebar-close').addEventListener('click', () => document.body.classList.remove('nav-open'));
$('#scrim').addEventListener('click', () => document.body.classList.remove('nav-open'));

/* ---------- motyw ---------- */
const THEME_KEY = 'llmapi.theme';
function applyTheme(mode) {
  document.documentElement.dataset.theme = mode;
  const dark = mode === 'dark';
  $('#theme-icon').className = `ti ti-${dark ? 'sun' : 'moon'}`;
  $('#theme-label').textContent = dark ? 'Light' : 'Dark';
  localStorage.setItem(THEME_KEY, mode);
  if (usageChart) applyChartTheme();
}
$('#theme-toggle').addEventListener('click', () => {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
});

/* ---------- modale ---------- */
let lastFocus = null;
function openModal(id) {
  lastFocus = document.activeElement;
  const m = document.getElementById(id);
  m.hidden = false;
  document.body.style.overflow = 'hidden';
  const focusable = m.querySelector('input, select, button:not([data-noautofocus])');
  (focusable || m).focus?.();
}
function closeModal(id) {
  document.getElementById(id).hidden = true;
  if (!$$('.modal:not([hidden])').length) document.body.style.overflow = '';
  lastFocus?.focus?.();
}
$$('.modal').forEach((m) => {
  m.addEventListener('mousedown', (e) => { if (e.target === m) closeModal(m.id); });
});
$('#modal-x').addEventListener('click', () => closeModal('edit-modal'));
$('#modal-cancel').addEventListener('click', () => closeModal('edit-modal'));
$('#modal-save').addEventListener('click', saveEditKey);

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const open = $$('.modal:not([hidden])').pop();
  if (open) { closeModal(open.id); return; }
  if (document.body.classList.contains('nav-open')) document.body.classList.remove('nav-open');
});

/* pułapka focusu w modalu */
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Tab') return;
  const m = $$('.modal:not([hidden])').pop();
  if (!m) return;
  const f = $$('button, input, select, textarea, [tabindex]:not([tabindex="-1"])', m)
    .filter((n) => !n.disabled && n.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

/* confirm */
let confirmAction = null;
function askConfirm(message, action) {
  $('#confirm-text').textContent = message;
  confirmAction = action;
  openModal('confirm-modal');
}
$('#confirm-no').addEventListener('click', () => { closeModal('confirm-modal'); confirmAction = null; });
$('#confirm-yes').addEventListener('click', async () => {
  const fn = confirmAction;
  confirmAction = null;
  closeModal('confirm-modal');
  if (fn) await fn();
});

/* ==========================================================================
   HOME
   ========================================================================== */
const $s = (id) => document.getElementById(id);

function renderSlots(slots, loaded) {
  const track = $s('slot-track');
  track.replaceChildren();
  loaded.forEach((m) => {
    const busy = m.refcount > 0;
    track.append(el('div', { class: `slot${busy ? ' is-busy' : ''}` },
      el('div', { class: 'slot-idx', text: String(m.slot) }),
      el('div', { class: 'slot-bar' },
        el('div', { class: 'slot-top' },
          el('span', { class: 'slot-dev', text: m.engine }),
          el('span', { class: 'slot-name', text: m.name, title: m.name }),
        ),
        el('div', { class: 'slot-fill' },
          el('span', { style: `width:${busy ? 100 : 22}%` })),
      ),
      el('div', { class: 'slot-badge' },
        icon(busy ? 'loader-2' : 'circle-check'),
        busy ? t('slot_busy') : t('slot_loaded')),
    ));
  });

  for (let i = loaded.length; i < slots; i++) {
    track.append(el('div', { class: 'slot' },
      el('div', { class: 'slot-idx', text: '—' }),
      el('div', { class: 'slot-bar' },
        el('div', { class: 'slot-top' },
          el('span', { class: 'slot-dev', text: t('slot_free') }),
          el('span', { class: 'slot-name', text: t('slot_waiting') }))),
      el('div', { class: 'slot-badge' }, icon('circle'), t('slot_idle')),
    ));
  }
  $s('slots-chip').textContent = `${loaded.length}/${slots} ${t('stat_slots')}`;
}

function renderRecent(rows) {
  const tb = $s('recent-tbody');
  if (!rows.length) {
    tb.replaceChildren(el('tr', {},
      el('td', { colspan: 6 },
        el('div', { class: 'empty' },
          icon('inbox'),
          el('p', { text: t('home_no_requests') })))));
    return;
  }
  tb.replaceChildren(...rows.map((r) => el('tr', {},
    el('td', { class: 'dim' }, ago(r.timestamp), el('span', { class: 'dim' }, ` · ${fmtDT(r.timestamp).slice(-8)}`)),
    el('td', {}, el('span', { class: 'ellip mono', title: r.model, text: r.model })),
    el('td', { class: 'dim' }, el('span', { class: 'ellip', text: r.key_name || '—' })),
    el('td', { class: 'num' }, el('strong', { text: num(r.total_tokens) })),
    el('td', { class: 'num dim' }, dec(r.elapsed_seconds, 2)),
    el('td', { class: 'num good' }, dec(r.tokens_per_second, 1)),
  )));
}

async function loadStats() {
  try {
    const d = await api('/api/stats');
    const last = d.last;

    // ostatni model
    const lm = $s('s-last-model');
    if (last?.model) { lm.textContent = last.model; lm.title = last.model; }
    else { lm.textContent = t('models_none'); lm.title = ''; }
    $s('s-last-model-sub').textContent = last
      ? `${ago(last.timestamp)} · ${dec(last.tokens_per_second, 1)} t/s`
      : t('home_never_used');

    countTo($s('s-tokens'), d.total_tokens);
    $s('s-tokens-sub').textContent = d.requests_1h
      ? `+${num(d.tokens_1h)} ${t('last_hour')}` : t('stat_no_recent');

    countTo($s('s-requests'), d.total_requests);
    $s('s-requests-sub').textContent = d.requests_1h
      ? `+${num(d.requests_1h)} ${t('last_hour')}` : t('stat_no_recent');

    countTo($s('s-tps-n'), d.avg_tps, { decimals: 1 });
    $s('s-tps-sub').textContent = `${t('stat_best')} ${dec(d.best_tps, 1)} t/s`;

    countTo($s('s-models'), d.models_on_disk);
    const loadedN = d.loaded_models.length;
    $s('s-models-sub').textContent = `${loadedN} ${t('stat_in_vram')}`;

    $s('s-uptime').textContent = uptime(d.uptime);
    $s('s-uptime-sub').textContent = `port ${d.port} · ${d.local_ip}`;

    $s('hero-port').textContent = d.port;

    renderSlots(d.slots_total, d.loaded_models);
    renderRecent(d.recent || []);

    const chips = $s('home-loaded');
    chips.replaceChildren(...(d.loaded_models.length
      ? d.loaded_models.map((m) => el('div', { class: 'mchip' },
          icon('cpu-2'), el('span', { text: m.name }),
          el('em', { text: `slot ${m.slot} · ${m.engine}` })))
      : [el('div', { class: 'mchip' }, icon('info-circle'), el('em', { text: t('home_none_loaded') }))]));
  } catch (e) {
    console.error('stats', e);
  }
}

/* ==========================================================================
   MODELE
   ========================================================================== */
function renderModels(models, loadedNames) {
  const host = $s('models-list');
  if (!models.length) {
    host.replaceChildren(el('div', { class: 'empty', style: 'grid-column:1/-1' },
      icon('cloud-download'),
      el('p', { text: t('js_no_models') })));
    return;
  }
  host.replaceChildren(...models.map((m) => {
    const isLoaded = loadedNames.includes(m.id);
    return el('article', { class: `model-card reveal${isLoaded ? ' is-loaded' : ''}` },
      el('div', { class: 'mc-top' },
        el('div', { class: 'mc-ic' }, icon('cpu-2')),
        el('div', { class: 'mc-name', text: m.id })),
      el('div', { class: `mc-status ${isLoaded ? 'ok' : 'idle'}` },
        icon(isLoaded ? 'circle-check' : 'database'),
        el('span', { text: isLoaded ? t('js_loaded_vram') : t('js_avail_disk') })),
      el('div', { class: 'mc-id' },
        el('span', { text: m.id, title: m.id }),
        el('button', {
          class: 'icon-btn', 'data-tip': t('js_copy_id'),
          onclick: () => copyText(m.id).then((ok) => toast(ok ? t('js_copied') : t('js_copy_fail'), ok ? 'ok' : 'err')),
        }, icon('copy'))),
    );
  }));
}

/* ==========================================================================
   KLUCZE API
   ========================================================================== */
let keysCache = [];

function engineBadge(engine) {
  return el('span', { class: `engine-badge ${engine}`, text: (engine || 'vulkan').toUpperCase() });
}

function renderKeys(keys) {
  keysCache = keys;
  const tb = $s('keys-list');
  $s('keys-empty').hidden = keys.length > 0;
  $s('keys-count-chip').textContent = String(keys.length);
  $s('nav-keys-count').textContent = String(keys.length);

  if (!keys.length) {
    tb.replaceChildren();
    renderLogKeyGrid([]);
    return;
  }

  tb.replaceChildren(...keys.map((k) => el('tr', {},
    el('td', {},
      el('div', { class: 'key-name' },
        el('strong', { text: k.name }),
        el('span', {
          class: 'key-val', 'data-tip': t('js_copy_key'),
          onclick: () => copyText(k.api_key).then((ok) => toast(ok ? t('js_copied') : t('js_copy_fail'), ok ? 'ok' : 'err')),
        }, icon('copy'), el('span', { text: maskKey(k.api_key) })))),
    el('td', {}, engineBadge(k.engine)),
    el('td', { class: 'dim', title: fmtDT(k.last_used) },
      k.last_used ? ago(k.last_used) : t('js_never')),
    el('td', { class: 'num' }, el('strong', { text: num(k.total_tokens) })),
    el('td', {},
      el('div', { class: 'row-acts' },
        el('button', { class: 'icon-btn', 'data-tip': t('js_edit'), onclick: () => openEdit(k) }, icon('pencil')),
        el('button', {
          class: 'icon-btn danger', 'data-tip': t('js_delete'),
          onclick: () => askConfirm(t('confirm_delete_key').replace('{name}', k.name), () => deleteKey(k.id)),
        }, icon('trash')))),
  )));
  renderLogKeyGrid(keys);
}

function randomKey() {
  const alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  const bytesArr = new Uint8Array(24);
  crypto.getRandomValues(bytesArr);
  return 'sk-' + Array.from(bytesArr, (b) => alphabet[b % alphabet.length]).join('');
}

$('#gen-key').addEventListener('click', () => {
  $s('new-key-value').value = randomKey();
  $s('new-key-value').focus();
});

$('#create-key-btn').addEventListener('click', async (e) => {
  const btn = e.currentTarget;
  const name = $s('new-key-name').value.trim();
  const value = $s('new-key-value').value.trim();
  const engine = $s('new-key-engine').value;
  const msg = $s('key-error');

  if (!name || !value) {
    msg.className = 'form-msg is-err';
    msg.textContent = t('js_err_fields');
    (name ? $s('new-key-value') : $s('new-key-name')).classList.add('shake');
    setTimeout(() => $$('.shake').forEach((n) => n.classList.remove('shake')), 600);
    return;
  }
  btn.classList.add('is-spinning');
  btn.disabled = true;
  try {
    await api('/api/keys', { method: 'POST', body: JSON.stringify({ name, api_key: value, engine }) });
    $s('new-key-name').value = '';
    $s('new-key-value').value = '';
    msg.className = 'form-msg';
    msg.textContent = '';
    toast(t('js_created'), 'ok');
    keysCache = [];                 // wymuś odświeżenie listy
    await refresh(true);
  } catch (err) {
    msg.className = 'form-msg is-err';
    msg.textContent = err.message;
  } finally {
    btn.classList.remove('is-spinning');
    btn.disabled = false;
  }
});

let editingId = null;
function openEdit(k) {
  editingId = k.id;
  $s('edit-key-input').value = k.name;
  $s('edit-key-value-input').value = k.api_key;
  $s('edit-key-engine-input').value = k.engine || 'vulkan';
  openModal('edit-modal');
}
$('#edit-gen-key').addEventListener('click', () => { $s('edit-key-value-input').value = randomKey(); });

async function saveEditKey() {
  if (!editingId) return;
  const name = $s('edit-key-input').value.trim();
  const value = $s('edit-key-value-input').value.trim();
  const engine = $s('edit-key-engine-input').value;
  if (!name || !value) { toast(t('js_err_fields'), 'err'); return; }
  try {
    await api(`/api/keys/${editingId}`, { method: 'PUT', body: JSON.stringify({ name, api_key: value, engine }) });
    closeModal('edit-modal');
    toast(t('js_changes_saved'), 'ok');
    keysCache = [];
    await refresh(true);
  } catch (err) { toast(err.message, 'err'); }
}

async function deleteKey(id) {
  try {
    await api(`/api/keys/${id}`, { method: 'DELETE' });
    if (currentLogKey === id) backToKeyGrid();
    keysCache = [];
    toast(t('js_key_deleted'), 'ok');
    await refresh(true);
  } catch (err) { toast(err.message, 'err'); }
}

/* ==========================================================================
   LOGI
   ========================================================================== */
let currentLogKey = null;
let logRows = [];
let usageChart = null;

function renderLogKeyGrid(keys) {
  const host = $s('log-keys-grid');
  const empty = $s('no-keys-msg');
  empty.hidden = keys.length > 0;
  if (!keys.length) { host.replaceChildren(); return; }

  const sorted = [...keys].sort((a, b) => (b.last_used || 0) - (a.last_used || 0));
  host.replaceChildren(...sorted.map((k) => el('button', { class: 'kcard reveal', onclick: () => selectLogKey(k) },
    el('div', { class: 'kcard-head' }, icon('key'), el('strong', { text: k.name })),
    el('div', { class: 'kcard-row' }, icon('coins'), el('span', { text: t('stat_tokens') }),
      el('b', { text: num(k.total_tokens) })),
    el('div', { class: 'kcard-row' }, icon('clock'), el('span', { text: t('th_last_used') }),
      el('b', { text: k.last_used ? ago(k.last_used) : t('js_never') })),
  )));
}

async function selectLogKey(k) {
  currentLogKey = k.id;
  $s('log-keys-view').hidden = true;
  $s('key-details').hidden = false;
  const title = $s('key-details-title');
  title.replaceChildren(icon('key'), el('span', { text: k.name }));
  title.dataset.i18nTitle = k.name;
  renderCode._sig = null;
  $s('logs-back').focus();
  await loadLogs();
}

function backToKeyGrid() {
  currentLogKey = null;
  $s('key-details').hidden = true;
  $s('log-keys-view').hidden = false;
}

$('#logs-back').addEventListener('click', backToKeyGrid);

function applyChartTheme() {
  if (!usageChart) return;
  const cs = getComputedStyle(document.documentElement);
  usageChart.options.scales.y.ticks.color = cs.getPropertyValue('--text-3');
  usageChart.options.scales.x.ticks.color = cs.getPropertyValue('--text-3');
  usageChart.options.scales.y.grid.color = 'rgba(127,140,170,.12)';
  usageChart.update('none');
}

function ensureChart() {
  if (usageChart) return usageChart;
  const ctx = $s('usageChart').getContext('2d');
  const cs = getComputedStyle(document.documentElement);

  usageChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: Array.from({ length: 24 }, (_, i) => `${i}:00`),
      datasets: [{
        label: t('th_tokens'),
        data: Array(24).fill(0),
        backgroundColor: 'rgba(139,124,248,.45)',
        borderColor: 'rgba(139,124,248,.9)',
        borderWidth: 1,
        borderRadius: 5,
        hoverBackgroundColor: 'rgba(139,124,248,.75)',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: cs.getPropertyValue('--surface-3'),
          borderColor: cs.getPropertyValue('--border-2'),
          borderWidth: 1,
          titleColor: cs.getPropertyValue('--text'),
          bodyColor: cs.getPropertyValue('--text-2'),
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: cs.getPropertyValue('--text-3'), font: { size: 10 } } },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(127,140,170,.12)' },
          ticks: { color: cs.getPropertyValue('--text-3'), font: { size: 10 }, precision: 0 },
        },
      },
    },
  });
  return usageChart;
}

function renderLogs() {
  const filter = $s('log-search').value.trim().toLowerCase();
  const rows = filter ? logRows.filter((r) => (r.model || '').toLowerCase().includes(filter)) : logRows;

  $s('logs-empty').hidden = rows.length > 0;
  $s('logs-table-wrap').hidden = rows.length === 0;   // pusty nagłówek bez wierszy wygląda źle
  if (!rows.length) { $s('logs-tbody').replaceChildren(); return; }

  $s('logs-tbody').replaceChildren(...[...rows].reverse().map((r) => el('tr', {},
    el('td', { class: 'dim' }, fmtDT(r.timestamp)),
    el('td', {},
      el('div', { style: 'display:flex;align-items:center;gap:6px' },
        el('span', { class: 'ellip mono', title: r.model, text: r.model }),
        el('button', {
          class: 'icon-btn', style: 'width:24px;height:24px;font-size:.95rem;border:0',
          'data-tip': t('js_copy_id'),
          onclick: () => copyText(r.model).then((ok) => toast(ok ? t('js_copied') : t('js_copy_fail'), ok ? 'ok' : 'err')),
        }, icon('copy')))),
    el('td', { class: 'num dim' }, dec(r.elapsed_seconds, 2)),
    el('td', { class: 'num dim' }, dec(r.ttft, 3)),
    el('td', { class: 'num' }, el('strong', { text: num(r.total_tokens) })),
    el('td', { class: 'num' },
      el('strong', { class: 'good', text: dec(r.tokens_per_second, 1) }),
      el('span', { class: 'dim', text: ` (${dec(r.min_tps, 1)} / ${dec(r.max_tps, 1)})` })),
  )));
}

async function loadLogs() {
  if (!currentLogKey) return;
  try {
    logRows = await api(`/api/logs/${currentLogKey}`);
    const sum = logRows.reduce((a, r) => {
      a.tokens += r.total_tokens || 0;
      a.tps.push(r.tokens_per_second || 0);
      return a;
    }, { tokens: 0, tps: [] });
    countTo($s('lg-tokens'), sum.tokens);
    countTo($s('lg-requests'), logRows.length);
    const avg = sum.tps.length ? sum.tps.reduce((x, y) => x + y, 0) / sum.tps.length : 0;
    countTo($s('lg-avg'), avg, { decimals: 1 });
    countTo($s('lg-best'), Math.max(0, ...sum.tps), { decimals: 1 });

    const today = new Date(); today.setHours(0, 0, 0, 0);
    const hourly = Array(24).fill(0);
    for (const r of logRows) {
      const d = new Date(r.timestamp * 1000);
      if (d >= today) hourly[d.getHours()] += r.total_tokens || 0;
    }
    const chart = ensureChart();
    chart.data.datasets[0].data = hourly;
    chart.update();
    renderLogs();
  } catch (e) { console.error('logs', e); }
}

$('#log-search').addEventListener('input', renderLogs);

/* ==========================================================================
   POŁĄCZENIE
   ========================================================================== */
let serverIp = '127.0.0.1';
let codeLang = 'python';

const CODE = {
  python: (ip, key) => [
    ['c-com', '# pip install openai'],
    ['c', 'from openai import OpenAI'],
    ['', ''],
    ['c-com', '# 1. Utwórz klucz w zakładce "Klucze API"'],
    ['c-key', `client = OpenAI(base_url="http://${ip}:${PORT}/v1", api_key="${key}")`],
    ['', ''],
    ['c-com', '# 2. Użyj nazwy modelu z zakładki "Modele"'],
    ['res', 'stream = client.chat.completions.create('],
    ['c-key', `    model="MODEL_NAME",`],
    ['c-key', '    messages=[{"role": "user", "content": "Cześć!"}],'],
    ['c-key', '    stream=True,'],
    ['', '    temperature=0.7,'],
    ['', ')'],
    ['', ''],
    ['c-com', '# 3. Strumień tokenów'],
    ['fn', 'for chunk in stream:'],
    ['c-key', '    print(chunk.choices[0].delta.content or "", end="", flush=True)'],
  ],
  curl: (ip, key) => [
    ['c-com', '# streaming'],
    ['c-key', `curl -N http://${ip}:${PORT}/v1/chat/completions \\`],
    ['c-key', '  -H "Content-Type: application/json" \\'],
    ['c-key', `  -H "Authorization: Bearer ${key}" \\`],
    ['c-key', '  -d \'{'],
    ['c-key', '    "model": "MODEL_NAME",'],
    ['c-key', '    "messages": [{"role": "user", "content": "Cześć!"}],'],
    ['c-key', '    "stream": true'],
    ['', "  }'"],
  ],
  js: (ip, key) => [
    ['c-com', '// npm install openai'],
    ['c', 'import OpenAI from "openai";'],
    ['', ''],
    ['c-key', `const client = new OpenAI({ baseURL: "http://${ip}:${PORT}/v1", apiKey: "${key}" });`],
    ['', ''],
    ['c-com', 'const stream = await client.chat.completions.create({'],
    ['c-key', '  model: "MODEL_NAME",'],
    ['c-key', '  messages: [{ role: "user", content: "Cześć!" }],'],
    ['', '  stream: true,'],
    ['', '});'],
    ['', ''],
    ['fn', 'for await (const chunk of stream) {'],
    ['c-key', '  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");'],
    ['', '}'],
  ],
};

const CODE_META = {
  python: ['example.py', { com: 'c-com', key: 'c-key', fn: 'fn', res: 'fn' }],
  curl:   ['request.sh',  { com: 'c-com', key: 'c-key', fn: 'fn', res: 'fn' }],
  js:     ['example.mjs', { com: 'c-com', key: 'c-key', fn: 'fn', res: 'fn' }],
};

function renderCode() {
  const key = keysCache[0]?.api_key || 'sk-TWOJ_KLUCZ';
  const [file, cls] = CODE_META[codeLang];
  const lines = CODE[codeLang](serverIp, key).map(([type, text]) => {
    const k = type === 'c' ? '' : (type === 'res' ? cls.res : cls[type]) || '';
    const span = el('span', { class: k, text });
    span.style.whiteSpace = 'pre';
    return span;
  });

  const pre = $s('connection-code');
  const sig = `${codeLang}|${serverIp}|${key}`;
  if (renderCode._sig === sig) return;      // nie przebudowuj bez zmian
  renderCode._sig = sig;

  $s('code-file').textContent = file;
  pre.replaceChildren();
  lines.forEach((span, i) => {
    pre.append(span);
    if (i < lines.length - 1) pre.append(document.createTextNode('\n'));
  });
}

$('#code-tabs').addEventListener('click', (e) => {
  const tab = e.target.closest('.tab');
  if (!tab) return;
  $$('.tab', $('#code-tabs')).forEach((x) => x.classList.toggle('is-active', x === tab));
  codeLang = tab.dataset.lang;
  renderCode();
});

$('#copy-code').addEventListener('click', async () => {
  const ok = await copyText($s('connection-code').textContent);
  toast(ok ? t('js_copied') : t('js_copy_fail'), ok ? 'ok' : 'err');
});

function renderEndpoints() {
  const host = $s('endpoints');
  const eps = [
    { icon: 'world',  label: t('ep_local'),   value: `http://127.0.0.1:${PORT}/v1` },
    { icon: 'server', label: t('ep_lan'),     value: `http://${serverIp}:${PORT}/v1` },
    { icon: 'plug',   label: t('ep_chat'),    value: '/v1/chat/completions' },
    { icon: 'api',    label: t('ep_models'),  value: '/v1/models' },
  ];
  host.replaceChildren(...eps.map((e) => el('div', { class: 'ep reveal' },
    el('div', { class: 'ep-ic' }, icon(e.icon)),
    el('div', { class: 'ep-body' },
      el('small', { text: e.label }),
      el('code', {
        title: t('js_copy_id'),
        onclick: () => copyText(e.value.startsWith('http') ? e.value : `http://${serverIp}:${PORT}${e.value}`)
          .then((ok) => toast(ok ? t('js_copied') : t('js_copy_fail'), ok ? 'ok' : 'err')),
      }, e.value)))));
}

/* ==========================================================================
   USTAWIENIA
   ========================================================================== */
const ENGINES = ['cpu', 'cuda', 'vulkan'];

async function loadSlots() {
  try {
    const slots = await api('/api/settings/slots');
    $s('slots-container').replaceChildren(...Object.entries(slots).map(([idx, s]) =>
      el('div', { class: 'slot-edit' },
        el('div', { class: 'field', style: 'flex:0 0 auto;min-width:64px' },
          el('label', { text: `${t('settings_slot_label')} ${idx}` })),
        el('div', { class: 'field' },
          el('label', { text: t('settings_device_label') }),
          el('select', { class: 'slot-sel', dataset: { slot: idx } },
            ...ENGINES.map((d) => el('option', { value: d, selected: s.device === d }, d.toUpperCase())))),
        el('div', { class: 'field', style: 'flex:1 1 190px' },
          el('label', { text: t('settings_loaded_in') }),
          el('div', { class: 'info' },
            icon(s.loaded_model ? 'circle-check' : 'circle'),
            el('span', { text: s.loaded_model || t('js_never') }))),
        el('button', { class: 'btn btn-ghost btn-sm', onclick: () => saveSlot(idx) },
          icon('device-floppy'), el('span', { text: t('settings_save_btn') })),
      )));
  } catch (e) { console.error('slots', e); }
}

async function saveSlot(idx) {
  const sel = $(`.slot-sel[data-slot="${idx}"]`);
  if (!sel) return;
  try {
    await api('/api/settings/slots', {
      method: 'PUT',
      body: JSON.stringify({ slot_index: Number(idx), device: sel.value }),
    });
    toast(t('settings_saved'), 'ok');
    loadSlots();
  } catch (e) { toast(e.message, 'err'); }
}

async function loadLoadedModels() {
  const host = $s('loaded-models-container');
  try {
    const d = await api('/api/status');
    const entries = Object.entries(d.loaded_models || {});
    if (!entries.length) {
      host.replaceChildren(el('div', { class: 'empty' }, icon('cpu-off'),
        el('p', { text: t('settings_no_models') })));
      return;
    }
    host.replaceChildren(...entries.map(([name, m]) => el('div', { class: 'slot-edit' },
      el('div', { class: 'field', style: 'flex:1 1 210px' },
        el('label', { text: name }),
        el('div', { class: 'info' }, icon('cpu-2'),
          el('span', { text: `${t('settings_loaded_in')} ${m.slot} · ${String(m.engine).toUpperCase()}` }))),
      el('div', { class: 'field', style: 'flex:0 0 auto' },
        el('label', { text: t('settings_n_ctx') }),
        el('div', { class: 'info' }, icon('stack-2'), el('span', { text: String(m.n_ctx) }))),
      el('div', { class: 'field', style: 'flex:0 0 auto' },
        el('label', { text: t('settings_refcount') }),
        el('div', { class: 'info' }, icon('activity'), el('span', { text: String(m.refcount) }))),
      el('button', {
        class: 'btn btn-ghost btn-sm', 'data-tip': t('settings_unload'),
        onclick: async () => {
          try {
            await api(`/api/unload?model_name=${encodeURIComponent(name)}`, { method: 'POST' });
            toast(t('settings_unloaded'), 'ok');
            loadLoadedModels();
          } catch (e) { toast(e.message, 'err'); }
        },
      }, icon('trash')),
    )));
  } catch (e) { console.error('loaded', e); }
}

$('#unload-all').addEventListener('click', () =>
  askConfirm(t('confirm_unload_all'), async () => {
    try {
      const r = await api('/api/unload', { method: 'POST' });
      toast(r.message, 'ok');
      loadLoadedModels();
    } catch (e) { toast(e.message, 'err'); }
  }));

/* ==========================================================================
   POLLING
   ========================================================================== */
let online = null;
let timer = null;
let failures = 0;
let refreshing = false;

function setStatus(isOnline, sub) {
  const dot = $s('status-indicator');
  dot.classList.toggle('is-online', isOnline);
  dot.classList.toggle('is-busy', false);
  $s('status-text').textContent = isOnline ? t('js_online') : t('js_offline');
  if (sub !== undefined) $s('status-sub').textContent = sub;
  if (online === isOnline) return;
  online = isOnline;
  if (!isOnline) toast(t('js_err_conn'), 'err');
}

/* Interwał rośnie przy błędach i w tle karty, żeby nie obciążać serwera. */
function schedule() {
  clearTimeout(timer);
  const base = online ? 2000 : 6000;
  const max = 30000;
  const delay = Math.min(max, base * (1 + failures * 0.7));
  timer = setTimeout(poll, document.hidden ? Math.max(delay, 10000) : delay);
}

async function refresh(force = false) {
  if (refreshing) return;
  refreshing = true;
  try {
    const [status, models, keys] = await Promise.all([
      api('/api/status'),
      api('/v1/models'),
      api('/api/keys'),
    ]);
    setStatus(true, `${status.local_ip}:${status.port}`);
    serverIp = status.local_ip;
    renderCode._sig = null;
    $s('active-model-name').textContent = loadedNames[0] || t('models_none');

    if (currentTab === 'home') await loadStats();
    if (currentTab === 'models') {
      const sig = JSON.stringify([models.data, loadedNames]);
      if (force || sig !== renderModels._sig) {
        renderModels._sig = sig;
        renderModels(models.data, loadedNames);
      }
    }
    if (JSON.stringify(keys) !== JSON.stringify(keysCache)) renderKeys(keys);

    failures = 0;
  } catch (e) {
    setStatus(false, '—');
    failures++;
  } finally {
    refreshing = false;
  }
}

async function poll() {
  if (document.hidden) { schedule(); return; }
  try {
    if (currentTab === 'home') {
      // Na HOME wystarczy status + stats — nie ciągniemy listy kluczy.
      const s = await api('/api/status');
      serverIp = s.local_ip;
      setStatus(true, `${s.local_ip}:${s.port}`);
      await loadStats();
    } else {
      const [status, keys] = await Promise.all([api('/api/status'), api('/api/keys')]);
      serverIp = status.local_ip;
      setStatus(true, `${status.local_ip}:${status.port}`);
      if (JSON.stringify(keys) !== JSON.stringify(keysCache)) renderKeys(keys);
      if (currentTab === 'settings') { loadSlots(); loadLoadedModels(); }
      if (currentTab === 'connect') { renderEndpoints(); renderCode(); }
      if (currentLogKey) await loadLogs();
    }
    failures = 0;
  } catch {
    setStatus(false, '—');
    failures++;
  }
  schedule();
}

$('#refresh-now').addEventListener('click', async (e) => {
  const btn = e.currentTarget;
  btn.classList.add('is-spinning');
  renderModels._sig = null;
  keysCache = [];
  await refresh(true);
  if (currentLogKey) await loadLogs();
  if (currentTab === 'settings') { loadSlots(); loadLoadedModels(); }
  btn.classList.remove('is-spinning');
});

document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

/* ==========================================================================
   START
   ========================================================================== */
function start() {
  applyTheme(localStorage.getItem(THEME_KEY)
    || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));

  $$('.lang-btn').forEach((b) => b.addEventListener('click', () => setLanguage(b.dataset.lang)));

  const initial = location.hash.replace('#', '');
  showTab(['home', 'models', 'keys', 'logs', 'connect', 'settings'].includes(initial) ? initial : 'home', false);

  renderEndpoints();
  renderCode();
  loadStats();
  refresh(true).then(schedule);
  setTimeout(schedule, 2000);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
else start();

/* i18n musi znać te funkcje, a i18n.js ładuje się przed script.js */
window.LLMAPI = { toast, copyText, showTab, loadStats, renderCode, renderEndpoints, renderKeys };

})();
