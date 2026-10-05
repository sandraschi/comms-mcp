"""Configuration via pydantic-settings (env prefix COMMS_)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COMMS_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    host: str = "127.0.0.1"
    port: int = 11205

    # Telegram (v0.1)
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""  # comma-separated allowlist
    telegram_api_base: str = "https://api.telegram.org"

    # WhatsApp (v0.2, via Node baileys sidecar)
    whatsapp_sidecar_url: str = "http://127.0.0.1:11208"
    whatsapp_allow_numbers: str = ""  # comma-separated E.164 allowlist

    # Slack (v0.3, official SDK, Socket Mode)
    slack_app_token: str = ""  # xapp-* (Socket Mode, connections:write)
    slack_bot_token: str = ""  # xoxb-* (Web API)
    slack_channel_ids: str = ""  # comma-separated channel allowlist

    # Teams (v0.4, Microsoft Graph app - delegated device flow)
    # Reuse the same Azure app registration as email-mcp's
    # EMAIL_MCP_OAUTH_CLIENT_ID; no Bot Framework/bot registration needed.
    graph_client_id: str = ""  # Azure app (public) client id for the Graph app
    teams_recipients: str = ""  # comma-separated allowlist: name=email or name=19:chatId
    teams_token_file: Path = Path("data/teams_oauth.json")
    teams_graph_base: str = "https://graph.microsoft.com/v1.0"

    # Storage / retention
    db_path: Path = Path("data/comms.db")
    retention_days: int = 7  # message-body TTL; metadata kept longer

    # Inbound webhook (wa-sidecar -> POST /api/v1/inbound/wa). Optional shared
    # secret: when set, the sidecar must send it as X-Comms-Secret and the
    # backend 401s without it. Same-machine default is empty (localhost bind).
    inbound_secret: str = ""

    # HTTP daemon base URL for the stdio probe (else 127.0.0.1:MCP_PORT).
    daemon_url: str = ""


def get_settings() -> Settings:
    return Settings()


def chat_allowlist() -> list[str]:
    return [c.strip() for c in get_settings().telegram_chat_ids.split(",") if c.strip()]


def teams_allowlist() -> dict[str, str]:
    """Parse COMMS_TEAMS_RECIPIENTS 'name=email|19:chatId' pairs into a name->target map.

    Bare entries (no '=') are keyed by themselves. The map keys are the
    friendly names an agent sends to; the values are the email or chat id.
    """
    out: dict[str, str] = {}
    for part in get_settings().teams_recipients.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, target = part.split("=", 1)
            out[name.strip()] = target.strip()
        else:
            out[part] = part
    return out
