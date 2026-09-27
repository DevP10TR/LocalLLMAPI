# LocalLLMAPI

A fast, lightweight, **local** API server that mimics OpenAI's endpoints (`/v1/chat/completions`, `/v1/models`), powered by `llama-cpp-python` with hardware acceleration (Vulkan / CUDA / CPU). It ships with a model manager, custom API keys, detailed usage logging and a web dashboard.

Runs on **port 1000**.

## Features

- **OpenAI API compatibility** — works out of the box with the official Python/JS clients, LangChain, Open WebUI and anything else that speaks the OpenAI protocol.
- **Home dashboard** — at a glance: last used model, total tokens, request count, average and best tokens/s, models on disk, uptime, slot occupancy and the last requests.
- **3 model slots** — each slot can be bound to a different device (`Vulkan` / `CUDA` / `CPU`). Models are routed into the slot matching the API key's engine.
- **No duplicate loads** — concurrent requests for the same model share a single in-memory instance instead of loading one per request.
- **VRAM auto-unload** — models idle for more than 2 minutes are freed automatically.
- **API key management** — create, edit and delete keys, switch their engine, and track token usage per key.
- **Detailed logging** — every request is recorded with TTFT, duration, token count and tokens/s (avg / min / max), plus a 24-hour chart.
- **Light & dark theme** — follows your OS preference, with a manual toggle.
- **Polish / English** — switchable from the Settings tab.
- **Works offline** — Chart.js, the Tabler icon font and all assets are served locally. No CDN, no internet required.

## Requirements

- **Python 3.10+**
- A `.gguf` model in `models/` (a small test model is downloaded automatically if the folder is empty)
- Optional: a GPU with Vulkan or CUDA for acceleration

## Getting started

1. Run `install_vulkan.bat` (or `pip install -r requirements.txt`, then install `llama-cpp-python` with the flags for your backend).
2. Put your models in `.gguf` format into `models/`.
3. Run `start.bat` — the dashboard opens at <http://localhost:1000>.

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

The dashboard's **Connection** tab shows ready-made snippets for Python, cURL and JavaScript with your LAN address already filled in.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/chat/completions` | Chat completion (streaming and non-streaming) |
| `GET` | `/v1/models` | List of available models |
| `GET` | `/api/status` | Loaded models, slots, uptime, local IP |
| `GET` | `/api/stats` | Aggregates for the Home dashboard |
| `GET` | `/api/keys` · `POST` · `PUT` · `DELETE` | API key management |
| `GET` | `/api/logs/{id}` | Request history for one key |
| `GET`/`PUT` | `/api/settings/slots` | Slot → device mapping |
| `POST` | `/api/unload` | Free models from memory |
| `GET` | `/docs` | Interactive OpenAPI docs |

## Development

```bat
python tools\test_backend.py      :: 33 testy: blokowanie pętli, duplikaty modeli, refcount, sloty, CORS, endpointy
node tools\test_frontend.js       :: 36 testów: składnia, i18n, ikony, XSS, port, zależności
python tools\check_frontend.py    :: spójność HTML/JS: ID, klucze i18n, ikony
```

> **Note:** the panel endpoints under `/api/*` are not authenticated — anyone who can
> reach port 1000 on your network can create and delete keys. Bind to `127.0.0.1`
> if that matters to you.

*This project is designed for personal use and serves as a lightweight local LLM sandbox.*
