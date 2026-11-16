"""PWD-RBAC-3 / USR-AUTH-5: the server-side password complexity policy.

One rule set for every endpoint that *sets* a password (create user, admin
reset, self-service change, forgot-password reset, legacy activation, signup),
so the FE's checklist and the server cannot disagree. Login never applies it —
an existing password that predates the policy still signs in.

Published at ``GET /auth/password-policy`` so the form renders the same list.
``settings.PASSWORD_POLICY_ENFORCED`` is the ops kill switch (length is always
enforced by the schemas' ``min_length``).
"""

from __future__ import annotations

import re

from app.core.config import settings
from app.core.exceptions import ValidationError

MIN_LENGTH = 8

#: (code, human label, predicate). Order = the order the FE lists them.
RULES: tuple[tuple[str, str, object], ...] = (
    ("min_length", f"At least {MIN_LENGTH} characters", lambda p: len(p) >= MIN_LENGTH),
    ("lowercase", "At least one lowercase letter", lambda p: re.search(r"[a-z]", p) is not None),
    ("uppercase", "At least one uppercase letter", lambda p: re.search(r"[A-Z]", p) is not None),
    ("number", "At least one number", lambda p: re.search(r"[0-9]", p) is not None),
    ("symbol", "At least one symbol", lambda p: re.search(r"[^A-Za-z0-9\s]", p) is not None),
)


def failed_rules(password: str) -> list[str]:
    return [code for code, _label, check in RULES if not check(password or "")]


def validate_password(password: str, *, field: str = "password") -> None:
    """422 ``password_too_weak`` naming every rule the password fails."""
    if not settings.PASSWORD_POLICY_ENFORCED:
        return
    failed = failed_rules(password)
    if failed:
        labels = {code: label for code, label, _ in RULES}
        raise ValidationError(
            "Password does not meet the complexity policy: "
            + "; ".join(labels[c] for c in failed),
            code="password_too_weak",
            details={"field": field, "failed_rules": failed},
        )


def describe() -> dict:
    return {
        "enforced": settings.PASSWORD_POLICY_ENFORCED,
        "min_length": MIN_LENGTH,
        "rules": [{"code": code, "label": label} for code, label, _ in RULES],
    }


__all__ = ["MIN_LENGTH", "RULES", "describe", "failed_rules", "validate_password"]
