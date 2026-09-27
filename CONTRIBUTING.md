# Contributing to LocalLLMAPI

Thank you for considering contributing.

## Setup

```bat
pip install -r requirements.txt -r requirements-dev.txt
npm install
```

The first command installs the runtime and test dependencies, the second
installs `jsdom`, which is used **only** by the browser interaction tests. The
application itself has no Node dependency — `npm` is not needed to run it.

## Running the tests

Everything runs offline and loads no model, so the suite is fast and safe to
run on a laptop.

```bat
python tools\test_backend.py     :: server, model registry, API contract
node tools\test_keys.js          :: every button, sidebar, tooltip, docs
node tools\test_frontend.js      :: syntax, i18n, icons, security, assets
python tools\check_frontend.py   :: HTML/JS consistency: ids, i18n keys, icons
python tools\check_i18n.py       :: per-language key completeness
```

All five must pass before you open a pull request. `test_backend.py` and
`test_keys.js` exit non-zero on failure, so they work in CI as-is.

## Things worth knowing before you change something

- **The i18n dictionaries must stay in sync.** `check_i18n.py` verifies each
  language separately and fails on keys that exist in one but not the other,
  or that nothing uses. This exists because that bug shipped once: a missing
  English key rendered as `65d time_ago` in the interface.
- **The documentation is under test.** The error table in the **Docs** tab is
  compared against the real API responses by `test_backend.py`. If you change
  a status code, update `DOC_ERRORS` in `web/script.js` in the same commit.
- **Never build HTML from user data.** `el()` in `web/script.js` deliberately
  has no `html:` option. Model names and API key names come from the database
  and end up in the DOM — keep it that way.
- **Model loading must not block the event loop.** `Llama()` is built in a
  worker thread, each model has its own lock, and `release_model()` runs in a
  `finally`. These are not stylistic choices; removing any of them reintroduces
  frozen servers, VRAM leaks or permanent `503`s.

## Pull requests

- One concern per commit; the message should explain *why*, not *what*.
- Reference the issue number in the body, not the title.
- Include a screenshot for anything visual.
- End files with a newline.

## Reporting bugs

Include the model name, the slot configuration, the engine, and the relevant
part of `error.txt` (it is rotated automatically). The tabler at the bottom of
the sidebar shows whether the server is reachable.
