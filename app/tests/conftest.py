import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.permission import Permission as PermissionModel
from app.models.role_permission import RolePermission

DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def db():
    engine = create_engine(DATABASE_URL)
    TestingSessionLocal = sessionmaker(bind=engine)

    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    yield session

    session.close()


# 2 SEED RBAC DATA FIXTURE

@pytest.fixture
def rbac_seed(db):
    # Permissions
    perms = [
        PermissionModel(code="user:create"),
        PermissionModel(code="user:assign_role"),
    ]
    db.add_all(perms)
    db.flush()

    # Roles
    owner = Role(name="practice_owner", level=10, tenant_id=1)
    admin = Role(name="office_admin", level=30, tenant_id=1)
    staff = Role(name="front_desk", level=70, tenant_id=1)

    db.add_all([owner, admin, staff])
    db.flush()

    # Role permissions
    db.add(RolePermission(role_id=owner.id, permission="user:assign_role"))
    db.add(RolePermission(role_id=admin.id, permission="user:create"))

    db.commit()
    return {
        "owner": owner,
        "admin": admin,
        "staff": staff,
    }
