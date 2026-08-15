# comms-mcp — Unified fleet comms gateway

One portmanteau tool, all messaging channels behind adapters. **v0.1 ships
Telegram** (Bot API — simplest headless E2E). Signal, WhatsApp (baileys) and
Slack adapters slot in behind the same `comms_ops` surface.

| Surface | Detail |
|---|---|
| MCP tool | `comms_ops(operation=send\|read_recent\|list_threads\|status\|help, channel=telegram, …)` |
| Send | Allowlist-gated (`COMMS_TELEGRAM_CHAT_IDS`), outbox-logged (pending/sent/failed) |
| Inbound | Polling `getUpdates`, sanitized (prompt-injection neutralized), **7-day body TTL** |
| Storage | SQLite WAL (`data/comms.db`) — delivery log + inbound with retention |
| Zero-pay | Telegram Bot API is free; no cloud dependencies |

## Quick start

```powershell
git clone https://github.com/sandraschi/comms-mcp
cd comms-mcp
copy .env.example .env     # set COMMS_TELEGRAM_BOT_TOKEN + COMMS_TELEGRAM_CHAT_IDS
just serve                 # or: uv run python -m comms_mcp
```

Then, in any MCP client:

```
comms_ops(operation="status")                       # bot + allowlist + stats
comms_ops(operation="send", chat_id="123456", text="hello")
comms_ops(operation="read_recent")                  # pulls + lists inbound
```

## Security model

- **Allowlist**: send is blocked for chats outside `COMMS_TELEGRAM_CHAT_IDS`.
- **Sanitization**: inbound bodies are stripped of zero-width/control chars and
  wrapped when they look like prompt-injection payloads (email-mcp pattern).
- **Retention**: message bodies auto-purge after `COMMS_RETENTION_DAYS` (7);
  metadata is kept.
- **Secrets**: token lives in `.env` only (env-ref, never committed).

## Docs

- [Install](INSTALL.md) · [Tools](docs/TOOLS.md) · [Configuration](docs/CONFIGURATION.md) ·
  [Architecture](docs/ARCHITECTURE.md)
- Channel rollout: P4 spec (`mcp-central-docs/operations/planning/specs/P4-comms-mcp.md`) —
  Telegram v0.1 → Signal + Slack v0.2 → WhatsApp v0.3 (baileys, self-hosted).
