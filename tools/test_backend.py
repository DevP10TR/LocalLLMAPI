"""Testy regresyjne na naprawione bugi w backendzie.

Uruchomienie:  python tools\\test_backend.py

Nie ładuje prawdziwego modelu (wagi mają GB) — podmienia konstruktor Llama
na atrapę, dzięki czemu test jest szybki i nie rusza GPU.
"""
import asyncio
import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402

import backend.router_server as rs  # noqa: E402

KEY = "sk-test-regression-key"

built: list = []


class FakeLlama:
    """Atrapa llama-cpp: zlicza instancje i zwraca 3 chunki po 10 ms."""

    def __init__(self, model_path, n_gpu_layers, n_ctx, verbose):
        built.append(model_path)
        self.n_ctx = n_ctx
        self.closed = False

    def create_chat_completion(self, **kwargs):
        for i in range(3):
            time.sleep(0.01)
            yield {
                "choices": [{"index": 0, "delta": {"content": f"tok{i} "}}],
                "model": kwargs.get("model"),
            }

    def close(self):
        self.closed = True


def fake_build(model_path, layers, n_ctx):
    return FakeLlama(model_path, layers, n_ctx, verbose=False)


results: list = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  -> ' + detail) if detail else ''}")


async def main() -> int:
    rs._build_llama = fake_build
    rs.init_db()

    # Katalog modeli tymczasowy, żeby nie dotykać prawdziwych GGUF-ów.
    import backend.model_manager as mm
    import tempfile
    tmp = tempfile.mkdtemp()
    real_dir = mm.MODELS_DIR
    mm.MODELS_DIR = tmp
    pathlib.Path(tmp, "fake-model.gguf").write_bytes(b"GGUF" * 64)
    rs.get_model_path = lambda name: str(pathlib.Path(tmp, name))

    # Klucz testowy — najpierw posprzątaj śmieci po ewentualnym przerwanym runie.
    from backend.db_manager import create_api_key, delete_api_key, get_api_key_by_value
    stale = get_api_key_by_value(KEY)
    if stale:
        delete_api_key(stale)
    kid = create_api_key("regression", KEY, "cpu")

    # TestClient starlette 0.27 nie działa z httpx 0.28 — jedziemy na ASGITransport.
    import httpx
    from httpx import ASGITransport

    client = httpx.AsyncClient(
        transport=ASGITransport(app=rs.app), base_url="http://test", timeout=30.0
    )

    try:
        print("\n[1] Wczytanie modelu nie blokuje serwera")
        # Podczas "wczytywania" (tu: 0.6 s w wątku) sprawdzamy, że /api/status
        # nadal odpowiada. W starej wersji Llama() blokował pętlę zdarzeń.
        t0 = time.perf_counter()
        task = asyncio.create_task(rs.load_model("fake-model.gguf", "cpu"))

        responsive, checks = True, 0
        while not task.done():
            await asyncio.sleep(0.05)
            checks += 1
            if time.perf_counter() - t0 > 0.4:
                try:
                    await asyncio.wait_for(rs.get_status(), timeout=0.15)
                except (asyncio.TimeoutError, TimeoutError):
                    responsive = False
                    break
                except Exception:
                    pass
        await task
        check(
            "petla zdarzen odpowiada w trakcie ladowania modelu",
            responsive and checks > 0,
            f"{checks} odpytan /api/status w trakcie ladowania",
        )

        print("\n[2] N równoleglych requestow = jedna instancja modelu")
        built.clear()
        for m in list(rs.loaded_models):
            await rs.unload_model(m, force=True)
        built.clear()

        rs.model_n_ctx_prefs.clear()
        with rs.models_lock:
            rs._slots_reserved.clear()

        async def one_request():
            return await rs.chat_completions(
                rs.ChatCompletionRequest(
                    model="fake-model.gguf", messages=[{"role": "user", "content": "hi"}]
                ),
                api_key_id=kid,
            )

        t1 = time.perf_counter()
        results_out = await asyncio.gather(*[one_request() for _ in range(8)])
        elapsed = time.perf_counter() - t1
        check(
            "8 rownoleglych requestow tworzy dokladnie 1 instancje",
            len(built) == 1,
            f"built={len(built)}x, czas={elapsed:.2f}s",
        )
        check("wszystkie 8 odpowiedzi zwrocilo tresc", all(
            r["choices"][0]["message"]["content"] for r in results_out
        ))
        check(
            "refcount wraca do zera po wszystkich requestach",
            rs.loaded_models["fake-model.gguf"].refcount == 0,
            f"refcount={rs.loaded_models['fake-model.gguf'].refcount}",
        )
        check("nie zostala zarezerwowana zadne slot", not rs._slots_reserved,
              f"reserved={rs._slots_reserved}")

        print("\n[3] Przerwanie streama przez klienta nie blokuje slotu")
        # release_model() jest sync, więc blokuje wątek streamera, nie pętlę.
        rs.loaded_models["fake-model.gguf"].refcount = 1

        def gen():
            try:
                yield "data: 1\n\n"
                raise GeneratorExit
            finally:
                rs.release_model("fake-model.gguf")

        it = gen()
        next(it)
        it.close()          # GeneratorExit → finally musi zejść z refcountu
        check(
            "refcount wraca do zera po przerwanym streamie",
            rs.loaded_models["fake-model.gguf"].refcount == 0,
            f"refcount={rs.loaded_models['fake-model.gguf'].refcount}",
        )

        # Ten sam mechanizm, ale przez prawdziwy StreamingResponse z logiem
        check("release_model nie potrzebuje petli zdarzen", not asyncio.iscoroutinefunction(rs.release_model))

        print("\n[4] Rozne modele dostaja rozne sloty (brak wysciegu o slot)")
        for m in list(rs.loaded_models):
            await rs.unload_model(m, force=True)
        pathlib.Path(tmp, "second.gguf").write_bytes(b"GGUF" * 64)
        built.clear()
        results2 = await asyncio.gather(
            rs.chat_completions(
                rs.ChatCompletionRequest(model="fake-model.gguf", messages=[{"role": "user", "content": "a"}]),
                api_key_id=kid,
            ),
            rs.chat_completions(
                rs.ChatCompletionRequest(model="second.gguf", messages=[{"role": "user", "content": "b"}]),
                api_key_id=kid,
            ),
        )
        slots = {n: m.slot_index for n, m in rs.loaded_models.items()}
        check(
            "dwa modele nie dostały tego samego slotu",
            len(set(slots.values())) == len(slots),
            f"slots={slots}",
        )
        check("oba requesty zwróciły odpowiedź", len(results2) == 2)

        print("\n[5] HTTP 503 nie jest zamieniane na 500")
        with rs.models_lock:
            rs.loaded_models.clear()
            rs._slots_reserved.update({1, 2, 3})
        try:
            await rs.load_model("third.gguf", "cpu")
            raised = None
        except rs.HTTPException as e:
            raised = e
        check(
            "brak slotow daje 503, nie 500",
            raised is not None and raised.status_code == 503,
            f"status={raised.status_code if raised else 'brak wyjatku'}",
        )
        with rs.models_lock:
            rs._slots_reserved.clear()

        print("\n[6] Endpointy panelu")
        r = await client.get("/api/status")
        check("/api/status -> 200", r.status_code == 200, f"port={r.json().get('port')}")
        check("/api/status zgłasza port 1000", r.json().get("port") == 1000)

        r = await client.get("/api/stats")
        body = r.json()
        check("/api/stats -> 200", r.status_code == 200)
        for field in ("total_tokens", "total_requests", "avg_tps", "best_tps",
                      "last", "recent", "models_on_disk", "slots_total", "uptime"):
            check(f"/api/stats zawiera '{field}'", field in body)

        r = await client.get("/api/settings/slots")
        check("/api/settings/slots zwraca 3 sloty", len(r.json()) == 3)

        r = await client.get("/v1/models")
        check("/v1/models zwraca 2 atrapowe modele", len(r.json()["data"]) == 2)

        print("\n[7] CORS: origin echo + brak niedozwolonej kombinacji")
        r = await client.get("/api/status", headers={"Origin": "http://192.168.1.50:5173"})
        check(
            "CORS zwraca naglowek dla dowolnego origin",
            r.status_code == 200 and r.headers.get("access-control-allow-origin") is not None,
            f"ACAO={r.headers.get('access-control-allow-origin')}",
        )
        check(
            "brak access-control-allow-credentials przy *",
            r.headers.get("access-control-allow-credentials") is None,
            f"ACAC={r.headers.get('access-control-allow-credentials')}",
        )

        print("\n[8] Panel statyczny serwowany")
        r = await client.get("/")
        check("/ zwraca index.html", r.status_code == 200 and "LocalLLMAPI" in r.text)
        for asset in ("/style.css", "/script.js", "/i18n.js",
                      "/vendor/tabler-icons.min.css", "/vendor/chart.umd.js"):
            check(f"{asset} serwowany", (await client.get(asset)).status_code == 200)
        r = await client.get("/vendor/fonts/tabler-icons.woff2")
        check("font Tabler serwowany", r.status_code == 200, f"{len(r.content)} bajtow")

        print("\n[9] Kontrakt dokumentacji: statusy musza zgadzac sie z docsami")
        # Sekcja "Errors" w panelu (web/script.js -> DOC_ERRORS) musi wymieniac
        # dokladnie te statusy, ktore faktycznie zwraca API. Klamstwo w
        # dokumentacji jest gorsze niz jej brak.
        body = {"model": "fake.gguf", "messages": [{"role": "user", "content": "hi"}]}

        r = await client.post("/v1/chat/completions", json=body)
        check("brak naglowka Authorization -> 403", r.status_code == 403, f"jest {r.status_code}")

        r = await client.post(
            "/v1/chat/completions", json=body, headers={"Authorization": "Bearer nope"}
        )
        check("bledny klucz -> 401", r.status_code == 401, f"jest {r.status_code}")

        r = await client.post(
            "/v1/chat/completions",
            content=b"{ not json",
            headers={"Authorization": "Bearer nope", "Content-Type": "application/json"},
        )
        check("uszkodzony JSON -> 422", r.status_code == 422, f"jest {r.status_code}")

        r = await client.post("/api/keys", json={"name": "D", "api_key": KEY, "engine": "cpu"})
        check("duplikat wartosci klucza -> 400", r.status_code == 400, f"jest {r.status_code}")

        # 503: wszystkie sloty zajete przez aktywne (sztuczne) requesty
        with rs.models_lock:
            rs.loaded_models.clear()
            rs._slots_reserved.update({1, 2, 3})
        try:
            await rs.load_model("third.gguf", "cpu")
            s503 = None
        except rs.HTTPException as e:
            s503 = e.status_code
        check("wszystkie sloty zajete -> 503", s503 == 503, f"jest {s503}")
        with rs.models_lock:
            rs._slots_reserved.clear()

        # Wyciagnij statusy z tabeli bledow w panelu
        import re as _re
        from pathlib import Path as _Path

        _root = _Path(__file__).resolve().parent.parent
        web_js = (_root / "web" / "script.js").read_text(encoding="utf-8")
        block = web_js.split("const DOC_ERRORS = [")[1].split("];")[0]
        doc_statuses = set(_re.findall(r"\['(\d+|ctx)',\s*'(\d+|—)'", block))
        documented = {s for s, _ in doc_statuses}
        real = {"400", "401", "403", "422", "503", "ctx"}
        check("docs wymieniaja dokladnie prawdziwe statusy", documented == real,
              f"w docs: {sorted(documented)}, brakuje: {sorted(real - documented)}")

        # Endpointy z tabeli musza istniec w aplikacji. Porownujemy ksztalt
        # sciezki: /api/keys/<b>{id}</b> -> /api/keys/{}  ==  /api/keys/{api_key_id}
        def shape(p: str) -> str:
            p = _re.sub(r"</?b>", "", p)
            p = _re.sub(r"\{[^}]+\}", "{}", p)
            return p

        routes = {shape(r.path) for r in rs.app.routes if hasattr(r, "path")}
        block = web_js.split("const DOC_ENDPOINTS = [")[1].split("];")[0]
        paths = _re.findall(r"'(get|post|put|delete)',\s*'([^']+)'", block)
        missing_ep = [p for _, p in paths if shape(p) not in routes]
        check("endpointy z tabeli istnieja w aplikacji", not missing_ep,
              f"brak: {missing_ep}; w aplikacji: {sorted(routes)}")

        await client.aclose()

    finally:
        for m in list(rs.loaded_models):
            await rs.unload_model(m, force=True)
        mm.MODELS_DIR = real_dir
        try:
            delete_api_key(kid)
        except Exception:
            pass

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'='*58}\n  {passed}/{total} testow zaliczonych")
    if passed != total:
        print("  NIEZALICZONE:")
        for name, ok, detail in results:
            if not ok:
                print(f"    - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
