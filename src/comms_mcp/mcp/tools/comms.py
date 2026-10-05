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


def _error_response(operation: str, channel: str, error: str) -> dict[str, Any]:
    """Shared error envelope with auto-logging (traceback via exception)."""
    logger.exception("comms_ops %s/%s failed: %s", channel, operation, error)
    return {"success": False, "message": error, "error": error}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
    output_schema={"type": "object"},
    version="0.4.0",
)
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
                result = await whatsapp.status()
                return {"message": "whatsapp status", **result}
            if channel == "slack":
                result = await slack.status()
                return {"message": "slack status", **result}
            if channel == "teams":
                result = await teams.status()
                return {"message": "teams status", **result}
            ok = await telegram.get_me()
            return {
                "success": ok.get("ok", False),
                "message": "telegram status",
                "channel": "telegram",
                "configured": bool(ok.get("ok")),
                "bot": (ok.get("result") or {}).get("username"),
                "allowlist": chat_allowlist(),
                "stats": store.status_counts(),
            }
        if operation == "list_threads":
            if channel == "whatsapp":
                return {
                    "success": True,
                    "message": "whatsapp allowlist",
                    "channel": "whatsapp",
                    "threads": whatsapp.allow_numbers(),
                }
            if channel == "slack":
                return {
                    "success": True,
                    "message": "slack allowlist",
                    "channel": "slack",
                    "threads": slack.allow_channels(),
                }
            if channel == "teams":
                return {
                    "success": True,
                    "message": "teams allowlist",
                    "channel": "teams",
                    "threads": teams.allow_list(),
                }
            return {
                "success": True,
                "message": "telegram allowlist",
                "channel": "telegram",
                "threads": chat_allowlist(),
            }
        if operation == "send":
            if not chat_id:
                error = "chat_id required"
                return {"success": False, "message": error, "error": error}
            return await _do_send(channel, chat_id, text)
        if operation == "auth":
            if channel == "teams":
                result = teams.auth_status()
                return {"message": "teams device-flow status", **result}
            error = f"auth not supported for channel {channel}"
            return {"success": False, "message": error, "error": error}
        if operation == "read_recent":
            await telegram.poll_updates()
            messages = store.list_inbound()
            return {
                "success": True,
                "message": f"{len(messages)} recent messages",
                "messages": messages,
            }
        if operation == "help":
            return {
                "success": True,
                "message": "comms-mcp channel setup",
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
        error = f"unknown operation {operation}"
        return {"success": False, "message": error, "error": error}
    except Exception as exc:
        return _error_response(operation, channel, str(exc))


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
            error = f"unknown channel {channel}"
            return {
                "success": False,
                "message": error,
                "error": error,
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
    return {"success": False, "message": error, "error": error, "outbox_id": entry["id"]}
