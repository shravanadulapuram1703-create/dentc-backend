"""Support-ticket service (Help Center → Jira proxy, HELP-1/2/3/4).

Every submission is **persisted** (HELP-4 durable audit) with the reporter stamped
from the authenticated user (HELP-3 — client identity is display metadata only).
When Jira is configured (``JIRA_BASE_URL`` + ``JIRA_EMAIL`` + ``JIRA_API_TOKEN``),
the issue is mirrored to Jira Cloud and its key/url stored, attachments uploaded,
and "My Tickets" shows live status; otherwise the ticket lives locally with a
``LOCAL-<id>`` key. Either way the FE gets ``{issue_key, issue_url}``.

All outbound Atlassian calls are isolated in ``app.integrations.jira_client`` so
this module (and the whole test suite) works with no Jira configured — flip it on
via env, no code change.
"""

from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.db.models import SupportTicket, User
from app.integrations import jira_client

logger = get_logger(__name__)

# Jira workflow status → the FE's Open | In Progress | Done set.
_STATUS_MAP = {
    "to do": "Open", "open": "Open", "backlog": "Open", "new": "Open",
    "in progress": "In Progress", "in review": "In Progress", "reopened": "In Progress",
    "done": "Done", "closed": "Done", "resolved": "Done",
}


def _map_status(raw: str | None) -> str:
    return _STATUS_MAP.get((raw or "").lower(), raw or "Open")


def _push_to_jira(
    ticket: SupportTicket, raw_attachments: list[dict], description_adf: dict | None
) -> list[dict] | None:
    """Create the issue in Jira and upload attachments. Returns the (possibly
    enriched) attachment metadata to persist, or raises :class:`~app.integrations.
    jira_client.JiraError` on a create failure. No-op caller path handles the
    "not configured" case — this is only invoked when Jira is on."""
    requested = ticket.issue_type or settings.JIRA_DEFAULT_ISSUE_TYPE
    issue_type = settings.JIRA_ISSUE_TYPE_MAP.get(requested, requested)
    project_key = ticket.project_key or settings.JIRA_PROJECT_KEY
    kw = dict(
        project_key=project_key,
        summary=ticket.summary,
        priority=ticket.priority or settings.JIRA_DEFAULT_PRIORITY,
        description_adf=description_adf or _fallback_adf(ticket),
        reporter_account_id=settings.JIRA_REPORTER_ACCOUNT_ID,
    )
    try:
        created = jira_client.create_issue(issue_type=issue_type, **kw)
    except jira_client.JiraError as exc:
        # A project may not have the requested issue type — retry once with the
        # configured default so the ticket is never lost to a bad type name.
        fallback = settings.JIRA_DEFAULT_ISSUE_TYPE
        if "issuetype" in exc.message.lower() and issue_type != fallback:
            logger.warning("Issue type %r rejected; retrying as %r", issue_type, fallback)
            created = jira_client.create_issue(issue_type=fallback, **kw)
        else:
            raise
    ticket.jira_issue_key = created["key"]
    ticket.jira_issue_url = created["url"] or jira_client.issue_browse_url(created["key"])

    # Attachments are best-effort: a failed upload must not lose the issue.
    stored: list[dict] = []
    for att in raw_attachments:
        meta = {"name": att.get("name"), "type": att.get("type"), "size": att.get("size")}
        data_b64 = att.get("data_base64")
        if data_b64:
            try:
                content = base64.b64decode(data_b64)
            except (ValueError, TypeError):
                logger.warning("Skipping attachment with invalid base64: %s", meta["name"])
                content = None
            if content is not None:
                uploaded = jira_client.add_attachment(
                    ticket.jira_issue_key, meta["name"] or "attachment", content, meta["type"]
                )
                if uploaded and uploaded.get("content"):
                    meta["url"] = uploaded["content"]
        stored.append(meta)
    return stored or None


def _fallback_adf(ticket: SupportTicket) -> dict:
    """Minimal ADF doc from the plain-text description — used only when the FE did
    not send a pre-built ``description_adf`` (so an issue is never created empty)."""
    text = ticket.description or ticket.summary or ""
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}] if text else []}],
    }


def create_ticket(db: Session, tenant_id: int, user: User, body: dict) -> SupportTicket:
    fields = body.get("fields") or {}
    context = dict(body.get("context") or {})
    raw_attachments = list(body.get("attachments") or [])
    description_adf = body.get("description_adf")

    ticket = SupportTicket(
        tenant_id=tenant_id,
        reporter_user_id=user.id,  # HELP-3: trust the token, not context.user_id
        project_key=body.get("project_key") or settings.JIRA_PROJECT_KEY,
        summary=body.get("summary") or fields.get("title") or "(no summary)",
        issue_type=body.get("issue_type"),
        priority=body.get("priority"),
        module=(context.get("module") or fields.get("module")),
        description=fields.get("description"),
        status="Open",
        context=context or None,
        # Sanitized meta first; enriched with the Jira attachment url after upload.
        attachments=[
            {"name": a.get("name"), "type": a.get("type"), "size": a.get("size")}
            for a in raw_attachments
        ] or None,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)  # need ticket.id for the LOCAL fallback key

    if jira_client.is_configured():
        try:
            stored = _push_to_jira(ticket, raw_attachments, description_adf)
            if stored is not None:
                ticket.attachments = stored
        except jira_client.JiraError as exc:
            # Persist the failure for audit, then surface it so the FE offers Retry.
            ticket.status = "Failed"
            db.commit()
            logger.warning("Support ticket %s: Jira create failed: %s", ticket.id, exc.message)
            raise AppError(exc.message, code="jira_error", status_code=502) from exc
    else:
        ticket.jira_issue_key = f"LOCAL-{ticket.id}"  # durable, browsable in "My Tickets"

    db.commit()
    db.refresh(ticket)
    return ticket


def _to_read(t: SupportTicket) -> dict:
    return {
        "id": t.id,
        "issue_key": t.jira_issue_key,
        "issue_url": t.jira_issue_url,
        "title": t.summary,
        "issue_type": t.issue_type,
        "priority": t.priority,
        "module": t.module,
        "status": _map_status(t.status),
        "mode": "proxy" if t.jira_issue_url else "local",
        "reporter_id": str(t.reporter_user_id) if t.reporter_user_id is not None else None,
        "created_at": t.created_at,
    }


def _sync_status(db: Session, tickets: list[SupportTicket]) -> None:
    """HELP-2: refresh live Jira status for Jira-backed tickets that aren't already
    terminal. Best-effort — a Jira hiccup leaves the stored status untouched."""
    changed = False
    for t in tickets:
        if not t.jira_issue_url or not t.jira_issue_key or t.jira_issue_key.startswith("LOCAL-"):
            continue
        if _map_status(t.status) == "Done":
            continue
        raw = jira_client.get_status(t.jira_issue_key)
        mapped = _map_status(raw) if raw else None
        if mapped and mapped != t.status:
            t.status = mapped
            changed = True
    if changed:
        db.commit()


def list_my_tickets(db: Session, tenant_id: int, user: User) -> list[dict]:
    rows = db.execute(
        select(SupportTicket)
        .where(SupportTicket.tenant_id == tenant_id, SupportTicket.reporter_user_id == user.id)
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
    ).scalars().all()

    if settings.JIRA_STATUS_SYNC and jira_client.is_configured():
        _sync_status(db, rows)

    return [_to_read(t) for t in rows]
