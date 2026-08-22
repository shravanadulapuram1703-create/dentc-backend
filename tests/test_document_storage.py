"""Object-storage paths for patient documents / consent forms (LTR-1, LTR-16).

The bucket-backed code only runs when ``GCS_BUCKET_DOCUMENTS`` is set, which it
never is locally — so the signed-URL path, the ``/content`` proxy and the
consent-form prefix went to the frontend unexercised. These tests stand a fake
GCS client in front of :mod:`app.integrations.object_storage` so every branch is
covered without cloud credentials.

They are *not* a substitute for a real bucket: IAM signing permissions, bucket
ACLs and network reachability can only be proven in a deployed environment. Run
``python -m scripts.check_document_storage`` there for that half.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.core.config import settings
from app.db.models import Patient
from app.integrations import object_storage as obj
from app.services import document_store

BUCKET = "reco-documents"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="John", last_name="Smith",
                dob=date(1980, 1, 1), is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


class FakeBlob:
    def __init__(self, name: str, data: bytes = b"", content_type: str | None = None):
        self.name = name
        self._data = data
        self.content_type = content_type
        self.updated = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)

    @property
    def size(self) -> int:
        return len(self._data)

    def open(self, _mode: str = "rb"):  # noqa: ANN201
        import io

        return io.BytesIO(self._data)


class FakeBucket:
    def __init__(self, store: dict[str, FakeBlob]):
        self._store = store

    def blob(self, name: str) -> FakeBlob:
        return self._store.setdefault(name, FakeBlob(name))

    def get_blob(self, name: str) -> FakeBlob | None:
        return self._store.get(name)


class FakeClient:
    """Just enough of ``google.cloud.storage.Client`` for the document paths."""

    def __init__(self):
        self.store: dict[str, FakeBlob] = {}

    def bucket(self, _name: str) -> FakeBucket:
        return FakeBucket(self.store)

    def list_blobs(self, _bucket: str, prefix: str = "", max_results: int = 100):  # noqa: ANN201
        return [b for name, b in sorted(self.store.items()) if name.startswith(prefix)][:max_results]


@pytest.fixture
def gcs(monkeypatch):
    """Configure a bucket and swap in the fake client for the whole module."""
    fake = FakeClient()
    monkeypatch.setattr(settings, "GCS_BUCKET_DOCUMENTS", BUCKET)
    monkeypatch.setattr(settings, "DOCUMENT_URL_MODE", "auto")
    monkeypatch.setattr(settings, "PUBLIC_API_BASE_URL", None)
    monkeypatch.setattr(obj, "_get_client", lambda: fake)

    def _upload(bucket, key, data, *, content_type="application/octet-stream", create_only=False):
        assert bucket == BUCKET
        fake.store[key] = FakeBlob(key, data, content_type)

    monkeypatch.setattr(obj, "upload_bytes", _upload)
    monkeypatch.setattr(
        obj, "signed_url",
        lambda bucket, key, **kw: f"https://storage.googleapis.com/{bucket}/{key}?X-Goog-Signature=fake",
    )
    return fake


def _upload_consent(client, patient, name="a01-informed-consent.pdf", payload=b"%PDF-1.4 consent"):
    return client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id), "document_type": "consent-form"},
        files={"file": (name, payload, "application/pdf")},
    )


# ── Routing ──────────────────────────────────────────────────────────────────
def test_consent_form_lands_under_the_consent_prefix(client, db_session, patient, gcs):
    r = _upload_consent(client, patient)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["storage_backend"] == "gcs"
    assert doc["storage_bucket"] == BUCKET
    assert doc["storage_path"].startswith(
        f"consent-forms/{db_session._tenant_id}/{patient.id}/"
    )
    assert doc["storage_path"].endswith(".pdf")
    assert doc["storage_path"] in gcs.store


def test_other_document_types_use_the_generic_prefix(client, patient, gcs):
    doc = client.post(
        "/api/v1/patient-documents",
        data={"patient_id": str(patient.id), "document_type": "insurance_card"},
        files={"file": ("card.png", b"\x89PNG", "image/png")},
    ).json()
    assert doc["storage_path"].startswith("patient-documents/")
    assert not doc["storage_path"].startswith("consent-forms/")


# ── URLs ─────────────────────────────────────────────────────────────────────
def test_file_url_is_a_signed_https_url_never_a_gs_uri(client, patient, gcs):
    doc = _upload_consent(client, patient).json()
    assert doc["file_url"].startswith("https://")
    assert "X-Goog-Signature" in doc["file_url"]
    assert not doc["file_url"].startswith("gs://")


def test_proxy_mode_returns_the_content_endpoint(client, patient, gcs, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_URL_MODE", "proxy")
    doc = _upload_consent(client, patient).json()
    assert doc["file_url"] == f"/api/v1/patient-documents/{doc['id']}/content"


def test_unsignable_credentials_fall_back_to_the_proxy(client, patient, gcs, monkeypatch):
    """On Cloud Run without ``serviceAccountTokenCreator`` signing returns None —
    the browser must still get a fetchable URL."""
    monkeypatch.setattr(obj, "signed_url", lambda *a, **kw: None)
    doc = _upload_consent(client, patient).json()
    assert doc["file_url"].endswith(f"/patient-documents/{doc['id']}/content")


def test_public_api_base_url_absolutises_the_proxy_url(client, patient, gcs, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_URL_MODE", "proxy")
    monkeypatch.setattr(settings, "PUBLIC_API_BASE_URL", "https://api.example.com/")
    doc = _upload_consent(client, patient).json()
    assert doc["file_url"].startswith("https://api.example.com/api/v1/patient-documents/")


def test_signed_urls_are_not_persisted(client, db_session, patient, gcs):
    """A signed URL expires; storing one would serve a dead link on the next read."""
    from app.db.models import PatientDocument

    doc_id = _upload_consent(client, patient).json()["id"]
    db_session.expire_all()
    row = db_session.get(PatientDocument, doc_id)
    assert "X-Goog-Signature" not in (row.file_url or "")


# ── The /content proxy ───────────────────────────────────────────────────────
def test_content_proxy_streams_the_object_from_the_bucket(client, patient, gcs):
    payload = b"%PDF-1.4 the real consent bytes"
    doc = _upload_consent(client, patient, payload=payload).json()
    r = client.get(f"/api/v1/patient-documents/{doc['id']}/content")
    assert r.status_code == 200
    assert r.content == payload
    assert r.headers["content-type"].startswith("application/pdf")


def test_content_proxy_404s_when_the_object_is_gone(client, patient, gcs):
    doc = _upload_consent(client, patient).json()
    gcs.store.clear()
    assert client.get(f"/api/v1/patient-documents/{doc['id']}/content").status_code == 404


def test_content_proxy_enforces_tenancy(client, db_session, patient, gcs):
    """The proxy exists so the caller's tenant check runs before a byte moves."""
    from app.db.models import PatientDocument

    doc_id = _upload_consent(client, patient).json()["id"]
    db_session.get(PatientDocument, doc_id).tenant_id = 9999
    db_session.commit()
    assert client.get(f"/api/v1/patient-documents/{doc_id}/content").status_code == 404


# ── Resilience ───────────────────────────────────────────────────────────────
def test_upload_failure_falls_back_to_local_rather_than_losing_the_consent(
    client, patient, gcs, monkeypatch,
):
    def _boom(*_a, **_kw):
        raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(obj, "upload_bytes", _boom)
    doc = _upload_consent(client, patient).json()
    assert doc["storage_backend"] == "local"
    # NOTE-DOC-3: the local fallback is served by the authenticated proxy, not by
    # the old public /uploads path — a failed bucket write must not downgrade a
    # consent form to an unauthenticated URL.
    assert doc["file_url"] == f"/api/v1/patient-documents/{doc['id']}/content"
    assert client.get(f"/api/v1/patient-documents/{doc['id']}/content").status_code == 200


def test_deleting_a_gcs_document_keeps_the_blob(client, patient, gcs):
    """The bucket's retention policy owns a signed clinical record; the
    soft-deleted row is the marker."""
    doc = _upload_consent(client, patient).json()
    key = doc["storage_path"]
    assert client.delete(f"/api/v1/patient-documents/{doc['id']}").status_code == 204
    assert key in gcs.store
    assert client.get(f"/api/v1/patient-documents/{doc['id']}").status_code == 404


# ── GET /consent-forms ───────────────────────────────────────────────────────
def test_consent_forms_lists_the_bucket_masters(client, gcs):
    gcs.store["consent-forms/_masters/a01-extraction.pdf"] = FakeBlob(
        "consent-forms/_masters/a01-extraction.pdf", b"%PDF-1.4 master", "application/pdf"
    )
    gcs.store["patient-documents/1/2/other.pdf"] = FakeBlob(
        "patient-documents/1/2/other.pdf", b"%PDF", "application/pdf"
    )
    body = client.get("/api/v1/consent-forms").json()
    assert body["is_configured"] is True
    assert body["storage_bucket"] == BUCKET
    names = [i["name"] for i in body["items"]]
    assert names == ["a01-extraction.pdf"]  # the generic-prefix object is excluded
    assert body["items"][0]["url"].startswith("https://")
    assert body["items"][0]["storage_path"].startswith("consent-forms/")


def test_consent_forms_accepts_a_custom_prefix(client, gcs):
    gcs.store["blank-forms/x.pdf"] = FakeBlob("blank-forms/x.pdf", b"%PDF", "application/pdf")
    body = client.get("/api/v1/consent-forms?prefix=blank-forms").json()
    assert [i["name"] for i in body["items"]] == ["x.pdf"]
    assert body["storage_prefix"] == "blank-forms"


# ── Key construction (what the probe script asserts against a real bucket) ───
@pytest.mark.parametrize(("doc_type", "expected_prefix"), [
    ("consent-form", "consent-forms/"),
    ("consent_form", "consent-forms/"),
    ("consent", "consent-forms/"),
    ("xray", "patient-documents/"),
    (None, "patient-documents/"),
])
def test_object_key_routing(doc_type, expected_prefix, gcs):
    key = document_store.object_key(1, 42, doc_type, "f.pdf")
    assert key.startswith(expected_prefix)
    assert "/1/42/" in key


def test_object_key_defaults_a_consent_to_pdf(gcs):
    assert document_store.object_key(1, 42, "consent-form", "no-extension").endswith(".pdf")
