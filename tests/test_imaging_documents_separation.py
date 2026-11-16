"""Imaging <-> Documents separation (IMG-DOC-1..6).

``patient_documents`` is shared by eight screens; an insurance-card JPG uploaded
on Documents showed up in the X-ray gallery because nothing on the row said who
owned it and ``?context=`` was silently ignored. These tests pin:

* IMG-DOC-1 ``context`` is persisted, returned, inferred when omitted, and picks
  a per-owner storage folder.
* IMG-DOC-2 the list filters by owner (repeated / comma / exclude) and
  ``document_type`` is multi-value + case-insensitive across spellings.
* IMG-DOC-3 the backfill rule (same expression as the migration).
* IMG-DOC-4 the vocabulary: stored as written while the switch is off, folded
  to codes / 422 when on, published on ``/limits``.
* IMG-DOC-5 PATCH moves Documents <-> Imaging only, bytes follow, audited.
* IMG-DOC-6 an unknown query param is a 422, not an unfiltered 200.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import ImageDetail, Patient, PatientDocument
from app.services import document_vocabulary as vocab

URL = "/api/v1/patient-documents"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Ima", last_name="Ging",
                dob=date(1980, 1, 1), is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _up(client, patient, *, document_type=None, context=None, name="f.png",
        payload=b"\x89PNG img", content_type="image/png", expect=201):
    data = {"patient_id": str(patient.id)}
    if document_type is not None:
        data["document_type"] = document_type
    if context is not None:
        data["context"] = context
    r = client.post(URL, data=data, files={"file": (name, payload, content_type)})
    assert r.status_code == expect, r.text
    return r.json()


def _list(client, patient, **params):
    r = client.get(URL, params={"patient_id": patient.id, **params})
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ── IMG-DOC-1 ────────────────────────────────────────────────────────────────
def test_declared_context_is_persisted_and_returned(client, patient):
    doc = _up(client, patient, document_type="Bitewing", context="imaging")
    assert doc["context"] == "imaging"
    assert doc["storage_path"].startswith("documents/imaging/")
    again = client.get(f"{URL}/{doc['id']}").json()
    assert again["context"] == "imaging"


@pytest.mark.parametrize(("doc_type", "expected"), [
    ("Insurance Card", "documents"),
    ("X-Ray / Radiograph", "documents"),   # shared label: never inferred as imaging
    ("XR", "documents"),
    ("Bitewing", "imaging"),
    ("x-ray", "imaging"),
    ("PH", "patient_photo"),
    ("consent-form", "consent"),
    ("patient-letter", "letter"),
    ("progress_note", "progress_note"),
    ("restorative-drawing", "restorative"),
    ("treatment-plan", "treatment_plan"),
    (None, "documents"),
])
def test_context_is_inferred_from_type_when_omitted(client, patient, doc_type, expected):
    """A client that has not cut over to sending ``context`` still files right."""
    assert _up(client, patient, document_type=doc_type)["context"] == expected


def test_each_owner_gets_its_own_folder(client, patient):
    paths = {
        ctx: _up(client, patient, context=ctx)["storage_path"]
        for ctx in vocab.DOCUMENT_CONTEXTS
    }
    assert paths["documents"].startswith("documents/general/")
    assert paths["note"].startswith("documents/notes/")
    assert paths["consent"].startswith("documents/consent-forms/")
    assert paths["imaging"].startswith("documents/imaging/")
    assert all(p.startswith("documents/") for p in paths.values())
    prefixes = {p.rsplit("/", 3)[0] for p in paths.values()}
    assert len(prefixes) == len(vocab.DOCUMENT_CONTEXTS)  # no two owners share a folder


def test_unknown_context_still_rejected(client, patient):
    r = client.post(URL, data={"patient_id": str(patient.id), "context": "xrays"},
                    files={"file": ("f.png", b"\x89PNG", "image/png")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_document_context"


# ── IMG-DOC-2 ────────────────────────────────────────────────────────────────
@pytest.fixture
def mixed(client, patient):
    return {
        "card": _up(client, patient, document_type="Insurance Card", context="documents"),
        "bw": _up(client, patient, document_type="Bitewing", context="imaging"),
        "note": _up(client, patient, document_type="CF", context="note",
                    name="c.pdf", payload=b"%PDF", content_type="application/pdf"),
    }


def test_imaging_list_never_contains_a_documents_upload(client, patient, mixed):
    ids = {d["id"] for d in _list(client, patient, context="imaging")}
    assert ids == {mixed["bw"]["id"]}
    ids = {d["id"] for d in _list(client, patient, context="documents")}
    assert ids == {mixed["card"]["id"]}


def test_context_filter_takes_repeated_and_comma_values(client, patient, mixed):
    want = {mixed["card"]["id"], mixed["note"]["id"]}
    r = client.get(URL, params=[("patient_id", patient.id), ("context", "documents"),
                                ("context", "note")])
    assert {d["id"] for d in r.json()["items"]} == want
    assert {d["id"] for d in _list(client, patient, context="documents,note")} == want
    assert {d["id"] for d in _list(client, patient, exclude_context="imaging")} == want


def test_an_invalid_context_filter_is_a_422(client, patient):
    r = client.get(URL, params={"patient_id": patient.id, "context": "imagin"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_document_context"


def test_document_type_filter_is_case_insensitive_and_multi_value(client, patient, mixed):
    assert {d["id"] for d in _list(client, patient, document_type="insurance card")} == {
        mixed["card"]["id"]}
    both = _list(client, patient, document_type="Insurance Card,CF")
    assert {d["id"] for d in both} == {mixed["card"]["id"], mixed["note"]["id"]}
    # A code also matches the free-text label of the same type.
    assert {d["id"] for d in _list(client, patient, document_type="IC")} == {mixed["card"]["id"]}


# ── IMG-DOC-3 ────────────────────────────────────────────────────────────────
def test_backfill_rule(db_session, patient):
    t = db_session._tenant_id

    def row(**kw):
        d = PatientDocument(tenant_id=t, patient_id=patient.id, file_name="x",
                            file_path=kw.pop("path", "documents/general/1/1/x"),
                            file_url="", context="documents", **kw)
        d.storage_path = d.file_path
        db_session.add(d)
        db_session.flush()
        return d

    note = row(path="documents/notes/1/1/a.png", document_type="PH")
    consent = row(path="documents/consent-forms/1/1/a.pdf", document_type="consent-form")
    letter = row(path="documents/consent-forms/1/1/b.pdf", document_type="patient-letter")
    linked = row(document_type="Other")
    db_session.add(ImageDetail(tenant_id=t, tile_id=str(linked.id)))
    photo = row(document_type="photo")
    patient.photo_document_id = photo.id
    ph = row(document_type="PH")
    bw = row(document_type="Bitewing")
    drawing = row(document_type="restorative-drawing")
    card = row(document_type="X-Ray / Radiograph")
    db_session.flush()

    derived = vocab.backfill_case().label("d")
    got = dict(db_session.execute(select(PatientDocument.id, derived)).all())
    assert got[note.id] == "note"            # path beats the PH type
    assert got[consent.id] == "consent"
    assert got[letter.id] == "letter"
    assert got[linked.id] == "imaging"       # image_details.tile_id link
    assert got[photo.id] == "patient_photo"  # patients.photo_document_id
    assert got[ph.id] == "patient_photo"
    assert got[bw.id] == "imaging"
    assert got[drawing.id] == "restorative"
    assert got[card.id] == "documents"       # left for staff review
    db_session.rollback()


def test_infer_context_and_backfill_agree_on_types():
    """The upload path and the migration must give a type the same owner."""
    for t in list(vocab.SYSTEM_TYPE_CONTEXT) + sorted(vocab.IMAGING_INFERENCE_TYPES) + [
        "consent-form", "CF", "Insurance Card", "XR",
    ]:
        assert vocab.infer_context(t) in vocab.DOCUMENT_CONTEXTS


# ── IMG-DOC-4 ────────────────────────────────────────────────────────────────
def test_type_is_stored_as_written_while_vocabulary_is_off(client, patient):
    doc = _up(client, patient, document_type="Bitewing", context="imaging")
    assert doc["document_type"] == "Bitewing"   # the current gallery matches the label
    assert doc["document_type_label"] == "Bitewing"


def test_vocabulary_folds_and_rejects_when_enforced(client, patient, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_TYPE_VOCABULARY_ENFORCED", True)
    bw = _up(client, patient, document_type="bitewing", context="imaging")
    assert bw["document_type"] == "BW"
    assert bw["document_type_label"] == "Bitewing"
    card = _up(client, patient, document_type="Identification", context="documents")
    assert card["document_type"] == "ID"
    # A Documents sub-type is not an Imaging one.
    r = client.post(URL, data={"patient_id": str(patient.id), "context": "imaging",
                               "document_type": "Insurance Card"},
                    files={"file": ("f.png", b"\x89PNG", "image/png")})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "invalid_document_type"
    assert {"code": "BW", "label": "Bitewing"} in body["details"]["allowed"]
    # System contexts keep their fixed type.
    assert _up(client, patient, document_type="restorative-drawing")["document_type"] == \
        "restorative-drawing"


def test_limits_publish_the_vocabulary(client):
    body = client.get(f"{URL}/limits").json()
    assert body["allowed_contexts"] == list(vocab.DOCUMENT_CONTEXTS)
    assert body["movable_contexts"] == ["documents", "imaging"]
    assert body["document_type_enforced"] is False
    imaging = {o["code"] for o in body["document_types"]["imaging"]["options"]}
    assert {"BW", "PA", "PAN", "FMX"} <= imaging
    assert body["document_types"]["documents"]["group_code"] == "document_type"


def test_imaging_catalog_is_seeded(client, db_session):
    from scripts.seed_account_definitions import seed_for_tenant

    seed_for_tenant(db_session, db_session._tenant_id)
    db_session.commit()
    items = client.get("/api/v1/definitions?group_code=imaging_document_type&size=100").json()["items"]
    assert {i["key1"] for i in items} >= {"BW", "PA", "PAN", "FMX", "IO"}


# ── IMG-DOC-5 ────────────────────────────────────────────────────────────────
def test_patch_moves_a_radiograph_from_documents_to_imaging(client, db_session, patient):
    from pathlib import Path

    doc = _up(client, patient, document_type="X-Ray / Radiograph")
    assert doc["context"] == "documents"
    r = client.patch(f"{URL}/{doc['id']}", json={"context": "imaging", "document_type": "X-Ray"})
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["context"] == "imaging"
    assert moved["document_type"] == "X-Ray"
    assert moved["relocated"] is True
    assert moved["storage_path"].startswith("documents/imaging/")
    assert moved["updated_by"] is not None and moved["updated_at"]
    assert (Path(settings.UPLOAD_DIR) / moved["storage_path"]).is_file()
    assert not (Path(settings.UPLOAD_DIR) / doc["storage_path"]).exists()
    # The content proxy still streams it.
    assert client.get(f"{URL}/{doc['id']}/content").content == b"\x89PNG img"
    assert {d["id"] for d in _list(client, patient, context="imaging")} == {doc["id"]}


def test_patch_refuses_to_move_a_record_owned_file(client, patient):
    note = _up(client, patient, document_type="CF", context="note")
    r = client.patch(f"{URL}/{note['id']}", json={"context": "imaging"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "context_not_movable"
    doc = _up(client, patient, context="documents")
    r = client.patch(f"{URL}/{doc['id']}", json={"context": "consent"})
    assert r.json()["error"]["code"] == "context_not_movable"


def test_patch_rejects_unknown_keys_and_no_op_changes_nothing(client, patient):
    doc = _up(client, patient, context="documents", document_type="Other")
    assert client.patch(f"{URL}/{doc['id']}", json={"contxt": "imaging"}).status_code == 422
    same = client.patch(f"{URL}/{doc['id']}", json={"document_type": "Other"}).json()
    assert same["updated_at"] is None and same["relocated"] is None


def test_patch_move_survives_a_storage_failure(client, patient, monkeypatch):
    from app.services import document_store

    doc = _up(client, patient, context="documents")
    monkeypatch.setattr(document_store, "relocate", lambda d, c: False)
    moved = client.patch(f"{URL}/{doc['id']}", json={"context": "imaging"}).json()
    assert moved["context"] == "imaging" and moved["relocated"] is False
    assert moved["storage_path"] == doc["storage_path"]


def test_patch_is_tenant_scoped(client, db_session, patient):
    from app.db.models import Tenant

    other = Tenant(name="Other", code="other-imgdoc")
    db_session.add(other)
    db_session.flush()
    p = Patient(tenant_id=other.id, first_name="X", last_name="Y", dob=date(1990, 1, 1))
    db_session.add(p)
    db_session.flush()
    d = PatientDocument(tenant_id=other.id, patient_id=p.id, file_name="x", file_path="x",
                        file_url="", context="documents")
    db_session.add(d)
    db_session.commit()
    assert client.patch(f"{URL}/{d.id}", json={"context": "imaging"}).status_code == 404


# ── IMG-DOC-6 ────────────────────────────────────────────────────────────────
def test_unknown_list_param_is_a_422(client, patient):
    r = client.get(URL, params={"patient_id": patient.id, "contxt": "note"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "unknown_query_parameter"
    assert err["details"]["unknown"] == ["contxt"]
    assert "context" in err["details"]["allowed"] and "page" in err["details"]["allowed"]


def test_unknown_param_check_has_a_kill_switch(client, patient, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_LIST_REJECT_UNKNOWN_PARAMS", False)
    r = client.get(URL, params={"patient_id": patient.id, "contxt": "note"})
    assert r.status_code == 200
