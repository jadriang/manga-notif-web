from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    # Database (Supabase Postgres connection string)
    database_url: str = ""

    # Telegram
    telegram_bot_token: str = ""

    # Cron secret (protects /api/cron/check)
    cron_secret: str = ""

    # CORS
    frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env"}


settings = Settings()
