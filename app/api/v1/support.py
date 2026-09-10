"""Help Center support-ticket proxy (HELP-1/2). Server holds the Jira secret and
persists every submission; the reporter is the authenticated user."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.schemas.common import ErrorResponse
from app.schemas.support import (
    SupportTicketCreate,
    SupportTicketList,
    SupportTicketRead,
    SupportTicketResult,
    SupportTicketStatusUpdate,
)
from app.services import support_service

router = APIRouter(
    prefix="/support/tickets",
    tags=["Support"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


@router.post("", response_model=SupportTicketResult, operation_id="create_support_ticket",
             summary="File a support ticket (Jira proxy when configured, else local) — HELP-1")
def create_support_ticket(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                          body: SupportTicketCreate):
    ticket = support_service.create_ticket(db, tenant_id, current, body.model_dump())
    return SupportTicketResult(issue_key=ticket.jira_issue_key, issue_url=ticket.jira_issue_url)


@router.get("", response_model=SupportTicketList, operation_id="list_my_support_tickets",
            summary="List the caller's tickets with mapped status (HELP-2)")
def list_my_support_tickets(db: DbSession, tenant_id: TenantId, current: CurrentUser):
    return SupportTicketList(tickets=support_service.list_my_tickets(db, tenant_id, current))


@router.patch("/{ticket_id}", response_model=SupportTicketRead,
              operation_id="update_support_ticket_status",
              summary="Change the status of one of the caller's tickets (HELP-6)",
              responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
                         502: {"model": ErrorResponse}})
def update_support_ticket_status(db: DbSession, tenant_id: TenantId, current: CurrentUser,
                                 ticket_id: int, body: SupportTicketStatusUpdate):
    """Moves the ticket to ``Open`` / ``In Progress`` / ``Done``. When the ticket is
    mirrored in Jira, the matching workflow transition is applied there first so the
    two never disagree (409 if Jira offers no transition into that status, 502 if
    Jira is unreachable)."""
    return support_service.update_ticket_status(db, tenant_id, current, ticket_id, body.status)
