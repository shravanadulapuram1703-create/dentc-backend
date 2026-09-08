"""Real-time push for SMS activity (SMS-4).

The Messages tab polls ``GET /sms-messages`` every 15 s while visible. These
events ride the **existing messaging WebSocket** on the tenant-wide topic
(:func:`messaging_events.publish_tenant`) — the same seam procedure-entry uses
(PROC-INT-3) — so there is no second socket to open and nothing per-patient to
subscribe to; the client drops envelopes whose ``patient_id`` it is not showing
(or, for the practice-wide inbox, keeps all of them). Same delivery contract as
messaging: Redis Pub/Sub across gunicorn workers when Redis is up, in-process
otherwise, and always best-effort — a fan-out failure never fails the webhook
that already committed.

Envelopes (ids are strings, matching the messaging wire format)::

    {"type": "sms.inbound", "sms_message_id": "…", "patient_id": "…"|null,
     "office_id": "…"|null, "reply_intent": "confirm"|…|null,
     "needs_attention": bool, "at": "<ISO-8601 UTC>"}

    {"type": "sms.status", "sms_message_id": "…", "patient_id": "…"|null,
     "office_id": "…"|null, "send_status": "delivered", "at": "…"}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.services import messaging_events

logger = get_logger(__name__)

INBOUND_EVENT = "sms.inbound"
STATUS_EVENT = "sms.status"


def _s(value: Any) -> str | None:  # noqa: ANN401
    return None if value is None else str(value)


def _publish(tenant_id: int | None, envelope: dict) -> None:
    if tenant_id is None:
        return
    try:
        messaging_events.publish_tenant(int(tenant_id), envelope)
    except Exception as exc:  # noqa: BLE001 — never fail the caller
        logger.warning("SMS event publish failed for tenant %s: %s", tenant_id, exc)


def announce_inbound(row: Any) -> None:  # noqa: ANN401
    _publish(getattr(row, "tenant_id", None), {
        "type": INBOUND_EVENT,
        "sms_message_id": _s(row.id),
        "patient_id": _s(row.patient_id),
        "office_id": _s(row.office_id),
        "reply_intent": row.reply_intent,
        "needs_attention": bool(row.needs_attention),
        "at": datetime.now(UTC).isoformat(),
    })


def announce_status(row: Any) -> None:  # noqa: ANN401
    _publish(getattr(row, "tenant_id", None), {
        "type": STATUS_EVENT,
        "sms_message_id": _s(row.id),
        "patient_id": _s(row.patient_id),
        "office_id": _s(row.office_id),
        "send_status": row.send_status,
        "at": datetime.now(UTC).isoformat(),
    })
