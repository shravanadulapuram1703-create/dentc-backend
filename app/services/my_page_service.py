"""My Page self-service logic (profile, tasks, preferences, notifications).

Everything is derived from the auth token — a user only ever reads/writes their
own rows (MP tenant-isolation). No client-supplied user id is trusted.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import (
    Notification,
    Provider,
    User,
    UserPreference,
    UserTask,
)

_PREF_KEY = "ui_prefs"  # MP-4: single opaque JSON blob per user


# ── MP-1: profile ─────────────────────────────────────────────────────────────
def update_self(db: Session, user: User, data: dict) -> User:
    for key in ("first_name", "last_name", "phone", "email"):
        if key in data:
            setattr(user, key, data[key])
    try:
        db.commit()
    except Exception as exc:  # unique email, etc.  # noqa: BLE001
        db.rollback()
        raise ConflictError("Could not update profile (email may be in use)",
                            details=str(getattr(exc, "orig", exc))) from exc
    db.refresh(user)
    return user


# ── MP-7: the provider row linked to this user ───────────────────────────────
def linked_provider_id(db: Session, user_id: int) -> str | None:
    return db.execute(
        select(Provider.id).where(Provider.user_id == user_id, Provider.is_active.is_(True))
    ).scalars().first()


# ── MP-3: tasks ───────────────────────────────────────────────────────────────
def list_tasks(db: Session, user: User) -> list[UserTask]:
    return list(db.execute(
        select(UserTask).where(UserTask.user_id == user.id)
        .order_by(UserTask.is_done.asc(), UserTask.due_date.asc().nulls_last(), UserTask.id.desc())
    ).scalars().all())


def create_task(db: Session, user: User, data: dict) -> UserTask:
    task = UserTask(tenant_id=user.tenant_id, user_id=user.id, **data)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _own_task(db: Session, user: User, task_id: int) -> UserTask:
    task = db.get(UserTask, task_id)
    if task is None or task.user_id != user.id:
        raise NotFoundError(f"Task '{task_id}' was not found")
    return task


def update_task(db: Session, user: User, task_id: int, data: dict) -> UserTask:
    task = _own_task(db, user, task_id)
    for key, value in data.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user: User, task_id: int) -> None:
    task = _own_task(db, user, task_id)
    db.delete(task)
    db.commit()


# ── MP-4: preferences blob ────────────────────────────────────────────────────
def get_preferences(db: Session, user: User) -> dict:
    row = db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user.id, UserPreference.pref_key == _PREF_KEY
        )
    ).scalar_one_or_none()
    if row is None or not row.pref_value:
        return {}
    try:
        return json.loads(row.pref_value)
    except (ValueError, TypeError):
        return {}


def set_preferences(db: Session, user: User, preferences: dict) -> dict:
    row = db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user.id, UserPreference.pref_key == _PREF_KEY
        )
    ).scalar_one_or_none()
    payload = json.dumps(preferences)
    if row is None:
        row = UserPreference(tenant_id=user.tenant_id, user_id=user.id,
                             pref_key=_PREF_KEY, pref_value=payload)
        db.add(row)
    else:
        row.pref_value = payload
    db.commit()
    return preferences


# ── MP-6: notifications ───────────────────────────────────────────────────────
def list_notifications(db: Session, user: User, *, unread_only: bool = False, limit: int = 50) -> dict:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    items = list(db.execute(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    ).scalars().all())
    unread = db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
    ).scalar_one()
    return {"unread_count": unread, "items": items}


def mark_notification_read(db: Session, user: User, notif_id: int) -> Notification:
    notif = db.get(Notification, notif_id)
    if notif is None or notif.user_id != user.id:
        raise NotFoundError(f"Notification '{notif_id}' was not found")
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notif)
    return notif


def mark_all_read(db: Session, user: User) -> int:
    rows = db.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for n in rows:
        n.is_read = True
        n.read_at = now
    db.commit()
    return len(rows)
