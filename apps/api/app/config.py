from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_env_file = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_env_file), extra="ignore")

    SUPABASE_URL: str
    DATABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str
    SECRET_KEY: str
    ANTHROPIC_API_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"
    FRONTEND_URL: str = "http://localhost:3000"
    # Comma-separated additional allowed CORS origins (e.g. apex domain, old deploy URL).
    CORS_ORIGINS: str = ""
    # Optional regex for allowed origins (e.g. r"https://(.*\.)?riphere\.com").
    CORS_ORIGIN_REGEX: str = ""
    API_URL: str = "http://localhost:8000"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""
    SLACK_SIGNING_SECRET: str = ""
    SLACK_HITL_CHANNEL: str = "general"
    HUNTER_API_KEY: str = ""
    # Gmail push notifications (Google Pub/Sub)
    GMAIL_WEBHOOK_SECRET: str = ""  # shared secret appended to webhook URL
    GMAIL_PUBSUB_TOPIC: str = ""    # e.g. projects/myproject/topics/gmail-push


settings = Settings()
