"""Sprawdza spójność frontendu: ID z JS vs HTML, klucze i18n, klasy ikon Tabler."""
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
js = (ROOT / "web" / "script.js").read_text(encoding="utf-8")
i18n = (ROOT / "web" / "i18n.js").read_text(encoding="utf-8")
css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
icons_css = (ROOT / "web" / "vendor" / "tabler-icons.min.css").read_text(encoding="utf-8")

errors = []

# --- 1. ID używane w JS muszą istnieć w HTML -------------------------------
html_ids = set(re.findall(r'\bid="([^"]+)"', html))
js_ids = set(re.findall(r"\$\$?\('#([A-Za-z0-9_-]+)'", js)) | set(
    re.findall(r"\$s\('([A-Za-z0-9_-]+)'\)", js)
)
missing_ids = sorted(js_ids - html_ids)
if missing_ids:
    errors.append(f"ID uzywane w JS, brak w HTML: {missing_ids}")

# --- 2. Klucze i18n użyte w HTML muszą być w słownikach ---------------------
html_keys = set(re.findall(r'data-i18n(?:-placeholder)?="([^"]+)"', html))
dict_block = i18n[i18n.index("const DICT"):i18n.index("const KEY =")]
dict_keys = set(re.findall(r"^\s{4}(\w+):", dict_block, re.M))
missing_i18n = sorted(html_keys - dict_keys)
if missing_i18n:
    errors.append(f"Brak tlumaczen dla kluczy z HTML: {missing_i18n}")

# --- 3. Klucze i18n użyte w JS (t('...')) ----------------------------------
js_keys = set(re.findall(r"\bt\('([a-z0-9_]+)'", js))
missing_js_i18n = sorted(js_keys - dict_keys)
if missing_js_i18n:
    errors.append(f"Brak tlumaczen dla kluczy z JS: {missing_js_i18n}")

# --- 4. Wszystkie ikony Tabler musza istniec w vendor CSS -------------------
used = set(re.findall(r"ti-([a-z0-9-]+)", html + js))
used |= set(re.findall(r"icon\('([a-z0-9-]+)'", js))
used |= set(re.findall(r"icon\('([a-z0-9-]+)'", html))
missing_icons = sorted(i for i in used if f".ti-{i}:" not in icons_css)
if missing_icons:
    errors.append(f"Ikony Tabler nieznane w wersji 3.19.0: {missing_icons}")

# --- 5. Zmienne CSS użyte w JS/HTML musza byc zdefiniowane -----------------
defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
used_vars = set(re.findall(r"var\((--[a-z0-9-]+)\)", css))
# 3. logika --bg-color byla uzywana, ale nigdy nie zdefiniowana
if "--bg-color" in used_vars and "--bg-color" not in defined:
    errors.append("CSS: --bg-color jest uzywane, ale nie zdefiniowane")

# --- 6. ID w data-goto musza odpowiadac panelom ----------------------------
panels = set(re.findall(r'<section class="panel[^"]*" id="([^"]+)"', html))
for target in set(re.findall(r'data-goto="([^"]+)"', html)):
    if target not in panels:
        errors.append(f"data-goto=\"{target}\" nie wskazuje na istniejacy panel")

# --- 7. Nav items musza maja odpowiadajacy panel ---------------------------
for tab in re.findall(r'class="nav-item[^"]*" data-tab="([^"]+)"', html):
    if tab not in panels:
        errors.append(f"nav data-tab=\"{tab}\" bez sekcji #{tab}")

# --- 8. Playground musi byc calkowicie usuniety ---------------------------
if "pg-model-select" in html or "sendPlaygroundMessage" in js or "playground" in js.lower():
    errors.append("Playground nie jest w pelni usuniety")
for banned in ("chat-teardrop-text", "pg-message-input", "chat-window"):
    if banned in html or banned in js or banned in css:
        errors.append(f"Zostala resztka Playgroundu: {banned}")

print(f"HTML id: {len(html_ids)} | i18n keys: {len(dict_keys)} | icons used: {len(used)}")
if errors:
    print("\nPROBLEMY:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("\nOK - frontend spojny")
