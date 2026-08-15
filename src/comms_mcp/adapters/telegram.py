"""Telegram Bot API adapter (v0.1) - plain httpx, no extra deps.

Send is allowlist-gated (COMMS_TELEGRAM_CHAT_IDS); inbound is fetched via
getUpdates (polling) on demand and stored with 7-day TTL. All inbound text
runs through sanitize.sanitize_inbound.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import chat_allowlist, get_settings
from ..outbox import sqlite as store
from ..sanitize import sanitize_inbound, sanitize_text

log = logging.getLogger("comms_mcp.telegram")

TIMEOUT_S = 15


def _base() -> str:
    return f"{get_settings().telegram_api_base.rstrip('/')}/bot{get_settings().telegram_bot_token}"


def _configured() -> bool:
    return bool(get_settings().telegram_bot_token)


async def get_me() -> dict[str, Any]:
    if not _configured():
        return {"success": False, "error": "COMMS_TELEGRAM_BOT_TOKEN not set"}
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.get(f"{_base()}/getMe")
        r.raise_for_status()
        return r.json()


async def send_message(chat_id: str, text: str) -> dict[str, Any]:
    if not _configured():
        return {"success": False, "error": "COMMS_TELEGRAM_BOT_TOKEN not set"}
    allow = chat_allowlist()
    if allow and chat_id not in allow:
        return {"success": False, "error": f"chat {chat_id} not in allowlist", "allowlist": allow}
    body = sanitize_text(text)
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(
            f"{_base()}/sendMessage", json={"chat_id": chat_id, "text": body[:4000]}
        )
        r.raise_for_status()
        return r.json()


async def poll_updates(offset: int = 0, timeout: int = 5) -> list[dict[str, Any]]:
    """Fetch updates (long-poll) and store inbound messages."""
    if not _configured():
        return []
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        r = await client.get(
            f"{_base()}/getUpdates",
            params={"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
        )
        r.raise_for_status()
        data = r.json()
    updates = data.get("result", [])
    stored: list[dict[str, Any]] = []
    for update in updates:
        msg = (update.get("message") or {}).get("text")
        if not msg:
            continue
        chat_id = str(update["message"]["chat"]["id"])
        from_id = str((update["message"].get("from") or {}).get("id", "?"))
        safe = sanitize_inbound(msg)
        store.store_inbound("telegram", chat_id, from_id, safe)
        stored.append({"update_id": update["update_id"], "chat_id": chat_id, "from_id": from_id})
    return stored
