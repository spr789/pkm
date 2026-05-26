"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # Telegram
    telegram_bot_token: SecretStr
    allowed_user_ids: str = ""

    # AI Providers
    openrouter_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    opencode_api_key: SecretStr | None = None
    sarvam_api_key: SecretStr | None = None

    # AI Configuration
    ai_default_provider: str = "gemini"
    ai_default_model: str = "gemini-2.0-flash"

    # Application
    env: str = "development"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        """Check if the application is running in production mode."""
        return self.env.lower() == "production"

    @property
    def allowed_user_id_list(self) -> list[int]:
        """Parse comma-separated allowed user IDs into a list of integers."""
        if not self.allowed_user_ids.strip():
            return []
        return [int(uid.strip()) for uid in self.allowed_user_ids.split(",") if uid.strip()]


settings = Settings()
