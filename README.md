# comms-mcp

One MCP tool that sends and reads messages on Telegram, WhatsApp, Slack,
Microsoft Teams, and Signal, with a local web console and a per-channel allowlist.

![python](https://img.shields.io/badge/python-3.11%2B-blue) ![fastmcp](https://img.shields.io/badge/fastmcp-3.4-green) ![ruff](https://img.shields.io/badge/ruff-clean-green) ![pytest](https://img.shields.io/badge/pytest-31%20passing-green) ![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue) ![license](https://img.shields.io/badge/license-MIT-green)

## What You Can Do

- **Send on any of five channels** from one tool: Telegram, WhatsApp (baileys
  sidecar), Slack (Socket Mode), Teams (Graph device flow), Signal (Docker
  bridge, dedicated number). `comms_ops(operation=...)`.
- **Read inbound** messages; bodies are sanitized and auto-expire after 7 days.
- **See every attempt**: a local outbox records sent / failed and the platform's reason.
- **Use the console** on `http://127.0.0.1:11205/` - dashboard, inbox, outbox,
  allowlist, chat, logs.
- **Stay local-first**: credentials in `.env` only, no cloud account required.

## Quick Install

Windows 10/11 - one command:

```powershell
git clone https://github.com/sandraschi/comms-mcp
cd comms-mcp
.\start.bat
```

`start.bat` installs **uv** if needed, syncs dependencies, starts the server and
opens the console. `start.bat -Check` tells you whether it will work here without
installing anything. `stop.bat` stops it. Every method: [INSTALL.md](INSTALL.md).

## Let your AI install it

Paste this into Claude Code, Cursor, Codex or Copilot:

```text
Set up comms-mcp on this PC for me: https://github.com/sandraschi/comms-mcp - follow docs/AI_SETUP.md in that repository.
```

It checks the machine first (installs nothing until that passes), then sets up the
server and connects it to your AI app.

## Example Prompts

- "Send 'fleet green' to my Telegram chat."
- "Do I have any new messages?"
- "Post the release announcement to the Slack channel."
- "Sign in to Teams and message Steve."
- "Why did my last WhatsApp send fail?"

## Ports

| Port | Use |
|---|---|
| 11205 | Backend (FastAPI REST + FastMCP `/mcp`; serves the console) |
| 11204 | Console dev server (Vite, optional) |
| 11208 | WhatsApp baileys sidecar |
| 18080 | Signal bridge (Docker) |

## Security Model

- **Allowlist** - send is blocked for recipients outside the channel allowlist.
- **Sanitization** - inbound bodies have zero-width/control chars stripped and
  prompt-injection-looking text wrapped.
- **Retention** - message bodies auto-purge after `COMMS_RETENTION_DAYS` (7).
- **Secrets** - credentials live in `.env` (never committed); the wa-sidecar
  webhook accepts an optional shared secret.
- **Local-first** - binds `127.0.0.1`; no telemetry.

## Fleet Crossconnects

Teams reuses the same Azure app registration as the fleet **email-mcp**
(`EMAIL_MCP_OAUTH_CLIENT_ID`). Optional; no companion server is required.

## Documentation

| Doc | Contents |
|---|---|
| [Installation](INSTALL.md) | All install methods, prerequisites |
| [Onboarding](docs/ONBOARDING.md) | Per-channel setup, costs, pitfalls |
| [AI setup](docs/AI_SETUP.md) | Install-for-me contract for coding agents |
| [Configuration](docs/CONFIGURATION.md) | Env vars, `.env` |
| [Architecture](docs/ARCHITECTURE.md) | Adapters, outbox, transports, ports |
| [Tools](docs/TOOLS.md) | Full MCP tool reference |
| [Development](docs/DEVELOPMENT.md) | Contributing, local setup |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues |

## Requirements

Windows 10/11. `start.bat` installs **uv** for you; nothing else is global. A
channel account (Telegram bot / WhatsApp phone / Slack workspace / Teams identity
/ Signal dedicated number)
is required per channel. The console needs no extra runtime once built.

## License

MIT - see [LICENSE](LICENSE).
