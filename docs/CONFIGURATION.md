# Configuration

All settings via env (prefix `COMMS_`) or `.env`:

| Var | Default | Purpose |
|---|---|---|
| `COMMS_TELEGRAM_BOT_TOKEN` | "" | Telegram bot token (@BotFather) |
| `COMMS_TELEGRAM_CHAT_IDS` | "" | Comma-separated chat-id allowlist (send gate) |
| `COMMS_TELEGRAM_API_BASE` | https://api.telegram.org | API base (tests/proxy) |
| `COMMS_SLACK_APP_TOKEN` | "" | Slack Socket Mode app token (xapp-*) |
| `COMMS_SLACK_BOT_TOKEN` | "" | Slack Web API bot token (xoxb-*) |
| `COMMS_SLACK_CHANNEL_IDS` | "" | Comma-separated channel allowlist |
| `COMMS_GRAPH_CLIENT_ID` | "" | Azure app (public) client id - reuse email-mcp's `EMAIL_MCP_OAUTH_CLIENT_ID` |
| `COMMS_TEAMS_RECIPIENTS` | "" | Teams allowlist: `name=email` or `name=19:chatId` |
| `COMMS_TEAMS_TOKEN_FILE` | data/teams_oauth.json | Teams OAuth token store (device flow) |
| `COMMS_TEAMS_GRAPH_BASE` | https://graph.microsoft.com/v1.0 | Graph API base |
| `COMMS_DB_PATH` | data/comms.db | SQLite store (WAL) |
| `COMMS_RETENTION_DAYS` | 7 | Inbound body TTL |
| `MCP_PORT` / `PORT` | — | HTTP daemon port (else stdio) |
| `MCP_HOST` | 127.0.0.1 | Daemon bind |
