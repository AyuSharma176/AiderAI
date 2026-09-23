from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://supportai:supportai@postgres:5432/supportai"
    redis_url: str = "redis://redis:6379/0"
    gemini_api_key: SecretStr | None = None
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:5173"]
    upload_dir: str = "/app/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    retrieval_top_k: int = 5
    auth_rate_limit: int = 10
    chat_rate_limit: int = 30
    upload_rate_limit: int = 10
    rate_limit_window_seconds: int = 60

    @model_validator(mode="after")
    def require_provider_key(self) -> "Settings":
        if self.app_env == "production" and (
            self.gemini_api_key is None or not self.gemini_api_key.get_secret_value()
        ):
            raise ValueError("GEMINI_API_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
