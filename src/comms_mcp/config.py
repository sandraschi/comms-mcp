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
    port: int = 11028

    # Telegram (v0.1)
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""  # comma-separated allowlist
    telegram_api_base: str = "https://api.telegram.org"

    # Storage / retention
    db_path: Path = Path("data/comms.db")
    retention_days: int = 7  # message-body TTL; metadata kept longer


def get_settings() -> Settings:
    return Settings()


def chat_allowlist() -> list[str]:
    return [c.strip() for c in get_settings().telegram_chat_ids.split(",") if c.strip()]
