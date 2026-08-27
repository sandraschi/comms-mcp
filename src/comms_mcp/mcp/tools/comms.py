"""comms_ops portmanteau - unified fleet comms (P4 spec).

One tool, all channels behind adapters. v0.1 Telegram; v0.2 WhatsApp via the
baileys sidecar. send enforces the per-channel allowlist; inbound is
sanitized + 7-day TTL.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from pydantic import Field

from ...adapters import slack, teams, telegram, whatsapp
from ...config import chat_allowlist
from ...outbox import sqlite as store
from ...registry import mcp

logger = logging.getLogger("comms_mcp.tools")

_Channel = Literal["telegram", "whatsapp", "slack", "teams"]


@mcp.tool(annotations={"readonly": False}, version="0.4.0")
async def comms_ops(
    operation: Annotated[
        Literal["send", "read_recent", "list_threads", "status", "auth", "help"],
        Field(description="Comms operation."),
    ],
    channel: Annotated[
        _Channel,
        Field(description="Channel (v0.1 telegram, v0.2 whatsapp, v0.3 slack, v0.4 teams)."),
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
    (allowlist COMMS_SLACK_CHANNEL_IDS; official SDK, no sidecar).
    v0.4: Teams via Microsoft Graph (allowlist COMMS_TEAMS_RECIPIENTS; reuse
    email-mcp's Graph app, device-code auth - see operation='auth'). Inbound
    is sanitized (prompt-injection neutralized) and retained 7 days.

    ## Return Format
    {"success": bool, "message": str, ...operation-specific fields}

    ## Examples
    comms_ops(operation="status", channel="telegram")
    comms_ops(operation="send", channel="whatsapp", chat_id="+436991234567",
              text="Morning briefing: fleet green")
    comms_ops(operation="auth", channel="teams")     # start/poll device flow
    comms_ops(operation="send", channel="teams", chat_id="steve",
              text="Hey - on my way")
    """
    try:
        if operation == "status":
            if channel == "whatsapp":
                return await whatsapp.status()
            if channel == "slack":
                return await slack.status()
            if channel == "teams":
                return await teams.status()
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
            if channel == "teams":
                return {"success": True, "channel": "teams", "threads": teams.allow_list()}
            return {"success": True, "channel": "telegram", "threads": chat_allowlist()}
        if operation == "send":
            if not chat_id:
                return {"success": False, "error": "chat_id required"}
            return await _do_send(channel, chat_id, text)
        if operation == "auth":
            if channel == "teams":
                return teams.auth_status()
            return {"success": False, "error": f"auth not supported for channel {channel}"}
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
                    "Teams: 1. COMMS_GRAPH_CLIENT_ID = email-mcp's Graph app client id; "
                    "2. COMMS_TEAMS_RECIPIENTS = steve=stephanschipal@hotmail.com; "
                    "3. comms_ops(operation='auth', channel='teams') -> enter code, "
                    "call again to confirm; 4. send\n"
                    "Retention: COMMS_RETENTION_DAYS (7)"
                ),
            }
        return {"success": False, "error": f"unknown operation {operation}"}
    except Exception as exc:
        logger.warning("comms_ops %s/%s failed: %s", channel, operation, exc)
        return {"success": False, "error": str(exc)}


async def _do_send(channel: str, chat_id: str, text: str) -> dict[str, Any]:
    """Enqueue, dispatch to the channel adapter, and record the outbox result.

    Normalizes each adapter's success signal (telegram uses 'ok', the others
    'success') into a single outbox-aware response.
    """
    entry = store.enqueue(channel, chat_id, text)
    extra: dict[str, Any] = {}
    try:
        if channel == "telegram":
            result = await telegram.send_message(chat_id, text)
            ok = bool(result.get("ok"))
            if ok:
                extra["message_id"] = (result.get("result") or {}).get("message_id")
            error = str(result.get("description", result))
        elif channel == "whatsapp":
            result = await whatsapp.send_message(chat_id, text)
            ok = bool(result.get("success"))
            error = str(result.get("error", "send failed"))
        elif channel == "slack":
            result = await slack.send_message(chat_id, text)
            ok = bool(result.get("success"))
            extra["ts"] = result.get("ts") if ok else None
            error = str(result.get("error", "send failed"))
        elif channel == "teams":
            result = await teams.send_message(chat_id, text)
            ok = bool(result.get("success"))
            extra["chat_id"] = result.get("chat_id") if ok else None
            error = str(result.get("error", "send failed"))
        else:
            store.mark_failed(entry["id"], f"unknown channel {channel}")
            return {
                "success": False,
                "error": f"unknown channel {channel}",
                "outbox_id": entry["id"],
            }
    except Exception as exc:  # pragma: no cover - defensive
        ok = False
        error = str(exc)
    if ok:
        store.mark_sent(entry["id"])
        return {
            "success": True,
            "message": "sent",
            "outbox_id": entry["id"],
            **{k: v for k, v in extra.items() if v is not None},
        }
    store.mark_failed(entry["id"], error)
    return {"success": False, "error": error, "outbox_id": entry["id"]}
