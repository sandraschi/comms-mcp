"""comms-mcp server - FastMCP instance + Starlette REST (status/outbox).

Dual transport: stdio (default) or HTTP daemon (MCP_PORT set, per
SOTA_REQUIREMENTS 2.3). The HTTP daemon owns the outbox/inbound store;
stdio instances probe the daemon and proxy when reachable.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from . import __version__
from .config import chat_allowlist, get_settings
from .llm import register_llm_routes
from .mcp import context, tools  # noqa: F401  # imports register tools/resources
from .outbox import sqlite as store
from .registry import mcp  # noqa: F401  # re-exported for stdio entry

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("comms_mcp")


class _LogRing(logging.Handler):
    """In-memory ring buffer backing GET /api/logs (last 500 records)."""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._records: deque[dict[str, str]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._records.append(
                {
                    "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                    "level": record.levelname,
                    "source": record.name,
                    "message": record.getMessage(),
                }
            )
        except Exception:  # logging must never raise into the app
            pass

    def entries(
        self, level: str = "", source: str = "", search: str = "", limit: int = 100
    ) -> list[dict[str, str]]:
        rows = list(self._records)
        if level:
            rows = [r for r in rows if r["level"] == level.upper()]
        if source:
            rows = [r for r in rows if source.lower() in r["source"].lower()]
        if search:
            rows = [r for r in rows if search.lower() in r["message"].lower()]
        return rows[-limit:]


_log_ring = _LogRing()
logging.getLogger().addHandler(_log_ring)

# Mount the MCP streamable-HTTP app at /mcp (ports registry promises FastMCP
# HTTP on 11205). BUG-008: http_app(path="/") + mount("/mcp") — never
# http_app(path="/mcp") mounted at "/mcp" (double prefix, all calls 404).
# transport="streamable-http": the default legacy "http" (SSE) transport 405s
# modern client POSTs.
mcp_http = mcp.http_app(path="/", transport="streamable-http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # BUG-038: the mounted MCP sub-app's lifespan must run inside the parent
    # lifespan, or real HTTP clients fail (FastMCP: lifespan=mcp_app.lifespan).
    async with mcp_http.lifespan(app):
        async with _lifespan_body():
            yield


@asynccontextmanager
async def _lifespan_body():
    # Startup: purge expired inbound bodies (7-day TTL).
    purged = store.purge_expired()
    if purged:
        log.info("purged %d expired inbound messages", purged)

    # Slack Socket Mode listener (v0.3) - background task when configured.
    slack_client = None
    try:
        from .adapters import slack

        if slack.configured():
            slack_client = slack.start_socket_listener()
            asyncio.create_task(slack_client.connect())
            log.info("slack socket listener started")
    except Exception as exc:
        log.warning("slack socket listener failed to start: %s", exc)

    yield

    if slack_client is not None:
        try:
            slack_client.disconnect()
        except Exception as exc:
            log.warning("slack socket listener shutdown failed: %s", exc)


# REST surface (webapp + diagnostics)
app = FastAPI(title="comms-mcp", version=__version__, lifespan=lifespan)
_FRONTEND_PORT = 11204
_BACKEND_PORT = 11205
_cors_origins = [
    f"http://localhost:{_FRONTEND_PORT}",
    f"http://127.0.0.1:{_FRONTEND_PORT}",
    f"http://localhost:{_BACKEND_PORT}",
    f"http://127.0.0.1:{_BACKEND_PORT}",
    # Tauri WebView (CORS_STANDARD §The Pattern)
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
]
# Broad LAN + Tailscale, applied unconditionally (CORS_STANDARD.md).
_cors_regex = (
    r"https?://(?:[a-zA-Z0-9-]+\.ts\.net|.*?\.tail-[a-f0-9]+\.ts\.net"
    r"|tauri\.localhost|localhost|127\.0\.0\.1"
    r"|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|100\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?$|^tauri://localhost$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/mcp", mcp_http, name="mcp")


class _McpBarePathMiddleware:
    """Rewrite the exact bare /mcp path to /mcp/ before routing.

    Starlette Mount("/mcp") only matches /mcp/* — the bare path falls through
    (405 from unrelated handlers). MCP clients use the exact configured URL,
    so both shapes must answer. Internal rewrite, no client redirect needed.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope, path="/mcp/")
        await self.app(scope, receive, send)


app.add_middleware(_McpBarePathMiddleware)


@app.get("/health")
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "server": "comms-mcp",
        "version": __version__,
        "channels": ["telegram", "whatsapp", "slack", "teams"],
        "stats": store.status_counts(),
    }


@app.get("/api/v1/outbox")
async def api_outbox(status: str = "", limit: int = 25):
    return {"items": store.list_outbox(status=status, limit=limit)}


@app.get("/api/v1/inbound")
async def api_inbound(chat_id: str = "", limit: int = 20):
    return {"messages": store.list_inbound(chat_id=chat_id, limit=limit)}


@app.get("/api/v1/status")
async def api_status():
    from .adapters import telegram

    ok = await telegram.get_me()
    return {
        "configured": bool(ok.get("ok")),
        "bot": (ok.get("result") or {}).get("username"),
        "allowlist": chat_allowlist(),
        "stats": store.status_counts(),
        "retention_days": int(get_settings().retention_days),
    }


@app.post("/api/v1/send")
async def api_send(request: Request):
    from .adapters import telegram

    body = await request.json()
    chat_id = str(body.get("chat_id", ""))
    text = str(body.get("text", ""))
    if not chat_id or not text.strip():
        return JSONResponse(
            {"success": False, "error": "chat_id and text required"}, status_code=400
        )
    allow = chat_allowlist()
    if allow and chat_id not in allow:
        return JSONResponse(
            {"success": False, "error": f"chat {chat_id} not in allowlist"}, status_code=403
        )
    entry = store.enqueue("telegram", chat_id, text)
    result = await telegram.send_message(chat_id, text)
    if result.get("ok"):
        store.mark_sent(entry["id"])
        return {
            "success": True,
            "outbox_id": entry["id"],
            "message_id": (result.get("result") or {}).get("message_id"),
        }
    error = str(result.get("description", result))
    store.mark_failed(entry["id"], error)
    return JSONResponse(
        {"success": False, "error": error, "outbox_id": entry["id"]}, status_code=502
    )


@app.get("/api/capabilities")
async def api_capabilities():
    """Fleet-standard capability surface (WEBAPP_STANDARDS 1.4)."""
    return {
        "server": "comms-mcp",
        "version": __version__,
        "channels": ["telegram", "whatsapp", "slack", "teams"],
        "mcp_tools": ["comms_ops", "comms_shutdown", "comms_show_status"],
        "rest": [
            "GET /health",
            "GET /api/v1/outbox",
            "GET /api/v1/inbound",
            "GET /api/v1/status",
            "POST /api/v1/send",
            "POST /api/v1/inbound/wa",
            "GET /api/capabilities",
            "GET /api/skills",
            "POST /api/shutdown",
        ],
        "webhook_secret_configured": bool(get_settings().inbound_secret),
    }


@app.get("/api/skills")
async def api_skills():
    """Skill-first listing for agents (chat skill preprompt source)."""
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    items: list[dict[str, str]] = []
    if skills_dir.is_dir():
        for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
            text = skill_file.read_text(encoding="utf-8", errors="replace")
            name, description = skill_file.parent.name, ""
            if text.startswith("---"):
                head = text.split("---", 2)[1]
                for line in head.splitlines():
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
            items.append({"name": name, "description": description, "uri": f"skill://{name}"})
    return {"skills": items}


@app.get("/api/logs")
async def api_logs(level: str = "", source: str = "", search: str = "", limit: int = 100):
    """Recent log records from the in-memory ring (Logs page / Ctrl+L)."""
    entries = _log_ring.entries(level=level, source=source, search=search, limit=limit)
    return {"entries": entries, "count": len(entries)}


@app.get("/api/skills/{name}")
async def api_skill_content(name: str):
    """Markdown body of one skill (Skill page render source)."""
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    skill_file = skills_dir / name / "SKILL.md"
    if not skill_file.is_file():
        return JSONResponse({"error": "unknown skill"}, status_code=404)
    return {
        "name": name,
        "content": skill_file.read_text(encoding="utf-8", errors="replace"),
    }


@app.post("/api/shutdown")
async def api_shutdown():
    """Orderly exit for NSSM/launcher restarts: 200 now, exit after 500 ms so
    in-flight outbox writes can checkpoint."""
    import os
    import threading
    import time

    def _exit() -> None:
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True, name="comms-shutdown").start()
    log.warning("shutdown requested via REST - exiting in 500 ms")
    return {"success": True, "message": "shutting down"}


# Local + cloud LLM provider surface (WEBAPP_SOTA_STANDARDS §VI).
register_llm_routes(app)


@app.post("/api/v1/inbound/wa")
async def api_inbound_wa(request: Request):
    """Webhook target for the wa-sidecar (inbound WhatsApp messages).

    Bodies are sanitized (prompt-injection neutralized) and stored with the
    7-day retention TTL. from = WhatsApp jid (number@s.whatsapp.net).
    When COMMS_INBOUND_SECRET is set, the sidecar must send it as
    X-Comms-Secret (else 401).
    """
    from .sanitize import sanitize_inbound

    secret = get_settings().inbound_secret
    if secret and request.headers.get("x-comms-secret") != secret:
        return JSONResponse({"success": False, "error": "unauthorized"}, status_code=401)

    body = await request.json()
    jid = str(body.get("from", "?"))
    text = str(body.get("text", ""))
    if not text.strip():
        return {"success": False, "error": "empty text"}
    safe = sanitize_inbound(text)
    store.store_inbound("whatsapp", jid, jid.split("@")[0], safe)
    return {"success": True, "stored": True}


# Serve the built webapp (web_sota/dist) at the backend root when present -
# the console is then reachable on :11205 with no separate dev server.
# Registered LAST so /api/* routes win.
_DIST = Path(__file__).resolve().parent.parent.parent / "web_sota" / "dist"
if _DIST.is_dir():
    from starlette.staticfiles import StaticFiles

    class _SpaStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            response = await super().get_response(path, scope)
            if response.status_code == 404:
                response = await super().get_response("index.html", scope)
            return response

    app.mount("/", _SpaStaticFiles(directory=str(_DIST), html=True), name="console")
