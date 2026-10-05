# comms-mcp — Unified fleet comms gateway

![python](https://img.shields.io/badge/python-3.11%2B-blue) ![fastmcp](https://img.shields.io/badge/fastmcp-3.4-green) ![ruff](https://img.shields.io/badge/ruff-clean-green) ![tests](https://img.shields.io/badge/pytest-31%20passing-green)

One portmanteau tool, all messaging channels behind adapters. **v0.4 ships
Telegram, WhatsApp (baileys sidecar), Slack (Socket Mode), and Teams (Graph
device flow)** behind the same `comms_ops` surface.

| Surface | Detail |
|---|---|
| MCP tools | `comms_ops(operation=send\|read_recent\|list_threads\|status\|auth\|help, channel=…)` + `comms_shutdown(confirm=True)` + `comms_show_status()` (Prefab card) |
| MCP resource/prompt | `comms://status`, `comms_send_briefing`, skill `skill://comms` |
| Send | Allowlist-gated per channel, outbox-logged (pending/sent/failed) |
| Inbound | Sanitized (prompt-injection neutralized), **7-day body TTL** |
| Storage | SQLite WAL (`data/comms.db`) — delivery log + inbound with retention |
| Transports | stdio (Claude Desktop) + HTTP daemon (`MCP_PORT=11205`, MCP at `/mcp`) |
| Zero-pay | Telegram Bot API free; self-hosted sidecars; no cloud dependencies |

## Stack

- Backend: Python 3.11+, FastMCP 3.4, FastAPI, pydantic-settings, httpx, slack-sdk
- Console: React 18 + Vite 5 + TailwindCSS 3 + Lucide + Framer Motion + axios + **zustand** + react-router (**bun** for install/scripts, Vite stays on Node)
- Sidecar: Node + baileys + express (`wa-sidecar/`, port 11208)
- Quality: ruff (incl. T20), pyright, pytest + coverage gate, Biome + tsc, pre-commit

## Quick start

```powershell
git clone https://github.com/sandraschi/comms-mcp
cd comms-mcp
copy .env.example .env     # per-channel tokens + allowlists (see docs/ONBOARDING.md)
just serve                 # or: uv run python -m comms_mcp
```

Then, in any MCP client:

```
comms_ops(operation="status")                       # telegram health + allowlist + stats
comms_ops(operation="send", chat_id="123456", text="hello")
comms_ops(operation="read_recent")                  # pulls + lists inbound
comms_ops(operation="status", channel="whatsapp")   # pairing / connection
comms_ops(operation="auth", channel="teams")        # device-code flow
```

Claude Desktop config snippet:

```json
{
  "mcpServers": {
    "comms": { "command": "uv", "args": ["run", "--project", "D:/Dev/repos/comms-mcp", "python", "-m", "comms_mcp"] }
  }
}
```

## Env vars

| Var | Purpose |
|---|---|
| `COMMS_TELEGRAM_BOT_TOKEN` / `COMMS_TELEGRAM_CHAT_IDS` | Telegram token (@BotFather) + chat-id allowlist |
| `COMMS_WHATSAPP_SIDECAR_URL` / `COMMS_WHATSAPP_ALLOW_NUMBERS` | Sidecar URL (:11208) + E.164 allowlist |
| `COMMS_SLACK_APP_TOKEN` / `COMMS_SLACK_BOT_TOKEN` / `COMMS_SLACK_CHANNEL_IDS` | Socket Mode + Web API + channel allowlist |
| `COMMS_GRAPH_CLIENT_ID` / `COMMS_TEAMS_RECIPIENTS` | Azure app id + `name=email\|19:chatId` allowlist |
| `COMMS_DB_PATH` / `COMMS_RETENTION_DAYS` / `COMMS_INBOUND_SECRET` | Store path / body TTL (7) / webhook secret |
| `MCP_PORT` / `MCP_HOST` / `COMMS_DAEMON_URL` | Daemon port/host / stdio probe target |

## Ports

| Port | Use |
|---|---|
| 11205 | Backend (FastAPI REST + FastMCP `/mcp`; serves console from `web_sota/dist`) |
| 11204 | Console dev server (Vite, proxies `/api` → :11205) |
| 11208 | WhatsApp baileys sidecar |

## Security model

- **Allowlist**: send is blocked for recipients outside the channel allowlist.
- **Sanitization**: inbound bodies are stripped of zero-width/control chars and
  wrapped when they look like prompt-injection payloads.
- **Retention**: message bodies auto-purge after `COMMS_RETENTION_DAYS` (7);
  metadata is kept.
- **Secrets**: tokens live in `.env` only (env-ref, never committed); the
  wa-sidecar webhook accepts an optional shared secret (`COMMS_INBOUND_SECRET`).

## Docs

- [Install](INSTALL.md) · [Onboarding](docs/ONBOARDING.md) · [Tools](docs/TOOLS.md) ·
  [Configuration](docs/CONFIGURATION.md) · [Architecture](docs/ARCHITECTURE.md) ·
  [Development](docs/DEVELOPMENT.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Changelog](CHANGELOG.md) · [Full LLM reference](llms-full.txt) ·
  [Assessment 2026-10-05](docs/assess-reports/2026-10-05.md)
