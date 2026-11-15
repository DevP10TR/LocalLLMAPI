<div align="center">
  <img src="assets/banner.png" alt="LocalLLMAPI" width="100%" />

  <p align="center">
    <a href="#"><img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6.svg?style=flat-square&logo=windows" alt="Platform: Windows"></a>
    <a href="#"><img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python" alt="Python 3.10+"></a>
    <a href="#"><img src="https://img.shields.io/badge/Local%20Inference-GGUF%20%2F%20llama.cpp-brightgreen.svg?style=flat-square" alt="llama.cpp"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square" alt="License"></a>
  </p>

### Fast Local OpenAI-Compatible GGUF API Server & Dashboard
*Powered by `llama-cpp-python` with Vulkan, CUDA, and CPU hardware acceleration (port `1000`).*

</div>


## 🌟 About

**LocalLLMAPI** is a fast, lightweight local API server mimicking OpenAI's endpoints (`/v1/chat/completions`, `/v1/models`), powered by `llama-cpp-python` with hardware acceleration (**Vulkan / CUDA / CPU**). It ships with a model manager, custom API keys, detailed usage logging, and an offline web dashboard — and is the recommended local backend for **[CMDAI](https://github.com/DevP10TR/CMDAI)** and **[CMDAI-CODE](https://github.com/DevP10TR/CMDAI-CODE)**.

---

## 🚀 Key Features

- ⚡ **OpenAI API Compatibility**: Works out of the box with CMDAI, CMDAI-CODE, official OpenAI Python/JS clients, LangChain, and Open WebUI (`/v1/chat/completions`, `/v1/models`).
- 🎛️ **3 Device-Bound Model Slots**: Dedicated slots for `Vulkan`, `CUDA`, and `CPU` — requests are routed into the slot matching the API key's configured engine, with no duplicate in-memory loads.
- 🧠 **Smart Context & VRAM Auto-Unload**: Automatic context-limit detection and idle VRAM cleanup after 2 minutes (or on demand via `POST /api/unload`).
- 🛠️ **Backend Detection & One-Click Build**: Inspects compiled GPU backends in `llama-cpp-python` and builds missing Vulkan/CUDA wheels directly from **Settings → Backends**.
- 🔑 **API Key Management & Detailed Telemetry**: Create/manage keys per engine, track TTFT, duration, token counts, tokens/s, and inspect 24-hour usage charts.
- 🌐 **100% Offline Web Dashboard**: Plain HTML/CSS/JS dashboard served locally on `http://localhost:1000` with light/dark theme and Polish/English UI.

---

## 📥 Installation

### 1. Git Clone & Run
```powershell
git clone https://github.com/DevP10TR/LocalLLMAPI.git
cd LocalLLMAPI
pip install -r requirements.txt
```

### 2. Optional GPU Acceleration (Vulkan / CUDA)
For GPU acceleration, install the [Vulkan SDK](https://vulkan.lunarg.com/) or CUDA Toolkit, then either use **Settings → Backends → Install** in the dashboard or build `llama-cpp-python` directly:
```bat
set CMAKE_ARGS=-DGGML_VULKAN=on
pip install llama-cpp-python --upgrade --force-reinstall --no-deps
```

### 3. Add Models & Start
Place your `.gguf` files in `models/` (a small test model is downloaded automatically if empty) and launch:
```bat
.\start.bat
```
The server and web dashboard open at `http://localhost:1000`.

---

## 🔌 Connecting an App & Endpoints

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

| Method | Path | Purpose |
| :--- | :--- | :--- |
| `POST` | `/v1/chat/completions` | Chat completion (streaming & non-streaming, requires API key) |
| `GET` | `/v1/models` | List available `.gguf` models |
| `GET` | `/api/status` | Loaded models, slots, uptime, local IP, backend status |
| `GET` | `/api/stats` | Aggregates for the Home dashboard |
| `GET` | `/api/backends` | Installed GPU backends and prerequisites |
| `POST` | `/api/backends/{engine}/install` | Build `llama-cpp-python` wheel for a backend |
| `GET`/`POST`/`PUT`/`DELETE` | `/api/keys`, `/api/keys/{id}` | API key management |
| `GET` | `/api/logs/{id}` | Request history for one key |
| `GET`/`PUT` | `/api/settings/slots` | Slot → device mapping |
| `POST` | `/api/unload` | Free loaded models from memory |
| `GET` | `/docs` | Interactive OpenAPI reference |

---

## 🛠️ Project Structure

```text
LocalLLMAPI/
├── start.bat                 # Server & dashboard launcher
├── requirements.txt          # Python dependencies
├── assets/                   # Banners and visual assets
├── backend/                  # FastAPI/OpenAI router, model manager, DB & context limits
├── web/                      # Offline dashboard (HTML, CSS, JS, local icons/charts)
└── models/                   # Folder for local .gguf model weights
```

> **Security Note**: Panel endpoints under `/api/*` are unauthenticated on the local network; change the host in `start.bat` from `0.0.0.0` to `127.0.0.1` if you want strictly localhost access.

---

## 📄 License

This software is provided under the MIT License. See the [LICENSE](LICENSE) file for details.  
Copyright (c) 2026 LocalLLMAPI contributors.
