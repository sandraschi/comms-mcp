"""comms-mcp server - FastMCP instance + Starlette REST (status/outbox).

Dual transport: stdio (default) or HTTP daemon (MCP_PORT set, per
SOTA_REQUIREMENTS 2.3). The HTTP daemon owns the outbox/inbound store;
stdio instances probe the daemon and proxy when reachable.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from . import __version__
from .config import chat_allowlist, get_settings
from .mcp import tools  # noqa: F401  # import registers tools
from .outbox import sqlite as store
from .registry import mcp  # noqa: F401  # re-exported for stdio entry

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("comms_mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: purge expired inbound bodies (7-day TTL).
    purged = store.purge_expired()
    if purged:
        log.info("purged %d expired inbound messages", purged)
    yield


# REST surface (webapp + diagnostics)
app = FastAPI(title="comms-mcp", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:11029", "http://127.0.0.1:11029"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "server": "comms-mcp",
        "version": __version__,
        "channels": ["telegram"],
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


@app.post("/api/v1/inbound/wa")
async def api_inbound_wa(request: Request):
    """Webhook target for the wa-sidecar (inbound WhatsApp messages).

    Bodies are sanitized (prompt-injection neutralized) and stored with the
    7-day retention TTL. from = WhatsApp jid (number@s.whatsapp.net).
    """
    from .sanitize import sanitize_inbound

    body = await request.json()
    jid = str(body.get("from", "?"))
    text = str(body.get("text", ""))
    if not text.strip():
        return {"success": False, "error": "empty text"}
    safe = sanitize_inbound(text)
    store.store_inbound("whatsapp", jid, jid.split("@")[0], safe)
    return {"success": True, "stored": True}
