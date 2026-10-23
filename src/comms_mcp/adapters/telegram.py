"""Telegram Bot API adapter - plain httpx, no extra deps (text only).

Send is allowlist-gated (COMMS_TELEGRAM_CHAT_IDS); inbound is fetched via
getUpdates (polling) on demand and stored with 7-day TTL. All inbound text
runs through sanitize.sanitize_inbound.

Text-only scope: no photos/docs/media. Threading = reply_to_message_id,
formatting = HTML parse_mode only (MarkdownV2 escaping is a footgun).
Edits/deletes map to editMessageText/deleteMessage.
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


async def send_message(
    chat_id: str, text: str, reply_to: str | int | None = None, parse_mode: str | None = None
) -> dict[str, Any]:
    if not _configured():
        return {"success": False, "error": "COMMS_TELEGRAM_BOT_TOKEN not set"}
    allow = chat_allowlist()
    if allow and chat_id not in allow:
        return {"success": False, "error": f"chat {chat_id} not in allowlist", "allowlist": allow}
    body = sanitize_text(text)
    payload: dict[str, Any] = {"chat_id": chat_id, "text": body[:4000]}
    if reply_to is not None:
        try:
            payload["reply_to_message_id"] = int(reply_to)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid reply_to message id: {reply_to}"}
    if parse_mode is not None:
        if parse_mode != "HTML":
            return {"success": False, "error": "parse_mode must be 'HTML' or omitted"}
        payload["parse_mode"] = "HTML"
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(f"{_base()}/sendMessage", json=payload)
        r.raise_for_status()
        return r.json()


async def edit_message(chat_id: str, message_id: str | int, text: str) -> dict[str, Any]:
    """Edit a sent text message (editMessageText)."""
    if not _configured():
        return {"success": False, "error": "COMMS_TELEGRAM_BOT_TOKEN not set"}
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return {"success": False, "error": f"invalid message_id: {message_id}"}
    body = sanitize_text(text)
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(
            f"{_base()}/editMessageText",
            json={"chat_id": chat_id, "message_id": mid, "text": body[:4000]},
        )
        r.raise_for_status()
        return r.json()


async def delete_message(chat_id: str, message_id: str | int) -> dict[str, Any]:
    """Delete a message (deleteMessage)."""
    if not _configured():
        return {"success": False, "error": "COMMS_TELEGRAM_BOT_TOKEN not set"}
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return {"success": False, "error": f"invalid message_id: {message_id}"}
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(
            f"{_base()}/deleteMessage", json={"chat_id": chat_id, "message_id": mid}
        )
        r.raise_for_status()
        return r.json()


async def get_chat(chat_id: str) -> dict[str, Any]:
    """Best-effort chat title lookup for list_threads enrichment."""
    if not _configured():
        return {"success": False, "error": "COMMS_TELEGRAM_BOT_TOKEN not set"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(f"{_base()}/getChat", params={"chat_id": chat_id})
            r.raise_for_status()
            result = r.json().get("result", {})
        title = result.get("title") or result.get("username") or result.get("type") or chat_id
        return {"success": True, "chat_id": chat_id, "title": title}
    except Exception as exc:
        return {"success": False, "error": str(exc), "chat_id": chat_id}


def _offset_path() -> Any:
    from pathlib import Path

    return Path(get_settings().db_path).parent / "telegram_update_offset"


def _load_offset() -> int:
    try:
        return int(_offset_path().read_text(encoding="utf-8").strip() or 0)
    except Exception:
        return 0


def _save_offset(offset: int) -> None:
    try:
        p = _offset_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(offset), encoding="utf-8")
    except Exception as exc:
        log.warning("telegram offset save failed: %s", exc)


async def poll_updates(offset: int | None = None, timeout: int = 5) -> list[dict[str, Any]]:
    """Fetch updates (long-poll) and store inbound messages.

    Offset persists to data/telegram_update_offset so consecutive
    read_recent calls don't re-ingest the same messages. Handles
    message + edited_message + channel_post (text only).
    """
    if not _configured():
        return []
    if offset is None:
        offset = _load_offset()
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        r = await client.get(
            f"{_base()}/getUpdates",
            params={"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
        )
        r.raise_for_status()
        data = r.json()
    updates = data.get("result", [])
    stored: list[dict[str, Any]] = []
    max_id = offset
    for update in updates:
        try:
            max_id = max(max_id, int(update.get("update_id", 0)))
        except (TypeError, ValueError):
            pass
        msg_obj = (
            update.get("message") or update.get("edited_message") or update.get("channel_post")
        )
        if not isinstance(msg_obj, dict):
            continue
        msg = msg_obj.get("text")
        if not msg:
            continue
        chat = msg_obj.get("chat") or {}
        chat_id = str(chat.get("id", "?"))
        from_id = str((msg_obj.get("from") or {}).get("id", "?"))
        safe = sanitize_inbound(msg)
        store.store_inbound("telegram", chat_id, from_id, safe)
        stored.append({"update_id": update["update_id"], "chat_id": chat_id, "from_id": from_id})
    if max_id and max_id >= offset:
        _save_offset(max_id + 1)
    return stored
