# Troubleshooting — comms-mcp

## status shows configured:false

Token missing/empty for that channel. Check `.env` names: `COMMS_TELEGRAM_BOT_TOKEN`,
`COMMS_SLACK_APP_TOKEN` + `COMMS_SLACK_BOT_TOKEN`, `COMMS_GRAPH_CLIENT_ID`.
The backend reads `.env` at startup — restart after editing. (The console
reads the same backend, so a stale daemon shows stale status: restart it.)

## send blocked: "not in allowlist"

The recipient is outside the channel allowlist env (`COMMS_TELEGRAM_CHAT_IDS`,
`COMMS_WHATSAPP_ALLOW_NUMBERS`, `COMMS_SLACK_CHANNEL_IDS`,
`COMMS_TEAMS_RECIPIENTS`). Add the id, restart. Find Telegram chat ids via
`comms_ops(operation="read_recent")` after messaging the bot once.

## Telegram 404 / "Not Found" from api.telegram.org

Token wrong (often pasted with the `bot` prefix — the token alone is enough) or
revoked. Regenerate with @BotFather.

## WhatsApp 503 "not connected"

Sidecar up but the phone link dropped. GET `http://127.0.0.1:11208/qr` and
re-scan (WhatsApp → Settings → Linked devices). Auth lives in `data/wa-auth/`;
delete that dir to force a fresh pairing.

## wa inbound 401 "unauthorized"

`COMMS_INBOUND_SECRET` is set on the backend but the sidecar does not send it.
Set `COMMS_INBOUND_SECRET` to the same value in the sidecar env (NSSM:
`comms-mcp-wa` AppEnvironmentExtra) and bounce both services.

## Slack errors

- `not_in_channel`: invite the bot user into the channel, then add the channel
  id to `COMMS_SLACK_CHANNEL_IDS`.
- Socket Mode disconnects: the app-level token needs `connections:write`; the
  listener only starts when both tokens are set (see backend log).

## Teams errors

- `not authorized`: run `comms_ops(operation="auth", channel="teams")`, enter
  the code at microsoft.com/devicelogin, call `auth` again.
- `could not resolve a Teams chat`: consumer (personal) identities have limited
  `/chats` support — use a work/school account; check the email/UPN spelling.
- Token refresh failures: delete `data/teams_oauth.json` and re-run `auth`.

## Two databases / messages "disappear"

An NSSM service plus an interactive `just serve` use different stores when the
DB path resolves differently. The installer pins absolute `COMMS_DB_PATH`; for
interactive runs set it explicitly if you run outside the repo root.

## Port already in use (:11205)

`start.ps1` clears the zombie holder before binding. If you launched manually,
stop the old process (or `POST /api/shutdown`) before starting another.

## Web console shows "not configured" but .env is set

The console shows the *backend's* status. A backend started before the `.env`
edit (or from another directory) does not see it — restart the backend from the
repo root.
