# Onboarding — comms-mcp

comms-mcp is a unified fleet messaging gateway: one `comms_ops` tool sends and
reads Telegram, WhatsApp, Slack, and Teams. Set up any channel in ~2 minutes;
each is independent — do them in any order.

## What it costs

Nothing. Telegram Bot API is free. WhatsApp uses your own phone number as a
linked companion device (self-hosted baileys sidecar, no per-message fees).
Slack needs a free Slack workspace + app. Teams reuses an Azure app registration
(free tier); the Graph delegated flow costs nothing. No cloud LLM, no paid API.

## Channel setup

### 0. Prereq (all channels)

```powershell
cd comms-mcp
copy .env.example .env
just serve          # backend on :11205 (HTTP daemon via MCP_PORT, else stdio)
```

Sanity: `http://127.0.0.1:11205/health` returns `{"status":"ok",...}` and
`comms_ops(operation="help")` lists per-channel steps.

### 1. Telegram (2 min)

1. In Telegram open **@BotFather** → `/newbot` → name it → copy the token.
2. `.env`: `COMMS_TELEGRAM_BOT_TOKEN=<token>`, leave `COMMS_TELEGRAM_CHAT_IDS=`
   empty for now. Restart the backend.
3. Message the bot once, then `comms_ops(operation="read_recent")` — your chat
   id appears in the result. Add it to `COMMS_TELEGRAM_CHAT_IDS`, restart.
4. Verify: `comms_ops(operation="status")` shows `configured: true`, or use the
   console Test-send card on the Dashboard (:11204 or :11205).

### 2. WhatsApp (3 min, phone needed)

1. `cd wa-sidecar; npm install; node index.js` (or install the
   `comms-mcp-wa` NSSM service via `scripts/install-services.ps1`).
2. `comms_ops(operation="status", channel="whatsapp")` — on first run it reports
   pairing; open the sidecar `/qr` URL and scan it with WhatsApp on the phone
   (Settings → Linked devices). Auth persists in `data/wa-auth/`.
3. `.env`: `COMMS_WHATSAPP_ALLOW_NUMBERS=+43699...,+...` (E.164).

### 3. Slack (5 min, workspace admin)

1. Create an app at api.slack.com: enable **Socket Mode**, add scopes
   `channels:history`, `chat:write`, install to the workspace.
2. `.env`: `COMMS_SLACK_APP_TOKEN=xapp-...`, `COMMS_SLACK_BOT_TOKEN=xoxb-...`,
   `COMMS_SLACK_CHANNEL_IDS=C123...` (invite the bot to each channel first).
3. Verify: `comms_ops(operation="status", channel="slack")`.

### 4. Teams (5 min, work/school identity)

Graph Teams chat APIs need an organizational identity; personal consumer
accounts have limited `/chats` support.

1. `.env`: `COMMS_GRAPH_CLIENT_ID=<email-mcp's EMAIL_MCP_OAUTH_CLIENT_ID>`
   (same Azure app registration, no bot registration needed).
2. `.env`: `COMMS_TEAMS_RECIPIENTS=steve=steve@example.com`.
3. `comms_ops(operation="auth", channel="teams")` → open the shown
   microsoft.com/devicelogin URL, enter the code, call `auth` again to confirm.
4. Verify: `comms_ops(operation="status", channel="teams")`.

## Pitfalls

- **Send blocked**: the chat/number/channel is not in the allowlist env for that
  channel. Send is server-side gated — the error names the allowlist.
- **Telegram 404 from API**: token pasted with the `bot` prefix, or revoked —
  regenerate via @BotFather.
- **WhatsApp 503 "not connected"**: sidecar running but phone link dropped —
  re-scan the QR (GET sidecar `:11208/qr`).
- **Slack "not in channel"**: invite the bot user into the channel first.
- **Teams "could not resolve a chat"**: consumer identity or unknown email —
  use a work/school account and an exact email/UPN.
- **Two backends, two databases**: the NSSM service and an interactive
  `just serve` each own their store unless `COMMS_DB_PATH` is absolute and
  shared. The installer pins it; interactive runs default to `data/comms.db`
  under the repo root.

## Sanity check (fresh install)

1. `GET /health` → 200. 2. `comms_ops(operation="status")` per channel →
   `configured` matches what you set up. 3. Send one test message from the
   console, then confirm it in `GET /api/v1/outbox?status=sent`.
