"""comms_ops portmanteau - unified fleet comms (P4 spec).

One tool, all channels behind adapters. v0.1 Telegram; v0.2 WhatsApp via the
baileys sidecar; v0.7 Signal via the signal-cli-rest-api sidecar. send
enforces the per-channel allowlist; inbound is sanitized + 7-day TTL.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from pydantic import Field

from ...adapters import signal, slack, teams, telegram, whatsapp
from ...config import chat_allowlist
from ...outbox import sqlite as store
from ...registry import mcp

logger = logging.getLogger("comms_mcp.tools")

_Channel = Literal["telegram", "whatsapp", "slack", "teams", "signal"]


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
    version="0.7.0",
)
async def comms_ops(
    operation: Annotated[
        Literal[
            "send",
            "read_recent",
            "list_threads",
            "status",
            "auth",
            "help",
            "history",
            "search",
            "react",
            "edit",
            "delete",
        ],
        Field(description="Comms operation."),
    ],
    channel: Annotated[
        _Channel,
        Field(description="Channel (v0.1 telegram … v0.7 signal)."),
    ] = "telegram",
    chat_id: Annotated[
        str | None, Field(description="Recipient chat id / E.164 number (send).")
    ] = None,
    text: Annotated[str, Field(description="Message body (send).")] = "",
    limit: Annotated[int, Field(description="Max messages (history/search/read_recent).")] = 20,
    thread_ts: Annotated[
        str | None,
        Field(
            description="Reply target / message id: Slack ts, Telegram message_id, "
            "Teams message id (send reply, edit/delete target, react ts)."
        ),
    ] = None,
    query: Annotated[str, Field(description="Search query (search).")] = "",
    emoji: Annotated[str, Field(description="Emoji name, colons optional (react).")] = "",
    parse_mode: Annotated[
        str | None, Field(description="Telegram formatting: 'HTML' or omitted.")
    ] = None,
) -> dict[str, Any]:
    """Unified comms gateway - send + read fleet messaging channels (text only).

    v0.1: Telegram Bot API (allowlist COMMS_TELEGRAM_CHAT_IDS).
    v0.2: WhatsApp via baileys sidecar (allowlist COMMS_WHATSAPP_ALLOW_NUMBERS,
    E.164; pair once - status shows the QR). v0.3: Slack Socket Mode
    (allowlist COMMS_SLACK_CHANNEL_IDS; official SDK, no sidecar).
    v0.4: Teams via Microsoft Graph (allowlist COMMS_TEAMS_RECIPIENTS; reuse
    email-mcp's Graph app, device-code auth - see operation='auth'). v0.5:
    Slack history/search/react + thread replies.     v0.6: text-only fatten -
    Telegram replies/HTML/edit/delete + chat titles + offset-persisted polling,
    Teams live chats/history/replies/edit/delete, WhatsApp pairing in status,
    plus edit/delete ops (telegram/slack/teams). v0.7: Signal via the
    bbernhard signal-cli-rest-api sidecar (unofficial bridge — dedicated
    number required; link by QR or register by SMS/voice; Docker-managed).
    Inbound
    is sanitized (prompt-injection neutralized) and retained 7 days.

    ## Return Format
    {"success": bool, "message": str, ...operation-specific fields}

    ## Examples
    comms_ops(operation="status", channel="telegram")
    comms_ops(operation="send", channel="whatsapp", chat_id="+436991234567",
              text="Morning briefing: fleet green")
    comms_ops(operation="send", channel="slack", chat_id="C123",
              text="Release is green", thread_ts="1234567890.123456")
    comms_ops(operation="send", channel="telegram", chat_id="111",
              text="<b>Green</b>", parse_mode="HTML", thread_ts="42")
    comms_ops(operation="history", channel="slack", chat_id="C123", limit=20)
    comms_ops(operation="history", channel="teams", chat_id="19:abc123", limit=20)
    comms_ops(operation="search", channel="slack", query="release checklist")
    comms_ops(operation="react", channel="slack", chat_id="C123",
              thread_ts="1234567890.123456", emoji="white_check_mark")
    comms_ops(operation="edit", channel="telegram", chat_id="111",
              thread_ts="42", text="corrected")
    comms_ops(operation="delete", channel="slack", chat_id="C123",
              thread_ts="1234567890.123456")
    comms_ops(operation="auth", channel="teams")     # start/poll device flow
    comms_ops(operation="send", channel="teams", chat_id="steve",
              text="Hey - on my way")
    comms_ops(operation="send", channel="signal", chat_id="+436991234567",
              text="Ping from the fleet")
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
            if channel == "signal":
                result = await signal.status()
                return {"message": "signal status", **result}
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
            if channel == "signal":
                return {
                    "success": True,
                    "message": "signal allowlist",
                    "channel": "signal",
                    "threads": signal.allow_recipients(),
                }
            if channel == "slack":
                live = await slack.list_channels()
                if live.get("success"):
                    return {
                        "success": True,
                        "message": "slack channels",
                        "channel": "slack",
                        "threads": live.get("channels"),
                        "allowlist": live.get("allowlist"),
                        "source": "live",
                    }
                return {
                    "success": True,
                    "message": "slack allowlist (live list failed)",
                    "channel": "slack",
                    "threads": live.get("allowlist", slack.allow_channels()),
                    "source": "allowlist",
                    "warning": live.get("error"),
                }
            if channel == "teams":
                live = await teams.list_chats()
                if live.get("success"):
                    return {
                        "success": True,
                        "message": "teams chats",
                        "channel": "teams",
                        "threads": live.get("chats"),
                        "allowlist": live.get("allowlist"),
                        "source": "live",
                    }
                return {
                    "success": True,
                    "message": "teams allowlist (live list failed)",
                    "channel": "teams",
                    "threads": teams.allow_list(),
                    "source": "allowlist",
                    "warning": live.get("error"),
                }
            enriched = []
            for cid in chat_allowlist():
                info = await telegram.get_chat(cid)
                enriched.append(
                    {"id": cid, "title": info.get("title", cid) if info.get("success") else cid}
                )
            return {
                "success": True,
                "message": "telegram chats",
                "channel": "telegram",
                "threads": enriched,
            }
        if operation == "send":
            if not chat_id:
                error = "chat_id required"
                return {"success": False, "message": error, "error": error}
            return await _do_send(
                channel, chat_id, text, thread_ts=thread_ts, parse_mode=parse_mode
            )
        if operation == "auth":
            if channel == "teams":
                result = teams.auth_status()
                return {"message": "teams device-flow status", **result}
            error = f"auth not supported for channel {channel}"
            return {"success": False, "message": error, "error": error}
        if operation == "read_recent":
            if channel == "telegram":
                await telegram.poll_updates()
            if channel == "signal":
                await signal.poll_receive()
            if channel == "slack" and chat_id:
                live = await slack.channel_history(chat_id, limit=limit)
                if live.get("success"):
                    return {
                        "success": True,
                        "message": f"{len(live.get('messages', []))} slack messages",
                        "channel": "slack",
                        "messages": live.get("messages"),
                        "source": "live",
                    }
            if channel == "teams" and chat_id:
                target = teams._cfg_recipients().get(chat_id, chat_id)
                live = await teams.chat_messages(target, limit=limit)
                if live.get("success"):
                    return {
                        "success": True,
                        "message": f"{len(live.get('messages', []))} teams messages",
                        "channel": "teams",
                        "messages": live.get("messages"),
                        "source": "live",
                    }
                return {"success": False, "message": "teams history failed", **live}
            messages = store.list_inbound(chat_id=chat_id or "", limit=limit)
            return {
                "success": True,
                "message": f"{len(messages)} recent messages",
                "messages": messages,
            }
        if operation == "history":
            if chat_id is None:
                error = "chat_id required"
                return {"success": False, "message": error, "error": error}
            if channel == "slack":
                result = await slack.channel_history(chat_id, limit=limit)
                return {"message": "slack history", **result}
            if channel == "teams":
                target = teams._cfg_recipients().get(chat_id, chat_id)
                result = await teams.chat_messages(target, limit=limit)
                return {"message": "teams history", **result}
            if channel == "signal":
                error = "signal has no history API — use read_recent (polls new messages)"
                return {"success": False, "message": error, "error": error}
            error = f"history only supported for channels slack/teams, got {channel}"
            return {"success": False, "message": error, "error": error}
        if operation == "search":
            if channel != "slack":
                error = f"search only supported for channel slack, got {channel}"
                return {"success": False, "message": error, "error": error}
            result = await slack.search_messages(query, count=limit)
            return {"message": "slack search", **result}
        if operation == "react":
            if channel != "slack":
                error = f"react only supported for channel slack, got {channel}"
                return {"success": False, "message": error, "error": error}
            if not chat_id or not thread_ts or not emoji:
                error = "chat_id + thread_ts (message ts) + emoji required"
                return {"success": False, "message": error, "error": error}
            result = await slack.add_reaction(chat_id, thread_ts, emoji)
            return {"message": "slack react", **result}
        if operation == "edit":
            if not chat_id or not thread_ts:
                error = "chat_id + thread_ts (message id/ts) + text required"
                return {"success": False, "message": error, "error": error}
            if channel == "telegram":
                result = await telegram.edit_message(chat_id, thread_ts, text)
                return {"message": "telegram edit", **result}
            if channel == "slack":
                result = await slack.edit_message(chat_id, thread_ts, text)
                return {"message": "slack edit", **result}
            if channel == "teams":
                target = teams._cfg_recipients().get(chat_id, chat_id)
                result = await teams.edit_message(target, thread_ts, text)
                return {"message": "teams edit", **result}
            error = f"edit not supported for channel {channel}"
            return {"success": False, "message": error, "error": error}
        if operation == "delete":
            if not chat_id or not thread_ts:
                error = "chat_id + thread_ts (message id/ts) required"
                return {"success": False, "message": error, "error": error}
            if channel == "telegram":
                result = await telegram.delete_message(chat_id, thread_ts)
                return {"message": "telegram delete", **result}
            if channel == "slack":
                result = await slack.delete_message(chat_id, thread_ts)
                return {"message": "slack delete", **result}
            if channel == "teams":
                target = teams._cfg_recipients().get(chat_id, chat_id)
                result = await teams.delete_message(target, thread_ts)
                return {"message": "teams delete", **result}
            error = f"delete not supported for channel {channel}"
            return {"success": False, "message": error, "error": error}
        if operation == "help":
            return {
                "success": True,
                "message": "comms-mcp channel setup",
                "setup": (
                    "Telegram: BotFather -> token; COMMS_TELEGRAM_BOT_TOKEN + "
                    "COMMS_TELEGRAM_CHAT_IDS; comms_ops(operation='status'). "
                    "Send supports thread_ts (reply_to message id) + parse_mode HTML. "
                    "edit/delete need chat_id + thread_ts (message id). "
                    "WhatsApp: start wa-sidecar, scan QR, COMMS_WHATSAPP_ALLOW_NUMBERS. "
                    "status surfaces QR/pairing when disconnected. History = local store. "
                    "Teams: COMMS_GRAPH_CLIENT_ID + COMMS_TEAMS_RECIPIENTS, "
                    "comms_ops(operation='auth', channel='teams'). "
                    "history/read_recent/edit/delete need chat_id (name or 19:chat id); "
                    "send thread_ts = replyTo message id. "
                    "Slack: create app (Socket Mode, scopes channels:history, "
                    "channels:read, chat:write, reactions:write, search:read), invite "
                    "bot, set COMMS_SLACK_APP_TOKEN + COMMS_SLACK_BOT_TOKEN + "
                    "COMMS_SLACK_CHANNEL_IDS. history/search/react/edit/delete need chat_id. "
                    "Signal: COMMS_SIGNAL_NUMBER (dedicated!) + COMMS_SIGNAL_RECIPIENTS + "
                    "sidecar (Docker, auto-started from Settings). Link by QR or "
                    "register by SMS/voice; read_recent polls (no history API). "
                    "Retention: COMMS_RETENTION_DAYS (7)"
                ),
            }
        error = f"unknown operation {operation}"
        return {"success": False, "message": error, "error": error}
    except Exception as exc:
        return _error_response(operation, channel, str(exc))


async def _do_send(
    channel: str,
    chat_id: str,
    text: str,
    thread_ts: str | None = None,
    parse_mode: str | None = None,
) -> dict[str, Any]:
    """Enqueue, dispatch to the channel adapter, and record the outbox result.

    Normalizes each adapter's success signal (telegram uses 'ok', the others
    'success') into a single outbox-aware response.
    """
    entry = store.enqueue(channel, chat_id, text)
    extra: dict[str, Any] = {}
    try:
        if channel == "telegram":
            result = await telegram.send_message(
                chat_id, text, reply_to=thread_ts, parse_mode=parse_mode
            )
            ok = bool(result.get("ok"))
            if ok:
                extra["message_id"] = (result.get("result") or {}).get("message_id")
            error = str(result.get("description", result))
        elif channel == "whatsapp":
            result = await whatsapp.send_message(chat_id, text)
            ok = bool(result.get("success"))
            error = str(result.get("error", "send failed"))
        elif channel == "slack":
            result = await slack.send_message(chat_id, text, thread_ts=thread_ts)
            ok = bool(result.get("success"))
            extra["ts"] = result.get("ts") if ok else None
            extra["thread_ts"] = result.get("thread_ts") if ok and result.get("thread_ts") else None
            error = str(result.get("error", "send failed"))
        elif channel == "teams":
            result = await teams.send_message(chat_id, text, reply_to=thread_ts)
            ok = bool(result.get("success"))
            extra["chat_id"] = result.get("chat_id") if ok else None
            error = str(result.get("error", "send failed"))
        elif channel == "signal":
            result = await signal.send_message(chat_id, text)
            ok = bool(result.get("success"))
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
