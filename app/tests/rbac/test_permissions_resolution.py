from app.services.rbac_service import get_user_permissions
from app.models.user import User
from app.models.user_role import UserRole

def test_permission_resolution(db, rbac_seed):
    user = User(email="admin@test.com")
    db.add(user)
    db.flush()

    db.add(
        UserRole(
            user_id=user.id,
            role_id=rbac_seed["admin"].id,
            tenant_id=1,
            office_id=101,
        )
    )
    db.commit()

    perms = get_user_permissions(
        db,
        user_id=user.id,
        tenant_id=1,
        office_id=101,
    )

    assert "user:create" in perms
    assert "user:assign_role" not in perms
