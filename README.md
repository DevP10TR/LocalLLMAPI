# LocalLLMAPI

A fast, lightweight, **local** API server that mimics OpenAI's endpoints
(`/v1/chat/completions`, `/v1/models`), powered by `llama-cpp-python` with
hardware acceleration (Vulkan / CUDA / CPU). It ships with a model manager,
custom API keys, detailed usage logging and a web dashboard.

Runs on **port 1000**.

## Features

- **OpenAI API compatibility** — works out of the box with the official
  Python/JS clients, LangChain, Open WebUI and anything else that speaks the
  OpenAI protocol.
- **Home dashboard** — last used model, total tokens, request count, average
  and best tokens/s, models on disk, uptime, slot occupancy and recent requests.
- **3 model slots** — each bound to a different device (`Vulkan` / `CUDA` /
  `CPU`). Models are routed into the slot matching the API key's engine.
- **No duplicate loads** — concurrent requests for the same model share a
  single in-memory instance instead of loading one per request.
- **VRAM auto-unload** — models idle for more than 2 minutes are freed
  automatically. Reload on demand from the panel or via `POST /api/unload`.
- **API key management** — create, edit and delete keys, switch their engine,
  track token usage per key.
- **Detailed logging** — every request is recorded with TTFT, duration, token
  count and tokens/s (avg / min / max), plus a 24-hour chart.
- **In-app documentation** — the **Docs** tab explains how to reload a model,
  what to send to the API, every endpoint and every error, with runnable
  examples filled in with your address and key.
- **Collapsible sidebar** — click the logo (or `Ctrl`/`Cmd`+`B`) to collapse it
  to icons. The state persists.
- **Light & dark theme** — follows your OS preference, with a manual toggle.
- **Polish / English** — switchable from the Settings tab.
- **Works offline** — Chart.js, the Tabler icon font and every asset are served
  locally. No CDN, no internet required.

## Requirements

- **Python 3.10+**
- A `.gguf` model in `models/` (a small test model downloads automatically if
  the folder is empty)
- Optional: a GPU with Vulkan or CUDA for acceleration

## Getting started

```bat
install_vulkan.bat
```

Put your `.gguf` models into `models/`, then:

```bat
start.bat
```

That's it — the server starts and the dashboard opens at
<http://localhost:1000>. Close the window or press `Ctrl`+`C` to stop.

## Connecting an app

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:1000/v1",
    api_key="PASTE_YOUR_API_KEY_HERE",
)

stream = client.chat.completions.create(
    model="MODEL_NAME_FROM_MODELS_TAB",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

The **Connection** tab shows ready-made snippets for Python, cURL and
JavaScript with your LAN address already filled in. The **Docs** tab covers
parameter reference, every endpoint and every error code.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/chat/completions` | Chat completion (streaming and non-streaming) — requires a key |
| `GET` | `/v1/models` | List of available models |
| `GET` | `/api/status` | Loaded models, slots, uptime, local IP |
| `GET` | `/api/stats` | Aggregates for the Home dashboard |
| `GET`/`POST`/`PUT`/`DELETE` | `/api/keys`, `/api/keys/{id}` | API key management |
| `GET` | `/api/logs/{id}` | Request history for one key |
| `GET`/`PUT` | `/api/settings/slots` | Slot → device mapping |
| `POST` | `/api/unload` | Free models from memory |
| `GET` | `/docs` | Interactive OpenAPI reference |

## Development

```bat
pip install -r requirements.txt
npm install                     :: jsdom, only for the interaction tests
```

```bat
python tools\test_backend.py    :: 40 tests: event loop, duplicate loads, refcount, slots, CORS, docs contract
node tools\test_keys.js         :: 181 tests: every button, sidebar rail, tooltips, documentation
node tools\test_frontend.js     :: 57 tests: syntax, i18n, icons, XSS, port, offline assets
python tools\check_frontend.py  :: HTML/JS consistency: ids, i18n keys, icons
python tools\check_i18n.py      :: per-language key completeness, dead keys
```

`tools/icon-preview.html` shows the app icon candidates at 16/32/180 px on
both backgrounds.

## Security note

The panel endpoints under `/api/*` are not authenticated — anyone who can
reach port 1000 on your network can create and delete keys. Bind to
`127.0.0.1` if that matters to you.

## License

MIT — see [LICENSE](LICENSE).
