"""Effective permissions for the signed-in user (EDIT-PLAN-5).

The rights catalog (``permissions``) and the group -> right assignment
(``user_group_rights``) existed, and ``GET /permissions`` listed all 529 codes,
but nothing answered *"which of these does the caller hold?"* — so the
frontend could not gate Edit Plan and the backend enforced nothing beyond the
coarse ``users.role``.

Model (deliberately the Phase-1 shape, not the deferred Phase-4 RBAC):

* A user's **effective codes** = the union of the rights of every active group
  they belong to.
* ``admin`` and ``super_admin`` hold **everything** — the role is the practice's
  own "full control" assertion and predates the catalog.
* A non-admin user who belongs to **no group** is *ungated*: the practice has
  not put them under the rights model yet, and refusing every write to such a
  user would lock a migrated tenant out of its own data the day this ships.
  ``permissions_enforced`` on ``GET /auth/me-full`` says which case applies, so
  the UI can hide a button it knows the server would refuse and leave it alone
  when the server would not.
* A gated user holds a code iff it is in their effective set.

Enforcement lives in :func:`require_permission` (a route dependency) and
:func:`assert_permission` (for service code that already has the user); a
refusal is 403 ``permission_denied`` naming the codes that would have
satisfied it, so the client can show *which* right is missing.

The lock (``insurance_plans.is_locked``) is the same mechanism with one more
rule: editing a locked plan needs ``setup_insurance_plans_screen_edit_locked_plan``
— and an **ungated** user does *not* get it for free, because a lock is an
explicit assertion someone made about that row (423 ``plan_locked``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, LockedError
from app.db.models import Permission, User, UserGroup, UserGroupMembership, UserGroupRight

#: Roles that hold every right without a group assignment.
FULL_ACCESS_ROLES: frozenset[str] = frozenset({"admin", "super_admin"})

# ── the codes this module is asked about ─────────────────────────────────────
#: Either of these lets a user create / edit / delete an insurance plan (and its
#: coverage rules and frequency groups): the Setup screen's full control, or
#: the patient-screen Insurance Plan Information full control (Edit Plan from
#: the slot). View-only codes never satisfy a write.
INSURANCE_PLAN_WRITE = (
    "setup_insurance_plans_screen_full_control",
    "patient_insurance_plan_information_screen_full_control",
)
#: Required *in addition* when the plan is locked (or to lock / unlock it).
INSURANCE_PLAN_EDIT_LOCKED = "setup_insurance_plans_screen_edit_locked_plan"


@dataclass
class EffectivePermissions:
    user_id: int
    role: str
    #: Codes the user holds through their groups (empty for a full-access role —
    #: see ``full_access``).
    codes: set[str] = field(default_factory=set)
    #: Names of the active groups the user belongs to.
    groups: list[str] = field(default_factory=list)
    #: ``admin`` / ``super_admin``: every code is held.
    full_access: bool = False
    #: True when the rights model applies to this user (they belong to at least
    #: one group). False = ungated (legacy role-only behaviour).
    enforced: bool = False

    def has(self, *codes: str) -> bool:
        """True when the user holds **any** of ``codes``."""
        if self.full_access:
            return True
        if not self.enforced:
            return True
        return any(c in self.codes for c in codes)

    def has_strict(self, *codes: str) -> bool:
        """Like :meth:`has`, but an ungated user does **not** qualify — used for
        rights that guard an explicit per-row assertion (the plan lock)."""
        if self.full_access:
            return True
        return any(c in self.codes for c in codes)


def effective_permissions(db: Session, user: User) -> EffectivePermissions:
    """Resolve the caller's effective rights in two statements."""
    role = (user.role or "").strip().lower()
    out = EffectivePermissions(user_id=user.id, role=role, full_access=role in FULL_ACCESS_ROLES)
    groups = db.execute(
        select(UserGroup.id, UserGroup.name)
        .join(UserGroupMembership, UserGroupMembership.group_id == UserGroup.id)
        .where(
            UserGroupMembership.user_id == user.id,
            UserGroup.is_active.is_(True),
        )
        .order_by(UserGroup.name.asc())
    ).all()
    if not groups:
        return out
    out.enforced = True
    out.groups = [name for _, name in groups]
    group_ids = [gid for gid, _ in groups]
    out.codes = set(db.execute(
        select(Permission.code)
        .join(UserGroupRight, UserGroupRight.permission_id == Permission.id)
        .where(
            UserGroupRight.group_id.in_(group_ids),
            Permission.is_active.is_(True),
        )
    ).scalars().all())
    return out


def assert_permission(perms: EffectivePermissions, *codes: str, action: str | None = None) -> None:
    if perms.has(*codes):
        return
    raise ForbiddenError(
        f"You do not have permission to {action or 'perform this action'}",
        code="permission_denied",
        details={"required_any_of": list(codes), "groups": perms.groups},
    )


def assert_can_edit_locked(perms: EffectivePermissions, *, plan_id: int | None = None) -> None:
    """The plan is locked (or the caller is toggling the lock): 423 unless the
    caller holds the edit-locked-plan right or a full-access role."""
    if perms.has_strict(INSURANCE_PLAN_EDIT_LOCKED):
        return
    raise LockedError(
        "This insurance plan is locked; editing it requires the "
        "'Edit Locked Plan' right",
        code="plan_locked",
        details={
            "plan_id": plan_id,
            "required_any_of": [INSURANCE_PLAN_EDIT_LOCKED],
            "groups": perms.groups,
        },
    )


def permissions_for_user_id(db: Session, user_id: int | None) -> EffectivePermissions | None:
    """Resolve by id — for CRUD paths that only carry the actor id."""
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None:
        return None
    return effective_permissions(db, user)


__all__ = [
    "EffectivePermissions",
    "FULL_ACCESS_ROLES",
    "INSURANCE_PLAN_EDIT_LOCKED",
    "INSURANCE_PLAN_WRITE",
    "assert_can_edit_locked",
    "assert_permission",
    "effective_permissions",
    "permissions_for_user_id",
]
