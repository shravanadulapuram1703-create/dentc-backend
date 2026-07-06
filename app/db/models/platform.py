"""Platform / cross-cutting models.

support_tickets (Help → Jira proxy, durable audit) · utility_runs (Utilities →
execution/audit history).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin


class SupportTicket(Base, IntPKMixin, CreatedAtMixin):
    """HELP-1/2/4: a support ticket filed from the Help Center. Persisted durably
    (tenant-wide audit) and, when Jira is configured, mirrored to a Jira issue —
    otherwise it lives locally with a ``LOCAL-<id>`` key. Reporter is always the
    authenticated user (client-supplied identity is display metadata only)."""

    __tablename__ = "support_tickets"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    reporter_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    project_key: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(String(500))
    issue_type: Mapped[str | None] = mapped_column(String(30))
    priority: Mapped[str | None] = mapped_column(String(20))
    module: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="Open")  # Open|In Progress|Done|Failed
    jira_issue_key: Mapped[str | None] = mapped_column(String(50), index=True)
    jira_issue_url: Mapped[str | None] = mapped_column(String(500))
    context: Mapped[dict | None] = mapped_column(JSON)
    attachments: Mapped[list | None] = mapped_column(JSON)  # [{name,type,size,url}]


class UtilityRun(Base, IntPKMixin, CreatedAtMixin):
    """UTIL-1/2: one execution of an administrative utility — the durable,
    tenant-wide audit + job record the Utilities dashboard reads. The actual batch
    business logic per utility is separate; this records the run lifecycle."""

    __tablename__ = "utility_runs"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    utility_id: Mapped[str] = mapped_column(String(100), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    run_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted|running|completed|failed
    parameters: Mapped[dict | None] = mapped_column(JSON)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    logs: Mapped[list | None] = mapped_column(JSON)  # ["line", ...]
    finished_at: Mapped[datetime | None]
