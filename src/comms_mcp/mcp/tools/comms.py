"""comms_ops portmanteau - unified fleet comms (P4 spec).

One tool, all channels behind adapters; v0.1 ships Telegram only.
send enforces the chat allowlist; inbound is sanitized + 7-day TTL.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from pydantic import Field

from ...adapters import telegram
from ...config import chat_allowlist
from ...outbox import sqlite as store
from ...registry import mcp

logger = logging.getLogger("comms_mcp.tools")


@mcp.tool(annotations={"readonly": False}, version="0.1.0")
async def comms_ops(
    operation: Annotated[
        Literal["send", "read_recent", "list_threads", "status", "help"],
        Field(description="Comms operation."),
    ],
    channel: Annotated[
        Literal["telegram"], Field(description="Channel (v0.1: telegram only).")
    ] = "telegram",
    chat_id: Annotated[str | None, Field(description="Recipient chat id (send).")] = None,
    text: Annotated[str, Field(description="Message body (send).")] = "",
) -> dict[str, Any]:
    """Unified comms gateway - send + read fleet messaging channels.

    v0.1: Telegram Bot API. `send` is allowlist-gated
    (COMMS_TELEGRAM_CHAT_IDS); inbound messages are sanitized (prompt-
    injection neutralized, email-mcp pattern) and retained 7 days.

    ## Return Format
    {"success": bool, "message": str, ...operation-specific fields}

    ## Examples
    comms_ops(operation="status", channel="telegram")
    comms_ops(operation="send", channel="telegram", chat_id="123456",
              text="Morning briefing: fleet green")
    comms_ops(operation="read_recent", channel="telegram")
    """
    try:
        if operation == "status":
            ok = await telegram.get_me()
            return {
                "success": ok.get("ok", False),
                "channel": "telegram",
                "configured": bool(ok.get("ok")),
                "bot": (ok.get("result") or {}).get("username"),
                "allowlist": chat_allowlist(),
                "stats": store.status_counts(),
            }
        if operation == "list_threads":
            return {"success": True, "channel": "telegram", "threads": chat_allowlist()}
        if operation == "send":
            if not chat_id:
                return {"success": False, "error": "chat_id required"}
            entry = store.enqueue("telegram", chat_id, text)
            result = await telegram.send_message(chat_id, text)
            if result.get("ok"):
                store.mark_sent(entry["id"])
                msg_id = (result.get("result") or {}).get("message_id")
                return {
                    "success": True,
                    "message": "sent",
                    "outbox_id": entry["id"],
                    "message_id": msg_id,
                }
            error = str(result.get("description", result))
            store.mark_failed(entry["id"], error)
            return {"success": False, "error": error, "outbox_id": entry["id"]}
        if operation == "read_recent":
            await telegram.poll_updates()
            return {"success": True, "messages": store.list_inbound()}
        if operation == "help":
            return {
                "success": True,
                "setup": (
                    "1. Create a bot with @BotFather -> token\n"
                    "2. Set COMMS_TELEGRAM_BOT_TOKEN and COMMS_TELEGRAM_CHAT_IDS in .env\n"
                    "3. Start a chat with the bot, then comms_ops(operation='status')\n"
                    "4. read_recent pulls inbound via polling (webhook mode later)"
                ),
                "retention_days": "7 (COMMS_RETENTION_DAYS)",
            }
        return {"success": False, "error": f"unknown operation {operation}"}
    except Exception as exc:
        logger.warning("comms_ops %s failed: %s", operation, exc)
        return {"success": False, "error": str(exc)}
