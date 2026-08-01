"""Jira Cloud REST v3 client — the *only* place the Atlassian secret is used.

Isolating every outbound Atlassian call here means the rest of the app (and the
whole test suite) works with **no Jira configured**: ``is_configured()`` returns
False and the support-ticket service falls back to durable local storage. Flip it
on by setting ``JIRA_BASE_URL`` + ``JIRA_EMAIL`` + ``JIRA_API_TOKEN`` (HELP-3) —
no code change.

Auth is HTTP Basic ``email:api_token`` (the standard for Jira Cloud API tokens).
The token is a server-side secret and is never returned to the browser.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class JiraError(Exception):
    """A Jira REST call failed (non-2xx or transport error). Carries a short,
    safe message for the caller to surface; the token is never included."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_configured() -> bool:
    """True when Jira Cloud creds are fully configured (base URL + email + token)."""
    return bool(settings.JIRA_BASE_URL and settings.JIRA_EMAIL and settings.JIRA_API_TOKEN)


def _base() -> str:
    return (settings.JIRA_BASE_URL or "").rstrip("/")


def issue_browse_url(issue_key: str | None) -> str | None:
    """Human browse URL for an issue key, e.g. https://site.atlassian.net/browse/SUP-1."""
    if not issue_key or not settings.JIRA_BASE_URL:
        return None
    return f"{_base()}/browse/{issue_key}"


def _auth_header() -> str:
    raw = f"{settings.JIRA_EMAIL}:{settings.JIRA_API_TOKEN}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=_base(),
        headers={"Authorization": _auth_header(), "Accept": "application/json"},
        timeout=settings.JIRA_TIMEOUT_SECONDS,
    )


def _short_error(resp: httpx.Response) -> str:
    """Best-effort human message from a Jira error body (errorMessages / errors),
    truncated so we never dump a huge payload into a client-facing error."""
    try:
        data = resp.json()
        parts: list[str] = list(data.get("errorMessages") or [])
        errs = data.get("errors")
        if isinstance(errs, dict):
            parts += [f"{k}: {v}" for k, v in errs.items()]
        if parts:
            return "; ".join(parts)[:300]
    except Exception:  # noqa: BLE001 — fall back to raw text
        pass
    return (resp.text or resp.reason_phrase or "")[:300]


def create_issue(
    *,
    project_key: str,
    summary: str,
    issue_type: str,
    priority: str | None,
    description_adf: dict[str, Any] | None,
    reporter_account_id: str | None = None,
) -> dict[str, str]:
    """Create a Jira issue (POST /rest/api/3/issue). Returns ``{"key", "url"}``.

    Raises :class:`JiraError` on any failure — the caller records the ticket as
    ``Failed`` and surfaces the message (with a Retry) to the user.
    """
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary[:255],  # Jira caps the summary field at 255 chars
        "issuetype": {"name": issue_type},
    }
    if description_adf:
        fields["description"] = description_adf
    if priority and settings.JIRA_INCLUDE_PRIORITY:
        fields["priority"] = {"name": priority}
    if reporter_account_id:
        fields["reporter"] = {"id": reporter_account_id}

    try:
        with _client() as client:
            resp = client.post("/rest/api/3/issue", json={"fields": fields})
    except httpx.HTTPError as exc:  # transport/timeout/DNS
        raise JiraError(f"Could not reach Jira: {exc}") from exc

    if resp.status_code >= 300:
        detail = _short_error(resp)
        logger.warning("Jira create failed (%s): %s", resp.status_code, detail)
        raise JiraError(f"Jira create failed ({resp.status_code}). {detail}",
                        status_code=resp.status_code)

    key = resp.json().get("key")
    if not key:
        raise JiraError("Jira create returned no issue key")
    return {"key": key, "url": issue_browse_url(key) or ""}


def add_attachment(
    issue_key: str, filename: str, content: bytes, content_type: str | None
) -> dict[str, Any] | None:
    """Upload one attachment to an issue (POST .../attachments, X-Atlassian-Token:
    no-check). Returns the first attachment object Jira reports (``{id, content,
    filename, ...}``) or None. Never raises — a failed attachment must not lose an
    already-created issue (mirrors the frontend ``direct`` transport)."""
    try:
        with _client() as client:
            resp = client.post(
                f"/rest/api/3/issue/{issue_key}/attachments",
                headers={"X-Atlassian-Token": "no-check"},
                files={"file": (filename, content, content_type or "application/octet-stream")},
            )
        if resp.status_code >= 300:
            logger.warning("Jira attachment upload failed (%s) for %s: %s",
                           resp.status_code, issue_key, _short_error(resp))
            return None
        items = resp.json()
        return items[0] if isinstance(items, list) and items else None
    except Exception as exc:  # noqa: BLE001 — issue survives a failed attachment
        logger.warning("Jira attachment upload error for %s: %s", issue_key, exc)
        return None


def get_status(issue_key: str) -> str | None:
    """Return an issue's raw Jira status name (e.g. "In Progress"), or None on any
    failure. Never raises — status sync is best-effort over a live cache."""
    try:
        with _client() as client:
            resp = client.get(f"/rest/api/3/issue/{issue_key}", params={"fields": "status"})
        if resp.status_code >= 300:
            return None
        return (((resp.json() or {}).get("fields") or {}).get("status") or {}).get("name")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Jira status fetch error for %s: %s", issue_key, exc)
        return None
