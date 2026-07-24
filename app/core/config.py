"""Application configuration (twelve-factor: all config from the environment).

A single, validated ``Settings`` instance is exported as ``settings`` and imported
everywhere. ``DATABASE_URL`` may be provided directly or assembled from the
discrete ``DB_*`` parts used by the migration tooling.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger("app.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ────────────────────────────────────────────────────────────────
    APP_NAME: str = "Dental PMS API"
    ENV: Literal["dev", "staging", "prod"] = "dev"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ── Database ───────────────────────────────────────────────────────────
    # Provide DATABASE_URL directly, or leave blank to assemble from DB_* parts.
    DATABASE_URL: str | None = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "dental_pms"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""

    # Connection-pool tuning (overridable via env).
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_STATEMENT_TIMEOUT_MS: int = 30_000
    DB_ECHO: bool = False

    # ── Auth / JWT ─────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # ── Login throttling (failed-attempt lockout → HTTP 423) ─────────────────
    # Redis-backed; degrades to "no lockout" when Redis is unavailable.
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # ── Password reset / legacy activation tokens ────────────────────────────
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = 60
    LEGACY_ACTIVATION_TOKEN_TTL_MINUTES: int = 1440  # 24h
    # Base URL the emailed reset link points at (frontend route).
    PASSWORD_RESET_URL_BASE: str = "http://localhost:5173/reset-password"

    # ── Email (SMTP transport) ───────────────────────────────────────────────
    # When SMTP_HOST is unset, the email integration stays in log-only mode
    # (links are written to the logs instead of sent) so dev works without creds.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True  # STARTTLS on port 587; set False + SMTP_USE_SSL for 465
    SMTP_USE_SSL: bool = False  # implicit TLS (port 465)
    SMTP_TIMEOUT_SECONDS: int = 10
    # From-address shown to recipients. Falls back to SMTP_USER when unset.
    EMAIL_FROM: str | None = None
    EMAIL_FROM_NAME: str = "Dental PMS"

    # ── Redis (token store / blacklist) ────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_ENABLED: bool = True

    # ── CORS ───────────────────────────────────────────────────────────────
    # Explicit allowed origins (exact match). With credentials enabled, the
    # browser rejects a "*" response, so list real origins here. Local dev ports
    # are allowed by default; set CORS_ORIGINS in prod for any non-Cloud-Run host.
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8080",
            "https://reckondental.com",
            "https://www.reckondental.com",
        ]
    )
    # Regex fallback for origins that vary per deploy (e.g. Cloud Run URLs carry a
    # project-number hash). Matches any *.run.app frontend and any reckondental.com
    # subdomain by default. Set to a tighter pattern (or "" to disable) in production.
    CORS_ORIGIN_REGEX: str | None = r"https://([a-z0-9-]+\.)*(run\.app|reckondental\.com)"

    # ── Encryption (EIN, AI-assist secret, …) ────────────────────────────────
    # A urlsafe-base64 32-byte Fernet key. If unset, derived from JWT_SECRET_KEY.
    ENCRYPTION_KEY: str | None = None

    # ── Uploads (account logo) ───────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    UPLOAD_URL_BASE: str = "/uploads"
    LOGO_MAX_BYTES: int = 2 * 1024 * 1024  # 2 MB
    LOGO_ALLOWED_TYPES: list[str] = Field(default_factory=lambda: ["image/jpeg", "image/png"])

    # ── Direct Messaging ─────────────────────────────────────────────────────
    # Presence key TTL. Must exceed the client's 30s heartbeat with headroom, or a
    # slightly late ping flaps the user to offline (requirements §12).
    MESSAGING_PRESENCE_TTL_SECONDS: int = 45
    # Windows after which a message can no longer be changed (§29).
    MESSAGING_EDIT_WINDOW_SECONDS: int = 15 * 60
    MESSAGING_DELETE_WINDOW_SECONDS: int = 60 * 60
    # Message history page size (§17).
    MESSAGING_HISTORY_DEFAULT_LIMIT: int = 30
    MESSAGING_HISTORY_MAX_LIMIT: int = 100
    # Conversations included in the WS `sync` warm-up snapshot on connect.
    MESSAGING_SYNC_CONVERSATION_LIMIT: int = 50

    # ── Logging ────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            v = [o.strip() for o in v.split(",") if o.strip()]
        if isinstance(v, list):
            # Security: we always send `allow_credentials=True`. Starlette then
            # special-cases a `"*"` origin by reflecting *whatever* Origin the
            # request carried — effectively "allow any origin with credentials"
            # (a CSRF / data-exposure risk). Strip wildcards so only the explicit
            # allow-list + CORS_ORIGIN_REGEX can ever match. This neutralises a
            # stale `CORS_ORIGINS=*` env var without needing a redeploy env edit.
            cleaned = [o.strip() for o in v if isinstance(o, str) and o.strip() and o.strip() != "*"]
            if len(cleaned) != len([o for o in v if str(o).strip()]):
                _log.warning(
                    "CORS_ORIGINS contained a '*' wildcard; ignoring it because "
                    "allow_credentials is enabled. Use an explicit allow-list "
                    "(and CORS_ORIGIN_REGEX for per-deploy origins) instead."
                )
            return cleaned
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        password = quote_plus(self.DB_PASSWORD)
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
