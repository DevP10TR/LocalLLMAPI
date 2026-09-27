/**
 * Smoke test panelu bez przegladarki (jsdom nie jest dostepny, wiec budujemy
 * minimalny stub DOM i sprawdzamy, czy modul startuje bez wyjatku).
 * Uruchomienie:  node tools\\test_frontend.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

/* ---------- 1. Syntax check ---------- */
const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  -> ' + detail : ''}`);
};

console.log('\n[1] Skladnia JavaScript');
for (const file of ['web/script.js', 'web/i18n.js']) {
  try {
    new vm.Script(read(file), { filename: file });
    check(`${file} parsuje sie`, true);
  } catch (e) {
    check(`${file} parsuje sie`, false, e.message);
  }
}

/* ---------- 2. Brak odwolan do niezdefiniowanych helperow ---------- */
console.log('\n[2] Funkcje globalne wymagane przez script.js');
const js = read('web/script.js');
const html = read('web/index.html');
for (const fn of ['t', 'setLanguage', 'translateUI']) {
  check(`i18n.js wystawia ${fn}()`, new RegExp(`window\\.${fn}\\s*=`).test(read('web/i18n.js')));
}
check('script.js eksponuje LLMAPI dla i18n', /window\.LLMAPI\s*=/.test(js));

/* ---------- 3. Mini DOM ---------- */
console.log('\n[3] Uruchomienie panelu na stub DOM');

const listeners = {};
function makeNode(id = '', tag = 'div') {
  const node = {
    id, tagName: tag.toUpperCase(), className: '', dataset: {}, style: {},
    children: [], childNodes: [], attributes: {}, value: '', textContent: '',
    hidden: false, disabled: false, firstElementChild: null, offsetParent: {},
    classList: {
      _s: new Set(),
      add(...c) { c.forEach((x) => this._s.add(x)); node.className = [...this._s].join(' '); },
      remove(...c) { c.forEach((x) => this._s.delete(x)); node.className = [...this._s].join(' '); },
      toggle(c, on) { on ? this.add(c) : this.remove(c); },
      contains(c) { return this._s.has(c); },
    },
    setAttribute(k, v) { this.attributes[k] = v; if (k.startsWith('data-')) this.dataset[k.slice(5)] = v; },
    getAttribute(k) { return this.attributes[k] ?? null; },
    removeAttribute(k) { delete this.attributes[k]; },
    addEventListener(ev, fn) { (listeners[ev] ||= []).push(fn); },
    removeEventListener() {},
    append(...n) { n.forEach((x) => this.children.push(x)); },
    prepend() {},
    replaceChildren(...n) { this.children = n; this.childNodes = n; },
    insertAdjacentHTML() {},
    appendChild(n) { this.children.push(n); return n; },
    remove() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    closest() { return null; },
    focus() {},
    click() {},
    getBoundingClientRect() { return { width: 100, height: 20, top: 0, left: 0 }; },
    toLocaleString() { return '00:00:00'; },
  };
  return node;
}

/* Rejestrujemy wszystkie id wystepujace w HTML jako gotowe stuby. */
const ids = [...new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]))];
const registry = new Map(ids.map((id) => [id, makeNode(id)]));

const document = {
  readyState: 'complete',
  hidden: false,
  body: makeNode('body', 'body'),
  documentElement: makeNode('html', 'html'),
  title: '',
  getElementById: (id) => registry.get(id) || makeNode(id),
  querySelector: (sel) => {
    const m = sel.match(/^#([\w-]+)$/);
    if (m) return registry.get(m[1]) || makeNode(m[1]);
    if (sel === '.panel.is-active') return makeNode('active-panel', 'section');
    if (sel === '.nav-item[data-tab="home"] span') { const n = makeNode('span'); n.textContent = 'Home'; return n; }
    return null;
  },
  querySelectorAll: () => [],
  createElement: (tag) => makeNode('', tag),
  createTextNode: (t) => ({ nodeType: 3, textContent: t }),
  addEventListener: (ev, fn) => { (listeners[`doc:${ev}`] ||= []).push(fn); },
  execCommand: () => true,
};

const sandbox = {
  document,
  navigator: { language: 'pl-PL', clipboard: { writeText: async () => {} } },
  localStorage: {
    _d: {},
    getItem(k) { return this._d[k] ?? null; },
    setItem(k, v) { this._d[k] = String(v); },
  },
  location: { hash: '' },
  history: { replaceState() {} },
  console,
  setTimeout, clearTimeout, setInterval, clearInterval,
  requestAnimationFrame: (fn) => setTimeout(() => fn(Date.now()), 0),
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  performance: { now: () => Date.now() },
  Intl, Date, Math, JSON, Object, Array, String, Number, Promise, Error,
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  crypto: { getRandomValues: (a) => { a.forEach((_, i) => { a[i] = i; }); return a; } },
  Chart: function () { return { data: { datasets: [{ data: [] }] }, options: { scales: {} }, update() {} }; },
};
sandbox.window = sandbox;   // w przegladarce window === globalThis
sandbox.globalThis = sandbox;

try {
  const ctx = vm.createContext(sandbox);
  vm.runInContext(read('web/i18n.js'), ctx, { filename: 'i18n.js' });
  check('i18n.js wykonuje sie bez wyjatku', true);

  vm.runInContext(read('web/script.js'), ctx, { filename: 'script.js' });
  check('script.js wykonuje sie bez wyjatku', true);
  check('t() zwraca tlumaczenie', sandbox.t('nav_home') === 'Home', `t('nav_home')=${sandbox.t('nav_home')}`);
  check('t() ma klucze dla PL i EN', typeof sandbox.t('stat_tokens') === 'string');
  check('brak klucza w obu jezykach zwraca sam klucz', sandbox.t('nie_ma_takiego') === 'nie_ma_takiego',
        `t('nie_ma_takiego')=${sandbox.t('nie_ma_takiego')}`);
  check('fill() podmienia {placeholder}', sandbox.t('confirm_delete_key').includes('{name}'));
} catch (e) {
  check('modul panelu startuje', false, `${e.message}\n${(e.stack || '').split('\n').slice(0, 4).join('\n')}`);
}

/* ---------- 4. Usuwanie Playgroundu ---------- */
console.log('\n[4] Playground calkowicie usuniety');
const all = html + js + read('web/style.css') + read('web/i18n.js');
for (const bad of ['pg-model-select', 'pg-message-input', 'chat-window', 'sendPlaygroundMessage', 'nav_playground', 'playground-container']) {
  check(`brak "${bad}"`, !all.includes(bad));
}

/* ---------- 5. Ikony Tabler ---------- */
console.log('\n[5] Ikony Tabler');
const iconsCss = read('web/vendor/tabler-icons.min.css');
const used = [...new Set([...(html + js).matchAll(/ti-([a-z0-9-]+)/g)].map((m) => m[1]))];
const missing = used.filter((n) => !iconsCss.includes(`.ti-${n}:`));
check(`wszystkie ikony (${used.length}) istnieja w vendor CSS`, missing.length === 0, missing.join(', '));
check('favicon to SVG, nie emoji', html.includes("data:image/svg+xml") && !html.includes('%E2%9A%A1'));
check('brak odwolan do CDN', !/https?:\/\/(cdn\.jsdelivr|unpkg|fonts\.googleapis)/.test(html + js));

/* ---------- 6. Bezpieczenstwo ---------- */
console.log('\n[6] Bezpieczenstwo (XSS)');
check('brak inline onclick w HTML', !/\sonclick=/.test(html));
check('nie budujemy HTML przez konkatenacje danych', !/innerHTML\s*=\s*`/.test(js));
check('helper el() nie ma trybu html:', !/k === 'html'/.test(js));
check('brak zdefiniowanego helpera esc()', !/const esc = /.test(js));
check('brak dostepnego przez auth API do panelu', /Depends\(security\)/.test(read('backend/router_server.py')));

/* ---------- 7. Brak CDN / zaleznosci lokalne ---------- */
console.log('\n[7] Zaleznosci lokalne');
for (const asset of ['vendor/tabler-icons.min.css', 'vendor/chart.umd.js', 'i18n.js', 'script.js', 'style.css']) {
  check(`${asset} istnieje na dysku`, fs.existsSync(path.join(ROOT, 'web', asset)));
}
check('font woff2 istnieje', fs.existsSync(path.join(ROOT, 'web', 'vendor', 'fonts', 'tabler-icons.woff2')));

/* ---------- 8. Port 1000 ---------- */
console.log('\n[8] Port 1000');
const py = read('backend/router_server.py');
check('router_server.py ma SERVER_PORT = 1000', /SERVER_PORT\s*=\s*1000/.test(py));
check('brak pozostałości portu 8000 w backendzie', !py.includes('8000'));
check('start.bat używa portu 1000', read('start.bat').includes('--port 1000'));
check('test.bat używa portu 1000', read('test.bat').includes('127.0.0.1:1000'));
check('JS nie ma hardkodowanego origin', !/https?:\/\/(localhost|127\.0\.0\.1):\d+/.test(js));

/* ---------- podsumowanie ---------- */
const passed = results.filter((r) => r.ok).length;
console.log(`\n${'='.repeat(58)}\n  ${passed}/${results.length} testow zaliczonych`);
if (passed !== results.length) {
  console.log('  NIEZALICZONE:');
  results.filter((r) => !r.ok).forEach((r) => console.log(`    - ${r.name}  ${r.detail}`));
}
// Panel planuje cykliczny polling, wiec petla zdarzen nigdy by nie wygasla.
process.exit(passed === results.length ? 0 : 1);
