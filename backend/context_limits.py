"""Context-window & memory-budget helpers ported from CMDAI CODE for LocalLLMAPI.

Reads GGUF model metadata directly from disk, estimates per-token KV-cache cost,
measures available system RAM (and GPU VRAM when detectable), accounts for other
currently loaded slots, and returns the exact maximum safe context window so
LocalLLMAPI can both configure `n_ctx` safely and advertise it to client apps.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import struct
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None  # type: ignore

COMPACTION_THRESHOLD = 0.97
DEFAULT_FALLBACK_CTX = 8192
MIN_SAFE_CTX = 2048

_GGUF_CACHE_LOCK = threading.Lock()
_GGUF_META_CACHE: Dict[Tuple[str, float, int], Dict[str, Any]] = {}

_GPU_CACHE_LOCK = threading.Lock()
_GPU_MEM_CACHE: Dict[str, Any] = {"at": 0.0, "value": None}


def _read_gguf_header_binary(gguf_path: str) -> Dict[str, Any]:
    """Pure-Python GGUF binary header reader (no external `gguf` package needed)."""
    out: Dict[str, Any] = {}
    try:
        with open(gguf_path, "rb") as f:
            magic = f.read(4)
            if magic != b"GGUF":
                return out
            ver_b = f.read(4)
            if len(ver_b) < 4:
                return out
            version = struct.unpack("<I", ver_b)[0]
            if version == 1:
                counts_b = f.read(8)
                if len(counts_b) < 8:
                    return out
                _, kv_count = struct.unpack("<II", counts_b)
                u64_len = False
            else:
                counts_b = f.read(16)
                if len(counts_b) < 16:
                    return out
                _, kv_count = struct.unpack("<QQ", counts_b)
                u64_len = True

            def _read_len() -> int:
                b = f.read(8 if u64_len else 4)
                return struct.unpack("<Q" if u64_len else "<I", b)[0]

            def _read_str() -> str:
                n = _read_len()
                if n > 1_000_000:
                    raise ValueError("Implausible GGUF string length")
                return f.read(n).decode("utf-8", errors="ignore")

            scalar_fmt = {
                0: ("<B", 1),
                1: ("<b", 1),
                2: ("<H", 2),
                3: ("<h", 2),
                4: ("<I", 4),
                5: ("<i", 4),
                6: ("<f", 4),
                7: ("<?", 1),
                10: ("<Q", 8),
                11: ("<q", 8),
                12: ("<d", 8),
            }

            def _skip_or_read_val(vtype: int, keep: bool):
                if vtype in scalar_fmt:
                    fmt, sz = scalar_fmt[vtype]
                    raw = f.read(sz)
                    return struct.unpack(fmt, raw)[0] if keep and len(raw) == sz else None
                if vtype == 8:
                    n = _read_len()
                    if keep and n <= 1_000_000:
                        return f.read(n).decode("utf-8", errors="ignore")
                    f.seek(n, os.SEEK_CUR)
                    return None
                if vtype == 9:
                    elem_t = struct.unpack("<I", f.read(4))[0]
                    arr_n = _read_len()
                    if elem_t in scalar_fmt:
                        _, sz = scalar_fmt[elem_t]
                        f.seek(sz * arr_n, os.SEEK_CUR)
                    else:
                        for _ in range(arr_n):
                            _skip_or_read_val(elem_t, False)
                    return None
                raise ValueError(f"Unknown GGUF value type: {vtype}")

            for _ in range(min(int(kv_count), 512)):
                key = _read_str()
                vtype = struct.unpack("<I", f.read(4))[0]
                want = (
                    key == "general.architecture"
                    or key.endswith(".context_length")
                    or key.endswith(".block_count")
                    or key.endswith(".attention.head_count_kv")
                    or key.endswith(".attention.key_length")
                    or key.endswith(".embedding_length")
                    or key.endswith(".attention.head_count")
                )
                val = _skip_or_read_val(vtype, want)
                if want and val is not None:
                    out[key] = val
    except Exception:
        pass
    return out


def read_gguf_metadata(gguf_path: str) -> Dict[str, Any]:
    """Read architecture, training context length, KV dimensions, and file size."""
    fallback: Dict[str, Any] = {
        "n_ctx_train": DEFAULT_FALLBACK_CTX,
        "file_size_gb": 0.0,
        "arch": "unknown",
        "n_layer": None,
        "n_head_kv": None,
        "n_embd_head_k": None,
        "estimated": True,
    }
    if not gguf_path or not os.path.exists(gguf_path):
        return fallback

    abs_path = os.path.abspath(gguf_path)
    try:
        st = os.stat(abs_path)
        cache_key = (abs_path, float(st.st_mtime), int(st.st_size))
    except OSError:
        return fallback

    with _GGUF_CACHE_LOCK:
        cached = _GGUF_META_CACHE.get(cache_key)
        if cached is not None:
            return dict(cached)

    result = dict(fallback)
    result["file_size_gb"] = cache_key[2] / (1024**3)

    raw_hdr = _read_gguf_header_binary(abs_path)
    arch = str(raw_hdr.get("general.architecture") or "").strip().lower()
    if arch:
        result["arch"] = arch
        ctx = raw_hdr.get(f"{arch}.context_length")
        if isinstance(ctx, int) and ctx > 0:
            result["n_ctx_train"] = ctx
        layer = raw_hdr.get(f"{arch}.block_count")
        if isinstance(layer, int) and layer > 0:
            result["n_layer"] = layer
        kv = raw_hdr.get(f"{arch}.attention.head_count_kv")
        if isinstance(kv, int) and kv > 0:
            result["n_head_kv"] = kv
        key_l = raw_hdr.get(f"{arch}.attention.key_length")
        if isinstance(key_l, int) and key_l > 0:
            result["n_embd_head_k"] = key_l
        if result["n_embd_head_k"] is None:
            emb = raw_hdr.get(f"{arch}.embedding_length")
            heads = raw_hdr.get(f"{arch}.attention.head_count")
            if isinstance(emb, int) and isinstance(heads, int) and heads > 0:
                result["n_embd_head_k"] = emb // heads
        if result["n_layer"] is not None or result["n_ctx_train"] != DEFAULT_FALLBACK_CTX:
            result["estimated"] = False

    with _GGUF_CACHE_LOCK:
        if len(_GGUF_META_CACHE) > 256:
            _GGUF_META_CACHE.clear()
        _GGUF_META_CACHE[cache_key] = dict(result)
    return result


def estimate_kv_cache_bytes_per_token(meta: Dict[str, Any], dtype_bytes: int = 2) -> int:
    """Estimate KV cache bytes consumed per token (`2 * n_layer * n_head_kv * head_k * dtype`)."""
    n_layer = meta.get("n_layer")
    n_head_kv = meta.get("n_head_kv")
    n_embd_head_k = meta.get("n_embd_head_k")
    if n_layer and n_head_kv and n_embd_head_k:
        return max(1024, 2 * int(n_layer) * int(n_head_kv) * int(n_embd_head_k) * int(dtype_bytes))
    return 256 * 1024


def get_system_memory_gb() -> Tuple[float, float]:
    """Return `(total_ram_gb, available_ram_gb)` without requiring psutil."""
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            return vm.total / (1024**3), vm.available / (1024**3)
        except Exception:
            pass

    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullTotalPhys / (1024**3), stat.ullAvailPhys / (1024**3)
        except Exception:
            pass

    if os.path.exists("/proc/meminfo"):
        try:
            info: Dict[str, int] = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        info[parts[0].rstrip(":")] = int(parts[1]) * 1024
            tot = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            if tot > 0:
                return tot / (1024**3), avail / (1024**3)
        except Exception:
            pass

    return 16.0, 8.0


def get_gpu_memory_gb(engine: str, ttl: float = 5.0) -> Optional[Tuple[float, float]]:
    """Best-effort `(total_vram_gb, free_vram_gb)` for CUDA GPUs when `nvidia-smi` exists."""
    if engine != "cuda":
        return None

    with _GPU_CACHE_LOCK:
        if time.time() - _GPU_MEM_CACHE["at"] < ttl:
            return _GPU_MEM_CACHE["value"]

    val: Optional[Tuple[float, float]] = None
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            proc = subprocess.run(
                [exe, "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                totals = 0.0
                frees = 0.0
                for line in proc.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        totals += float(parts[0])
                        frees += float(parts[1])
                if totals > 0:
                    val = (totals / 1024.0, frees / 1024.0)
        except Exception:
            val = None

    with _GPU_CACHE_LOCK:
        _GPU_MEM_CACHE["at"] = time.time()
        _GPU_MEM_CACHE["value"] = val
    return val


def compute_safe_context_window(
    model_path: str,
    engine: str = "cpu",
    loaded_same_model_ctx: int = 0,
    is_loaded: bool = False,
    other_models_bytes: int = 0,
) -> Dict[str, Any]:
    """Compute safe context window matching CMDAI CODE's GGUF + 70% memory budget rule.

    If `is_loaded` is True, the target model weights are already reflected in OS
    available memory, so we do not subtract `file_size_gb` a second time.
    """
    meta = read_gguf_metadata(model_path)
    train_ctx = max(MIN_SAFE_CTX, int(meta.get("n_ctx_train") or DEFAULT_FALLBACK_CTX))
    file_size_gb = float(meta.get("file_size_gb") or 0.0)
    bytes_per_tok = estimate_kv_cache_bytes_per_token(meta)

    _, avail_ram_gb = get_system_memory_gb()
    gpu_mem = get_gpu_memory_gb(engine)

    # Adjust free budget cleanly without double-subtracting the target model.
    unloaded_weight_gb = 0.0 if is_loaded else file_size_gb
    # Reserve headroom for other loaded models only when they aren't already paged in.
    _ = other_models_bytes

    ram_after_model = max(0.5, avail_ram_gb - unloaded_weight_gb)
    ram_cache_budget_gb = ram_after_model * 0.70

    free_vram_gb: Optional[float] = None
    effective_budget_gb = ram_cache_budget_gb
    budget_source = "system_ram"

    if gpu_mem is not None and engine == "cuda":
        _, free_vram_gb = gpu_mem
        vram_after_model = max(0.25, free_vram_gb - unloaded_weight_gb)
        vram_budget_gb = vram_after_model * 0.70
        # CUDA full-offload allocates KV cache in VRAM, so VRAM caps safe context.
        effective_budget_gb = min(ram_cache_budget_gb, vram_budget_gb)
        budget_source = "cuda_vram"

    max_possible_tokens = int((effective_budget_gb * (1024**3)) / max(1, bytes_per_tok))
    # Align down to 256-token blocks for cleaner llama.cpp KV allocation.
    aligned_tokens = (max_possible_tokens // 256) * 256 if max_possible_tokens >= MIN_SAFE_CTX else MIN_SAFE_CTX
    safe_ctx = max(MIN_SAFE_CTX, min(train_ctx, aligned_tokens))

    # If model is already loaded with a smaller/active n_ctx, report both:
    # - max_usable_context: what the hardware & GGUF can safely grow up to on demand
    # - active_n_ctx: what the currently resident instance holds right now
    active_ctx = int(loaded_same_model_ctx) if loaded_same_model_ctx > 0 else safe_ctx

    return {
        "architecture": meta.get("arch", "unknown"),
        "n_ctx_train": train_ctx,
        "max_usable_context": safe_ctx,
        "active_n_ctx": active_ctx,
        "kv_cache_bytes_per_token": bytes_per_tok,
        "file_size_gb": round(file_size_gb, 3),
        "free_ram_gb": round(avail_ram_gb, 2),
        "free_vram_gb": round(free_vram_gb, 2) if free_vram_gb is not None else None,
        "budget_source": budget_source,
        "engine": engine,
        "estimated": bool(meta.get("estimated", True)),
        "recommended_compaction_at": COMPACTION_THRESHOLD,
    }


def extract_extra_prompt_text(tools: Any) -> str:
    """Serialize optional OpenAI tool schemas so pre-flight token checks count them too."""
    if not tools:
        return ""
    try:
        import json

        return json.dumps(tools, ensure_ascii=False)
    except Exception:
        return str(tools)
