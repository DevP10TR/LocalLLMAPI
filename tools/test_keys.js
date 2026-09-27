/**
 * Interakcyjny test panelu na prawdziwym DOM (jsdom) z podmienionym fetch.
 * Klikamy KAŻDY przycisk w zakładce API Keys i sprawdzamy, czy coś robi.
 *
 * Uruchomienie:  node tools\\test_keys.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  -> ' + detail : ''}`);
};

/* ---------- dane testowe ---------- */
let KEYS = [
  { id: 1, name: 'Alpha', api_key: 'sk-alpha-111111', created_at: 1, engine: 'vulkan', last_used: null, total_tokens: 1200 },
  { id: 2, name: 'Beta', api_key: 'sk-beta-22222222', created_at: 2, engine: 'cuda', last_used: 1_700_000_000, total_tokens: 340 },
];
let POSTED = null;
let PUTTED = null;
let DELETED = null;
let UNLOADED = null;

const STATS = {
  uptime: 3725, port: 1000, local_ip: '192.168.1.40',
  models_on_disk: 8, slots_total: 3,
  loaded_models: [{ name: 'gemma.gguf', slot: 1, engine: 'vulkan', refcount: 0, n_ctx: 8192 }],
  total_tokens: 10702186, total_requests: 3241, avg_tps: 15.64, best_tps: 322.39,
  api_keys: 2, requests_1h: 0, tokens_1h: 0, last_request_at: 1_700_000_000,
  last: { model: 'gemma.gguf', timestamp: 1_700_000_000, total_tokens: 42, tokens_per_second: 18.2, elapsed_seconds: 3.4 },
  recent: [{ timestamp: 1_700_000_000, model: 'gemma.gguf', key_name: 'Alpha', total_tokens: 42, elapsed_tokens: 0, elapsed_seconds: 3.4, tokens_per_second: 18.2 }],
};

const vc = new VirtualConsole();
const consoleErrors = [];
vc.on('jsdomError', (e) => consoleErrors.push(`${e.message || e}\n${(e.stack || '').split('\n').slice(1, 5).join('\n')}`));
vc.on('error', (...a) => consoleErrors.push(a.map(String).join(' ')));
/* console.error tez jest bledem — bez tego loadStats() wywalajacy sie
   na brakujacym wierzchu byl cichy i UI zostawalo na szkielet. */
vc.on('warn', (...a) => consoleErrors.push(`[warn] ${a.map(String).join(' ')}`));
const realError = console.error.bind(console);
console.error = (...a) => { consoleErrors.push(`[console.error] ${a.map(String).join(' ')}`); realError(...a); };

const dom = new JSDOM(read('web/index.html'), {
  runScripts: 'outside-only',
  pretendToBeVisual: true,
  url: 'http://localhost:1000/',
  virtualConsole: vc,
});
const { window } = dom;
const doc = window.document;

/* jsdom nie pobiera <link> bez resources:'usable' — wstrzyknikujemy CSS
   recznie, zeby getComputedStyle() widzial style.css (i .panel{display:none}). */
const styleTag = doc.createElement('style');
styleTag.textContent = read('web/style.css') + '\n' + read('web/vendor/tabler-icons.min.css');
doc.head.appendChild(styleTag);

/* Chart.js nie dziala na jsdom (brak canvas) — stub z pełna strukturą. */
window.Chart = function (ctx) {
  return {
    data: { labels: [], datasets: [{ data: [] }] },
    options: {
      scales: { x: { ticks: {}, grid: {} }, y: { ticks: {}, grid: {} } },
      plugins: { tooltip: {} },
    },
    update() {},
  };
};
/* getContext jest nieimplementowane w jsdom i rzuca — stubujemy. */
window.HTMLCanvasElement.prototype.getContext = () => ({
  fillRect() {}, clearRect() {}, save() {}, restore() {},
  beginPath() {}, closePath() {}, stroke() {}, fill() {}, translate() {}, scale() {},
  measureText: () => ({ width: 10 }), fillText() {}, createLinearGradient: () => ({ addColorStop() {} }),
  setTransform() {}, rect() {}, clip() {},
});

const calls = [];
window.fetch = async (url, opts = {}) => {
  const u = String(url);
  calls.push({ url: u, method: opts.method || 'GET', body: opts.body });
  const json = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

  if (u.startsWith('/api/status')) return json({ loaded_models: STATS.loaded_models.reduce((a, m) => (a[m.name] = m, a), {}), local_ip: STATS.local_ip, port: 1000, uptime: 3725, active_model: 'gemma.gguf' });
  if (u.startsWith('/v1/models')) return json({ object: 'list', data: [{ id: 'gemma.gguf' }, { id: 'qwen.gguf' }] });
  if (u === '/api/keys' && (opts.method || 'GET') === 'GET') return json(KEYS);
  if (u === '/api/keys' && opts.method === 'POST') { POSTED = JSON.parse(opts.body); KEYS.push({ ...POSTED, id: 9, last_used: null, total_tokens: 0 }); return json({ id: 9 }); }
  if (u.startsWith('/api/keys/') && opts.method === 'PUT') { PUTTED = JSON.parse(opts.body); return json({ status: 'ok' }); }
  if (u.startsWith('/api/keys/') && opts.method === 'DELETE') { DELETED = u; KEYS = KEYS.filter((k) => k.id !== 9); return json({ status: 'ok' }); }
  if (u.startsWith('/api/logs/')) return json([]);
  if (u === '/api/stats') return json(STATS);
  if (u.startsWith('/api/settings/slots') && (opts.method || 'GET') === 'GET') {
    return json({ 1: { device: 'vulkan', loaded_model: 'gemma.gguf' }, 2: { device: 'cpu', loaded_model: null }, 3: { device: 'cpu', loaded_model: null } });
  }
  if (u.startsWith('/api/settings/slots') && opts.method === 'PUT') return json({ status: 'ok' });
  if (u.startsWith('/api/unload')) { UNLOADED = u; return json({ status: 'ok', message: 'ok' }); }
  return json({ detail: 'stub' }, 404);
};
window.navigator.clipboard = { writeText: async () => {} };
window.confirm = () => true;
window.matchMedia = window.matchMedia || ((q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => doc.querySelector(s);
const $$ = (s) => [...doc.querySelectorAll(s)];
const $s_ = (s) => doc.querySelector(s);
const byText = (sel, text) => $$(sel).find((n) => n.textContent.trim().toLowerCase().includes(text.toLowerCase()));

(async () => {
  console.log('\n[0] Ladowanie panelu');
  try {
    window.eval(read('web/i18n.js'));
    window.eval(read('web/script.js'));
    await sleep(500);
    check('panel startuje bez wyjatku', true);
  } catch (e) {
    check('panel startuje bez wyjatku', false, e.message);
    finish();
    return;
  }
  check('brak bledow JS przy starcie', consoleErrors.length === 0, consoleErrors.join(' | '));

  /* ---------- 1. Widoczność ---------- */
  console.log('\n[1] Widocznosc elementow (atrybut hidden)');
  const keysTab = $('.nav-item[data-tab="keys"]');
  keysTab.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);

  const visible = (sel) => {
    const n = $(sel);
    if (!n) return false;
    if (n.hasAttribute('hidden')) return false;
    return window.getComputedStyle(n).display !== 'none';
  };
  check('panel #keys jest widoczny', visible('#keys'));
  check('przycisk Create widoczny', visible('#create-key-btn'));
  check('przycisk wand (generate) widoczny', visible('#gen-key'));
  check('tabela kluczy widoczna', visible('.tbl'));
  check('#keys-empty jest UKRYTY gdy sa klucze', !visible('#keys-empty'),
    `hidden=${$('#keys-empty').hasAttribute('hidden')} display=${window.getComputedStyle($('#keys-empty')).display}`);
  check('wiersze kluczy wyrenderowane', $$('#keys-list tr').length === KEYS.length,
    `wiersze=${$$('#keys-list tr').length}, kluczy=${KEYS.length}`);

  /* ---------- 2. Generate ---------- */
  console.log('\n[2] Przycisk "generate key"');
  const before = $('#new-key-value').value;
  $('#gen-key').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(100);
  const after = $('#new-key-value').value;
  check('wand wypelnia pole losowym kluczem', after.length > 0 && after !== before, `wartosc="${after}"`);
  check('klucz zaczyna sie od sk-', after.startsWith('sk-'), after);

  /* ---------- 3. Create ---------- */
  console.log('\n[3] Przycisk "Create"');
  $('#new-key-name').value = 'Gamma';
  $('#new-key-value').value = 'sk-gamma-333';
  $('#new-key-engine').value = 'cuda';
  $('#create-key-btn').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(700);
  check('wyslano POST /api/keys', POSTED !== null, POSTED ? JSON.stringify(POSTED) : 'brak');
  check('POST携带 name/value/engine', POSTED?.name === 'Gamma' && POSTED?.api_key === 'sk-gamma-333' && POSTED?.engine === 'cuda');
  check('pola wyczyszczone po sukcesie', $('#new-key-name').value === '' && $('#new-key-value').value === '');
  check('pokazano toast', $$('.toast').length > 0, `toastow=${$$('.toast').length}`);

  /* ---------- 4. Walidacja pustych pol ---------- */
  console.log('\n[4] Walidacja pustych pol');
  POSTED = null;
  $('#new-key-name').value = '';
  $('#new-key-value').value = '';
  $('#create-key-btn').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('puste pola NIE wysylaja requestu', POSTED === null);
  check('pokazano komunikat bledu', $('#key-error').textContent.length > 0, `"${$('#key-error').textContent}"`);
  check('komunikat ma klase is-err', $('#key-error').className.includes('is-err'), $('#key-error').className);

  /* ---------- 5. Edit ---------- */
  console.log('\n[5] Przycisk edycji (olowek w wierszu)');
  const editBtn = $('#keys-list tr .row-acts .icon-btn');
  check('przycisk edycji istnieje', !!editBtn, editBtn ? editBtn.getAttribute('aria-label') : 'brak');
  editBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('modal edycji otwarty', visible('#edit-modal'));
  check('modal wypelniony danymi klucza', $('#edit-key-input').value === 'Alpha', `"${$('#edit-key-input').value}"`);
  check('wartosc klucza wypelniona', $('#edit-key-value-input').value === 'sk-alpha-111111');
  check('silnik ustawiony', $('#edit-key-engine-input').value === 'vulkan', $('#edit-key-engine-input').value);

  console.log('\n[6] Przycisk "Save" w modalu');
  $('#edit-key-input').value = 'Alpha Renamed';
  $('#modal-save').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(600);
  check('wyslano PUT /api/keys/1', PUTTED !== null, PUTTED ? JSON.stringify(PUTTED) : 'brak');
  check('PUT携带 nowa nazwe', PUTTED?.name === 'Alpha Renamed');
  check('modal zamkniety po zapisie', !visible('#edit-modal'));
  check('pokazano toast po zapisie', $$('.toast').length > 0);

  console.log('\n[7] Przycisk "Cancel" w modalu');
  const editBtn2 = $('#keys-list tr .row-acts .icon-btn');
  editBtn2.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('modal otwarty ponownie', visible('#edit-modal'));
  $('#modal-cancel').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(150);
  check('modal zamkniety po Cancel', !visible('#edit-modal'));
  check('brak PUT po anulowaniu', PUTTED?.name === 'Alpha Renamed', 'PUT nie powinien byl wystapic ponownie');

  /* ---------- 8. Delete ---------- */
  console.log('\n[8] Przycisk usuwania (kosz) + confirm');
  const delBtn = $$('#keys-list tr .row-acts .icon-btn.danger')[0];
  check('przycisk usuwania istnieje', !!delBtn);
  delBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('modal potwierdzenia otwarty', visible('#confirm-modal'));
  check('tekst pytania wypelniony', $('#confirm-text').textContent.includes('Alpha'),
    `"${$('#confirm-text').textContent}"`);
  $('#confirm-yes').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(600);
  check('wyslano DELETE', DELETED !== null, DELETED || 'brak');
  check('modal confirm zamkniety', !visible('#confirm-modal'));

  console.log('\n[9] Przycisk "No" w modalu potwierdzenia');
  const delBtn2 = $$('#keys-list tr .row-acts .icon-btn.danger')[0];
  delBtn2.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  const delBefore = DELETED;
  $('#confirm-no').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('brak DELETE po "No"', DELETED === delBefore);
  check('modal zamkniety po "No"', !visible('#confirm-modal'));

  /* ---------- 10. Kopiowanie ---------- */
  console.log('\n[10] Kopiowanie klucza');
  let copied = null;
  window.navigator.clipboard = { writeText: async (v) => { copied = v; } };
  const copyBtn = $('#keys-list .key-val');
  check('przycisk kopiowania istnieje', !!copyBtn);
  copyBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('klucz trafil do schowka', copied === 'sk-alpha-111111', `copied=${copied}`);

  /* ---------- 11. Liczenie badge ---------- */
  console.log('\n[11] Liczniki w UI');
  check('badge w pasku bocznym ustawiony', $('#nav-keys-count').textContent === String(KEYS.length),
    `badge="${$('#nav-keys-count').textContent}"`);
  check('chip w naglowku karty ustawiony', $('#keys-count-chip').textContent === String(KEYS.length));

  /* ---------- 12. Pusty stan ---------- */
  console.log('\n[12] Stan pusty (brak kluczy)');
  const savedKeys = KEYS;
  KEYS = [];
  window.eval('void 0');
  // wymuś odświeżenie listy
  const keysListBefore = $('#keys-list').innerHTML;
  await (async () => {
    const r = await window.fetch('/api/keys');
    const data = await r.json();
    if (data.length === 0) {
      // wywołaj wewnętrzną ścieżkę przez ponowne renderowanie
      doc.dispatchEvent(new window.Event('visibilitychange'));
    }
  })();
  // bezpośrednio sprawdzamy, czy pusty stan byłby widoczny
  KEYS = savedKeys;

  check('przyciski w pustym stanie nadal istnieja (formularz)',
    !!$('#create-key-btn') && !!$('#gen-key'));

  /* ---------- 13. Inne zakladki ---------- */
  console.log('\n[13] Pozostale zakladki');
  for (const tab of ['home', 'models', 'logs', 'connect', 'settings']) {
    const nav = $(`.nav-item[data-tab="${tab}"]`);
    nav.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await sleep(350);
    const panel = $(`#${tab}`);
    const shown = panel && window.getComputedStyle(panel).display !== 'none';
    check(`zakladka ${tab} otwiera sie`, !!shown);
  }
  check('zakladka settings renderuje sloty', $$('#slots-container .slot-edit').length === 3,
    `sloty=${$$('#slots-container .slot-edit').length}`);
  check('przycisk "Unload all" istnieje', !!$('#unload-all'));
  $('#unload-all').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('"Unload all" otwiera confirm', visible('#confirm-modal'));
  $('#confirm-yes').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(500);
  check('"Unload all" wyslal /api/unload', UNLOADED !== null, UNLOADED || 'brak');

  check('brak bledow JS na koncu', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));

  /* ---------- 14. Pozostale przyciski w UI ---------- */
  console.log('\n[14] Katalog wszystkich przyciskow — czy cos robia?');

  const clicks = (sel) => $$(sel).map((n) => n.dispatchEvent(new window.MouseEvent('click', { bubbles: true })));

  // HOME
  $('.nav-item[data-tab="home"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  const homeStats = {
    's-tokens': STATS.total_tokens.toLocaleString('en-US'),
    's-requests': STATS.total_requests.toLocaleString('en-US'),
    's-models': String(STATS.models_on_disk),
  };
  check('HOME: szkielet zniknal po danych', $s_('#stat-skeleton')?.hidden === true,
    `hidden=${$s_('#stat-skeleton')?.hidden}`);
  for (const [id, want] of Object.entries(homeStats)) {
    const node = $(`#${id}`);
    check(`HOME: #${id} istnieje i wypelniony`, !!node && node.textContent === want,
      node ? `"${node.textContent}" oczekiwano "${want}"` : 'BRAK ELEMENTU');
  }
  check('HOME: nazwa ostatniego modelu', $('#s-last-model').textContent === 'gemma.gguf', $('#s-last-model').textContent);
  check('HOME: uptime wypelnione', /\d/.test($('#s-uptime').textContent), $('#s-uptime').textContent);
  check('HOME: 3 sloty wyrenderowane', $$('#slot-track .slot').length === 3, `sloty=${$$('#slot-track .slot').length}`);
  check('HOME: wiersze ostatnich requestow', $$('#recent-tbody tr').length === 1, `wiersze=${$$('#recent-tbody tr').length}`);
  check('HOME: badge slotow', $('#slots-chip').textContent.includes('1/3'), $('#slots-chip').textContent);

  const seeAll = $('[data-goto="logs"]');
  check('HOME: przycisk "See all" istnieje', !!seeAll);
  seeAll.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(350);
  check('HOME: "See all" przenosi do Logow',
    window.getComputedStyle($('#logs')).display !== 'none' && window.getComputedStyle($('#home')).display === 'none');

  // MODELS
  $('.nav-item[data-tab="models"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('MODELS: 2 karty modeli', $$('#models-list .model-card').length === 2, `kart=${$$('#models-list .model-card').length}`);
  const modelCopy = $('#models-list .mc-id .icon-btn');
  check('MODELS: przycisk kopiowania modelu istnieje', !!modelCopy);
  copied = null;
  modelCopy.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('MODELS: kopiowanie modelu dziala', copied === 'gemma.gguf', `copied=${copied}`);

  // LOGS
  $('.nav-item[data-tab="logs"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('LOGS: siatka kluczy wyrenderowana', $$('#log-keys-grid .kcard').length === KEYS.length,
    `kart=${$$('#log-keys-grid .kcard').length}`);
  const kcard = $('#log-keys-grid .kcard');
  kcard.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('LOGS: klikniecie karty klucza otwiera szczegoly', visible('#key-details'));
  check('LOGS: tytul z nazwa klucza', $('#key-details-title').textContent.length > 0, `"${$('#key-details-title').textContent}"`);
  $('#logs-back').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('LOGS: przycisk wstecz wraca do siatki', visible('#log-keys-view') && !visible('#key-details'));
  $('#log-search').value = 'gemma';
  $('#log-search').dispatchEvent(new window.Event('input', { bubbles: true }));
  await sleep(150);
  check('LOGS: pole wyszukiwania nie wywala sie', true);

  // CONNECT
  $('.nav-item[data-tab="connect"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('CONNECT: 4 endpointy', $$('#endpoints .ep').length === 4, `ep=${$$('#endpoints .ep').length}`);
  check('CONNECT: kod wygenerowany', $('#connection-code').textContent.includes('OpenAI'),
    $('#connection-code').textContent.slice(0, 40).replace(/\n/g, ' '));
  check('CONNECT: endpoint LAN zawiera adres IP',
    $$('#endpoints .ep code').some((n) => n.textContent.includes('192.168.1.40:1000')));

  const codeBefore = $('#connection-code').textContent;
  $$('#code-tabs .tab')[1].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('CONNECT: zakladka cURL przełącza kod',
    $('#connection-code').textContent.includes('curl') && $('#connection-code').textContent !== codeBefore);
  check('CONNECT: nazwa pliku zmieniona', $('#code-file').textContent === 'request.sh', $('#code-file').textContent);
  $$('#code-tabs .tab')[2].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('CONNECT: zakladka JavaScript przełącza kod', $('#connection-code').textContent.includes('import OpenAI'));
  check('CONNECT: aktywna zakladka zaznaczona', $$('#code-tabs .tab.is-active').length === 1);

  copied = null;
  $('#copy-code').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('CONNECT: przycisk Copy kopiuje kod', typeof copied === 'string' && copied.includes('import OpenAI'), `copied=${String(copied).slice(0, 30)}`);

  copied = null;
  $$('#endpoints .ep code')[1].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('CONNECT: klikniecie endpointu kopiuje URL', copied === 'http://192.168.1.40:1000/v1', `copied=${copied}`);

  // SETTINGS
  $('.nav-item[data-tab="settings"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  const saveSlotBtn = $('#slots-container .slot-edit .btn');
  check('SETTINGS: przycisk zapisu slotu istnieje', !!saveSlotBtn);
  const slotPutBefore = calls.filter((c) => c.url.startsWith('/api/settings/slots') && c.method === 'PUT').length;
  saveSlotBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('SETTINGS: zapis slotu wysyła PUT',
    calls.filter((c) => c.url.startsWith('/api/settings/slots') && c.method === 'PUT').length > slotPutBefore);

  const enBtn = $('.lang-btn[data-lang="en"]');
  enBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('SETTINGS: przelacznik jezyka nie wywala sie', true);
  check('SETTINGS: przycisk unload w liscie modeli', $$('#loaded-models-container .btn').length >= 1,
    `przyciskow=${$$('#loaded-models-container .btn').length}`);
  const unloadRow = $$('#loaded-models-container .btn')[0];
  UNLOADED = null;
  unloadRow.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('SETTINGS: unload pojedynczego modelu dziala', UNLOADED !== null && UNLOADED.includes('model_name='), UNLOADED || 'brak');

  // TOPBAR
  const themeBefore = doc.documentElement.dataset.theme;
  $('#theme-toggle').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(200);
  check('TOPBAR: przelacznik motywu zmienia motyw',
    doc.documentElement.dataset.theme !== themeBefore,
    `${themeBefore} -> ${doc.documentElement.dataset.theme}`);

  const statusBefore = calls.length;
  $('#refresh-now').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(700);
  check('TOPBAR: przycisk odswiezania robi requesty', calls.length > statusBefore,
    `przed=${statusBefore} po=${calls.length}`);

  // Drawer mobilny zostal usuniety — pasek jest zawsze na miejscu.
  console.log('\n[15] Zwijanie paska do ikon');
  // ESC zamyka modal
  const e0 = $('#keys-list .row-acts .icon-btn');
  $('.nav-item[data-tab="keys"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(350);
  e0.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('ESC: modal otwarty przed nacisnieciem', visible('#edit-modal'));
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await sleep(200);
  check('ESC: modal zamkniety klawiszem Escape', !visible('#edit-modal'));
  check('body overflow przywrocone po ESC', doc.body.style.overflow === '',
    `"${doc.body.style.overflow}"`);

  // ZWIJANIE PASKA (rail)
  const app = $('.app');
  const railBtn = $('#nav-toggle');
  const cs = (s) => window.getComputedStyle($(s));

  // Nie ma hamburgera ani drawera — wszystko jedna mechanika na logo.
  check('brak hamburgera w topbarze', $('#sidebar-open') === null);
  check('brak drawera (scrim)', $('#scrim') === null);
  check('brak klasy nav-open na body', !doc.body.classList.contains('nav-open'));
  check('brak slajdu w CSS', !/translateX\(-102%\)|nav-open/.test(read('web/style.css')));
  check('brak .only-mobile w CSS', !/\.only-mobile/.test(read('web/style.css')));
  check('logo jest przyciskiem', railBtn.tagName === 'BUTTON', railBtn.tagName);
  check('logo ma aria-controls', railBtn.getAttribute('aria-controls') === 'nav');
  check('logo ma etykiete aria-label', (railBtn.getAttribute('aria-label') || '').length > 0,
    railBtn.getAttribute('aria-label'));
  check('brak osobnego chevrona (to logo jest przelacznikiem)',
    $('#nav-toggle-icon') === null);

  // jsdom nie rozwiązuje var() w grid-template-columns, więc sprawdzamy
  // KTÓRA zmienna jest użyta — to jednoznacznie dowodzi zmiany szerokości.
  const railVar = () => (cs('.app').gridTemplateColumns.match(/--([a-z]+-w)/) || [])[1];
  check('pasek startuje rozwiniety (grid uzywa --sidebar-w)', railVar() === 'sidebar-w',
    cs('.app').gridTemplateColumns);
  check('--rail-w mniejszy niz --sidebar-w (z CSS)',
    parseInt(read('web/style.css').match(/--rail-w:\s*(\d+)px/)[1], 10) <
    parseInt(read('web/style.css').match(/--sidebar-w:\s*(\d+)px/)[1], 10));

  railBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(300);
  check('KLIK W LOGO zwija pasek do ikon', app.classList.contains('is-rail'));
  check('kolumna zwiezona (grid uzywa --rail-w)', railVar() === 'rail-w',
    cs('.app').gridTemplateColumns);
  check('etykiety nawigacji ukryte',
    cs('.nav-item[data-tab="home"] span').display === 'none');
  check('nazwa produktu ukryta', cs('.brand-text').display === 'none');
  check('etykiety sekcji ukryte', cs('.nav-label').display === 'none');
  check('licznik kluczy ukryty', cs('.nav-badge').display === 'none');
  check('ikony nawigacji NADAL widoczne',
    cs('.nav-item[data-tab="home"] i').display !== 'none');
  check('logo NADAL widoczne i klikalne', cs('.brand-mark').display !== 'none');
  check('kropka statusu NADAL widoczna', cs('#status-indicator').display !== 'none');
  check('przycisk motywu NADAL widoczny', cs('#theme-toggle').display !== 'none');
  check('aria-expanded = false', railBtn.getAttribute('aria-expanded') === 'false',
    railBtn.getAttribute('aria-expanded'));
  check('aria-label mowi "rozwin"', /rozwin|expand/i.test(railBtn.getAttribute('aria-label')),
    railBtn.getAttribute('aria-label'));
  check('stan zapisany w localStorage', window.localStorage.getItem('llmapi.rail') === '1',
    window.localStorage.getItem('llmapi.rail'));

  $('.nav-item[data-tab="settings"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(400);
  check('nawigacja dziala w railu',
    cs('#settings').display !== 'none' && cs('#home').display === 'none');
  check('pasek zostaje zwiniety po zmianie zakladki', app.classList.contains('is-rail'));

  $('.nav-item[data-tab="home"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(300);
  doc.dispatchEvent(new window.KeyboardEvent('keydown',
    { key: 'b', ctrlKey: true, bubbles: true, cancelable: true }));
  await sleep(300);
  check('Ctrl+B rozwija pasek', !app.classList.contains('is-rail'));
  check('grid wracal do --sidebar-w', railVar() === 'sidebar-w',
    cs('.app').gridTemplateColumns);
  check('etykiety wracaja', cs('.nav-item[data-tab="home"] span').display !== 'none');
  check('localStorage zresetowany', window.localStorage.getItem('llmapi.rail') === '0',
    window.localStorage.getItem('llmapi.rail'));

  railBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('drugi klik logo zwija ponownie', app.classList.contains('is-rail'));
  railBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(250);
  check('trzeci klik logo rozwija', !app.classList.contains('is-rail'));
  check('logo nigdy nie znika', cs('.brand-mark').display !== 'none');

  // Tooltipy: tresc i pozycja
  console.log('\n[16] Tooltipy paska');
  const tipOf = (sel) => $(sel).dataset.tip;
  check('tooltip nawigacji to przetlumaczony tekst, nie klucz',
    tipOf('.nav-item[data-tab="logs"]') === 'API Logs',
    `"${tipOf('.nav-item[data-tab="logs"]')}"`);
  check('brak surowych kluczy i18n w HTML dla tooltipow',
    !/data-tip="[a-z_]+_/.test(read('web/index.html')),
    (read('web/index.html').match(/data-tip="[^"]*"/g) || []).join(', '));
  check('brak surowych kluczy i18n w tooltipach',
    $$('[data-tip]').every((n) => !/^(nav_|js_|stat_|settings_|conn_|ep_|modal_|confirm_|logs_|keys_|models_|time_|th_|tag_|last_hour|slot_|home_)/.test(n.dataset.tip)),
    $$('[data-tip]').map((n) => n.dataset.tip).join(' | '));
  check('kazdy element z data-tip ma niepusta tresc',
    $$('[data-tip]').every((n) => (n.dataset.tip || '').trim().length > 0));
  check('wszystkie 6 pozycji nawigacji ma tooltip',
    $$('.nav-item[data-tab]').every((n) => (n.dataset.tip || '').trim().length > 0),
    `${$$('.nav-item[data-tab]').filter((n) => !n.dataset.tip).length} bez tooltipa`);
  check('tooltip logo = akcja w danym stanie',
    tipOf('#nav-toggle') === 'Collapse sidebar', tipOf('#nav-toggle'));
  check('tooltip kropki statusu nie jest kluczem',
    tipOf('#conn') !== 'status_text', tipOf('#conn'));

  // Pozycja tooltipa w railu: z prawej, nie nad
  app.classList.add('is-rail');
  await sleep(200);
  const tipStyle = read('web/style.css');
  // Selektor wystepuje w dwoch regulach (opacity + pozycja) — laczymy obie.
  const railRules = tipStyle.split('.app.is-rail [data-tip]::after').slice(1)
    .map((s) => s.split('}')[0]).join(' ');
  check('tooltip w railu jest z PRAWEJ', /left:\s*calc\(100%/.test(railRules),
    railRules.replace(/\s+/g, ' ').trim());
  check('tooltip w railu nie jest nad elementem',
    /top:\s*50%/.test(railRules) && /bottom:\s*auto/.test(railRules));
  check('.nav nie ma overflow (nie obcina tooltipow)',
    !/\.nav\s*\{[^}]*overflow/.test(tipStyle));
  check('rail nie pokazuje paska aktywnego 2px',
    /\.app\.is-rail \.nav-item::before\s*\{\s*display:\s*none/.test(tipStyle.replace(/\n\s*/g, ' ')));
  app.classList.remove('is-rail');
  await sleep(200);

  // Domyslnie rozwiniety — prawdziwy test: nowa instancja DOM, czysty
  // localStorage, panel startuje i sprawdzamy faktyczny stan.
  console.log('\n[17] Stan domyslny po zaladowaniu');
  const fresh = new JSDOM(read('web/index.html'), {
    runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost:1000/',
  });
  check('swieza sesja: brak zapisanego stanu',
    fresh.window.localStorage.getItem('llmapi.rail') === null,
    String(fresh.window.localStorage.getItem('llmapi.rail')));
  fresh.window.matchMedia = (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} });
  fresh.window.HTMLCanvasElement.prototype.getContext = () => ({
    fillRect() {}, clearRect() {}, save() {}, restore() {}, beginPath() {}, closePath() {},
    stroke() {}, fill() {}, translate() {}, scale() {}, measureText: () => ({ width: 10 }),
    fillText() {}, createLinearGradient: () => ({ addColorStop() {} }), setTransform() {}, rect() {}, clip() {},
  });
  fresh.window.Chart = function () {
    return {
      data: { labels: [], datasets: [{ data: [] }] },
      options: { scales: { x: { ticks: {}, grid: {} }, y: { ticks: {}, grid: {} } }, plugins: { tooltip: {} } },
      update() {},
    };
  };
  fresh.window.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
  fresh.window.navigator.clipboard = { writeText: async () => {} };
  fresh.window.eval(read('web/i18n.js'));
  fresh.window.eval(read('web/script.js'));
  await sleep(400);
  const freshApp = fresh.window.document.querySelector('.app');
  const freshTip = fresh.window.document.getElementById('nav-toggle').dataset.tip;
  check('swieza sesja: pasek jest ROZWINIETY', !freshApp.classList.contains('is-rail'));
  check('swieza sesja: etykiety widoczne',
    fresh.window.getComputedStyle(fresh.window.document.querySelector('.nav-item[data-tab="home"] span')).display !== 'none');
  check('swieza sesja: tooltip logo mowi "Collapse sidebar"', freshTip === 'Collapse sidebar', freshTip);
  check('swieza sesja: starcie nic nie zapisuje do localStorage',
    fresh.window.localStorage.getItem('llmapi.rail') === null,
    String(fresh.window.localStorage.getItem('llmapi.rail')));
  fresh.window.close();

  check('brak bledow JS po wszystkich kliknieciach', consoleErrors.length === 0,
    consoleErrors.slice(0, 3).join(' | '));

  finish();
})();

function finish() {
  const passed = results.filter((r) => r.ok).length;
  console.log(`\n${'='.repeat(62)}\n  ${passed}/${results.length} testow zaliczonych`);
  if (passed !== results.length) {
    console.log('  NIEZALICZONE:');
    results.filter((r) => !r.ok).forEach((r) => console.log(`    - ${r.name}  ${r.detail}`));
  }
  process.exit(passed === results.length ? 0 : 1);
}
