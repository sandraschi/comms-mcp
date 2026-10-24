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
from typing import Any

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


async def channel_statuses() -> list[dict[str, Any]]:
    """Per-channel setup state for the Settings Channels section.

    Read-only aggregation over the existing adapters. Never returns tokens,
    QR payloads, or secrets — only booleans, display names, and counts.
    Every channel reports even when its adapter throws.
    """
    from .adapters import slack, teams, telegram, whatsapp
    from .adapters.telegram import chat_allowlist as tg_allow

    channels: list[dict[str, Any]] = []
    try:
        me = await telegram.get_me()
        ok = bool(me.get("ok"))
        channels.append(
            {
                "id": "telegram",
                "label": "Telegram",
                "configured": ok,
                "detail": f"@{(me.get('result') or {}).get('username', '?')}"
                if ok
                else "COMMS_TELEGRAM_BOT_TOKEN missing or invalid",
                "allowlist_count": len(tg_allow()),
                "setup_env": "COMMS_TELEGRAM_BOT_TOKEN + COMMS_TELEGRAM_CHAT_IDS",
                "keys": ["COMMS_TELEGRAM_BOT_TOKEN", "COMMS_TELEGRAM_CHAT_IDS"],
            }
        )
    except Exception as exc:
        channels.append(
            {
                "id": "telegram",
                "label": "Telegram",
                "configured": False,
                "detail": f"probe failed: {exc}",
                "allowlist_count": 0,
                "setup_env": "COMMS_TELEGRAM_BOT_TOKEN + COMMS_TELEGRAM_CHAT_IDS",
            }
        )
    try:
        st = await whatsapp.status()
        connected = bool(st.get("connected"))
        channels.append(
            {
                "id": "whatsapp",
                "label": "WhatsApp",
                "configured": bool(st.get("success")) and connected,
                "detail": (
                    "sidecar linked — send ready"
                    if connected
                    else "sidecar not linked — scan QR via Settings pairing panel"
                ),
                "allowlist_count": len(
                    [n for n in get_settings().whatsapp_allow_numbers.split(",") if n.strip()]
                ),
                "sidecar": st.get("sidecar", get_settings().whatsapp_sidecar_url),
                "pairing_needed": not connected,
                "setup_env": "COMMS_WHATSAPP_ALLOW_NUMBERS (E.164) + wa-sidecar running",
                "sidecar_state": whatsapp.sidecar_state(),
                "keys": ["COMMS_WHATSAPP_ALLOW_NUMBERS", "COMMS_WHATSAPP_SIDECAR_URL"],
            }
        )
    except Exception as exc:
        channels.append(
            {
                "id": "whatsapp",
                "label": "WhatsApp",
                "configured": False,
                "detail": f"sidecar unreachable: {exc}",
                "allowlist_count": 0,
                "pairing_needed": True,
                "setup_env": "COMMS_WHATSAPP_ALLOW_NUMBERS (E.164) + wa-sidecar running",
            }
        )
    try:
        sst = await slack.status()
        ok = bool(sst.get("success"))
        team = (sst.get("team") or {}) if isinstance(sst.get("team"), dict) else {}
        channels.append(
            {
                "id": "slack",
                "label": "Slack",
                "configured": ok,
                "detail": f"team {team.get('name', '?')} — bot {sst.get('bot', '?')}"
                if ok
                else str(sst.get("error", "COMMS_SLACK_APP_TOKEN/BOT_TOKEN missing")),
                "allowlist_count": len(slack.allow_channels()),
                "setup_env": (
                    "COMMS_SLACK_APP_TOKEN + COMMS_SLACK_BOT_TOKEN + COMMS_SLACK_CHANNEL_IDS"
                ),
                "keys": [
                    "COMMS_SLACK_APP_TOKEN",
                    "COMMS_SLACK_BOT_TOKEN",
                    "COMMS_SLACK_CHANNEL_IDS",
                ],
            }
        )
    except Exception as exc:
        channels.append(
            {
                "id": "slack",
                "label": "Slack",
                "configured": False,
                "detail": f"probe failed: {exc}",
                "allowlist_count": 0,
                "setup_env": (
                    "COMMS_SLACK_APP_TOKEN + COMMS_SLACK_BOT_TOKEN + COMMS_SLACK_CHANNEL_IDS"
                ),
            }
        )
    try:
        tst = teams.auth_status()
        authed = bool(tst.get("authorized"))
        channels.append(
            {
                "id": "teams",
                "label": "Teams",
                "configured": bool(tst.get("client_configured")) and authed,
                "detail": (
                    f"authorized as {tst.get('account', '?')}"
                    if authed
                    else "device-code auth required — see Help, Teams tab"
                ),
                "allowlist_count": len(teams.allow_list()),
                "needs_auth": not authed,
                "setup_env": "COMMS_GRAPH_CLIENT_ID + COMMS_TEAMS_RECIPIENTS",
                "keys": ["COMMS_GRAPH_CLIENT_ID", "COMMS_TEAMS_RECIPIENTS"],
            }
        )
    except Exception as exc:
        channels.append(
            {
                "id": "teams",
                "label": "Teams",
                "configured": False,
                "detail": f"probe failed: {exc}",
                "allowlist_count": 0,
                "needs_auth": True,
                "setup_env": "COMMS_GRAPH_CLIENT_ID + COMMS_TEAMS_RECIPIENTS",
            }
        )
    return channels


@app.get("/api/v1/channels")
async def api_channels():
    """Per-channel setup state (Settings Channels section). No secrets."""
    return {"channels": await channel_statuses()}


# Writable config surface (Settings Channels section). Keys outside this
# allowlist are rejected — the browser can never touch anything else.
_WRITABLE_ENV_KEYS = frozenset(
    {
        "COMMS_TELEGRAM_BOT_TOKEN",
        "COMMS_TELEGRAM_CHAT_IDS",
        "COMMS_WHATSAPP_ALLOW_NUMBERS",
        "COMMS_WHATSAPP_SIDECAR_URL",
        "COMMS_SLACK_APP_TOKEN",
        "COMMS_SLACK_BOT_TOKEN",
        "COMMS_SLACK_CHANNEL_IDS",
        "COMMS_GRAPH_CLIENT_ID",
        "COMMS_TEAMS_RECIPIENTS",
        "COMMS_RETENTION_DAYS",
        "COMMS_INBOUND_SECRET",
    }
)

# Test override for the .env location (tests point it at a temp file).
_ENV_FILE_OVERRIDE: Path | None = None


def env_path() -> Path:
    if _ENV_FILE_OVERRIDE is not None:
        return _ENV_FILE_OVERRIDE
    return Path(__file__).resolve().parent.parent.parent / ".env"


def apply_config(values: dict[str, Any]) -> dict[str, Any]:
    """Validate + persist config values to .env and the live process env.

    Returns {"applied": [keys]}. Raises ValueError on the first problem —
    nothing is written unless every value validates.
    """
    import os

    cleaned: dict[str, str] = {}
    for key, raw in values.items():
        if key not in _WRITABLE_ENV_KEYS:
            raise ValueError(f"key not writable: {key}")
        value = str(raw).strip() if raw is not None else ""
        if key == "COMMS_RETENTION_DAYS":
            try:
                days = int(value or "7")
            except ValueError:
                raise ValueError("COMMS_RETENTION_DAYS must be an integer") from None
            if days < 1:
                raise ValueError("COMMS_RETENTION_DAYS must be >= 1")
            value = str(days)
        cleaned[key] = value
    path = env_path()
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name = stripped.split("=", 1)[0].strip()
            if name in cleaned:
                out.append(f"{name}={cleaned[name]}")
                seen.add(name)
                continue
        out.append(line)
    for key, value in cleaned.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    for key, value in cleaned.items():
        os.environ[key] = value
    log.warning("config updated via REST: %s", ", ".join(sorted(cleaned)))
    return {"applied": sorted(cleaned)}


@app.post("/api/v1/config")
async def api_config(request: Request):
    """Persist channel credentials (Settings Channels section).

    Body: {"values": {"COMMS_TELEGRAM_BOT_TOKEN": "...", ...}}. Applies to
    .env AND the live process (config is re-read per call — no restart).
    Returns applied key NAMES only, never values.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "invalid JSON"}, status_code=400)
    values = body.get("values")
    if not isinstance(values, dict) or not values:
        return JSONResponse({"success": False, "error": "values object required"}, status_code=400)
    try:
        result = apply_config(values)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    except OSError as exc:
        return JSONResponse({"success": False, "error": f"write failed: {exc}"}, status_code=500)
    return {"success": True, **result}


@app.post("/api/v1/teams/auth")
async def api_teams_auth(request: Request):
    """Teams device-code flow from the Settings UI (no CLI needed).

    Body: {"action": "start"|"poll"|"reset"}. start fetches a fresh user
    code (clears any stale flow first); poll checks a pending flow; reset
    wipes tokens + pending flow. The single auth_status() primitive both
    starts and polls, so start = reset-pending + call, poll = call.
    """
    import asyncio as _asyncio

    from .adapters import teams

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "invalid JSON"}, status_code=400)
    action = str(body.get("action", "poll")).strip().lower()
    if action not in ("start", "poll", "reset"):
        return JSONResponse(
            {"success": False, "error": "action must be start|poll|reset"},
            status_code=400,
        )

    def _run() -> dict[str, Any]:
        if action == "reset":
            teams._pending_flow = None
            try:
                path = teams._token_path()
                if path.exists():
                    path.unlink()
            except OSError as exc:
                return {"success": False, "error": f"reset failed: {exc}"}
            return {"success": True, "status": "reset"}
        if action == "start":
            teams._pending_flow = None
        return teams.auth_status()

    try:
        result = await _asyncio.to_thread(_run)
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=502)
    return result


@app.get("/api/v1/whatsapp/qr")
async def api_whatsapp_qr():
    """Pairing state for the Settings WhatsApp card (explicit click only).

    Returns presence flags + pairing_code; the raw QR blob stays in the
    sidecar. Never logged.
    """
    from .adapters import whatsapp

    try:
        pair = await whatsapp.pairing_info()
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": f"sidecar unreachable: {exc}"}, status_code=502
        )
    if not pair.get("success"):
        return JSONResponse(
            {"success": False, "error": str(pair.get("error", "no pairing data"))},
            status_code=502,
        )
    return {
        "success": True,
        "qr_present": bool(pair.get("qr")),
        "pairing_code": pair.get("pairing_code"),
    }


@app.post("/api/v1/whatsapp/sidecar")
async def api_whatsapp_sidecar(request: Request):
    """Start/stop the baileys sidecar — nobody hand-starts node anymore.

    Body: {"action": "start"|"stop"}. start is async: returns immediately,
    poll sidecar_state via GET /api/v1/channels (phase installing/starting/
    running/failed). First run does npm install (may take minutes).
    """
    from .adapters import whatsapp

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "invalid JSON"}, status_code=400)
    action = str(body.get("action", "")).strip().lower()
    import asyncio as _asyncio

    if action == "start":
        result = await _asyncio.to_thread(whatsapp.start_sidecar)
        return {"success": True, **result}
    if action == "stop":
        result = await _asyncio.to_thread(whatsapp.stop_sidecar)
        return {"success": True, **result}
    return JSONResponse({"success": False, "error": "action must be start|stop"}, status_code=400)


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
            "GET /api/v1/channels",
            "POST /api/v1/config",
            "POST /api/v1/teams/auth",
            "GET /api/v1/whatsapp/qr",
            "POST /api/v1/whatsapp/sidecar",
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
