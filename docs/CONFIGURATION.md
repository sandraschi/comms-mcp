# Configuration

All settings via env (prefix `COMMS_`) or `.env`:

| Var | Default | Purpose |
|---|---|---|
| `COMMS_TELEGRAM_BOT_TOKEN` | "" | Telegram bot token (@BotFather) |
| `COMMS_TELEGRAM_CHAT_IDS` | "" | Comma-separated chat-id allowlist (send gate) |
| `COMMS_TELEGRAM_API_BASE` | https://api.telegram.org | API base (tests/proxy) |
| `COMMS_DB_PATH` | data/comms.db | SQLite store (WAL) |
| `COMMS_RETENTION_DAYS` | 7 | Inbound body TTL |
| `MCP_PORT` / `PORT` | — | HTTP daemon port (else stdio) |
| `MCP_HOST` | 127.0.0.1 | Daemon bind |
