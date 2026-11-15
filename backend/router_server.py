"""LocalLLMAPI — serwer FastAPI naśladujący endpointy OpenAI.

Kluczowe decyzje wydajnościowe (wszystkie potrzebne, żeby serwer nie zamrażał
się przy obsłudze dużych modeli):

* ``Llama(...)`` jest konstruowane w wątku roboczym (``asyncio.to_thread``),
  a nie w pętli zdarzeń. Wcześniej ładowanie modelu 7–16 GB blokowało cały
  serwer na 10–60 s i dashboard pokazywał „Offline".
* Każdy model ma własny ``asyncio.Lock``, więc N równoległych requestów
  tworzy **jedną** instancję zamiast N (wcześniej to był wyciek VRAM).
* Slot jest rezerwowany **przed** budowaniem modelu, więc dwa różne modele
  nie wskoczą do tego samego slotu.
* ``release_model`` jest wołane w ``finally``, więc rozłączenie klienta w
  trakcie streamu nie zostawia modelu „zablokowanego" na stałe (wcześniej
  powodowało to trwały 503).
"""

import asyncio
import contextlib
import gc
import glob as _glob
import json
import os
import queue
import shutil as _shutil
import socket
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.context_limits import (
    compute_safe_context_window,
    extract_extra_prompt_text,
)
from backend.db_manager import (
    add_log,
    create_api_key,
    delete_api_key,
    get_api_key_by_value,
    get_api_keys_stats,
    get_engine_for_key,
    get_global_stats,
    get_logs_for_key,
    get_recent_logs,
    get_slot_devices,
    init_db,
    update_api_key,
    update_slot_device,
)
from backend.model_manager import find_matching_mmproj, get_available_models, get_model_path

SERVER_PORT = 1000
MAX_SLOTS = 3
UNLOAD_IDLE_SECONDS = 120
START_TIME = time.time()

# Wymagane okno kontekstu per (model, silnik) — wyliczane dynamicznie z GGUF + pamięci
model_n_ctx_prefs: Dict[str, int] = {}

init_db()

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

# ==========================================================================
# Stan współdzielony
# ==========================================================================


@dataclass
class LoadedModel:
    slot_index: int
    engine: str
    llama_instance: Any
    model_name: str = ""
    refcount: int = 0
    last_used: float = 0.0
    n_ctx: int = 8192
    max_usable_context: int = 8192
    n_ctx_train: int = 8192
    size_bytes: int = 0
    loaded_at: float = 0.0
    use_mmproj: bool = False
    mmproj_path: Optional[str] = None
    call_lock: threading.Lock = field(default_factory=threading.Lock)


def _model_registry_key(model_name: str, engine: str) -> str:
    return f"{model_name}::{(engine or 'cpu').lower()}"


loaded_models: Dict[str, LoadedModel] = {}
# threading.RLock, nie asyncio.Lock: release_model() wołany jest z wątku
# streamera (GeneratorExit), więc nie może potrzebować pętli zdarzeń.
# Wszystkie sekcje krytyczne są krótkie i nie zawierają await.
models_lock = threading.RLock()
_slots_reserved: Set[int] = set()
_model_locks: Dict[str, asyncio.Lock] = {}
_model_locks_guard = asyncio.Lock()

app = FastAPI(title="Local LLM API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # nieparzwalne z "*" — inaczej FastAPI echo-uje origin
    allow_methods=["*"],
    allow_headers=["*"],
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(auto_unload_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app.router.lifespan_context = lifespan


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Błędy strukturalne (np. brak backendu) idą też w kształcie OpenAI.

    Klienci typu openai-python szukają ``{"error": {...}}``, a nie FastAPI'owe
    ``{"detail": ...}``. Zostawiamy oba, żeby panel i biblioteki działały.
    """
    if isinstance(exc.detail, dict) and exc.detail.get("error"):
        payload = {"error": exc.detail, "detail": exc.detail}
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


async def auto_unload_loop():
    """Zwalnia modele nieużywane przez ``UNLOAD_IDLE_SECONDS``."""
    while True:
        await asyncio.sleep(5)
        expired: List[str] = []
        with models_lock:
            now = time.time()
            for name, lm in list(loaded_models.items()):
                if lm.refcount <= 0 and now - lm.last_used > UNLOAD_IDLE_SECONDS:
                    expired.append(name)
        for name in expired:
            print(f"[Auto-Unload] Zwalnianie modelu (bezczynność): {name}")
            await unload_model(name)


# ==========================================================================
# Backendy llama.cpp: wykrywanie, warunki wstępne, instalacja
#
# llama-cpp-python jest kompilowany ze źródeł i backend jest w nim "zaszyty"
# w momencie instalacji. Nie da się go włączyć w trakcie pracy procesu —
# trzeba przebudować pakiet. Dlatego:
#   * wykrywamy, co faktycznie jest wbudowane,
#   * sprawdzamy warunki wstępne PRZED kompilacją (20 min bez kompilatora
#     to strata czasu),
#   * przy ładowaniu modelu z niedostępnym backendem zwracamy jawny błąd
#     zamiast po cichu jechać na CPU.
# ==========================================================================

# Nazwa engine -> flaga cmake wymagana przy instalacji
BACKEND_CMAKE: Dict[str, Optional[str]] = {
    "cpu": None,
    "vulkan": "-DGGML_VULKAN=on",
    "cuda": "-DGGML_CUDA=on",
}
BACKEND_LABELS = {"cpu": "CPU", "vulkan": "Vulkan", "cuda": "CUDA"}
BACKEND_DLLS = {"vulkan": "ggml-vulkan", "cuda": "ggml-cuda"}

_backend_cache: Dict[str, Any] = {"at": 0.0, "value": {}}
_install_lock = threading.Lock()
_install_state: Dict[str, Any] = {
    "engine": None, "status": "idle", "log": [], "error": None, "pid": None,
}


def _llama_package_dir() -> Optional[str]:
    try:
        import llama_cpp

        return os.path.dirname(llama_cpp.__file__)
    except Exception:
        return None


def detect_backends(ttl: float = 30.0) -> Dict[str, bool]:
    """Które backendy są faktycznie skompilowane w zainstalowanym llama-cpp.

    Sprawdzamy obecność ``ggml-<backend>.dll`` obok pakietu — to jedyne
    pewne źródło, bo API llama.cpp nie eksponuje tego per-backend
    (jest tylko globalne ``llama_supports_gpu_offload()``).
    """
    if time.time() - _backend_cache["at"] < ttl:
        return dict(_backend_cache["value"])

    found: Dict[str, bool] = {"cpu": True, "vulkan": False, "cuda": False}
    pkg = _llama_package_dir()
    if pkg:
        try:
            names = {os.path.basename(p).lower() for p in _glob.glob(os.path.join(pkg, "**", "ggml-*"), recursive=True)}
            for engine, prefix in BACKEND_DLLS.items():
                found[engine] = any(n.startswith(prefix) for n in names)
        except OSError:
            pass

    _backend_cache.update({"at": time.time(), "value": found})
    return dict(found)


def gpu_offload_supported() -> bool:
    """Globalny przełącznik z llama.cpp — weryfikacja krzyżowa wykrywania.

    Nie miesza się z ``detect_backends()``: tam są wyłącznie silniki, tutaj
    flaga boolowska. Zwracamy ``True``, gdy API nie jest dostępne, żeby brak
    symbolu nie blokował ładowania modelu.
    """
    try:
        from llama_cpp.llama_cpp import llama_supports_gpu_offload

        return bool(llama_supports_gpu_offload())
    except Exception:
        return True


def _has_cpp_compiler() -> bool:
    if _shutil.which("cl") or _shutil.which("g++") or _shutil.which("clang++"):
        return True
    # cl.exe jest zwykle poza PATH-em — szukamy go przez vswhere.
    try:
        import subprocess

        vswhere = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
        if os.path.exists(vswhere):
            out = subprocess.run(
                [vswhere, "-latest", "-products", "*", "-find", r"VC\Tools\MSVC\**\bin\Hostx64\x64\cl.exe"],
                capture_output=True, text=True, timeout=20,
            )
            return bool(out.stdout.strip())
    except Exception:
        pass
    return False


def _vulkan_sdk() -> Optional[str]:
    sdk = os.environ.get("VULKAN_SDK")
    if sdk and os.path.isdir(sdk):
        return sdk
    for base in ("C:/VulkanSDK", "C:/VulkanSDK/latest"):
        if os.path.isdir(base):
            return base
    return None


def backend_prereqs(engine: str) -> Dict[str, Any]:
    """Czy da się tu zbudować ten backend. Zwraca brakujące prereqsy."""
    missing: List[str] = []
    if engine == "vulkan":
        if not _vulkan_sdk():
            missing.append("Vulkan SDK")
        elif not _glob.glob(os.path.join(_vulkan_sdk(), "**", "glslc*"), recursive=True):
            missing.append("glslc (Vulkan SDK)")
    elif engine == "cuda":
        if not _shutil.which("nvcc") and not os.path.isdir(
            "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA"
        ):
            missing.append("CUDA Toolkit")
    if not _has_cpp_compiler():
        missing.append("C++ compiler (Visual Studio Build Tools)")

    return {
        "engine": engine,
        "ok": not missing,
        "missing": missing,
        "vulkan_sdk": _vulkan_sdk(),
    }


def missing_provider_message(engine: str) -> str:
    found = detect_backends()
    available = [BACKEND_LABELS[e] for e in BACKEND_CMAKE if found.get(e)]
    return (
        f"{BACKEND_LABELS.get(engine, engine)} backend is not available in this "
        f"llama-cpp-python build - the {BACKEND_LABELS.get(engine, engine)} loader "
        f"is not installed. Available backends: {', '.join(available) or 'none'}. "
        f"Install the {BACKEND_LABELS.get(engine, engine)} loader from the Settings "
        f"tab, or change this API key's engine to one of: {', '.join(available) or 'none'}."
    )


def require_backend(engine: str) -> None:
    """Błąd providera: żądany backend nie istnieje w tej instalacji.

    Bez tego llama.cpp po cichu zostawia warstwy na CPU, a panel pokazuje
    „VULKAN" - użytkownik myśli, że przyspiesza, a model jedzie na CPU.
    Wolno zobaczyć twardy błąd niż ciche kłamstwo w UI.
    """
    if detect_backends().get(engine, True):
        return
    prereq = backend_prereqs(engine)
    raise HTTPException(
        status_code=503,
        detail={
            "error": "backend_unavailable",
            "provider": engine,
            "provider_label": BACKEND_LABELS.get(engine, engine),
            "message": missing_provider_message(engine),
            "available": [e for e in BACKEND_CMAKE if detect_backends().get(e)],
            "missing_prereqs": prereq["missing"],
            "fix": f"POST /api/backends/{engine}/install",
        },
    )


def _installed_llama_version() -> Optional[str]:
    """Wersja llama-cpp-python, którą mamy teraz.

    Przebudowujemy tę samą wersję — zmieniamy tylko backend, więc nie ma
    powodu przeprowadzać przy okazji aktualizacji biblioteki.
    """
    try:
        from importlib.metadata import version

        return version("llama-cpp-python")
    except Exception:
        return None


def _run_pip(lines: List[str], cmd: List[str], env: Dict[str, str], phase: str) -> Optional[int]:
    """Uruchamia potok pip i przepisuje wyjście do logu. Zwraca kod wyjścia."""
    import subprocess

    lines.append(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1
    )
    _install_state["pid"] = proc.pid
    assert proc.stdout is not None
    for raw in proc.stdout:
        text = raw.rstrip()
        if text:
            lines.append(text[:300])
        if len(lines) > 400:
            del lines[: len(lines) - 400]
    proc.wait()
    lines.append(f"[{phase}] exit code {proc.returncode}")
    return proc.returncode


def start_backend_install(engine: str) -> Dict[str, Any]:
    """Buduje llama-cpp-python z danym backendem w watku tle.

    Dwie fazy, celowo rozdzielone:

    1. ``pip wheel`` — kompilacja do pliku .whl. Trwa minuty, ale **niczego
       nie zmienia w środowisku**, więc przerwanie lub błąd kompilacji
       zostawia działającą instalację nietkniętą.
    2. ``pip install <wheel>`` — podmiana trwa sekundy i jest już skompilowana.

    Bez tego rozdzielenia zwykłe ``pip install --force-reinstall`` kasuje
    bieżący pakiet przed kompilacją: błąd w fazie 2 zostawiałby aplikację
    bez llama.cpp w ogóle, a brak ``--no-deps`` przebudowałby też numpy.
    """
    if engine not in BACKEND_CMAKE or engine == "cpu":
        return {"status": "error", "error": f"'{engine}' is not an installable backend"}
    if detect_backends().get(engine):
        return {"status": "already", "message": f"{BACKEND_LABELS[engine]} is already installed"}

    prereq = backend_prereqs(engine)
    if not prereq["ok"]:
        return {
            "status": "missing_prereqs",
            "error": "Missing: " + ", ".join(prereq["missing"]),
            "prereqs": prereq,
        }

    with _install_lock:
        if _install_state["status"] == "running":
            return {"status": "busy", "engine": _install_state["engine"]}
        _install_state.update(
            {"engine": engine, "status": "running", "log": [], "error": None, "pid": None}
        )

    version = _installed_llama_version()
    spec = f"llama-cpp-python=={version}" if version else "llama-cpp-python"

    def worker():
        import glob as g
        import shutil
        import tempfile

        label = BACKEND_LABELS[engine]
        lines = _install_state["log"]
        env = dict(os.environ)
        env["CMAKE_ARGS"] = BACKEND_CMAKE[engine] or ""
        # Wykorzystaj wielowątkową kompilację (MSBuild / CMake), inaczej budowanie
        # llama-cpp-python z Vulkan/CUDA potrafi trwać kilkukrotnie dłużej.
        cpu_jobs = str(max(2, os.cpu_count() or 4))
        env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", cpu_jobs)
        env.setdefault("MAX_JOBS", cpu_jobs)

        # Środowisko musi widzieć toolkit - bez tego cmake nie znajdzie kompilatora.
        if engine == "vulkan" and not env.get("VULKAN_SDK"):
            sdk = _vulkan_sdk()
            if sdk:
                env["VULKAN_SDK"] = sdk
                lines.append(f"VULKAN_SDK={sdk}")
        if engine == "cuda" and not _shutil.which("nvcc"):
            base = "C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA"
            if os.path.isdir(base):
                versions = sorted(
                    (p for p in os.listdir(base) if os.path.isdir(os.path.join(base, p))),
                    reverse=True,
                )
                if versions:
                    env["PATH"] = os.path.join(base, versions[0], "bin") + os.pathsep + env["PATH"]
                    env["CUDA_PATH"] = os.path.join(base, versions[0])
                    lines.append(f"CUDA_PATH={env['CUDA_PATH']}")

        outdir = tempfile.mkdtemp(prefix="llamacpp-build-")
        lines.append(f"--- Phase 1/2: compiling {spec} with {env['CMAKE_ARGS']} ---")
        lines.append("This does NOT touch the current installation yet.")
        try:
            code = _run_pip(
                lines,
                [sys.executable, "-m", "pip", "wheel", spec, "-w", outdir,
                 "--no-cache-dir", "--no-deps"],
                env, "build",
            )
            if code != 0:
                _install_state.update(
                    {"status": "error", "error": f"build failed (exit {code}) — install unchanged"}
                )
                return

            wheels = g.glob(os.path.join(outdir, "*.whl"))
            if not wheels:
                _install_state.update(
                    {"status": "error", "error": "build produced no wheel — install unchanged"}
                )
                return

            wheel = wheels[0]
            size_mb = os.path.getsize(wheel) / (1024 * 1024)
            lines.append(f"--- Phase 2/2: installing {os.path.basename(wheel)} ({size_mb:.1f} MB) ---")
            code = _run_pip(
                lines,
                [sys.executable, "-m", "pip", "install", wheel, "--force-reinstall", "--no-deps"],
                env, "install",
            )
            if code != 0:
                _install_state.update(
                    {"status": "error", "error": f"wheel install failed (exit {code})"}
                )
                return

            lines.append(f"Done — {label} loader installed. Restart the server to use it.")
            _backend_cache["at"] = 0.0            # wymuś ponowne wykrycie
            _install_state.update({"status": "done", "error": None})
        except Exception as exc:  # pragma: no cover - zależy od środowiska
            lines.append(str(exc))
            _install_state.update({"status": "error", "error": str(exc)})
        finally:
            shutil.rmtree(outdir, ignore_errors=True)
            _install_state["pid"] = None

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "running", "engine": engine, "version": version}


# ==========================================================================
# Registry modeli i slotów
# ==========================================================================


async def _model_lock(name: str) -> asyncio.Lock:
    async with _model_locks_guard:
        lk = _model_locks.get(name)
        if lk is None:
            lk = asyncio.Lock()
            _model_locks[name] = lk
        return lk


async def _acquire_slot(requested_engine: str) -> tuple:
    """Rezerwuje wolny slot pasujący do silnika (ewictując LRU jeśli trzeba).

    Zwraca ``(slot_index, model_do_wygnania)``. Rezerwacja następuje **przed**
    budową modelu, więc równoległe requesty nie wybiorą tego samego slotu.
    """
    # Urządzenia slotów czytamy PRZED blokadą — nie trzymamy locka przez await.
    devices = await asyncio.to_thread(get_slot_devices)

    with models_lock:
        for idx in range(1, MAX_SLOTS + 1):
            if devices.get(idx, "cpu") != requested_engine:
                continue
            if idx in _slots_reserved:
                continue
            if any(lm.slot_index == idx for lm in loaded_models.values()):
                continue
            _slots_reserved.add(idx)
            return idx, None

        # Brak wolnego slotu z pasującym silnikiem → wyrzuć LRU (refcount == 0).
        candidates = [
            (lm.last_used, name)
            for name, lm in loaded_models.items()
            if lm.refcount <= 0
            and lm.slot_index not in _slots_reserved
            and devices.get(lm.slot_index, "cpu") == requested_engine
        ]
        label = "matching engine"
        if not candidates:
            candidates = [
                (lm.last_used, name)
                for name, lm in loaded_models.items()
                if lm.refcount <= 0 and lm.slot_index not in _slots_reserved
            ]
            label = "any slot"

        if not candidates:
            raise HTTPException(
                status_code=503,
                detail="All slots are busy with active requests. Try again shortly.",
            )

        _, evict_name = min(candidates)
        slot_idx = loaded_models[evict_name].slot_index
        # Wyrzucamy pod lockiem, więc nikt nie zdąży chwycić ofiary w międzyczasie.
        victim = loaded_models.pop(evict_name)
        print(f"[Model] Evicting ({label}): {evict_name}")
        _slots_reserved.add(slot_idx)
        return slot_idx, victim


def _engine_layers(engine: str) -> int:
    return 0 if engine == "cpu" else -1  # cuda / vulkan → wszystko na GPU


def _messages_have_images(messages: List[Dict[str, Any]]) -> bool:
    """Sprawdza, czy którakolwiek wiadomość zawiera część obrazkową (image_url / image)."""
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and (
                    part.get("type") in ("image_url", "image", "input_image")
                    or "image_url" in part
                ):
                    return True
    return False


def _create_vision_chat_handler(model_path: str, mmproj_path: str):
    """Dobiera handler wizyjny llama_cpp pasujący do modelu i pliku mmproj."""
    import llama_cpp.llama_chat_format as cf

    low = f"{os.path.basename(model_path)} {os.path.basename(mmproj_path)}".lower()
    if "gemma-4" in low or "gemma4" in low:
        cls = getattr(cf, "Gemma4ChatHandler", None)
    elif "qwen2.5-vl" in low or "qwen25-vl" in low or "qwen2-vl" in low or "qwen2_vl" in low:
        cls = getattr(cf, "Qwen25VLChatHandler", None) or getattr(cf, "MTMDChatHandler", None)
    elif "minicpm" in low:
        cls = getattr(cf, "MiniCPMv26ChatHandler", None)
    elif "moondream" in low:
        cls = getattr(cf, "MoondreamChatHandler", None)
    elif "llava-v1.6" in low or "llava-1.6" in low:
        cls = getattr(cf, "Llava16ChatHandler", None)
    else:
        cls = getattr(cf, "MTMDChatHandler", None) or getattr(cf, "Llava15ChatHandler", None)

    if cls is None:
        cls = getattr(cf, "Llava15ChatHandler", None)
    if cls is None:
        raise RuntimeError("Brak obsługiwanych handlerów wizyjnych w llama_cpp.")
    return cls(clip_model_path=mmproj_path, verbose=False)


def _build_llama(model_path: str, layers: int, n_ctx: int, mmproj_path: Optional[str] = None):
    """Budowa instancji Llama — wołana w wątku roboczym, nie w pętli zdarzeń."""
    from llama_cpp import Llama

    kwargs: Dict[str, Any] = {
        "model_path": model_path,
        "n_gpu_layers": layers,
        "n_ctx": n_ctx,
        "flash_attn": True,
        "swa_full": False,
        "type_k": 8,
        "type_v": 8,
        "verbose": False,
    }
    if mmproj_path:
        kwargs["chat_handler"] = _create_vision_chat_handler(model_path, mmproj_path)
    try:
        return Llama(**kwargs)
    except TypeError:
        for opt_key in ("flash_attn", "swa_full", "type_k", "type_v"):
            kwargs.pop(opt_key, None)
        return Llama(**kwargs)


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _resolve_model_ctx_info(model_name: str, engine: str) -> Dict[str, Any]:
    """Oblicza bezpieczne okno kontekstu (GGUF + 70% pamięci urządzenia/RAM)."""
    reg_key = _model_registry_key(model_name, engine)
    with models_lock:
        lm = loaded_models.get(reg_key)
        is_loaded = lm is not None
        active_ctx = lm.n_ctx if lm is not None else 0
        other_bytes = sum(
            m.size_bytes for k, m in loaded_models.items() if k != reg_key
        )
    model_path = get_model_path(model_name)
    return compute_safe_context_window(
        model_path=model_path,
        engine=engine,
        loaded_same_model_ctx=active_ctx,
        is_loaded=is_loaded,
        other_models_bytes=other_bytes,
    )


def _ctx_candidates(preferred_ctx: int) -> List[int]:
    """Malejąca lista bezpiecznych wartości n_ctx na wypadek limitu VRAM przy alokacji."""
    raw = [preferred_ctx, 32768, 16384, 8192, 4096, 2048]
    out: List[int] = []
    for v in raw:
        iv = int(v)
        if 2048 <= iv <= preferred_ctx and iv not in out:
            out.append(iv)
    if 2048 not in out:
        out.append(2048)
    return out


async def load_model(
    model_name: str,
    requested_engine: str,
    min_ctx: int = 0,
    use_mmproj: bool = False,
) -> LoadedModel:
    """Zwraca ``LoadedModel``, wczytując model z bezpiecznym ``n_ctx`` (i opcjonalnym ``mmproj``) jeśli trzeba."""
    reg_key = _model_registry_key(model_name, requested_engine)
    model_path = await asyncio.to_thread(get_model_path, model_name)
    desired_mmproj: Optional[str] = None
    if use_mmproj:
        desired_mmproj = await asyncio.to_thread(find_matching_mmproj, model_path)
        if not desired_mmproj:
            print(f"[Model] Brak pliku mmproj dla {model_name} — ładowanie bez projektora wizji.")

    with models_lock:
        lm = loaded_models.get(reg_key)
        if lm is not None:
            if lm.mmproj_path == desired_mmproj:
                lm.refcount += 1
                lm.last_used = time.time()
                return lm

    # Blokada per (model, silnik): równoległe requesty czekają na jedno wczytanie.
    async with await _model_lock(reg_key):
        need_unload_inner = False
        prev_has_mmproj = False
        while True:
            with models_lock:
                lm = loaded_models.get(reg_key)
                if lm is None:
                    break
                if lm.mmproj_path == desired_mmproj:
                    lm.refcount += 1
                    lm.last_used = time.time()
                    return lm
                if lm.refcount <= 0:
                    prev_has_mmproj = bool(lm.mmproj_path)
                    need_unload_inner = True
                    break
            # Inny request właśnie trwa — poczekaj aż zwolni model, żeby przeładować w docelowym trybie mmproj.
            await asyncio.sleep(0.1)

        if need_unload_inner:
            print(
                f"[Model] Zmiana trybu mmproj dla {model_name} "
                f"({prev_has_mmproj} -> {bool(desired_mmproj)}), przeładowanie..."
            )
            await unload_model(model_name, engine=requested_engine)

        # Backend sprawdzamy PRZED rezerwacją slotu, żeby błąd providera nie
        # zostawiał za sobą zaalokowanego slotu ani pobranego modelu.
        require_backend(requested_engine)

        slot_idx, victim = await _acquire_slot(requested_engine)
        if victim is not None:
            await _close_instance(victim.llama_instance)

        try:
            ctx_info = await asyncio.to_thread(_resolve_model_ctx_info, model_name, requested_engine)
            safe_cap = int(ctx_info.get("max_usable_context") or 8192)
            train_ctx = int(ctx_info.get("n_ctx_train") or safe_cap)
            pref = int(model_n_ctx_prefs.get(reg_key) or 0)
            target_ctx = max(pref or safe_cap, int(min_ctx or 0))
            target_ctx = max(2048, min(safe_cap, target_ctx))
            layers = _engine_layers(requested_engine)

            instance = None
            chosen_ctx = target_ctx
            last_exc: Optional[BaseException] = None
            for cand_ctx in _ctx_candidates(target_ctx):
                try:
                    mm_info = f", mmproj={os.path.basename(desired_mmproj)}" if desired_mmproj else ""
                    print(
                        f"[Model] Loading {model_name} -> slot {slot_idx} "
                        f"({requested_engine}, n_ctx={cand_ctx}, safe_cap={safe_cap}, train={train_ctx}{mm_info})"
                    )
                    instance = await asyncio.to_thread(
                        _build_llama, model_path, layers, cand_ctx, desired_mmproj
                    )
                    chosen_ctx = cand_ctx
                    break
                except Exception as exc:
                    last_exc = exc
                    msg_low = str(exc).lower()
                    if any(w in msg_low for w in ("memory", "vram", "alloc", "context", "failed to create")) and cand_ctx > 2048:
                        print(f"[Model] n_ctx={cand_ctx} failed ({exc}), retrying lower n_ctx...")
                        continue
                    raise
            if instance is None:
                assert last_exc is not None
                raise last_exc

            # Jeśli sprzęt wymusił mniejsze n_ctx przy alokacji, ogranicz max_usable_context
            # do wartości faktycznie wykonalnej na tym urządzeniu.
            effective_max_ctx = safe_cap if chosen_ctx == target_ctx else chosen_ctx
            model_n_ctx_prefs[reg_key] = chosen_ctx
        except BaseException:
            with models_lock:
                _slots_reserved.discard(slot_idx)
            raise

        lm = LoadedModel(
            slot_index=slot_idx,
            engine=requested_engine,
            llama_instance=instance,
            model_name=model_name,
            refcount=1,
            last_used=time.time(),
            n_ctx=chosen_ctx,
            max_usable_context=effective_max_ctx,
            n_ctx_train=train_ctx,
            size_bytes=_file_size(model_path),
            loaded_at=time.time(),
            use_mmproj=bool(desired_mmproj),
            mmproj_path=desired_mmproj,
        )
        with models_lock:
            loaded_models[reg_key] = lm
            _slots_reserved.discard(slot_idx)
        return lm


def release_model(model_name: str, engine: Optional[str] = None) -> None:
    """Synchronous — wywoływane też z wątku streamera, bez pętli zdarzeń.

    Dzięki ``threading.RLock`` nie potrzebujemy ``run_coroutine_threadsafe``,
    który w bloku ``finally`` potrafił zakleszczyć pętlę.
    """
    with models_lock:
        if engine:
            lm = loaded_models.get(_model_registry_key(model_name, engine))
            if lm is not None:
                lm.refcount = max(0, lm.refcount - 1)
                lm.last_used = time.time()
            return
        for key, lm in loaded_models.items():
            if lm.model_name == model_name or key == model_name:
                lm.refcount = max(0, lm.refcount - 1)
                lm.last_used = time.time()


async def unload_model(model_name: str, force: bool = False, engine: Optional[str] = None) -> bool:
    """Zwalnia model (wg nazwy lub pełnego klucza ``model::engine``)."""
    victims: List[Tuple[str, Any, int]] = []
    with models_lock:
        target_key = _model_registry_key(model_name, engine) if engine else None
        for key, lm in list(loaded_models.items()):
            matched = (key == target_key) if target_key else (key == model_name or lm.model_name == model_name)
            if not matched:
                continue
            if lm.refcount > 0 and not force:
                continue
            loaded_models.pop(key, None)
            victims.append((key, lm.llama_instance, lm.slot_index))

    if not victims:
        return False
    for _, instance, slot in victims:
        await _close_instance(instance)
        print(f"[Model] Unloaded {model_name} (slot {slot})")
    return True


async def _close_instance(instance) -> None:
    with contextlib.suppress(Exception):
        instance.close()
    gc.collect()


async def _handle_context_overflow(model_name: str, engine: Optional[str] = None) -> None:
    """Zwiększa n_ctx w granicach bezpiecznego limitu i zwalnia model na następne zapytanie."""
    to_unload: List[str] = []
    with models_lock:
        target_key = _model_registry_key(model_name, engine) if engine else None
        for key, lm in loaded_models.items():
            matched = (key == target_key) if target_key else (key == model_name or lm.model_name == model_name)
            if not matched:
                continue
            cap = lm.max_usable_context or lm.n_ctx_train or 32768
            new_ctx = min(lm.n_ctx + 4096, cap)
            if new_ctx > lm.n_ctx:
                model_n_ctx_prefs[key] = new_ctx
                print(f"[Model] n_ctx for {key} -> {new_ctx} (cap={cap})")
                if lm.refcount <= 1:
                    lm.refcount = 0
                    to_unload.append(key)
    for key in to_unload:
        await unload_model(key)


def snapshot_models() -> List[Dict[str, Any]]:
    """Migawka stanu modeli — bezpieczna do iteracji."""
    with models_lock:
        source = list(loaded_models.items())
    items = [
        {
            "key": key,
            "name": lm.model_name or key.split("::", 1)[0],
            "slot": lm.slot_index,
            "engine": lm.engine,
            "refcount": lm.refcount,
            "n_ctx": lm.n_ctx,
            "max_usable_context": lm.max_usable_context,
            "n_ctx_train": lm.n_ctx_train,
            "size_bytes": lm.size_bytes,
            "loaded_at": lm.loaded_at,
            "last_used": lm.last_used,
        }
        for key, lm in source
    ]
    items.sort(key=lambda m: m["slot"])
    return items


# ==========================================================================
# Cache kosztownych operacji
# ==========================================================================

_ip_cache: Dict[str, Any] = {"value": "127.0.0.1", "at": 0.0}


def get_local_ip(ttl: float = 60.0) -> str:
    """Lookup IP tylko raz na ttl — było wołane co 2 s i robiło nowy socket."""
    if time.time() - _ip_cache["at"] < ttl:
        return _ip_cache["value"]
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    _ip_cache.update({"value": ip, "at": time.time()})
    return ip


_encoders: Dict[str, Any] = {}
_encoder_lock = threading.Lock()


def _get_encoder(name: str = "cl100k_base"):
    """tiktoken ładuje rankingi BPE z dysku — cache'ujemy, wołamy to per request."""
    with _encoder_lock:
        enc = _encoders.get(name)
        if enc is None:
            import tiktoken

            enc = tiktoken.get_encoding(name)
            _encoders[name] = enc
        return enc


def count_prompt_tokens(messages: List[Dict[str, Any]], tools: Any = None) -> int:
    try:
        enc = _get_encoder()
    except Exception:
        enc = None
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
            content = "\n".join(parts)
        if isinstance(content, str):
            total += len(enc.encode(content)) if enc is not None else max(1, len(content) // 4)
    tools_text = extract_extra_prompt_text(tools)
    if tools_text:
        total += len(enc.encode(tools_text)) if enc is not None else max(1, len(tools_text) // 4)
    return total + len(messages) * 4 + 2


_signature_cache: Dict[type, frozenset] = {}


def _supported_kwargs(llm) -> frozenset:
    """Sygnatura create_chat_completion jest stała dla klasy — cache'ujemy."""
    cls = type(llm)
    sig = _signature_cache.get(cls)
    if sig is None:
        import inspect

        sig = frozenset(inspect.signature(llm.create_chat_completion).parameters.keys())
        _signature_cache[cls] = sig
    return sig


_ERROR_LOG = "error.txt"
_ERROR_LOG_MAX = 256 * 1024


def log_error(message: str):
    """Dopisuje błąd zamiast nadpisywać plik przy każdym wyjątku."""
    try:
        with open(_ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{message}\n")
        if os.path.getsize(_ERROR_LOG) > _ERROR_LOG_MAX:
            with open(_ERROR_LOG, "r+", encoding="utf-8") as f:
                f.seek(_ERROR_LOG_MAX // 2)
                rest = f.read()
                f.seek(0)
                f.write("[...starsze wpisy usunięte...]\n")
                f.write(rest)
                f.truncate()
    except OSError:
        pass


def friendly_error(exc: BaseException) -> str:
    msg = str(exc).lower()
    if isinstance(exc, MemoryError) or any(
        w in msg for w in ("memory", "vram", "allocation", "out of memory")
    ):
        return "GPU memory exhausted — the model is too large for this hardware."
    if isinstance(exc, FileNotFoundError) or "no such file" in msg:
        return "Model file not found in models/."
    if "context window" in msg or "context length" in msg:
        return "Context window exceeded — the server is growing it, please retry."
    if "json" in msg or "decode" in msg:
        return "Malformed request payload."
    return f"{type(exc).__name__}: {str(exc)[:180]}"


# ==========================================================================
# Pomiar wydajności
# ==========================================================================


class Metrics:
    """Dokładny pomiar tokenów/s, TTFT i liczby tokenów (perf_counter + usage/tokenizer)."""

    __slots__ = (
        "chunk_tokens",
        "window_tokens",
        "window_start",
        "bucket_tps",
        "gen_start",
        "first_token_t",
        "last_token_t",
        "content",
        "all_generated",
        "reported_prompt_tokens",
        "reported_completion_tokens",
    )

    def __init__(self):
        now = time.perf_counter()
        self.chunk_tokens = 0
        self.window_tokens = 0
        self.window_start = now
        self.bucket_tps: List[float] = []
        self.gen_start = now
        self.first_token_t: Optional[float] = None
        self.last_token_t: Optional[float] = None
        self.content: List[str] = []
        self.all_generated: List[str] = []
        self.reported_prompt_tokens = 0
        self.reported_completion_tokens = 0

    def mark_gen_start(self) -> None:
        """Ustawia punkt startu inferencji po wczytaniu modelu i przejęciu locka."""
        now = time.perf_counter()
        self.gen_start = now
        self.window_start = now

    def observe(self, delta_content: str):
        now = time.perf_counter()
        self.chunk_tokens += 1
        if self.first_token_t is None:
            self.first_token_t = now
            self.window_start = now
            self.window_tokens = 0
        else:
            self.window_tokens += 1
            win_dt = now - self.window_start
            if win_dt >= 0.25 and self.window_tokens >= 2:
                self.bucket_tps.append(self.window_tokens / win_dt)
                self.window_start = now
                self.window_tokens = 0
        self.last_token_t = now
        if delta_content:
            self.content.append(delta_content)
            self.all_generated.append(delta_content)

    def observe_chunk(self, chunk: Dict[str, Any]) -> None:
        raw_usage = chunk.get("usage")
        if isinstance(raw_usage, dict):
            pt = raw_usage.get("prompt_tokens")
            ct = raw_usage.get("completion_tokens")
            if isinstance(pt, (int, float)) and int(pt) > 0:
                self.reported_prompt_tokens = int(pt)
            if isinstance(ct, (int, float)) and int(ct) > 0:
                self.reported_completion_tokens = int(ct)

        try:
            delta = chunk["choices"][0]["delta"] or {}
        except (KeyError, IndexError, TypeError):
            delta = {}
        if not isinstance(delta, dict):
            return

        content_piece = delta.get("content") or ""
        reason_piece = (
            delta.get("reasoning_content")
            or delta.get("reasoning")
            or delta.get("thinking")
            or ""
        )
        tool_calls = delta.get("tool_calls")
        tool_piece = ""
        if tool_calls:
            try:
                tool_piece = json.dumps(tool_calls, ensure_ascii=False)
            except Exception:
                tool_piece = str(tool_calls)

        if content_piece or reason_piece or tool_piece:
            now = time.perf_counter()
            self.chunk_tokens += 1
            if self.first_token_t is None:
                self.first_token_t = now
                self.window_start = now
                self.window_tokens = 0
            else:
                self.window_tokens += 1
                win_dt = now - self.window_start
                if win_dt >= 0.25 and self.window_tokens >= 2:
                    self.bucket_tps.append(self.window_tokens / win_dt)
                    self.window_start = now
                    self.window_tokens = 0
            self.last_token_t = now
            if content_piece:
                self.content.append(content_piece)
                self.all_generated.append(content_piece)
            if reason_piece:
                self.all_generated.append(reason_piece)
            if tool_piece:
                self.all_generated.append(tool_piece)

    def _exact_completion_tokens(self, llm: Any = None) -> int:
        if self.reported_completion_tokens > 0:
            return self.reported_completion_tokens
        full_out = "".join(self.all_generated)
        if llm is not None and full_out:
            try:
                toks = llm.tokenize(full_out.encode("utf-8", errors="ignore"), add_bos=False)
                if isinstance(toks, list) and len(toks) > 0:
                    return max(self.chunk_tokens, len(toks)) if self.chunk_tokens > 0 else len(toks)
            except Exception:
                pass
        if full_out and self.chunk_tokens <= 0:
            try:
                return len(_get_encoder().encode(full_out))
            except Exception:
                return max(1, len(full_out) // 4)
        return self.chunk_tokens

    def summary(self, prompt_tokens: int, llm: Any = None) -> Dict[str, Any]:
        end_t = self.last_token_t or time.perf_counter()
        elapsed = max(0.001, end_t - self.gen_start)
        ttft = (self.first_token_t - self.gen_start) if self.first_token_t is not None else 0.0
        comp_tokens = self._exact_completion_tokens(llm=llm)
        p_tokens = self.reported_prompt_tokens if self.reported_prompt_tokens > 0 else int(prompt_tokens)

        if comp_tokens > 1 and self.first_token_t is not None and end_t > self.first_token_t:
            decode_time = max(0.001, end_t - self.first_token_t)
            avg_tps = (comp_tokens - 1) / decode_time
        elif comp_tokens == 1:
            avg_tps = 1.0 / max(0.001, elapsed)
        else:
            avg_tps = 0.0

        samples = list(self.bucket_tps)
        if self.window_tokens >= 1 and end_t > self.window_start and (end_t - self.window_start) >= 0.05:
            samples.append(self.window_tokens / (end_t - self.window_start))
        if not samples and avg_tps > 0:
            samples = [avg_tps]

        return {
            "elapsed": round(elapsed, 2),
            "prompt_tokens": p_tokens,
            "completion_tokens": comp_tokens,
            "total_tokens": comp_tokens + p_tokens,
            "avg_tps": round(avg_tps, 2),
            "min_tps": round(min(samples), 2) if samples else 0.0,
            "max_tps": round(max(samples), 2) if samples else 0.0,
            "ttft": round(max(0.0, ttft), 3),
        }


def _persist(api_key_id: int, model: str, m: Dict[str, Any]):
    add_log(
        api_key_id,
        model,
        m["elapsed"],
        m["total_tokens"],
        m["avg_tps"],
        m["min_tps"],
        m["max_tps"],
        m["ttft"],
    )


def _collect_chunks(chunks, metrics: Metrics) -> None:
    """Blokujące — wywoływane w wątku roboczym dla trybu non-streaming."""
    for chunk in chunks:
        metrics.observe_chunk(chunk)


# ==========================================================================
# Endpointy OpenAI
# ==========================================================================


class ChatCompletionRequest(BaseModel):
    model_config = {"extra": "allow"}
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096
    stream: Optional[bool] = False


def get_current_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    key_id = get_api_key_by_value(credentials.credentials)
    if not key_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Create one in the API Keys tab.",
        )
    return key_id


def _context_headers(
    max_ctx: int, active_ctx: int, prompt_tokens: int, engine: str
) -> Dict[str, str]:
    remaining = max(0, int(max_ctx) - int(prompt_tokens))
    return {
        "X-LocalLLM-Max-Context": str(int(max_ctx)),
        "X-LocalLLM-Active-Context": str(int(active_ctx)),
        "X-LocalLLM-Prompt-Tokens": str(int(prompt_tokens)),
        "X-LocalLLM-Remaining-Context": str(remaining),
        "X-LocalLLM-Engine": str(engine),
    }


def _resolve_caller_engine_sync(credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    if credentials and credentials.credentials:
        key_id = get_api_key_by_value(credentials.credentials)
        if key_id:
            return get_engine_for_key(key_id)
    devices = get_slot_devices()
    return devices.get(1, "cpu")


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest, api_key_id: int = Depends(get_current_api_key)
):
    if not request.model:
        raise HTTPException(status_code=400, detail="Missing the 'model' field.")

    api_engine = await asyncio.to_thread(get_engine_for_key, api_key_id)
    start_time = time.time()
    needs_vision = _messages_have_images(request.messages)
    lm = await load_model(request.model, api_engine, use_mmproj=needs_vision)
    handed_off_to_stream = False
    released = False

    # Od tego momentu refcount musi zawsze spaść — inaczej slot zostaje
    # zablokowany na stałe (tak było przy rozłączeniu klienta w trakcie streamu).
    try:
        extra = request.model_extra or {}
        prompt_tokens = await asyncio.to_thread(
            count_prompt_tokens, request.messages, extra.get("tools")
        )
        ctx_info = await asyncio.to_thread(_resolve_model_ctx_info, request.model, api_engine)
        safe_cap = int(ctx_info.get("max_usable_context") or lm.max_usable_context or lm.n_ctx)
        effective_max = max(lm.n_ctx, min(lm.max_usable_context or safe_cap, safe_cap))

        if prompt_tokens > effective_max:
            ctx_headers = _context_headers(effective_max, lm.n_ctx, prompt_tokens, lm.engine)
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": (
                            f"Context length exceeded: prompt uses {prompt_tokens} tokens, "
                            f"but maximum usable context for '{request.model}' ({lm.engine}) is {effective_max} tokens."
                        ),
                        "type": "invalid_request_error",
                        "code": "context_length_exceeded",
                        "max_context_tokens": effective_max,
                        "prompt_tokens": prompt_tokens,
                    }
                },
                headers=ctx_headers,
            )

        # Jeśli model był załadowany z mniejszym n_ctx niż aktualny prompt (ale mieści się
        # w bezpiecznym limicie), przeładuj go automatycznie przed inferencją.
        if prompt_tokens > lm.n_ctx and lm.refcount <= 1:
            needed_ctx = min(effective_max, max(prompt_tokens + 1024, lm.n_ctx + 4096))
            release_model(request.model, api_engine)
            released = True
            await unload_model(request.model, engine=api_engine)
            lm = await load_model(
                request.model, api_engine, min_ctx=needed_ctx, use_mmproj=needs_vision
            )
            released = False

        llm = lm.llama_instance
        filtered = {k: v for k, v in extra.items() if k in _supported_kwargs(llm)}
        metrics = Metrics()
        ctx_headers = _context_headers(effective_max, lm.n_ctx, prompt_tokens, lm.engine)

        if request.stream:
            handed_off_to_stream = True
            return _stream_response(
                request,
                api_key_id,
                lm,
                filtered,
                metrics,
                start_time,
                prompt_tokens,
                effective_max,
                ctx_headers,
            )

        # Non-streaming: generacja w wątku pod blokadą instancji Llama.
        def _run_non_streaming():
            with lm.call_lock:
                metrics.mark_gen_start()
                chunks = llm.create_chat_completion(
                    model=request.model,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    stream=True,
                    **filtered,
                )
                _collect_chunks(chunks, metrics)

        try:
            await asyncio.to_thread(_run_non_streaming)
        except (OSError, ValueError) as e:
            if "context window" in str(e) or "context length" in str(e):
                await _handle_context_overflow(request.model, engine=api_engine)
                log_error(f"context overflow ({request.model}): {e}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "message": f"{e} (max usable context: {effective_max} tokens)",
                            "type": "invalid_request_error",
                            "code": "context_length_exceeded",
                            "max_context_tokens": effective_max,
                            "prompt_tokens": prompt_tokens,
                        }
                    },
                    headers=ctx_headers,
                )
            else:
                raise

        summary = metrics.summary(prompt_tokens, llm=llm)
        await asyncio.to_thread(_persist, api_key_id, request.model, summary)
        remaining_after = max(0, effective_max - summary["total_tokens"])
        return JSONResponse(
            content={
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "".join(metrics.content)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": summary["prompt_tokens"],
                    "completion_tokens": summary["completion_tokens"],
                    "total_tokens": summary["total_tokens"],
                    "max_context_tokens": effective_max,
                    "active_n_ctx": lm.n_ctx,
                    "remaining_context_tokens": remaining_after,
                },
            },
            headers=ctx_headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        log_error(f"{e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=friendly_error(e))
    finally:
        if not handed_off_to_stream and not released:
            release_model(request.model, api_engine)


def _stream_response(
    request,
    api_key_id,
    lm: LoadedModel,
    filtered: Dict[str, Any],
    metrics: Metrics,
    start_time: float,
    prompt_tokens: int,
    effective_max: int,
    ctx_headers: Dict[str, str],
):
    """Odpowiedź SSE z keep-alive podczas długiego prompt eval i bezpiecznym zwalnianiem."""
    q: queue.Queue = queue.Queue()
    cancel_event = threading.Event()
    producer_started = False

    def _producer():
        final_summary: Optional[Dict[str, Any]] = None
        try:
            with lm.call_lock:
                if cancel_event.is_set():
                    return
                metrics.mark_gen_start()
                chunks = lm.llama_instance.create_chat_completion(
                    model=request.model,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    stream=True,
                    **filtered,
                )
                for chunk in chunks:
                    if cancel_event.is_set():
                        break
                    metrics.observe_chunk(chunk)
                    chunk["object"] = "chat.completion.chunk"
                    q.put(("chunk", chunk))

                final_summary = metrics.summary(prompt_tokens, llm=lm.llama_instance)
            q.put(("done", final_summary))
        except (OSError, ValueError) as e:
            msg = str(e)
            log_error(f"stream error ({request.model}): {msg}")
            if "context window" in msg or "context length" in msg:
                new_ctx = min((lm.n_ctx or 8192) + 4096, effective_max)
                model_n_ctx_prefs[_model_registry_key(request.model, lm.engine)] = new_ctx
                q.put(("ctx_err", msg))
            else:
                q.put(("err", e))
        except Exception as e:
            log_error(f"stream error ({request.model}): {e}")
            q.put(("err", e))
        finally:
            with contextlib.suppress(Exception):
                _persist(
                    api_key_id,
                    request.model,
                    final_summary or metrics.summary(prompt_tokens),
                )
            with contextlib.suppress(Exception):
                release_model(request.model, lm.engine)

    t = threading.Thread(target=_producer, daemon=True)
    t.start()
    producer_started = True

    def stream_generator():
        try:
            while True:
                try:
                    kind, payload = q.get(timeout=5.0)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue

                if kind == "chunk":
                    yield f"data: {json.dumps(payload)}\n\n"
                elif kind == "done":
                    remaining_after = max(0, effective_max - payload["total_tokens"])
                    usage_chunk = {
                        "id": f"chatcmpl-{int(start_time)}",
                        "object": "chat.completion.chunk",
                        "created": int(start_time),
                        "model": request.model,
                        "choices": [],
                        "usage": {
                            "prompt_tokens": payload["prompt_tokens"],
                            "completion_tokens": payload["completion_tokens"],
                            "total_tokens": payload["total_tokens"],
                            "max_context_tokens": effective_max,
                            "active_n_ctx": lm.n_ctx,
                            "remaining_context_tokens": remaining_after,
                            "tokens_per_second": payload["avg_tps"],
                        },
                    }
                    yield f"data: {json.dumps(usage_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    break
                elif kind == "ctx_err":
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "error": {
                                    "message": f"{payload} (max usable context: {effective_max} tokens)",
                                    "type": "context_length_exceeded",
                                    "code": "context_length_exceeded",
                                    "max_context_tokens": effective_max,
                                    "prompt_tokens": prompt_tokens,
                                }
                            }
                        )
                        + "\n\n"
                    )
                    yield "data: [DONE]\n\n"
                    break
                elif kind == "err":
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "error": {
                                    "message": friendly_error(payload),
                                    "type": "server_error",
                                }
                            }
                        )
                        + "\n\n"
                    )
                    yield "data: [DONE]\n\n"
                    break
        finally:
            cancel_event.set()
            if not producer_started:
                with contextlib.suppress(Exception):
                    release_model(request.model, lm.engine)

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **ctx_headers,
        },
    )


def _model_list_entry(model_name: str, engine: str) -> Dict[str, Any]:
    ctx_info = _resolve_model_ctx_info(model_name, engine)
    max_ctx = int(ctx_info.get("max_usable_context") or 8192)
    mmproj = find_matching_mmproj(get_model_path(model_name))
    return {
        "id": model_name,
        "object": "model",
        "vision": bool(mmproj),
        "context_length": max_ctx,
        "max_model_len": max_ctx,
        "max_usable_context": max_ctx,
        "n_ctx_train": int(ctx_info.get("n_ctx_train") or max_ctx),
        "active_n_ctx": int(ctx_info.get("active_n_ctx") or max_ctx),
        "engine": engine,
        "architecture": ctx_info.get("architecture", "unknown"),
        "kv_cache_bytes_per_token": int(ctx_info.get("kv_cache_bytes_per_token") or 0),
        "memory_budget": {
            "file_size_gb": ctx_info.get("file_size_gb", 0.0),
            "free_ram_gb": ctx_info.get("free_ram_gb", 0.0),
            "free_vram_gb": ctx_info.get("free_vram_gb"),
            "budget_source": ctx_info.get("budget_source", "system_ram"),
            "recommended_compaction_at": ctx_info.get("recommended_compaction_at", 0.97),
        },
    }


@app.get("/models")
@app.get("/v1/models")
async def list_models(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
):
    engine = await asyncio.to_thread(_resolve_caller_engine_sync, credentials)
    models = await asyncio.to_thread(get_available_models)
    entries = await asyncio.to_thread(lambda: [_model_list_entry(m, engine) for m in models])
    return {"object": "list", "data": entries}


@app.get("/context")
@app.get("/v1/context")
async def get_all_models_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
):
    engine = await asyncio.to_thread(_resolve_caller_engine_sync, credentials)
    models = await asyncio.to_thread(get_available_models)
    entries = await asyncio.to_thread(lambda: [_model_list_entry(m, engine) for m in models])
    return {"object": "context_budget_list", "engine": engine, "data": entries}


@app.get("/v1/models/{model_id:path}/context")
async def get_model_context(
    model_id: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
):
    engine = await asyncio.to_thread(_resolve_caller_engine_sync, credentials)
    return await asyncio.to_thread(_model_list_entry, model_id, engine)


# ==========================================================================
# Endpointy panelu
# ==========================================================================


class CreateKeyRequest(BaseModel):
    name: str
    api_key: str
    engine: Optional[str] = "vulkan"


@app.post("/api/keys")
async def create_new_key(req: CreateKeyRequest):
    if not req.name or not req.api_key:
        raise HTTPException(status_code=400, detail="Fields 'name' and 'api_key' are required.")
    try:
        key_id = await asyncio.to_thread(create_api_key, req.name, req.api_key, req.engine)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": key_id, "name": req.name, "api_key": req.api_key, "engine": req.engine}


@app.get("/api/keys")
async def get_keys():
    return await asyncio.to_thread(get_api_keys_stats)


class UpdateKeyRequest(BaseModel):
    name: str
    api_key: Optional[str] = None
    engine: Optional[str] = "vulkan"


@app.put("/api/keys/{api_key_id}")
async def update_key(api_key_id: int, req: UpdateKeyRequest):
    if not req.name:
        raise HTTPException(status_code=400, detail="Name is required.")
    await asyncio.to_thread(update_api_key, api_key_id, req.name, req.api_key, req.engine)
    return {"status": "ok"}


@app.delete("/api/keys/{api_key_id}")
async def delete_key(api_key_id: int):
    await asyncio.to_thread(delete_api_key, api_key_id)
    return {"status": "ok"}


@app.get("/api/logs/{api_key_id}")
async def get_logs(api_key_id: int):
    return await asyncio.to_thread(get_logs_for_key, api_key_id, 200)


@app.post("/api/unload")
async def unload_all(model_name: Optional[str] = None):
    if model_name:
        ok = await unload_model(model_name)
        return {
            "status": "ok",
            "message": f"Model {model_name} {'unloaded' if ok else 'was not loaded'}",
        }
    free = [m["key"] for m in snapshot_models() if m["refcount"] <= 0]
    for n in free:
        await unload_model(n)
    return {"status": "ok", "message": "All unused models unloaded"}


@app.get("/api/status")
async def get_status():
    loaded = snapshot_models()
    name_counts: Dict[str, int] = {}
    for m in loaded:
        name_counts[m["name"]] = name_counts.get(m["name"], 0) + 1
    loaded_map = {}
    for m in loaded:
        label = f"{m['name']} ({m['engine']})" if name_counts.get(m["name"], 0) > 1 else m["name"]
        loaded_map[label] = {k: v for k, v in m.items() if k not in ("name", "key")}
    return {
        "loaded_models": loaded_map,
        "local_ip": get_local_ip(),
        "port": SERVER_PORT,
        "uptime": int(time.time() - START_TIME),
        # Które backendy llama.cpp faktycznie skompilowano - panel używa tego
        # do wyłączenia wyboru silników, których nie da się użyć.
        "backends": await asyncio.to_thread(backends_payload),
        # Backward-compat: panel używa tego pola do podświetlenia modelu
        "active_model": loaded[0]["name"] if loaded else None,
    }


@app.get("/api/stats")
async def get_stats():
    """Agregaty dla strony HOME."""
    models_on_disk = await asyncio.to_thread(get_available_models)
    glob = await asyncio.to_thread(get_global_stats)
    recent = await asyncio.to_thread(get_recent_logs, 8)
    return {
        "uptime": int(time.time() - START_TIME),
        "port": SERVER_PORT,
        "local_ip": get_local_ip(),
        "models_on_disk": len(models_on_disk),
        "loaded_models": snapshot_models(),
        "slots_total": MAX_SLOTS,
        "recent": recent,
        **glob,
    }


@app.get("/api/settings/slots")
async def get_slots():
    devices = await asyncio.to_thread(get_slot_devices)
    loaded = snapshot_models()
    result = {}
    for idx in range(1, MAX_SLOTS + 1):
        occupied = next((m["name"] for m in loaded if m["slot"] == idx), None)
        result[str(idx)] = {"device": devices.get(idx, "cpu"), "loaded_model": occupied}
    return result


class SlotUpdateRequest(BaseModel):
    slot_index: int
    device: str


@app.put("/api/settings/slots")
async def update_slot(req: SlotUpdateRequest):
    if not 1 <= req.slot_index <= MAX_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot index must be between 1 and {MAX_SLOTS}")
    if req.device not in ("cpu", "cuda", "vulkan"):
        raise HTTPException(status_code=400, detail="Device must be 'cpu', 'cuda' or 'vulkan'")
    await asyncio.to_thread(update_slot_device, req.slot_index, req.device)
    return {"status": "ok"}


# ==========================================================================
# Backendy llama.cpp
# ==========================================================================


def _engines_in_use() -> Dict[str, int]:
    """Które silniki są faktycznie używane — przez sloty i przez klucze API.

    Panel ostrzega tylko wtedy, gdy brakujący backend jest realnie wykorzystywany:
    niewykorzystywany Vulkan nie jest problemem, a używany — tak.
    """
    usage: Dict[str, int] = {}
    try:
        for device in get_slot_devices().values():
            usage[device] = usage.get(device, 0) + 1
    except Exception:
        pass
    try:
        for k in get_api_keys_stats():
            eng = k.get("engine")
            if eng:
                usage[eng] = usage.get(eng, 0) + 1
    except Exception:
        pass
    return usage


def backends_payload() -> Dict[str, Any]:
    """Stan backendów + warunki wstępne, w formie wygodnej dla panelu."""
    found = detect_backends()
    engines = {}
    for name, cmake in BACKEND_CMAKE.items():
        entry: Dict[str, Any] = {
            "label": BACKEND_LABELS[name],
            "installed": bool(found.get(name)),
            "cmake_args": cmake,
            "prereqs": None,
        }
        if name != "cpu":
            entry["prereqs"] = backend_prereqs(name)
        engines[name] = entry

    in_use = _engines_in_use()
    return {
        "engines": engines,
        "available": [n for n in BACKEND_CMAKE if found.get(n)],
        "gpu_offload": gpu_offload_supported(),
        "in_use": in_use,
        # Silniki, na których coś stoi, a których nie ma - każdy taki request
        # skończy się 503 zamiast działać.
        "broken": [
            n for n in in_use if n in BACKEND_CMAKE and not found.get(n)
        ],
        # Kopiujemy stan: wątek instalacji dopisuje do logu w trakcie, gdy
        # panel go odpytuje - serializacja żywego obiektu potrafi rzucić wyjątek.
        "install": dict(_install_state, log=list(_install_state["log"])),
        "restart_required": _install_state["status"] == "done",
    }


@app.get("/api/backends")
async def get_backends():
    return await asyncio.to_thread(backends_payload)


@app.post("/api/backends/{engine}/install")
async def install_backend_endpoint(engine: str):
    if engine not in BACKEND_CMAKE or engine == "cpu":
        raise HTTPException(
            status_code=400, detail=f"'{engine}' is not an installable backend"
        )
    return await asyncio.to_thread(start_backend_install, engine)


@app.post("/api/backends/refresh")
async def refresh_backends():
    """Wymusza ponowne wykrycie (po ręcznej instalacji SDK w trakcie sesji)."""
    _backend_cache["at"] = 0.0
    if _install_state["status"] == "done":
        _install_state["status"] = "idle"
    return await asyncio.to_thread(backends_payload)


# ==========================================================================
# Panel WWW
# ==========================================================================

web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")


if __name__ == "__main__":
    import sys as _sys

    if "--backends" in _sys.argv:
        # start.bat woła to przed wstaniem serwera. Trzymamy to w Pythonie,
        # a nie w linii .bat, bo cudzysłowy w BAT-ie są podatne na zjedzenie.
        _state = backends_payload()
        print("  Installed : " + ", ".join(_state["available"]))
        if _state["broken"]:
            print("  MISSING   : " + ", ".join(_state["broken"])
                  + "  (in use - every request will fail)")
            for _name in _state["broken"]:
                _miss = _state["engines"][_name]["prereqs"].get("missing") or []
                if _miss:
                    print(f"              {_name}: first install " + ", ".join(_miss))
                else:
                    print(f"              {_name}: buildable - use Settings > Backends")
        else:
            print("  All backends used by this setup are installed.")
    else:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="warning")
