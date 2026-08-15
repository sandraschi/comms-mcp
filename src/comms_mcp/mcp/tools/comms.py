"""comms_ops portmanteau - unified fleet comms (P4 spec).

One tool, all channels behind adapters. v0.1 Telegram; v0.2 WhatsApp via the
baileys sidecar. send enforces the per-channel allowlist; inbound is
sanitized + 7-day TTL.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from pydantic import Field

from ...adapters import slack, telegram, whatsapp
from ...config import chat_allowlist
from ...outbox import sqlite as store
from ...registry import mcp

logger = logging.getLogger("comms_mcp.tools")

_Channel = Literal["telegram", "whatsapp"]


@mcp.tool(annotations={"readonly": False}, version="0.2.0")
async def comms_ops(
    operation: Annotated[
        Literal["send", "read_recent", "list_threads", "status", "help"],
        Field(description="Comms operation."),
    ],
    channel: Annotated[
        _Channel, Field(description="Channel (v0.1 telegram, v0.2 whatsapp).")
    ] = "telegram",
    chat_id: Annotated[
        str | None, Field(description="Recipient chat id / E.164 number (send).")
    ] = None,
    text: Annotated[str, Field(description="Message body (send).")] = "",
) -> dict[str, Any]:
    """Unified comms gateway - send + read fleet messaging channels.

    v0.1: Telegram Bot API (allowlist COMMS_TELEGRAM_CHAT_IDS).
    v0.2: WhatsApp via baileys sidecar (allowlist COMMS_WHATSAPP_ALLOW_NUMBERS,
    E.164; pair once - status shows the QR). v0.3: Slack Socket Mode
    (allowlist COMMS_SLACK_CHANNEL_IDS; official SDK, no sidecar). Inbound
    is sanitized (prompt-injection neutralized) and retained 7 days.

    ## Return Format
    {"success": bool, "message": str, ...operation-specific fields}

    ## Examples
    comms_ops(operation="status", channel="telegram")
    comms_ops(operation="send", channel="whatsapp", chat_id="+436991234567",
              text="Morning briefing: fleet green")
    comms_ops(operation="status", channel="whatsapp")
    """
    try:
        if operation == "status":
            if channel == "whatsapp":
                return await whatsapp.status()
            if channel == "slack":
                return await slack.status()
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
            if channel == "whatsapp":
                return {"success": True, "channel": "whatsapp", "threads": whatsapp.allow_numbers()}
            if channel == "slack":
                return {"success": True, "channel": "slack", "threads": slack.allow_channels()}
            return {"success": True, "channel": "telegram", "threads": chat_allowlist()}
        if operation == "send":
            if not chat_id:
                return {"success": False, "error": "chat_id required"}
            if channel == "whatsapp":
                entry = store.enqueue("whatsapp", chat_id, text)
                result = await whatsapp.send_message(chat_id, text)
                if result.get("success"):
                    store.mark_sent(entry["id"])
                    return {"success": True, "message": "sent", "outbox_id": entry["id"], **result}
                error = str(result.get("error", "send failed"))
                store.mark_failed(entry["id"], error)
                return {"success": False, "error": error, "outbox_id": entry["id"]}
            if channel == "slack":
                entry = store.enqueue("slack", chat_id, text)
                result = await slack.send_message(chat_id, text)
                if result.get("success"):
                    store.mark_sent(entry["id"])
                    return {
                        "success": True,
                        "message": "sent",
                        "outbox_id": entry["id"],
                        "ts": result.get("ts"),
                    }
                error = str(result.get("error", "send failed"))
                store.mark_failed(entry["id"], error)
                return {"success": False, "error": error, "outbox_id": entry["id"]}
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
                    "Telegram: 1. BotFather -> token; 2. COMMS_TELEGRAM_BOT_TOKEN + "
                    "COMMS_TELEGRAM_CHAT_IDS; 3. comms_ops(operation='status')\n"
                    "WhatsApp: 1. start wa-sidecar (node wa-sidecar); 2. "
                    "comms_ops(operation='status', channel='whatsapp') -> scan QR with "
                    "the phone (Linked devices); 3. COMMS_WHATSAPP_ALLOW_NUMBERS = "
                    "E.164 numbers you will message\n"
                    "Retention: COMMS_RETENTION_DAYS (7)"
                ),
            }
        return {"success": False, "error": f"unknown operation {operation}"}
    except Exception as exc:
        logger.warning("comms_ops %s/%s failed: %s", channel, operation, exc)
        return {"success": False, "error": str(exc)}
