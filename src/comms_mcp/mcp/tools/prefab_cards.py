"""Prefab UI cards (@mcp.tool(app=True)) for comms-mcp.

Rendered inline in hosts that support MCP Apps; plain-text hosts fall back to
the tool's text summary.
"""

from __future__ import annotations

import logging

from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Separator,
    Text,
)

from ...config import chat_allowlist
from ...outbox import sqlite as store
from ...registry import mcp

log = logging.getLogger("comms_mcp.prefab")


@mcp.tool(app=True)
async def comms_show_status() -> PrefabApp:
    """COMMS_SHOW_STATUS - Live comms-mcp status as a rich in-chat card.

    Renders bot identity, allowlist size, outbox delivery counts, and inbound
    totals. Hosts without MCP Apps render the text fallback.

    ## Return Format
    PrefabApp card + text summary.

    ## Examples
    comms_show_status()
    """
    from ...adapters import telegram

    try:
        ok = await telegram.get_me()
        configured = bool(ok.get("ok"))
        bot = (ok.get("result") or {}).get("username")
    except Exception as exc:  # a probe failure must not blank the card
        log.warning("status card telegram probe failed: %s", exc)
        configured, bot = False, None

    allow = chat_allowlist()
    stats = store.status_counts()
    outbox = stats.get("outbox", {}) or {}
    total = sum(outbox.values())

    with Card(css_class="max-w-2xl") as view:
        with CardHeader():
            CardTitle("comms-mcp status")
        with CardContent():
            Text(
                f"Bot: {'@' + bot if configured and bot else 'not configured'}",
                css_class="text-sm",
            )
            Text(f"Allowlist: {len(allow)} chats", css_class="text-sm")
            Separator(spacing=3)
            Text("Outbox", css_class="font-semibold text-sm mb-1")
            for status, n in sorted(outbox.items()):
                Badge(f"{status}: {n}", variant="secondary")
            Separator(spacing=3)
            Text(
                f"Outbox total: {total} · inbound: {stats.get('inbound_total', 0)}",
                css_class="text-sm text-muted-foreground",
            )

    return PrefabApp(view=view, title="comms-mcp status")
