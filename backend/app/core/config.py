from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"
    smtp_url: str = "smtp://localhost:1025"
    public_app_url: str = "http://localhost:8080"
    nexus_data_key: str
    current_policy_version: str = "privacy-2026-08-01"
    session_cookie_name: str = "nexus_session"
    session_ttl_seconds: int = 43200
    session_idle_seconds: int = 1800
    mfa_challenge_ttl_seconds: int = 300
    session_cookie_secure: bool = True
    trusted_proxy_ips: str = ""

    @field_validator("nexus_data_key")
    @classmethod
    def _require_32_byte_key(cls, value: str) -> str:
        if len(value.encode("utf-8")) != 32:
            raise ValueError("NEXUS_DATA_KEY must be exactly 32 bytes")
        return value


settings = Settings()
