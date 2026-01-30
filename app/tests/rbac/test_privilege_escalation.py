import pytest
from fastapi import HTTPException
from app.services.user_role_service import assign_role_to_user
from app.models.user import User
from app.models.user_role import UserRole

def test_cannot_assign_higher_role(db, rbac_seed):
    admin = User(email="admin@test.com")
    target = User(email="target@test.com")

    db.add_all([admin, target])
    db.flush()

    db.add(
        UserRole(
            user_id=admin.id,
            role_id=rbac_seed["admin"].id,
            tenant_id=1,
            office_id=1,
        )
    )
    db.commit()

    with pytest.raises(HTTPException):
        assign_role_to_user(
            db,
            actor_id=admin.id,
            target_user_id=target.id,
            role_id=rbac_seed["owner"].id,  # ❌ higher privilege
            tenant_id=1,
            office_id=1,
        )
