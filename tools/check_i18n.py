"""Audyt slownikow i18n — osobno dla kazdego jezyka.

Wczesniejsza wersja sprawdzala tylko unie obu jezykow, przez co przepuscila
7 kluczy brakujacych w angielskim slowniku (uzytkownik widzial "65d time_ago").
"""
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = (ROOT / "web" / "i18n.js").read_text(encoding="utf-8")
html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
js = (ROOT / "web" / "script.js").read_text(encoding="utf-8")

start = src.index("const DICT")
end = src.index("const KEY =")
dicts = src[start:end]

# Kazdy jezyk jako osobny blok (kolejnosc w pliku dowolna).
blocks = {}
positions = [(m.group(1), m.start()) for m in re.finditer(r"^  (\w+): \{$", dicts, re.M)]
positions.append(("__end__", len(dicts)))
for i, (lang, pos) in enumerate(positions[:-1]):
    body = dicts[pos : positions[i + 1][1]]
    blocks[lang] = dict(re.findall(r"^    (\w+): (.*)$", body, re.M))

used = set(re.findall(r'data-i18n(?:-placeholder)?="([^"]+)"', html))
used |= set(re.findall(r"\bt\('([a-z0-9_]+)'", js))
# Klucze skladane dynamicznie: t(`sub_${name}`) — trzeba je wyliczyc explicite.
used |= {f"sub_{n}" for n in ("home", "models", "keys", "logs", "connect", "settings")}

errors = []
langs = sorted(blocks)
print(f"slowniki: {', '.join(f'{l}={len(blocks[l])}' for l in langs)}")
print(f"kluczy uzytych w kodzie: {len(used)}\n")

for lang in langs:
    missing = sorted(used - set(blocks[lang]))
    if missing:
        errors.append(f"[{lang}] brak tlumaczen dla kluczy uzytych w kodzie: {missing}")

# Klucze obecne tylko w jednym jezyku sa zwykle smietkami po refaktorze.
if len(langs) == 2:
    a, b = langs
    only_a = sorted(set(blocks[a]) - set(blocks[b]))
    only_b = sorted(set(blocks[b]) - set(blocks[a]))
    dead = sorted((set(blocks[a]) | set(blocks[b])) - used)
    if only_a:
        print(f"tylko w {a}: {only_a}")
    if only_b:
        print(f"tylko w {b}: {only_b}")
    if dead:
        print(f"martwe (nieuzywane nigdzie): {dead}")
    for d in dead:
        errors.append(f"martwy klucz i18n '{d}' — nikt go nie uzywa")

# Wartosci puste / podejrzane
for lang in langs:
    for k, v in blocks[lang].items():
        if v.strip() in ("''", '""', "``"):
            errors.append(f"[{lang}] klucz '{k}' ma pusta wartosc")
        if v.startswith("'") and k.startswith("nav_") is False and "<i" in v:
            errors.append(f"[{lang}] klucz '{k}' zawiera znaczniki <i> (ikony przeniesione do HTML)")

if errors:
    print("\nPROBLEMY:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("\nOK - slowniki i18n kompletne i spojne")
