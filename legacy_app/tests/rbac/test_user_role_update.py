from app.services.user_role_service import update_user_role
from app.models.user import User
from app.models.user_role import UserRole

def test_update_role(db, rbac_seed):
    owner = User(email="owner@test.com")
    staff = User(email="staff@test.com")

    db.add_all([owner, staff])
    db.flush()

    db.add(
        UserRole(
            user_id=owner.id,
            role_id=rbac_seed["owner"].id,
            tenant_id=1,
            office_id=1,
        )
    )

    user_role = UserRole(
        user_id=staff.id,
        role_id=rbac_seed["staff"].id,
        tenant_id=1,
        office_id=1,
    )
    db.add(user_role)
    db.commit()

    updated = update_user_role(
        db,
        actor_id=owner.id,
        user_role_id=user_role.id,
        new_role_id=rbac_seed["admin"].id,
        tenant_id=1,
    )

    assert updated.role_id == rbac_seed["admin"].id
