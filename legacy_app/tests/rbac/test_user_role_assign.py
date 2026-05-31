from app.services.user_role_service import assign_role_to_user
from app.models.user import User
from app.models.user_role import UserRole

def test_assign_role_success(db, rbac_seed):
    owner = User(email="owner@test.com")
    target = User(email="staff@test.com")

    db.add_all([owner, target])
    db.flush()

    db.add(
        UserRole(
            user_id=owner.id,
            role_id=rbac_seed["owner"].id,
            tenant_id=1,
            office_id=1,
        )
    )
    db.commit()

    role = assign_role_to_user(
        db,
        actor_id=owner.id,
        target_user_id=target.id,
        role_id=rbac_seed["admin"].id,
        tenant_id=1,
        office_id=1,
    )

    assert role.user_id == target.id
    assert role.role_id == rbac_seed["admin"].id
