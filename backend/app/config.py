from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Clerk
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""

    # Database
    database_url: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Cron secret (protects /api/cron/check)
    cron_secret: str = ""

    # CORS
    frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env"}


settings = Settings()
