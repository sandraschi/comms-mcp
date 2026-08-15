"""Slack adapter (v0.3) - official slack-sdk, Socket Mode + Web API.

No sidecar needed (Python SDK). Socket Mode receives inbound in real time
(app-level token, connections:write); sends go through the Web API (bot
token, chat_postMessage), allowlist-gated (COMMS_SLACK_CHANNEL_IDS).

The sync SDK runs in threads (no aiohttp dependency); inbound events are
sanitized + stored by the same pipeline as the other channels; bot messages
are skipped (no echo loops).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from ..config import get_settings
from ..outbox import sqlite as store
from ..sanitize import sanitize_inbound

log = logging.getLogger("comms_mcp.slack")

TIMEOUT_S = 15


def configured() -> bool:
    cfg = get_settings()
    return bool(cfg.slack_app_token and cfg.slack_bot_token)


def allow_channels() -> list[str]:
    return [c.strip() for c in get_settings().slack_channel_ids.split(",") if c.strip()]


def _web_client() -> Any:
    from slack_sdk.web import WebClient

    return WebClient(token=get_settings().slack_bot_token, timeout=TIMEOUT_S)


async def status() -> dict[str, Any]:
    if not configured():
        return {"success": False, "configured": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    try:
        client = _web_client()
        result = await asyncio.to_thread(client.auth_test)
        return {
            "success": True,
            "configured": True,
            "bot": result.get("user_id"),
            "team": result.get("team"),
            "allowlist": allow_channels(),
        }
    except Exception as exc:
        return {"success": False, "configured": True, "error": str(exc)}


async def send_message(channel: str, text: str) -> dict[str, Any]:
    if not configured():
        return {"success": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    allow = allow_channels()
    if allow and channel not in allow:
        return {
            "success": False,
            "error": f"channel {channel} not in allowlist",
            "allowlist": allow,
        }
    try:
        client = _web_client()
        result = await asyncio.to_thread(client.chat_postMessage, channel=channel, text=text[:4000])
        return {"success": True, "ts": result.get("ts")}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _handle_inbound_event(event: dict[str, Any]) -> None:
    """Store one inbound message event (sanitized)."""
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return
    text = event.get("text", "")
    if not text.strip():
        return
    channel = str(event.get("channel", "?"))
    user = str(event.get("user", "?"))
    safe = sanitize_inbound(text)
    store.store_inbound("slack", channel, user, safe)


def _socket_message_handler(client: Any, req: Any) -> None:
    event = (req.payload or {}).get("event") or {}
    try:
        asyncio.run(_handle_inbound_event(event))
    except Exception as exc:
        log.warning("slack inbound failed: %s", exc)


def start_socket_listener() -> Any:
    """Start the Socket Mode client in a background thread. Returns the client."""
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.web import WebClient

    client = SocketModeClient(
        app_token=get_settings().slack_app_token,
        web_client=WebClient(token=get_settings().slack_bot_token),
        logger=log,
    )
    client.socket_mode_request_listeners.append(_socket_message_handler)
    thread = threading.Thread(target=client.connect, daemon=True, name="slack-socket")
    thread.start()
    return client
