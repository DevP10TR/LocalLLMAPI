/* ==========================================================================
   LocalLLMAPI — tłumaczenia PL / EN
   i18n.js ładuje się PRZED script.js i wystawia t() globalnie.
   ========================================================================== */
(() => {
'use strict';

const DICT = {
  pl: {
    /* --- sidebar / topbar --- */
    brand_tagline: 'Lokalny router LLM',
    nav_label_overview: 'Przegląd',
    nav_label_manage: 'Zarządzanie',
    nav_label_system: 'System',
    nav_home: 'Home',
    nav_models: 'Modele',
    nav_keys: 'Klucze API',
    nav_logs: 'Logi API',
    nav_connect: 'Połączenie',
    nav_settings: 'Ustawienia',
    status_connecting: 'Łączenie…',
    topbar_api: 'API',
    sub_home: 'Podsumowanie pracy lokalnego serwera',
    sub_models: 'Pliki GGUF wykryte w katalogu models/',
    sub_keys: 'Klucze do śledzenia zużycia per aplikacja',
    sub_logs: 'Historia requestów i wykres zużycia',
    sub_connect: 'Jak połączyć aplikację do tego routera',
    sub_settings: 'Sloty, motyw i język panelu',

    /* --- home --- */
    home_hero_text: 'Lokalny router zgodny z OpenAI. Modele ładowane na GPU z automatycznym zwalnianiem pamięci i pełnym logowaniem zużycia.',
    conn_desc_short: 'Zgodne z OpenAI',
    tag_vulkan: 'Vulkan / CUDA / CPU',
    tag_unload: 'Auto-zwalnianie po 2 min',
    stat_last_model: 'Ostatnio używany model',
    stat_tokens: 'Zużyte tokeny',
    stat_requests: 'Requesty',
    stat_tps: 'Średnia prędkość',
    stat_models: 'Modele na dysku',
    stat_uptime: 'Czas działania',
    stat_slots: 'slotów',
    stat_best: 'Rekord',
    stat_in_vram: 'w pamięci',
    stat_no_recent: 'brak w ostatniej godzinie',
    stat_avg_tps: 'Średnia',
    stat_best_tps: 'Rekord',
    home_loaded_title: 'Sloty i załadowane modele',
    home_recent_title: 'Ostatnie requesty',
    home_see_all: 'Zobacz wszystkie',
    home_no_requests: 'Jeszcze nie było żadnego requestu. Wyślij zapytanie przez API, aby zobaczyć tu statystyki.',
    home_never_used: 'API nie zostało jeszcze użyte',
    home_none_loaded: 'Brak modeli w pamięci — załadują się przy pierwszym zapytaniu',
    last_hour: 'w ostatniej godz.',
    slot_busy: 'Aktywny',
    slot_loaded: 'Wczytany',
    slot_free: 'Wolny',
    slot_waiting: 'Oczekuje na model',
    slot_idle: 'Bezczynny',

    /* --- table headers --- */
    th_time: 'Czas',
    th_model_id: 'Model',
    th_key_name: 'Klucz',
    th_tokens: 'Tokeny',
    th_time_s: 'Czas (s)',
    th_tps_short: 't/s',
    th_tps: 't/s (śr / min / max)',
    th_ttft: 'TTFT (s)',
    th_name: 'Nazwa',
    th_engine: 'Silnik',
    th_last_used: 'Ostatnio użyty',
    th_usage: 'Tokeny',
    th_actions: 'Akcje',

    /* --- models --- */
    models_active_label: 'Wczytany w pamięci:',
    models_none: 'Brak',

    /* --- keys --- */
    keys_create_title: 'Nowy klucz',
    keys_name_label: 'Nazwa',
    keys_name_placeholder: 'np. Mój Projekt',
    keys_val_label: 'Wartość klucza',
    keys_val_placeholder: 'np. sk-moje-api-123',
    keys_engine_label: 'Silnik',
    keys_create_btn: 'Utwórz',
    keys_list_title: 'Twoje klucze',
    keys_empty: 'Brak kluczy. Utwórz pierwszy powyżej.',

    /* --- logs --- */
    logs_no_keys: 'Brak kluczy. Wygeneruj je w zakładce Klucze API.',
    logs_go_keys: 'Przejdź do kluczy',
    logs_back: 'Wróć do wyboru klucza',
    logs_chart_title: 'Tokeny w ostatnich 24 godzinach',
    logs_history_title: 'Historia zapytań',

    /* --- connect --- */
    conn_title: 'Jak się połączyć?',
    conn_copy: 'Kopiuj',
    conn_tip: 'Podaj dokładną nazwę modelu z zakładki <b>Modele</b> i poprawny klucz z zakładki <b>Klucze API</b>.',
    ep_local: 'Na tym komputerze',
    ep_lan: 'Z innego urządzenia (LAN)',
    ep_chat: 'Czat',
    ep_models: 'Lista modeli',

    /* --- settings --- */
    settings_slots_title: 'Sloty modeli',
    settings_slots_desc: 'Każdy slot ma własne urządzenie. Model trafia do slotu pasującego do silnika klucza API.',
    settings_lang: 'Język',
    settings_loaded_title: 'Załadowane modele',
    settings_unload_all: 'Zwolnij wszystkie',
    settings_unload: 'Zwolnij z pamięci',
    settings_unloaded: 'Model zwolniony',
    settings_slot_label: 'Slot',
    settings_device_label: 'Urządzenie',
    settings_save_btn: 'Zapisz',
    settings_saved: 'Ustawienia zapisane',
    settings_no_models: 'Brak modeli w pamięci.',
    settings_loaded_in: 'W slocie',
    settings_n_ctx: 'Kontekst',
    settings_refcount: 'Aktywne',

    /* --- modals --- */
    modal_edit_title: 'Edytuj klucz API',
    modal_key_name: 'Nazwa klucza',
    modal_key_val: 'Wartość klucza',
    modal_engine: 'Silnik',
    modal_cancel: 'Anuluj',
    modal_save: 'Zapisz',
    confirm_title: 'Potwierdź',
    confirm_yes: 'Usuń',
    confirm_delete_key: 'Usunąć klucz „{name}"? Wszystkie powiązane logi też zostaną skasowane.',
    confirm_unload_all: 'Zwolnić wszystkie nieużywane modele z pamięci GPU?',

    /* --- komunikaty --- */
    time_never: 'nigdy',
    time_now: 'przed chwilą',
    time_min: 'min',
    time_h: 'godz.',
    time_d: 'd',
    js_never: 'nigdy',
    js_copied: 'Skopiowano do schowka',
    js_copy_fail: 'Nie udało się skopiować',
    js_copy_key: 'Kliknij, aby skopiować klucz',
    js_copy_id: 'Kopiuj nazwę modelu',
    js_loaded_vram: 'Załadowany w pamięci',
    js_avail_disk: 'Dostępny na dysku',
    js_no_models: 'Brak plików .gguf w katalogu models/. Trwa pobieranie modelu testowego w tle…',
    js_created: 'Klucz utworzony',
    js_changes_saved: 'Zmiany zapisane',
    js_key_deleted: 'Klucz usunięty',
    js_err_fields: 'Uzupełnij nazwę i wartość klucza',
    js_online: 'Połączono',
    js_offline: 'Brak połączenia',
    js_err_conn: 'Utracono połączenie z serwerem',
    js_edit: 'Edytuj',
    js_delete: 'Usuń',
    js_no_queries: 'Brak zapytań dla tego klucza',
    js_search: 'Szukaj modelu…',
  },

  en: {
    brand_tagline: 'Local LLM router',
    nav_label_overview: 'Overview',
    nav_label_manage: 'Manage',
    nav_label_system: 'System',
    nav_home: 'Home',
    nav_models: 'Models',
    nav_keys: 'API Keys',
    nav_logs: 'API Logs',
    nav_connect: 'Connection',
    nav_settings: 'Settings',
    status_connecting: 'Connecting…',
    topbar_api: 'API',
    sub_home: 'Local server at a glance',
    sub_models: 'GGUF files found in models/',
    sub_keys: 'Keys to track usage per application',
    sub_logs: 'Request history and usage chart',
    sub_connect: 'Connect your app to this router',
    sub_settings: 'Slots, theme and panel language',

    home_hero_text: 'An OpenAI-compatible local router. Models load onto your GPU, unload themselves when idle, and every request is logged.',
    conn_desc_short: 'OpenAI compatible',
    tag_vulkan: 'Vulkan / CUDA / CPU',
    tag_unload: 'Auto-unload after 2 min',
    stat_last_model: 'Last used model',
    stat_tokens: 'Tokens used',
    stat_requests: 'Requests',
    stat_tps: 'Average speed',
    stat_models: 'Models on disk',
    stat_uptime: 'Uptime',
    stat_slots: 'slots',
    stat_best: 'Best',
    stat_in_vram: 'in memory',
    stat_no_recent: 'none in the last hour',
    stat_avg_tps: 'Average',
    stat_best_tps: 'Best',
    home_loaded_title: 'Slots and loaded models',
    home_recent_title: 'Recent requests',
    home_see_all: 'See all',
    home_no_requests: 'No requests yet. Send one through the API and it will show up here.',
    home_never_used: 'The API has not been used yet',
    home_none_loaded: 'Nothing in memory — models load on first request',
    last_hour: 'in the last hour',
    slot_busy: 'Active',
    slot_loaded: 'Loaded',
    slot_free: 'Free',
    slot_waiting: 'Awaiting a model',
    slot_idle: 'Idle',

    th_time: 'Time',
    th_model_id: 'Model',
    th_key_name: 'Key',
    th_tokens: 'Tokens',
    th_time_s: 'Time (s)',
    th_tps_short: 't/s',
    th_tps: 't/s (avg / min / max)',
    th_ttft: 'TTFT (s)',
    th_name: 'Name',
    th_engine: 'Engine',
    th_last_used: 'Last used',
    th_usage: 'Tokens',
    th_actions: 'Actions',

    models_active_label: 'Loaded in memory:',
    models_none: 'None',

    keys_create_title: 'New key',
    keys_name_label: 'Name',
    keys_name_placeholder: 'e.g. My Project',
    keys_val_placeholder: 'e.g. sk-my-api-123',
    keys_val_label: 'Key value',
    keys_engine_label: 'Engine',
    keys_create_btn: 'Create',
    keys_list_title: 'Your keys',
    keys_empty: 'No keys yet. Create the first one above.',

    logs_no_keys: 'No keys available. Create one in the API Keys tab.',
    logs_go_keys: 'Go to keys',
    logs_back: 'Back to key selection',
    logs_chart_title: 'Tokens over the last 24 hours',
    logs_history_title: 'Query history',

    conn_title: 'How to connect?',
    conn_copy: 'Copy',
    conn_tip: 'Use the exact model name from the <b>Models</b> tab and a valid key from the <b>API Keys</b> tab.',
    ep_local: 'On this machine',
    ep_lan: 'From another device (LAN)',
    ep_chat: 'Chat',
    ep_models: 'Model list',

    settings_slots_title: 'Model slots',
    settings_slots_desc: 'Each slot has its own device. A model is placed in the slot matching the API key engine.',
    settings_lang: 'Language',
    settings_loaded_title: 'Loaded models',
    settings_unload_all: 'Unload all',
    settings_unload: 'Unload from memory',
    settings_unloaded: 'Model unloaded',
    settings_slot_label: 'Slot',
    settings_device_label: 'Device',
    settings_save_btn: 'Save',
    settings_saved: 'Settings saved',
    settings_no_models: 'No models in memory.',
    settings_loaded_in: 'In slot',
    settings_n_ctx: 'Context',
    settings_refcount: 'Active',

    modal_edit_title: 'Edit API key',
    modal_key_name: 'Key name',
    modal_key_val: 'Key value',
    modal_engine: 'Engine',
    modal_cancel: 'Cancel',
    modal_save: 'Save',
    confirm_title: 'Confirm',
    confirm_yes: 'Delete',
    confirm_delete_key: 'Delete key “{name}"? All of its logs will be removed too.',
    confirm_unload_all: 'Unload all unused models from GPU memory?',

    time_never: 'never',
    time_now: 'just now',
    time_min: 'min',
    time_h: 'h',
    time_d: 'd',
    js_never: 'never',
    js_copied: 'Copied to clipboard',
    js_copy_fail: 'Copy failed',
    js_copy_key: 'Click to copy the key',
    js_copy_id: 'Copy model name',
    js_loaded_vram: 'Loaded in memory',
    js_avail_disk: 'Available on disk',
    js_no_models: 'No .gguf files in models/. A test model is downloading in the background…',
    js_created: 'Key created',
    js_changes_saved: 'Changes saved',
    js_key_deleted: 'Key deleted',
    js_err_fields: 'Fill in both the name and the key value',
    js_online: 'Online',
    js_offline: 'Offline',
    js_err_conn: 'Lost connection to the server',
    js_edit: 'Edit',
    js_delete: 'Delete',
    js_no_queries: 'No requests for this key',
    js_search: 'Search model…',
  },
};

const KEY = 'llmapi.lang';
let lang = localStorage.getItem(KEY)
  || ((navigator.language || 'pl').toLowerCase().startsWith('pl') ? 'pl' : 'en');

/** Podmienia {placeholder} w tłumaczeniu. */
function fill(str, vars) {
  return Object.entries(vars || {}).reduce(
    (acc, [k, v]) => acc.replaceAll(`{${k}}`, v), str,
  );
}

function t(key, vars) {
  const dict = DICT[lang] || DICT.en;
  return dict[key] ?? DICT.en[key] ?? key;
}

function translateUI() {
  document.documentElement.lang = lang;
  document.title = 'LocalLLMAPI';

  document.querySelectorAll('[data-i18n]').forEach((node) => {
    const value = DICT[lang]?.[node.dataset.i18n];
    if (value === undefined) return;
    // Ikony wewnątrz elementu z data-i18n zostają nietknięte tylko tam,
    // gdzie klucz dotyczy samego tekstu (nav ma własny <span>).
    node.innerHTML = value;
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
    const value = DICT[lang]?.[node.dataset.i18nPlaceholder];
    if (value !== undefined) node.placeholder = value;
  });

  document.querySelectorAll('[data-i18n-title]').forEach((node) => {
    const value = DICT[lang]?.[node.dataset.i18nTitle];
    if (value !== undefined) node.title = value;
  });

  document.querySelectorAll('.lang-btn').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.lang === lang);
  });
}

function setLanguage(next) {
  lang = DICT[next] ? next : 'en';
  localStorage.setItem(KEY, lang);
  translateUI();
  // Odświeżamy dane, bo etykiety są generowane w JS.
  const api = window.LLMAPI;
  if (!api) return;
  document.querySelectorAll('.nav-item').forEach((n) => {
    n.classList.toggle('is-active', n.dataset.tab === document.querySelector('.panel.is-active')?.id);
  });
  api.showTab(document.querySelector('.panel.is-active')?.id || 'home', false);
  api.renderCode();
  api.loadStats();
}

window.t = t;
window.setLanguage = setLanguage;
window.translateUI = translateUI;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', translateUI);
} else {
  translateUI();
}

})();
