"""Idempotent dev seed: one tenant + one super-admin user.

Safe to re-run — looks up by unique key before inserting::

    python -m scripts.seed
"""

from __future__ import annotations

from app.core.security import hash_password
from app.db.models import Tenant, User
from app.db.session import SessionLocal

TENANT_CODE = "dev"
ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@dentalpms.local"
ADMIN_PASSWORD = "ChangeMe123!"  # noqa: S105 - dev seed only


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.code == TENANT_CODE).first()
        if tenant is None:
            tenant = Tenant(name="Dev Practice", code=TENANT_CODE, is_active=True)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"Created tenant id={tenant.id}")
        else:
            print(f"Tenant already exists id={tenant.id}")

        user = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=ADMIN_EMAIL,
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                first_name="Admin",
                last_name="User",
                role="super_admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            print(f"Created admin user '{ADMIN_USERNAME}' / '{ADMIN_PASSWORD}'")
        else:
            print(f"Admin user already exists id={user.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
