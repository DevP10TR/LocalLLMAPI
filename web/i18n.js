/* ==========================================================================
   LocalLLMAPI — tłumaczenia PL / EN
   i18n.js ładuje się PRZED script.js i wystawia t() globalnie.
   ========================================================================== */
(() => {
'use strict';

const DICT = {
  pl: {
    /* --- sidebar / topbar --- */
    brand_tagline: 'Local inference router',
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

    /* --- home --- */
    home_headline: 'OpenAI-compatible router running entirely on this machine.',
    tag_compat: 'OpenAI compatible',
    tag_vulkan: 'Vulkan / CUDA / CPU',
    tag_unload: 'Unload after 2 min',
    stat_last_model: 'Last used model',
    stat_tokens: 'Tokens used',
    stat_requests: 'Requests',
    stat_tps: 'Average speed',
    stat_models: 'Models on disk',
    stat_uptime: 'Uptime',
    stat_slots: 'slots',
    stat_best: 'Best',
    stat_in_memory: 'in memory',
    stat_no_recent: 'none in the last hour',
    stat_avg_tps: 'Average',
    stat_best_tps: 'Best',
    home_slots_title: 'Slots',
    home_recent_title: 'Recent requests',
    home_see_all: 'See all',
    home_no_requests: 'No requests yet. Send one through the API and it will show up here.',
    home_never_used: 'The API has not been used yet',
    home_none_loaded: 'Nothing in memory — models load on first request',
    last_hour: 'in the last hour',
    time_ago: 'ago',
    slot_busy: 'Active',
    slot_loaded: 'Loaded',
    slot_free: 'Free',
    slot_waiting: 'Awaiting a model',
    slot_idle: 'Idle',

    /* --- table headers --- */
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

    /* --- models --- */
    models_active_label: 'Loaded in memory:',
    models_none: 'None',

    /* --- keys --- */
    keys_create_title: 'New key',
    keys_name_label: 'Name',
    keys_name_placeholder: 'e.g. My Project',
    keys_val_label: 'Key value',
    keys_val_placeholder: 'e.g. sk-my-api-123',
    keys_engine_label: 'Engine',
    keys_create_btn: 'Create',
    keys_list_title: 'Your keys',
    keys_empty: 'No keys yet. Create the first one above.',

    /* --- logs --- */
    logs_pick_key: 'Select a key',
    logs_no_keys: 'No keys available. Create one in the API Keys tab.',
    logs_go_keys: 'Go to keys',
    logs_back: 'All keys',
    logs_chart_title: 'Tokens, last 24 hours',
    logs_history_title: 'Query history',

    /* --- connect --- */
    conn_title: 'How to connect',
    conn_copy: 'Copy',
    conn_tip: 'Use the exact model name from the <b>Models</b> tab and a valid key from the <b>API Keys</b> tab.',
    ep_local: 'On this machine',
    ep_lan: 'From another device (LAN)',
    ep_chat: 'Chat',
    ep_models: 'Model list',

    /* --- settings --- */
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

    /* --- modals --- */
    modal_edit_title: 'Edit API key',
    modal_key_name: 'Key name',
    modal_key_val: 'Key value',
    modal_engine: 'Engine',
    modal_cancel: 'Cancel',
    modal_save: 'Save',
    confirm_title: 'Confirm',
    confirm_yes: 'Delete',
    confirm_delete_key: 'Delete key “{name}”? All of its logs will be removed too.',
    confirm_unload_all: 'Unload all unused models from GPU memory?',

    /* --- komunikaty --- */
    time_never: 'never',
    time_now: 'just now',
    time_min: 'min',
    time_h: 'h',
    time_d: 'd',
    js_never: 'never',
    js_copied: 'Copied to clipboard',
    js_copy: 'Copy',
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
// Angielski domyślnie, niezależnie od lokalizacji przeglądarki.
let lang = localStorage.getItem(KEY) || 'en';

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
