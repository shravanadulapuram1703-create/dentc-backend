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

    # ── Email (Microsoft Graph transport — preferred) ────────────────────────
    # App-only (client-credentials) sending via Graph ``sendMail``. Preferred over
    # SMTP because it works with Entra Security Defaults enabled, needs no mailbox
    # password, and is unaffected by the Dec-2026 SMTP basic-auth retirement.
    # All three of tenant/client/secret must be set to activate this transport.
    GRAPH_TENANT_ID: str | None = None
    GRAPH_CLIENT_ID: str | None = None
    GRAPH_CLIENT_SECRET: str | None = None
    # Mailbox to send as. Falls back to EMAIL_FROM. The app registration should be
    # scoped (Exchange application access policy) so it can *only* send as this one.
    GRAPH_SENDER: str | None = None
    GRAPH_TIMEOUT_SECONDS: int = 15
    # Keep a copy in the mailbox's Sent Items. Off by default — reset mails are
    # high-volume and low-value to retain.
    GRAPH_SAVE_TO_SENT_ITEMS: bool = False

    # ── Email (SMTP transport — legacy fallback) ─────────────────────────────
    # Used only when Graph is not configured. When neither is configured the
    # integration stays in log-only mode (links written to the logs) so dev works
    # without creds.
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
    # NOTE-DOC-3: ``UPLOAD_DIR`` holds BOTH branding assets (logos, watermarks) and
    # PHI (patient documents, claim/progress-note attachments). Only these subdirs
    # are mounted as public static files; everything else under UPLOAD_DIR is
    # reachable exclusively through an authenticated, tenant-checked ``/content``
    # endpoint. Adding a subdir here makes it world-readable — do not add a PHI one.
    UPLOAD_PUBLIC_SUBDIRS: list[str] = Field(
        default_factory=lambda: ["logos", "office_logos", "provider_watermarks"]
    )

    # ── Imaging / object storage (GCS) ───────────────────────────────────────
    # DICOM originals + derived (thumbnail/web) buckets. When both are unset the
    # imaging serving layer runs in "proxy" mode (streams through the API) so dev
    # works without cloud creds; when set and signing credentials are available it
    # issues short-lived V4 signed URLs straight to GCS.
    GCS_BUCKET_ORIGINALS: str | None = None
    GCS_BUCKET_DERIVED: str | None = None
    # Path to a service-account JSON key for GCS. If unset, Application Default
    # Credentials are used (the norm on Cloud Run). Set this for local dev.
    GCS_CREDENTIALS_PATH: str | None = None
    GCS_ORIGINALS_PREFIX: str = "dicom"
    GCS_DERIVED_PREFIX: str = "v1"
    # TTL of the GCS signed URL the browser is redirected to (short — it's a
    # direct-to-bucket PHI link).
    IMAGING_SIGNED_URL_TTL_SECONDS: int = 900  # 15 min
    # TTL of the stable, browser-facing asset token embedded in <img src> URLs.
    # Longer, so an open gallery keeps working; the token authorises one asset.
    IMAGING_ASSET_TOKEN_TTL_SECONDS: int = 24 * 3600
    # "auto" = signed URLs when GCS signing works, else proxy; force with gcs|proxy.
    IMAGING_URL_MODE: Literal["auto", "gcs", "proxy"] = "auto"
    # Log every imaging binary read to audit_logs (HIPAA access trail).
    IMAGING_AUDIT_READS: bool = True

    # ── Patient documents / consent forms (object storage, LTR-1) ────────────
    # The practice keeps every consent PDF in a cloud bucket, not on the app
    # server's disk (a Cloud Run container restart loses local uploads and nothing
    # else in the estate can find them). When GCS_BUCKET_DOCUMENTS is set,
    # ``patient-documents`` writes there; leave it unset and uploads stay on the
    # local filesystem so dev/tests work without cloud creds.
    GCS_BUCKET_DOCUMENTS: str | None = None          # e.g. "reco-documents"
    # Object-key prefix per document class. ``consent-form`` uploads land under
    # CONSENT prefix (gs://<bucket>/consent-forms/{tenant}/{patient}/{uuid}.pdf);
    # everything else under the generic prefix.
    GCS_CONSENT_FORMS_PREFIX: str = "consent-forms"
    GCS_DOCUMENTS_PREFIX: str = "patient-documents"
    # The document_type values routed to the consent-forms prefix. ``CF`` is the
    # code the Notes screen sends for "Consent Form" (NOTE-DOC-4); without it a
    # consent uploaded from Notes would land under the generic prefix.
    CONSENT_DOCUMENT_TYPES: list[str] = Field(
        default_factory=lambda: ["consent-form", "consent_form", "consent", "CF"]
    )
    # ── Patient-document upload rules (NOTE-DOC-5) ───────────────────────────
    # Enforced server-side by ``app.core.filestore.validate_upload`` on every
    # binary upload route, and published verbatim by
    # ``GET /patient-documents/limits`` so the UI states the same numbers.
    DOCUMENT_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    DOCUMENT_ALLOWED_TYPES: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/tiff",
            "image/bmp",
            "image/webp",
        ]
    )
    # Browsers and scanners routinely send ``application/octet-stream`` (or a
    # wrong type) for a perfectly good PDF, so the extension is the second half
    # of the check — a file passes when BOTH its extension and its declared type
    # are acceptable, and an unhelpful declared type defers to the extension.
    DOCUMENT_ALLOWED_EXTENSIONS: list[str] = Field(
        default_factory=lambda: [
            ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp", ".webp",
        ]
    )
    # TTL of the GCS signed URL handed to the browser for a document (PHI link).
    DOCUMENT_SIGNED_URL_TTL_SECONDS: int = 900  # 15 min
    # "auto" = signed URL when GCS signing works, else the API proxy; force with
    # gcs|proxy (proxy always returns the /patient-documents/{id}/content URL).
    DOCUMENT_URL_MODE: Literal["auto", "gcs", "proxy"] = "auto"
    # Absolute, browser-reachable origin of THIS API. Used to fully-qualify
    # ``file_url`` (LTR-1 ask #2 — the frontend cannot resolve a server-relative
    # path against a different origin). Unset = relative URLs, as before.
    PUBLIC_API_BASE_URL: str | None = None

    # ── Letters (server-side merge/render, LTR-5) ────────────────────────────
    # Cap on how many patients one batch letter run may cover in a request.
    LETTERS_BATCH_MAX_PATIENTS: int = 500

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

    # ── AppointNow (external online booking) ─────────────────────────────────
    # AN-8: how long a public request soft-holds its slot against concurrent
    # requests before availability treats the slot as free again.
    APPOINTNOW_HOLD_TTL_MINUTES: int = 15
    # AN-3 anti-abuse: per-IP/office throttle on the public intake write.
    APPOINTNOW_RATE_LIMIT_MAX: int = 10
    APPOINTNOW_RATE_LIMIT_WINDOW_MINUTES: int = 10
    # AN-3: Cloudflare Turnstile. When the secret is unset, verification is skipped
    # (dev/tests); when set, a missing/invalid token is a 403 on the public write.
    APPOINTNOW_TURNSTILE_SECRET: str | None = None
    APPOINTNOW_TURNSTILE_VERIFY_URL: str = (
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    # AN-2: short TTL on the cached availability response (public, cacheable).
    APPOINTNOW_AVAILABILITY_CACHE_SECONDS: int = 30

    # ── Jira (Help Center → support tickets, HELP-1/2/3) ─────────────────────
    # The server holds the Jira secret; the browser never sees it. When
    # JIRA_BASE_URL + JIRA_EMAIL + JIRA_API_TOKEN are all set, support tickets are
    # mirrored to Jira Cloud (REST v3). Leave any of them unset to stay in the
    # zero-config "local" mode (tickets persist with a LOCAL-<id> key, no outbound
    # call) so dev/tests work without Atlassian creds.
    JIRA_BASE_URL: str | None = None            # e.g. https://your-site.atlassian.net
    JIRA_EMAIL: str | None = None               # Atlassian account email (Basic-auth user)
    JIRA_API_TOKEN: str | None = None           # Atlassian API token (the SECRET)
    # Default project the issue is filed in when the FE omits project_key.
    JIRA_PROJECT_KEY: str = "SUP"
    # Fallbacks when the FE omits issue_type / priority.
    JIRA_DEFAULT_ISSUE_TYPE: str = "Bug"
    JIRA_DEFAULT_PRIORITY: str = "Medium"
    # FE issue-type name → Jira issue-type name, for projects that don't have every
    # FE type (e.g. a team-managed board with no "Support"/"Improvement"/"New
    # Feature"). JSON object in env, e.g.
    #   JIRA_ISSUE_TYPE_MAP={"Support":"Task","Improvement":"Story","New Feature":"Story"}
    # Unmapped names pass through unchanged; a create that still 400s on issuetype
    # falls back to JIRA_DEFAULT_ISSUE_TYPE so a ticket is never lost.
    JIRA_ISSUE_TYPE_MAP: dict[str, str] = Field(default_factory=dict)
    # Many Jira projects don't expose the Priority field on the create screen —
    # sending it then 400s the whole create. Set false to omit it.
    JIRA_INCLUDE_PRIORITY: bool = True
    # Optional: file every issue as this Atlassian accountId (a single service
    # account). When unset, Jira uses the token owner as reporter; the real
    # end-user is always captured in the issue's Environment block regardless.
    JIRA_REPORTER_ACCOUNT_ID: str | None = None
    # When true, "My Tickets" (HELP-2) refreshes each Jira-backed ticket's live
    # status on read and persists the mapped Open|In Progress|Done value.
    JIRA_STATUS_SYNC: bool = True
    # Per-call timeout for the outbound Atlassian REST calls.
    JIRA_TIMEOUT_SECONDS: int = 15

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
