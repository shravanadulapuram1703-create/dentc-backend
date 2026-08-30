"""Test fixtures: an in-memory SQLite DB, dependency overrides, and a client.

The suite runs anywhere (no Postgres required). Tenancy/auth dependencies are
overridden to a seeded super-admin so endpoint contracts can be exercised without
a real token exchange. ``test_auth`` covers the genuine login path separately.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_tenant_id
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Tenant, User
from app.db.session import get_db
from app.main import app

TEST_PASSWORD = "test1234"

# No Redis in CI/local test runs: degrade to the in-process safe path so cache
# helpers (balances/ledger/reports) don't pay connection timeouts.
settings.REDIS_ENABLED = False

# No cloud storage either. A developer's ``.env`` legitimately carries a real
# ``GCS_BUCKET_DOCUMENTS``, and without this every document-upload test made a
# live call to Google — slow, dependent on whoever's credentials happened to be
# on the machine, and quietly falling back to local storage when they were the
# wrong ones. Tests that want the bucket path use the ``gcs`` fixture in
# ``test_document_storage.py``, which patches this back on with a fake client.
settings.GCS_BUCKET_DOCUMENTS = None

# Same reasoning for Jira. A developer's ``.env`` legitimately carries real
# ``JIRA_*`` credentials, and with them set ``jira_client.is_configured()`` is
# True, so ``test_help_ticket_create_and_list`` filed a **live ticket** against
# whatever project those credentials point at — and failed with a 502 when the
# project didn't accept it. The support module's documented zero-config path
# (a ``LOCAL-<id>`` key, no outbound call) is what the tests are meant to
# exercise; ``test_support.py`` patches the client back in where it wants the
# configured path.
settings.JIRA_BASE_URL = None


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSessionLocal()

    tenant = Tenant(name="Test Practice", code="test", is_active=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    admin = User(
        tenant_id=tenant.id,
        email="admin@test.local",
        username="admin",
        password_hash=hash_password(TEST_PASSWORD),
        role="super_admin",
        is_active=True,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)

    session._tenant_id = tenant.id  # type: ignore[attr-defined]
    session._admin = admin  # type: ignore[attr-defined]
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    admin = db_session._admin  # type: ignore[attr-defined]
    tenant_id = db_session._tenant_id  # type: ignore[attr-defined]

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_tenant_id] = lambda: tenant_id
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
