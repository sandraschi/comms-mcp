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


async def send_message(channel: str, text: str, thread_ts: str | None = None) -> dict[str, Any]:
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
        kwargs: dict[str, Any] = {"channel": channel, "text": text[:4000]}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        result = await asyncio.to_thread(client.chat_postMessage, **kwargs)
        out: dict[str, Any] = {"success": True, "ts": result.get("ts")}
        if thread_ts:
            out["thread_ts"] = thread_ts
        return out
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def list_channels() -> dict[str, Any]:
    """Live workspace channels via conversations.list, fallback to allowlist."""
    if not configured():
        return {"success": False, "configured": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    try:
        client = _web_client()
        result = await asyncio.to_thread(
            client.conversations_list, types="public_channel,private_channel", limit=200
        )
        channels = [
            {"id": c.get("id"), "name": c.get("name"), "is_private": bool(c.get("is_private"))}
            for c in (result.get("channels") or [])
        ]
        return {"success": True, "channels": channels, "allowlist": allow_channels()}
    except Exception as exc:
        return {"success": False, "error": str(exc), "allowlist": allow_channels()}


async def channel_history(channel: str, limit: int = 20) -> dict[str, Any]:
    """Recent messages via conversations.history (read-only, no store write)."""
    if not configured():
        return {"success": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    try:
        n = max(1, min(int(limit), 100))
        client = _web_client()
        result = await asyncio.to_thread(client.conversations_history, channel=channel, limit=n)
        messages = [
            {
                "ts": m.get("ts"),
                "user": m.get("user"),
                "text": (m.get("text") or "")[:2000],
                "thread_ts": m.get("thread_ts"),
            }
            for m in (result.get("messages") or [])
        ]
        return {"success": True, "channel": channel, "messages": messages}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def search_messages(query: str, count: int = 20) -> dict[str, Any]:
    """Full-workspace search via search.messages (needs search:read scope)."""
    if not configured():
        return {"success": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    if not query.strip():
        return {"success": False, "error": "query required"}
    try:
        n = max(1, min(int(count), 100))
        client = _web_client()
        result = await asyncio.to_thread(client.search_messages, query=query, count=n)
        matches = (result.get("messages") or {}).get("matches") or []
        hits = [
            {
                "channel": (m.get("channel") or {}).get("name") or m.get("channel_id"),
                "user": m.get("user"),
                "ts": m.get("ts"),
                "text": (m.get("text") or "")[:2000],
            }
            for m in matches
        ]
        return {"success": True, "query": query, "messages": hits}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def add_reaction(channel: str, timestamp: str, emoji: str) -> dict[str, Any]:
    """Add an emoji reaction (reactions:write scope). Emoji colons optional."""
    if not configured():
        return {"success": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    name = emoji.strip().strip(":")
    if not name:
        return {"success": False, "error": "emoji required"}
    try:
        client = _web_client()
        await asyncio.to_thread(
            client.reactions_add, channel=channel, timestamp=timestamp, name=name
        )
        return {"success": True, "channel": channel, "ts": timestamp, "emoji": name}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def edit_message(channel: str, timestamp: str, text: str) -> dict[str, Any]:
    """Edit a message (chat.update, text only)."""
    if not configured():
        return {"success": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    try:
        client = _web_client()
        result = await asyncio.to_thread(
            client.chat_update, channel=channel, ts=timestamp, text=text[:4000]
        )
        return {"success": True, "channel": channel, "ts": result.get("ts")}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def delete_message(channel: str, timestamp: str) -> dict[str, Any]:
    """Delete a message (chat.delete)."""
    if not configured():
        return {"success": False, "error": "SLACK_APP_TOKEN/BOT_TOKEN not set"}
    try:
        client = _web_client()
        await asyncio.to_thread(client.chat_delete, channel=channel, ts=timestamp)
        return {"success": True, "channel": channel, "ts": timestamp}
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
