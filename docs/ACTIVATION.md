# Activate comms — channel setup checklist

All three channels behind `comms_ops(operation=…, channel=…)`. Each is a
2-minute setup; do them in any order. Everything stays in `.env` (never
committed).

## 0. Prereq

```powershell
cd comms-mcp
copy .env.example .env
just serve          # backend on :11028 (or MCP_PORT daemon)
```

Verify: `comms_ops(operation="help")` and `http://127.0.0.1:11028/health`.

## 1. Telegram (v0.1)

1. In Telegram: open **@BotFather** → `/newbot` → name it → copy the token.
2. `.env`:
   ```
   COMMS_TELEGRAM_BOT_TOKEN=123456:ABC…
   COMMS_TELEGRAM_CHAT_IDS=
   ```
3. Message the bot once, then:
   `comms_ops(operation="read_recent", channel="telegram")` — the chat id
   appears in the result. Add it to `COMMS_TELEGRAM_CHAT_IDS` and restart.
4. Verify: `comms_ops(operation="status", channel="telegram")` → `configured: true`,
   then Test send from the console (:11029) or
   `comms_ops(operation="send", channel="telegram", chat_id="<id>", text="hi")`.

## 2. WhatsApp (v0.2, baileys sidecar)

1. Start the sidecar:
   ```powershell
   cd comms-mcp\wa-sidecar
   npm install        # once
   node index.js      # listens on :10709
   ```
2. Open `http://127.0.0.1:10709/qr` in a browser — **scan the QR with
   WhatsApp → Linked devices** on the phone that owns the number.
   (`/qr` shows `pairing_code` too, for the phone-number pairing flow.)
3. `.env`:
   ```
   COMMS_WHATSAPP_SIDECAR_URL=http://127.0.0.1:10709
   COMMS_WHATSAPP_ALLOW_NUMBERS=+43699…
   ```
4. Verify: `comms_ops(operation="status", channel="whatsapp")` →
   `connected: true`; then send a test to your own number.

## 3. Slack (v0.3, official SDK — no sidecar)

1. api.slack.com → **Create New App** (from scratch) →
   - App-Level Tokens: generate an `xapp-*` token with `connections:write`
   - Bot Token Scopes: `chat:write`, `channels:history`, `groups:history`
   - **Enable Socket Mode** (Events tab: enable, subscribe to
     `message.channels` + `message.groups`)
   - Install to workspace → copy the `xoxb-*` bot token
2. Invite the bot to the channels it should read/write.
3. `.env`:
   ```
   COMMS_SLACK_APP_TOKEN=xapp-…
   COMMS_SLACK_BOT_TOKEN=xoxb-…
   COMMS_SLACK_CHANNEL_IDS=C01ABC…,C02DEF…
   ```
4. Restart the backend — the socket listener starts automatically.
5. Verify: `comms_ops(operation="status", channel="slack")` →
   `configured: true` + team; send a test; message the bot → `read_recent`
   shows the sanitized inbound.

## Gotchas

- WhatsApp QR expires ~60s — refresh `/qr` if it goes stale.
- Slack inbound arrives via Socket Mode in real time; the server must be
  running (it is not persisted across restarts — the listener lives in the
  process).
- Telegram `read_recent` pulls via long-poll; inbound arrives on demand.
- All inbound is sanitized (prompt-injection neutralized) and retained
  `COMMS_RETENTION_DAYS` (7).

