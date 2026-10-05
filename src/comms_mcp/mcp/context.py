"""Resources + prompts - live status data and send-flow templates."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ..config import chat_allowlist
from ..outbox import sqlite as store
from ..registry import mcp


@mcp.resource("comms://status")
async def comms_status_resource() -> dict:
    """Live comms status: telegram bot identity, allowlist, outbox stats."""
    from ..adapters import telegram

    ok = await telegram.get_me()
    return {
        "configured": bool(ok.get("ok")),
        "bot": (ok.get("result") or {}).get("username"),
        "allowlist": chat_allowlist(),
        "stats": store.status_counts(),
    }


@mcp.prompt("comms_send_briefing")
async def comms_send_briefing(
    channel: Annotated[
        str, Field(description="Channel: telegram, whatsapp, slack, teams.")
    ] = "telegram",
    chat_id: Annotated[str, Field(description="Recipient chat id / number / friendly name.")] = "",
    topic: Annotated[str, Field(description="One-line briefing topic.")] = "fleet status",
) -> str:
    """Prompt template for a channel briefing send (status -> allowlist -> send)."""
    return (
        f"Send a {topic} briefing via comms_ops on channel={channel}.\n"
        "1. comms_ops(operation='status', channel=<channel>) — confirm configured.\n"
        "2. comms_ops(operation='list_threads', channel=<channel>) — confirm the "
        f"recipient ({chat_id or '<chat_id>'}) is allowlisted.\n"
        "3. comms_ops(operation='send', ...) — send; on failure, report the error "
        "instead of retrying a blocked recipient."
    )
