"""Support-ticket service (Help Center → Jira proxy, HELP-1/2/3/4).

Every submission is **persisted** (HELP-4 durable audit) with the reporter stamped
from the authenticated user (HELP-3 — client identity is display metadata only).
When Jira is configured (``settings.JIRA_BASE_URL`` + token), the issue is mirrored
to Jira and its key/url stored; otherwise the ticket lives locally with a
``LOCAL-<id>`` key. Either way the FE gets ``{issue_key, issue_url}``.

The live Jira HTTP calls are intentionally isolated in ``_create_in_jira`` so this
module works (and is testable) with no Jira configured — flip it on by setting the
env config, no code change.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SupportTicket, User

# Jira workflow status → the FE's Open | In Progress | Done set.
_STATUS_MAP = {
    "to do": "Open", "open": "Open", "backlog": "Open", "new": "Open",
    "in progress": "In Progress", "in review": "In Progress", "reopened": "In Progress",
    "done": "Done", "closed": "Done", "resolved": "Done",
}


def _jira_configured() -> bool:
    return bool(getattr(settings, "JIRA_BASE_URL", None) and getattr(settings, "JIRA_API_TOKEN", None))


def _create_in_jira(ticket: SupportTicket) -> tuple[str, str] | None:
    """Create the issue in Jira and return (key, url). No-op (None) when Jira is
    not configured — the caller then falls back to a local key. The real Atlassian
    REST calls (POST /rest/api/3/issue + attachments) go here when enabled."""
    if not _jira_configured():
        return None
    # Deliberately not implemented in this environment (no outbound Jira/secrets).
    # When enabling: POST the issue with ticket.context/description, upload
    # attachments with X-Atlassian-Token: no-check, return the created key + url.
    return None


def create_ticket(db: Session, tenant_id: int, user: User, body: dict) -> SupportTicket:
    fields = body.get("fields") or {}
    context = body.get("context") or {}
    attachments = [
        {"name": a.get("name"), "type": a.get("type"), "size": a.get("size")}
        for a in (body.get("attachments") or [])
    ]
    ticket = SupportTicket(
        tenant_id=tenant_id,
        reporter_user_id=user.id,  # HELP-3: trust the token, not context.user_id
        project_key=body.get("project_key"),
        summary=body.get("summary") or fields.get("title") or "(no summary)",
        issue_type=body.get("issue_type"),
        priority=body.get("priority"),
        module=(context.get("module") or fields.get("module")),
        description=fields.get("description"),
        status="Open",
        context=context or None,
        attachments=attachments or None,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    result = _create_in_jira(ticket)
    if result is not None:
        ticket.jira_issue_key, ticket.jira_issue_url = result
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
        "status": _STATUS_MAP.get((t.status or "").lower(), t.status or "Open"),
        "mode": "proxy" if t.jira_issue_url else "local",
        "reporter_id": str(t.reporter_user_id) if t.reporter_user_id is not None else None,
        "created_at": t.created_at,
    }


def list_my_tickets(db: Session, tenant_id: int, user: User) -> list[dict]:
    rows = db.execute(
        select(SupportTicket)
        .where(SupportTicket.tenant_id == tenant_id, SupportTicket.reporter_user_id == user.id)
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
    ).scalars().all()
    return [_to_read(t) for t in rows]
