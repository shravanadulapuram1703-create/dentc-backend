"""Cross-workstation push for procedure-entry writes (PROC-INT-3).

Four screens write procedures, and until now the only thing keeping them in step
was **client-side**: after a write the browser invalidated its own react-query
caches and broadcast on a ``BroadcastChannel`` to its *own* other tabs. Another
user's workstation kept a 30 s-stale cache until the component remounted — so a
front-desk charge posted against a planned crown did not close that item on the
hygienist's chart.

Every write path into ``patient_procedures`` and ``treatment_plan_items`` (the
CRUD routes, the Post-to-Ledger endpoint) calls :func:`announce` after its
commit. The event rides the **existing messaging WebSocket** — the client already
holds that socket for DMs and presence — on the tenant-wide topic
(:func:`messaging_events.publish_tenant`), so there is no second socket to open
and nothing per-patient to subscribe to; the client drops envelopes whose
``patient_id`` it is not showing. Same delivery contract as messaging: Redis
Pub/Sub across gunicorn workers when Redis is up, in-process otherwise, and
always best-effort — a fan-out failure never fails the write that already landed.

Envelope (ids are strings, matching the messaging wire format)::

    {
      "type": "procedures.changed",
      "patient_id": "33618",
      "source": "patient_procedures" | "treatment_plan_items",
      "action": "created" | "updated" | "deleted" | "posted" | "voided",
      "id": "<row id>",
      "treatment_plan_id": "<plan id or null>",
      "treatment_plan_item_id": "<item id or null>",
      "actor_user_id": "<user id or null>",
      "at": "<ISO-8601 UTC>"
    }
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.services import messaging_events

logger = get_logger(__name__)

EVENT_TYPE = "procedures.changed"


def _s(value: Any) -> str | None:  # noqa: ANN401
    return None if value is None else str(value)


def build_envelope(
    patient_id: int | str,
    *,
    source: str,
    action: str,
    entity_id: Any,  # noqa: ANN401
    treatment_plan_id: Any = None,  # noqa: ANN401
    treatment_plan_item_id: Any = None,  # noqa: ANN401
    actor_user_id: Any = None,  # noqa: ANN401
) -> dict:
    return {
        "type": EVENT_TYPE,
        "patient_id": _s(patient_id),
        "source": source,
        "action": action,
        "id": _s(entity_id),
        "treatment_plan_id": _s(treatment_plan_id),
        "treatment_plan_item_id": _s(treatment_plan_item_id),
        "actor_user_id": _s(actor_user_id),
        "at": datetime.now(UTC).isoformat(),
    }


def announce(tenant_id: int | None, patient_id: int | str | None, **kwargs: Any) -> None:  # noqa: ANN401
    """Publish a ``procedures.changed`` event to the tenant. Never raises."""
    if tenant_id is None or patient_id is None:
        return
    try:
        messaging_events.publish_tenant(int(tenant_id), build_envelope(patient_id, **kwargs))
    except Exception as exc:  # noqa: BLE001 - best-effort by contract
        logger.warning("procedures.changed announce failed for patient %s: %s", patient_id, exc)
