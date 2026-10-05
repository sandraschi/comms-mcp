"""Local + cloud LLM provider surface for the comms console.

Per WEBAPP_SOTA_STANDARDS.md §VI (Local Intelligence) and the vendored contract
in `templates/llm/INTEGRATION.md`: the browser never talks to a provider
directly; every chat call goes through this backend proxy, so keys stay
server-side and Tauri/CORS keep working.

Vendored helpers: `llm_detect.py` (GPU/model tiers), `llm_engine.py` (resident
switch/evict). Endpoints:
  GET  /api/llm/providers          -> local probes + cloud configured flags
  GET  /api/llm/models?provider=   -> {models, source}
  POST /api/llm/test               -> validate a provider/key without saving
  POST /api/llm/chat               -> one-shot completion {content}
  POST /api/llm/chat/stream        -> SSE OpenAI-style data: chunks
  GET  /api/llm/gpus               -> per-GPU VRAM (nvidia-smi)
  GET  /api/llm/onboarding         -> starter facts + recommendation
  GET  /api/settings/llm           -> active pair + keys_configured flags
  POST /api/settings/llm           -> save key (write-only) / active pair
  DELETE /api/settings/llm/key     -> remove a stored key
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, StreamingResponse

from . import llm_detect, llm_engine

logger = logging.getLogger("comms_mcp.llm")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_KEYS_PATH = _REPO_ROOT / "data" / "llm_keys.json"
_PROBE_TIMEOUT = 3.0
_CHAT_TIMEOUT = 300.0
_NUM_CTX = 32768  # cap Ollama KV; long ctx offloads to CPU (INTEGRATION.md)

# base_url MUST be 127.0.0.1, never localhost (INTEGRATION.md §Localhost trap).
LOCAL_PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "label": "Ollama",
        "kind": "local",
        "base_url": "http://127.0.0.1:11434",
        "shape": "ollama",
    },
    "lmstudio": {
        "label": "LM Studio",
        "kind": "local",
        "base_url": "http://127.0.0.1:1234",
        "shape": "openai",
    },
    "vllm": {
        "label": "vLLM",
        "kind": "local",
        "base_url": "http://127.0.0.1:8000",
        "shape": "openai",
    },
}
CLOUD_PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "kind": "cloud",
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "shape": "openai",
    },
    "deepseek": {
        "label": "DeepSeek",
        "kind": "cloud",
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "shape": "openai",
    },
    "anthropic": {
        "label": "Anthropic",
        "kind": "cloud",
        "base_url": "https://api.anthropic.com/v1",
        "key_env": "ANTHROPIC_API_KEY",
        "shape": "anthropic",
    },
}
ALL_PROVIDERS: dict[str, dict[str, Any]] = {**LOCAL_PROVIDERS, **CLOUD_PROVIDERS}


def _read_keys() -> dict[str, str]:
    try:
        data = json.loads(_KEYS_PATH.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write_keys(keys: dict[str, str]) -> None:
    _KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _KEYS_PATH.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    try:  # 0600 where the OS honours it
        os.chmod(_KEYS_PATH, 0o600)
    except OSError:
        pass


def _key_for(provider: str, override: str | None = None) -> str:
    """Env wins over the file store (SPEC: never return key bytes to the client)."""
    if override:
        return override
    spec = ALL_PROVIDERS.get(provider, {})
    env_name = spec.get("key_env")
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return _read_keys().get(provider, "")


def _local_models_url(provider: str, base_url: str) -> str:
    spec = ALL_PROVIDERS[provider]
    if spec["shape"] == "ollama":
        return base_url.rstrip("/") + "/api/tags"
    return base_url.rstrip("/") + "/v1/models"


def _extract_models(provider: str, payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    if ALL_PROVIDERS[provider]["shape"] == "ollama":
        return [
            m["name"] for m in payload.get("models", []) if isinstance(m, dict) and m.get("name")
        ]
    return [m["id"] for m in payload.get("data", []) if isinstance(m, dict) and m.get("id")]


async def _fetch_models(
    provider: str, base_url: str, api_key: str = "", timeout: float = _PROBE_TIMEOUT
) -> tuple[bool, list[str], str]:
    """Return (ok, models, note). ok is True only for a live list."""
    spec = ALL_PROVIDERS[provider]
    url = _local_models_url(provider, base_url)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if spec["shape"] == "anthropic":
        url = base_url.rstrip("/") + "/models"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=headers)
            if r.status_code in (401, 403):
                return False, [], "key rejected"
            if r.status_code != 200:
                return False, [], f"HTTP {r.status_code}"
            return True, _extract_models(provider, r.json()), ""
    except httpx.HTTPError as exc:
        return False, [], str(exc)


# --------------------------------------------------------------------------- #
# Chat dispatch
# --------------------------------------------------------------------------- #
def _provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for m in messages:
        role = str(m.get("role", "user"))
        content = str(m.get("content", ""))
        if role in ("user", "assistant", "system") and content:
            out.append({"role": role, "content": content})
    return out or [{"role": "user", "content": "hello"}]


async def _complete(provider: str, model: str, messages: list[dict[str, Any]], api_key: str) -> str:
    spec = ALL_PROVIDERS.get(provider)
    if not spec:
        raise ValueError(f"unknown provider {provider}")
    base = spec["base_url"].rstrip("/")
    msgs = _provider_messages(messages)

    async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
        if spec["shape"] == "ollama":
            r = await client.post(
                base + "/api/chat",
                json={
                    "model": model,
                    "messages": msgs,
                    "stream": False,
                    "options": {"num_ctx": _NUM_CTX},
                },
            )
            r.raise_for_status()
            return str((r.json().get("message") or {}).get("content", ""))

        if spec["shape"] == "anthropic":
            r = await client.post(
                base + "/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                json={"model": model, "max_tokens": 2048, "messages": msgs},
            )
            r.raise_for_status()
            parts = r.json().get("content") or []
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

        r = await client.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            json={"model": model, "messages": msgs, "stream": False},
        )
        r.raise_for_status()
        return str((r.json().get("choices") or [{}])[0].get("message", {}).get("content", ""))


async def _stream(provider: str, model: str, messages: list[dict[str, Any]], api_key: str):
    """Yield OpenAI-style SSE `data:` chunks; always terminates with [DONE]."""
    spec = ALL_PROVIDERS.get(provider)
    if not spec:
        yield "data: " + json.dumps({"error": f"unknown provider {provider}"}) + "\n\n"
        yield "data: [DONE]\n\n"
        return
    base = spec["base_url"].rstrip("/")
    msgs = _provider_messages(messages)

    def chunk(text: str) -> str:
        return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n"

    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            if spec["shape"] == "ollama":
                async with client.stream(
                    "POST",
                    base + "/api/chat",
                    json={
                        "model": model,
                        "messages": msgs,
                        "stream": True,
                        "options": {"num_ctx": _NUM_CTX},
                    },
                ) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except ValueError:
                            continue
                        piece = (data.get("message") or {}).get("content", "")
                        if piece:
                            yield chunk(piece)
            elif spec["shape"] == "anthropic":
                async with client.stream(
                    "POST",
                    base + "/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    json={"model": model, "max_tokens": 2048, "messages": msgs, "stream": True},
                ) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            data = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        if data.get("type") == "content_block_delta":
                            piece = (data.get("delta") or {}).get("text", "")
                            if piece:
                                yield chunk(piece)
            else:
                async with client.stream(
                    "POST",
                    base + "/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                    json={"model": model, "messages": msgs, "stream": True},
                ) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            data = json.loads(payload)
                        except ValueError:
                            continue
                        piece = (data.get("choices") or [{}])[0].get("delta", {}).get("content", "")
                        if piece:
                            yield chunk(piece)
    except httpx.HTTPError as exc:
        yield "data: " + json.dumps({"error": str(exc)}) + "\n\n"
    yield "data: [DONE]\n\n"


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
def register_llm_routes(app: FastAPI) -> None:
    @app.get("/api/llm/providers")
    async def llm_providers():
        keys = _read_keys()
        providers: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            for pid, spec in LOCAL_PROVIDERS.items():
                ok, models, note = False, [], ""
                try:
                    r = await client.get(_local_models_url(pid, spec["base_url"]))
                    ok = r.status_code == 200
                    if ok:
                        models = _extract_models(pid, r.json())
                except httpx.HTTPError:
                    ok = False
                providers.append(
                    {
                        "id": pid,
                        "label": spec["label"],
                        "kind": "local",
                        "base_url": spec["base_url"],
                        "needs_key": False,
                        "key_env": None,
                        "configured": ok,
                        "detected": ok,
                        "models": models,
                        "note": note,
                    }
                )
        for pid, spec in CLOUD_PROVIDERS.items():
            key = _key_for(pid)
            if os.environ.get(spec["key_env"]):
                note = "key from env"
            elif keys.get(pid):
                note = "key stored"
            else:
                note = "no key"
            providers.append(
                {
                    "id": pid,
                    "label": spec["label"],
                    "kind": "cloud",
                    "base_url": spec["base_url"],
                    "needs_key": True,
                    "key_env": spec["key_env"],
                    "configured": bool(key),
                    "detected": bool(key),
                    "models": [],
                    "note": note,
                }
            )
        return {"providers": providers}

    @app.get("/api/llm/models")
    async def llm_models(provider: str = "ollama"):
        spec = ALL_PROVIDERS.get(provider)
        if not spec:
            return JSONResponse(
                {"models": [], "source": "curated", "note": "unknown provider"},
                status_code=404,
            )
        if spec["kind"] == "local":
            ok, models, note = await _fetch_models(provider, spec["base_url"])
            return {"models": models, "source": "live" if ok else "curated", "note": note}
        key = _key_for(provider)
        if not key:
            return {"models": [], "source": "curated", "key_missing": True, "note": "no key"}
        ok, models, note = await _fetch_models(provider, spec["base_url"], key, timeout=10.0)
        return {"models": models, "source": "live" if ok else "curated", "note": note}

    @app.post("/api/llm/test")
    async def llm_test(request: Request):
        body = await request.json()
        provider = str(body.get("provider", ""))
        spec = ALL_PROVIDERS.get(provider)
        if not spec:
            return JSONResponse({"ok": False, "note": "unknown provider"}, status_code=404)
        base = str(body.get("endpoint") or spec["base_url"])
        key = _key_for(provider, str(body.get("api_key") or "") or None)
        if spec["kind"] == "cloud" and not key:
            return {"ok": False, "source": "curated", "note": "no key"}
        ok, models, note = await _fetch_models(provider, base, key, timeout=10.0)
        return {"ok": ok, "models": models, "source": "live" if ok else "curated", "note": note}

    @app.post("/api/llm/chat")
    async def llm_chat(request: Request):
        body = await request.json()
        provider = str(body.get("provider", "ollama"))
        model = str(body.get("model", ""))
        if not model:
            return JSONResponse({"error": "model required"}, status_code=400)
        spec = ALL_PROVIDERS.get(provider)
        if not spec:
            return JSONResponse({"error": "unknown provider"}, status_code=404)
        key = _key_for(provider)
        if spec["kind"] == "cloud" and not key:
            return JSONResponse({"error": "no key"}, status_code=400)
        try:
            content = await _complete(provider, model, body.get("messages") or [], key)
        except (httpx.HTTPError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        return {"content": content}

    @app.post("/api/llm/chat/stream")
    async def llm_chat_stream(request: Request):
        body = await request.json()
        provider = str(body.get("provider", "ollama"))
        model = str(body.get("model", ""))
        if not model:
            return JSONResponse({"error": "model required"}, status_code=400)
        spec = ALL_PROVIDERS.get(provider)
        if not spec:
            return JSONResponse({"error": "unknown provider"}, status_code=404)
        key = _key_for(provider)
        if spec["kind"] == "cloud" and not key:
            return JSONResponse({"error": "no key"}, status_code=400)
        return StreamingResponse(
            _stream(provider, model, body.get("messages") or [], key),
            media_type="text/event-stream",
        )

    @app.get("/api/llm/gpus")
    async def llm_gpus():
        return {"gpus": llm_engine.gpu_vram()}

    @app.get("/api/llm/loaded")
    async def llm_loaded():
        return await llm_engine.ollama_loaded()

    @app.get("/api/llm/onboarding")
    async def llm_onboarding():
        result = llm_detect.detect()
        rec = llm_detect.recommend(result)
        keys = _read_keys()
        clouds_configured = [pid for pid, spec in CLOUD_PROVIDERS.items() if _key_for(pid)]
        return {
            "gpu": {
                "available": result.gpu.available,
                "name": result.gpu.name,
                "vram_gb": result.gpu.vram_gb,
                "tier_label": result.gpu.tier_label,
            },
            "ollama": {"available": result.ollama.available, "models": result.ollama.models},
            "clouds_configured": clouds_configured,
            "stored_keys": sorted(keys),
            "recommendation": {
                "mode": rec.mode,
                "model": rec.model,
                "installed": rec.installed,
                "message": rec.message,
                "cloud_fallback": rec.cloud_fallback,
            },
        }

    @app.get("/api/settings/llm")
    async def llm_settings_get():
        keys = _read_keys()
        return {
            "keys_configured": {pid: bool(_key_for(pid)) for pid in CLOUD_PROVIDERS},
            "key_env": {pid: spec["key_env"] for pid, spec in CLOUD_PROVIDERS.items()},
            "stored_keys": sorted(keys),
        }

    @app.post("/api/settings/llm")
    async def llm_settings_post(request: Request):
        body = await request.json()
        provider = str(body.get("provider", ""))
        if provider not in CLOUD_PROVIDERS:
            return JSONResponse({"error": "unknown provider"}, status_code=404)
        api_key = body.get("api_key")
        if api_key is not None:
            keys = _read_keys()
            if str(api_key):
                keys[provider] = str(api_key)
            else:
                keys.pop(provider, None)
            _write_keys(keys)
        return {
            "success": True,
            "message": "settings saved",
            "keys_configured": {pid: bool(_key_for(pid)) for pid in CLOUD_PROVIDERS},
        }

    @app.delete("/api/settings/llm/key")
    async def llm_settings_delete_key(provider: str = ""):
        if provider not in CLOUD_PROVIDERS:
            return JSONResponse({"error": "unknown provider"}, status_code=404)
        keys = _read_keys()
        keys.pop(provider, None)
        _write_keys(keys)
        return {"success": True, "message": f"{provider} key removed"}
