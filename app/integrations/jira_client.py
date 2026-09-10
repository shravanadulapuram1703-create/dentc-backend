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


def _normalize_adf(doc: Any) -> Any:
    """Repair the most common ADF mistake before sending to Jira: the top-level
    ``doc`` node MUST carry ``version`` at the top level (Jira 400s
    ``{"type":"doc","attrs":{"version":1}}`` as "not valid ADF content"). Moves a
    stray ``attrs.version`` up and defaults ``version`` to 1 when missing. Any
    non-doc / non-dict value is returned untouched."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        return doc
    out = dict(doc)
    attrs = out.get("attrs")
    if isinstance(attrs, dict) and "version" in attrs:
        out.setdefault("version", attrs["version"])
        rest = {k: v for k, v in attrs.items() if k != "version"}
        if rest:
            out["attrs"] = rest
        else:
            out.pop("attrs", None)
    if "version" not in out:
        out["version"] = 1
    return out


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
        fields["description"] = _normalize_adf(description_adf)
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


def get_statuses(issue_keys: list[str]) -> dict[str, str]:
    """Bulk variant of :func:`get_status`: one JQL search per 100 keys
    (POST /rest/api/3/search/jql — the GET /search endpoint is deprecated on
    Jira Cloud). Returns ``{issue_key: raw_status_name}`` for every issue Jira
    returned; keys Jira didn't return are simply absent. Never raises."""
    out: dict[str, str] = {}
    keys = [k for k in issue_keys if k]
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        jql = "key in (" + ",".join(chunk) + ")"
        try:
            with _client() as client:
                resp = client.post(
                    "/rest/api/3/search/jql",
                    json={"jql": jql, "fields": ["status"], "maxResults": len(chunk)},
                )
            if resp.status_code >= 300:
                logger.warning("Jira bulk status failed (%s): %s", resp.status_code, _short_error(resp))
                continue
            for issue in (resp.json() or {}).get("issues") or []:
                key = issue.get("key")
                name = (((issue.get("fields") or {}).get("status") or {}).get("name"))
                if key and name:
                    out[key] = name
        except Exception as exc:  # noqa: BLE001 — status sync is best-effort
            logger.warning("Jira bulk status error: %s", exc)
    return out


def list_transitions(issue_key: str) -> list[dict[str, Any]]:
    """Return the workflow transitions currently available on an issue
    (GET .../transitions) as ``[{"id", "name", "to": {"name"}}, ...]``.

    Raises :class:`JiraError` on any failure — the caller decides whether a
    status change can proceed without Jira agreeing to it."""
    try:
        with _client() as client:
            resp = client.get(f"/rest/api/3/issue/{issue_key}/transitions")
    except httpx.HTTPError as exc:
        raise JiraError(f"Could not reach Jira: {exc}") from exc
    if resp.status_code >= 300:
        raise JiraError(f"Jira transitions lookup failed ({resp.status_code}). {_short_error(resp)}",
                        status_code=resp.status_code)
    items = (resp.json() or {}).get("transitions") or []
    return [
        {"id": str(t.get("id")), "name": t.get("name"), "to": {"name": (t.get("to") or {}).get("name")}}
        for t in items
        if isinstance(t, dict)
    ]


def do_transition(issue_key: str, transition_id: str) -> None:
    """Apply one workflow transition to an issue (POST .../transitions).
    Raises :class:`JiraError` on any failure."""
    try:
        with _client() as client:
            resp = client.post(
                f"/rest/api/3/issue/{issue_key}/transitions",
                json={"transition": {"id": str(transition_id)}},
            )
    except httpx.HTTPError as exc:
        raise JiraError(f"Could not reach Jira: {exc}") from exc
    if resp.status_code >= 300:
        detail = _short_error(resp)
        logger.warning("Jira transition failed (%s) for %s: %s", resp.status_code, issue_key, detail)
        raise JiraError(f"Jira transition failed ({resp.status_code}). {detail}",
                        status_code=resp.status_code)
