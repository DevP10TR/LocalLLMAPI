from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time
import os
import socket

from backend.model_manager import get_available_models, get_model_path
from backend.db_manager import (
    init_db,
    add_log,
    get_logs_for_key,
    create_api_key,
    get_api_keys_stats,
    get_api_key_by_value,
    get_engine_for_key,
    update_api_key,
    get_slot_devices,
    update_slot_device,
)
import asyncio
from dataclasses import dataclass, field

# Słownik do zapamiętywania wymaganego okna kontekstu dla każdego modelu (nawet po unloadzie)
model_n_ctx_prefs: Dict[str, int] = {}

# Inicjalizacja bazy logów na starcie
init_db()

app = FastAPI(title="Local LLM Router API")
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class LoadedModel:
    slot_index: int
    engine: str
    llama_instance: object
    refcount: int = 0
    last_used: float = 0.0
    n_ctx: int = 8192


loaded_models: dict[str, LoadedModel] = {}  # model_name -> LoadedModel
models_lock = asyncio.Lock()


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_engine_layers(engine: str) -> int:
    if engine == "cpu":
        return 0
    elif engine == "cuda":
        return -1
    else:  # vulkan
        return -1


async def load_model(model_name: str, requested_engine: str):
    global loaded_models

    async with models_lock:
        # Already loaded?
        if model_name in loaded_models:
            lm = loaded_models[model_name]
            lm.refcount += 1
            lm.last_used = time.time()
            print(f"[Model] Re-użycie {model_name} (refcount={lm.refcount})")
            return lm.llama_instance

    # Not loaded — find or free a slot
    slot_devices = get_slot_devices()

    # Find a matching slot by engine
    def find_free_slot():
        for idx in range(1, 4):
            dev = slot_devices.get(idx, "cpu")
            # Check if any model already uses this slot
            slot_busy = any(lm.slot_index == idx for lm in loaded_models.values())
            if dev == requested_engine and not slot_busy:
                return idx
        return None

    slot_idx = find_free_slot()

    # No free slot with matching engine — evict LRU with refcount==0
    if slot_idx is None:
        # Try to find a slot where the engine matches, but model can be evicted
        candidates = []
        for model_name_candidate, lm_candidate in list(loaded_models.items()):
            dev = slot_devices.get(lm_candidate.slot_index, "cpu")
            if dev == requested_engine and lm_candidate.refcount == 0:
                candidates.append(
                    (
                        lm_candidate.last_used,
                        model_name_candidate,
                        lm_candidate.slot_index,
                    )
                )
        if candidates:
            candidates.sort()
            _, evict_model, slot_idx = candidates[0]
            print(f"[Model] LRU eviction: {evict_model} ze slotu {slot_idx}")
            await _unload_model_internal(evict_model)
        else:
            # Try ANY slot with refcount==0 regardless of engine
            for model_name_candidate, lm_candidate in list(loaded_models.items()):
                if lm_candidate.refcount == 0:
                    candidates.append(
                        (
                            lm_candidate.last_used,
                            model_name_candidate,
                            lm_candidate.slot_index,
                        )
                    )
            if candidates:
                candidates.sort()
                _, evict_model, slot_idx = candidates[0]
                print(f"[Model] LRU eviction (any slot): {evict_model}")
                await _unload_model_internal(evict_model)
            else:
                raise HTTPException(
                    status_code=503,
                    detail="Wszystkie sloty są zajęte przez aktywne requesty. Spróbuj później.",
                )

    try:
        from llama_cpp import Llama
    except ImportError:
        raise HTTPException(
            status_code=500, detail="llama-cpp-python nie jest zainstalowane."
        )

    model_path = get_model_path(model_name)
    print(
        f"[Model] Ładowanie {model_name} do slotu {slot_idx} ({requested_engine}): {model_path}"
    )

    layers = _get_engine_layers(requested_engine)
    n_ctx_val = model_n_ctx_prefs.get(model_name, 8192)
    llama_instance = Llama(
        model_path=model_path, n_gpu_layers=layers, n_ctx=n_ctx_val, verbose=False
    )

    async with models_lock:
        loaded_models[model_name] = LoadedModel(
            slot_index=slot_idx,
            engine=requested_engine,
            llama_instance=llama_instance,
            refcount=1,
            last_used=time.time(),
            n_ctx=n_ctx_val,
        )

    return llama_instance


async def release_model(model_name: str):
    async with models_lock:
        if model_name in loaded_models:
            loaded_models[model_name].refcount -= 1
            loaded_models[model_name].last_used = time.time()
            print(
                f"[Model] Release {model_name} (refcount={loaded_models[model_name].refcount})"
            )


async def _unload_model_internal(model_name: str):
    async with models_lock:
        if model_name not in loaded_models:
            return
        lm = loaded_models[model_name]
        if lm.refcount > 0:
            print(f"[Model] Nie można zwolnić {model_name} — refcount={lm.refcount}")
            return
        print(f"[Model] Zwalnianie {model_name} ze slotu {lm.slot_index}")
        try:
            lm.llama_instance.close()
        except Exception:
            pass
        del loaded_models[model_name]
        import gc

        gc.collect()


class ChatCompletionRequest(BaseModel):
    model_config = {"extra": "allow"}
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096
    stream: Optional[bool] = False


def get_current_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    key_val = credentials.credentials
    key_id = get_api_key_by_value(key_val)
    if not key_id:
        raise HTTPException(
            status_code=401,
            detail="Nieprawidłowy klucz API. Upewnij się, że utworzyłeś go w panelu.",
        )
    return key_id


background_tasks = set()


@app.on_event("startup")
async def startup_event():
    task = asyncio.create_task(auto_unload_model())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def auto_unload_model():
    global loaded_models
    while True:
        await asyncio.sleep(10)
        async with models_lock:
            now = time.time()
            for model_name, lm in list(loaded_models.items()):
                if lm.refcount == 0 and now - lm.last_used > 120:
                    print(
                        f"\n[Auto-Unload] Zwalnianie modelu z pamięci (bezczynność > 2 min): {model_name}"
                    )
                    try:
                        lm.llama_instance.close()
                    except Exception:
                        pass
                    del loaded_models[model_name]
                    import gc

                    gc.collect()


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest, api_key_id: int = Depends(get_current_api_key)
):
    try:
        if not request.model:
            raise HTTPException(status_code=400, detail="Brak pola 'model'.")

        api_engine = get_engine_for_key(api_key_id)
        start_time = time.time()
        llm = await load_model(request.model, api_engine)

        try:
            extra_kwargs = request.model_extra or {}
            import inspect

            supported_kwargs = inspect.signature(
                llm.create_chat_completion
            ).parameters.keys()
            filtered_kwargs = {
                k: v for k, v in extra_kwargs.items() if k in supported_kwargs
            }

            import tiktoken

            try:
                enc = tiktoken.get_encoding("cl100k_base")
                calculated_prompt_tokens = 0
                for m in request.messages:
                    content = m.get("content", "")
                    if isinstance(content, str):
                        calculated_prompt_tokens += len(enc.encode(content))
                calculated_prompt_tokens += len(request.messages) * 4 + 2
            except Exception:
                calculated_prompt_tokens = 0

            # Wymuszamy stream internally, by mierzyć prędkość każdego tokena
            chunks = llm.create_chat_completion(
                model=request.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
                **filtered_kwargs,
            )

            if request.stream:
                _loop = asyncio.get_running_loop()

                def stream_generator():
                    full_content = ""
                    chunk_times = []
                    gen_start = time.time()
                    last_t = gen_start
                    prompt_t = None
                    completion_tokens = 0

                    try:
                        for chunk in chunks:
                            delta_content = chunk["choices"][0]["delta"].get(
                                "content", ""
                            )

                            import json

                            chunk["object"] = "chat.completion.chunk"
                            yield f"data: {json.dumps(chunk)}\n\n"

                            if not delta_content:
                                continue

                            now = time.time()
                            delta = now - last_t
                            completion_tokens += 1
                            if prompt_t is None:
                                prompt_t = delta
                            elif delta > 0:
                                chunk_times.append(1.0 / delta)
                            last_t = now
                            full_content += delta_content
                    except (OSError, ValueError) as e:
                        error_msg = str(e)
                        print(f"[OSTrzeżenie] Błąd w stream_generator: {error_msg}")
                        if "context window" in error_msg:
                            asyncio.run_coroutine_threadsafe(_handle_context_overflow(request.model), _loop)
                            # Send error to client so it doesn't see an empty response
                            import json as _json
                            error_chunk = {
                                "error": {
                                    "message": error_msg,
                                    "type": "context_length_exceeded",
                                    "code": "context_length_exceeded"
                                }
                            }
                            yield f"data: {_json.dumps(error_chunk)}\n\n"

                    end_time = time.time()
                    elapsed = end_time - start_time
                    min_tps = min(chunk_times) if chunk_times else 0
                    max_tps = max(chunk_times) if chunk_times else 0
                    avg_tps = (
                        completion_tokens / (elapsed - prompt_t)
                        if prompt_t and elapsed > prompt_t
                        else 0
                    )
                    ttft = round(prompt_t, 3) if prompt_t else 0.0

                    total_tokens = completion_tokens + calculated_prompt_tokens
                    add_log(
                        api_key_id,
                        request.model,
                        round(elapsed, 2),
                        total_tokens,
                        round(avg_tps, 2),
                        round(min_tps, 2),
                        round(max_tps, 2),
                        ttft,
                    )
                    asyncio.run_coroutine_threadsafe(release_model(request.model), _loop)

                    yield "data: [DONE]\n\n"

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )
            else:
                full_content = ""
                chunk_times = []
                gen_start = time.time()
                last_t = gen_start
                prompt_t = None
                completion_tokens = 0

                try:
                    for chunk in chunks:
                        delta_content = chunk["choices"][0]["delta"].get("content", "")
                        if not delta_content:
                            continue

                        now = time.time()
                        delta = now - last_t
                        completion_tokens += 1
                        if prompt_t is None:
                            prompt_t = delta
                        elif delta > 0:
                            chunk_times.append(1.0 / delta)
                        last_t = now
                        full_content += delta_content
                except (OSError, ValueError) as e:
                    print(f"[OSTrzeżenie] Błąd w non-streaming: {e}")
                    if "context window" in str(e):
                        asyncio.get_event_loop().create_task(
                            _handle_context_overflow(request.model)
                        )

                end_time = time.time()
                elapsed = end_time - start_time

                total_tokens = completion_tokens + calculated_prompt_tokens

                min_tps = min(chunk_times) if chunk_times else 0
                max_tps = max(chunk_times) if chunk_times else 0
                avg_tps = (
                    completion_tokens / (elapsed - prompt_t)
                    if prompt_t and elapsed > prompt_t
                    else 0
                )
                ttft = round(prompt_t, 3) if prompt_t else 0.0

                add_log(
                    api_key_id,
                    request.model,
                    round(elapsed, 2),
                    total_tokens,
                    round(avg_tps, 2),
                    round(min_tps, 2),
                    round(max_tps, 2),
                    ttft,
                )
                await release_model(request.model)

                return {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": full_content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": calculated_prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                }
        except Exception:
            await release_model(request.model)
            raise
    except Exception as e:
        import traceback

        err_str = str(e).lower()
        with open("error.txt", "w") as f:
            f.write(f"{str(e)}\n{traceback.format_exc()}")

        friendly_error = "Wystąpił nieoczekiwany błąd serwera."
        if (
            "memory" in err_str
            or "vram" in err_str
            or "allocation" in err_str
            or isinstance(e, MemoryError)
        ):
            friendly_error = (
                "Błąd API: Przepełnienie VRAM (Zbyt duży model lub zbyt mało pamięci)."
            )
        elif (
            "not found" in err_str
            or "no such file" in err_str
            or isinstance(e, FileNotFoundError)
        ):
            friendly_error = (
                "Błąd API: Nie znaleziono pliku modelu na dysku (Sprawdź ścieżkę)."
            )
        elif "json" in err_str or "parse" in err_str:
            friendly_error = "Błąd API: Problem z parsowaniem danych wejściowych."
        else:
            friendly_error = f"Błąd API: {str(e)[:100]}..."

        raise HTTPException(status_code=500, detail=friendly_error)


@app.get("/v1/models")
async def list_models():
    models = get_available_models()
    return {"object": "list", "data": [{"id": m, "object": "model"} for m in models]}


class CreateKeyRequest(BaseModel):
    name: str
    api_key: str
    engine: Optional[str] = "vulkan"


@app.post("/api/keys")
async def create_new_key(req: CreateKeyRequest):
    if not req.name or not req.api_key:
        raise HTTPException(
            status_code=400, detail="Pola 'name' i 'api_key' są wymagane."
        )
    try:
        key_id = create_api_key(req.name, req.api_key, req.engine)
        return {
            "id": key_id,
            "name": req.name,
            "api_key": req.api_key,
            "engine": req.engine,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/keys")
async def get_keys():
    return get_api_keys_stats()


class UpdateKeyRequest(BaseModel):
    name: str
    api_key: Optional[str] = None
    engine: Optional[str] = "vulkan"


@app.put("/api/keys/{api_key_id}")
async def update_key(api_key_id: int, req: UpdateKeyRequest):
    if not req.name:
        raise HTTPException(status_code=400, detail="Nazwa jest wymagana.")
    update_api_key(api_key_id, req.name, req.api_key, req.engine)
    return {"status": "ok"}


@app.delete("/api/keys/{api_key_id}")
async def delete_key(api_key_id: int):
    from backend.db_manager import delete_api_key

    delete_api_key(api_key_id)
    return {"status": "ok"}


@app.get("/api/logs/{api_key_id}")
async def get_logs(api_key_id: int):
    return get_logs_for_key(api_key_id, limit=200)


async def _handle_context_overflow(model_name: str):
    global model_n_ctx_prefs
    async with models_lock:
        if model_name not in loaded_models:
            return
        lm = loaded_models[model_name]
        new_ctx = min(lm.n_ctx + 2000, 131072)
        model_n_ctx_prefs[model_name] = new_ctx
        print(f"[Model] Zwiększono n_ctx dla {model_name} do {new_ctx}")
        # Force refcount to 0 so unload can proceed (stream already failed)
        lm.refcount = 0
    # Unload so next request reloads with bigger context
    await _unload_model_internal(model_name)


@app.post("/api/unload")
async def unload_model(model_name: Optional[str] = None):
    global loaded_models
    if model_name:
        if model_name in loaded_models:
            await _unload_model_internal(model_name)
            return {"status": "ok", "message": f"Model {model_name} zwolniony"}
        return {"status": "ok", "message": f"Model {model_name} nie jest załadowany"}
    # Unload all
    async with models_lock:
        for name in list(loaded_models.keys()):
            if loaded_models[name].refcount == 0:
                try:
                    loaded_models[name].llama_instance.close()
                except Exception:
                    pass
                del loaded_models[name]
        import gc

        gc.collect()
    return {"status": "ok", "message": "Wszystkie nieużywane modele zwolnione"}


@app.get("/api/status")
async def get_status():
    slots_info = {}
    for name, lm in list(loaded_models.items()):
        slots_info[name] = {
            "slot": lm.slot_index,
            "engine": lm.engine,
            "refcount": lm.refcount,
            "last_used": lm.last_used,
            "n_ctx": lm.n_ctx,
        }
    return {
        "loaded_models": slots_info,
        "local_ip": get_local_ip(),
        "active_model": list(loaded_models.keys())[0] if loaded_models else None,
    }


@app.get("/api/settings/slots")
async def get_slots():
    devices = get_slot_devices()
    result = {}
    for idx in range(1, 4):
        dev = devices.get(idx, "cpu")
        # Find what model is loaded in this slot
        loaded_model = None
        for name, lm in loaded_models.items():
            if lm.slot_index == idx:
                loaded_model = name
                break
        result[str(idx)] = {
            "device": dev,
            "loaded_model": loaded_model,
        }
    return result


class SlotUpdateRequest(BaseModel):
    slot_index: int
    device: str


@app.put("/api/settings/slots")
async def update_slot(req: SlotUpdateRequest):
    if req.slot_index < 1 or req.slot_index > 3:
        raise HTTPException(status_code=400, detail="Slot index must be 1, 2, or 3")
    if req.device not in ("cpu", "cuda", "vulkan"):
        raise HTTPException(
            status_code=400, detail="Device must be 'cpu', 'cuda', or 'vulkan'"
        )
    update_slot_device(req.slot_index, req.device)
    return {"status": "ok"}


web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
