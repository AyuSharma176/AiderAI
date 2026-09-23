from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet
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
    gmail_integration_enabled: bool = False
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    google_oauth_redirect_uri: str = (
        "http://localhost:8000/api/v1/integrations/gmail/callback"
    )
    google_oauth_authorization_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_oauth_token_endpoint: str = "https://oauth2.googleapis.com/token"
    google_oauth_revoke_endpoint: str = "https://oauth2.googleapis.com/revoke"
    gmail_api_root: str = "https://gmail.googleapis.com/gmail/v1/users/me"
    gmail_token_encryption_keys: list[SecretStr] = []
    gmail_import_months: int = 12
    gmail_sync_interval_minutes: int = 30
    gmail_max_message_bytes: int = 1_000_000
    gmail_message_id_pepper: SecretStr | None = None
    frontend_url: str = "http://localhost:5173"
    integration_sync_rate_limit: int = 3

    @model_validator(mode="after")
    def require_provider_key(self) -> "Settings":
        if self.app_env == "production" and (
            self.gemini_api_key is None or not self.gemini_api_key.get_secret_value()
        ):
            raise ValueError("GEMINI_API_KEY is required in production")
        if self.app_env == "production" and self.gmail_integration_enabled:
            has_client_id = bool(self.google_oauth_client_id)
            has_client_secret = bool(
                self.google_oauth_client_secret
                and self.google_oauth_client_secret.get_secret_value()
            )
            if not has_client_id or not has_client_secret:
                raise ValueError("Google OAuth client ID and secret are required")
            if not self.google_oauth_redirect_uri.startswith("https://"):
                raise ValueError("Google OAuth redirect URI must use HTTPS")
            provider_endpoints = (
                self.google_oauth_authorization_endpoint,
                self.google_oauth_token_endpoint,
                self.google_oauth_revoke_endpoint,
                self.gmail_api_root,
            )
            if any(not endpoint.startswith("https://") for endpoint in provider_endpoints):
                raise ValueError("Google provider endpoints must use HTTPS")
            if not self.gmail_token_encryption_keys:
                raise ValueError("Google OAuth token encryption key is required")
            try:
                for key in self.gmail_token_encryption_keys:
                    Fernet(key.get_secret_value().encode())
            except (TypeError, ValueError) as exc:
                raise ValueError("Google OAuth token encryption key is invalid") from exc
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
