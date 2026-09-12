"""Progress-notes round 2 (PN-6, PN-8 audit, PN-9, PN-11, PN-12 + tenancy)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.db.models import Definition, Office, Patient, ProgressNote, Tenant, User
from app.services import progress_note_content as content
from app.services.progress_notes_service import _note_is_locked, note_lock_instant

PREFIX = "/api/v1"
NY = ZoneInfo("America/New_York")


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="PNNY", name="Eastern Office",
               timezone="America/New_York")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Round", last_name="Two",
                chart_no="PN-2", is_active=True, home_office_id=office.id)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_note(client, patient_id: int, **extra) -> dict:
    body = {"patient_id": patient_id, "notes": "initial", **extra}
    r = client.post(f"{PREFIX}/progress-notes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── PN-12: the content rules ─────────────────────────────────────────────────
LEGACY_20002 = (
    "~^^~lt;p~^^~gt;Patient presented for~^^~amp;nbsp;Periodic Exam. MHR~^^~lt;/p~^^~gt;\r\n"
    "~^^~lt;p~^^~gt;-- Soft Tissue Exam --~^^~lt;/p~^^~gt;\r\n"
    "~^^~lt;p~^^~gt;~^^~amp;nbsp;~^^~lt;/p~^^~gt;"
)


def test_decode_is_single_level():
    assert content.decode_legacy_markup("~^^~lt;p~^^~gt;a~^^~amp;nbsp;b~^^~lt;/p~^^~gt;") == "<p>a&nbsp;b</p>"
    # a typed "<" was &lt; in the editor, escaped again by the export: it comes back as &lt;
    assert content.decode_legacy_markup("pocket ~^^~amp;lt;3mm") == "pocket &lt;3mm"
    assert content.decode_legacy_markup("~^^~quot;x~^^~quot;") == '"x"'
    assert content.decode_legacy_markup("plain & clean") == "plain & clean"


def test_tidy_removes_import_artefacts_only():
    assert content.tidy_note_html("<p><p>a</p></p>\r\n<p>b</p>\r\n<p>&nbsp;</p>") == "<p>a</p><p>b</p>"
    # a deliberate mid-body spacer survives; only the trailing one goes
    assert content.tidy_note_html("<p>a</p><p>&nbsp;</p><p>b</p><p>&nbsp;</p>") == "<p>a</p><p>&nbsp;</p><p>b</p>"
    assert content.tidy_note_html('<p><span style="color:#f00">x</span></p>') == '<p><span style="color:#f00">x</span></p>'


def test_html_to_text_keeps_line_breaks_and_drops_nbsp_mojibake():
    text = content.html_to_text("<p>Patient presented for&nbsp;Periodic Exam.</p><p>Line<br>Two</p>")
    assert text == "Patient presented for Periodic Exam.\nLine\nTwo"
    assert content.html_to_text("a &amp; b &lt;c&gt;") == "a & b <c>"


def test_repair_note_content_sample_row():
    notes, html, changes = content.repair_note_content(
        "Patient presented for?Periodic Exam. MHR-- Soft Tissue Exam --", LEGACY_20002
    )
    assert html == "<p>Patient presented for&nbsp;Periodic Exam. MHR</p><p>-- Soft Tissue Exam --</p>"
    assert notes == "Patient presented for Periodic Exam. MHR\n-- Soft Tissue Exam --"
    assert changes == ["html_decoded", "notes_regenerated"]
    assert content.LEGACY_AMP_TOKEN not in html


def test_repair_leaves_clean_app_rows_alone():
    notes, html, changes = content.repair_note_content("hello", "<p>hello</p>")
    assert (notes, html, changes) == ("hello", "<p>hello</p>", [])
    # regenerate_text only rewrites the plain column when it disagrees
    notes, html, changes = content.repair_note_content("hello", "<p>hello</p>", regenerate_text=True)
    assert changes == []
    notes, html, changes = content.repair_note_content("stale", "<p>hello</p>", regenerate_text=True)
    assert notes == "hello" and changes == ["notes_regenerated"]


def test_drawing_payload_detection():
    assert content.drawing_payload('{"type":"rx-draw","strokes":[]}') == {"type": "rx-draw", "strokes": []}
    assert content.drawing_payload("<p>{not json}</p>") is None
    assert content.drawing_payload('{"type":"other"}') is None
    n, h, ch = content.repair_note_content("x", '{"type":"rx-draw","strokes":[]}')
    assert ch == [] and h == '{"type":"rx-draw","strokes":[]}'


# ── PN-12: the write path derives the searchable column ──────────────────────
def test_notes_derived_from_notes_html_on_write(client, patient):
    note = _make_note(client, patient.id, notes=None, notes_html="<p>Rich&nbsp;body</p><p>Two</p>")
    assert note["notes"] == "Rich body\nTwo"
    patched = client.patch(f"{PREFIX}/progress-notes/{note['id']}", json={"notes_html": "<p>Changed</p>"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["notes"] == "Changed"
    # an explicit plain body is never overridden
    both = _make_note(client, patient.id, notes="mine", notes_html="<p>theirs</p>")
    assert both["notes"] == "mine"

    # search= runs against the derived plain column
    listed = client.get(f"{PREFIX}/progress-notes", params={"patient_id": patient.id, "search": "Changed"})
    assert listed.status_code == 200
    assert {n["id"] for n in listed.json()["items"]} == {note["id"]}


# ── PN-9: the lock day is the office's day ───────────────────────────────────
def test_lock_uses_office_local_day():
    # 23:30 UTC on the 10th is 19:30 in New York on the 10th.
    note = ProgressNote(created_at=datetime(2026, 9, 10, 23, 30))
    # 02:00 UTC on the 11th is still 22:00 on the 10th in New York → editable
    assert _note_is_locked(note, NY, now=datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)) is False
    # …but the UTC date already rolled, which is the bug the report describes
    assert _note_is_locked(note, ZoneInfo("UTC"), now=datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)) is True
    # 01:00 New York on the 11th → locked
    assert _note_is_locked(note, NY, now=datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc)) is True
    # signed always locks
    assert _note_is_locked(ProgressNote(created_at=datetime(2026, 9, 11), signed_at=datetime(2026, 9, 11)), NY) is True
    # the lock instant is New York midnight (EDT = UTC−4)
    assert note_lock_instant(note, NY) == datetime(2026, 9, 11, 4, 0, tzinfo=timezone.utc)


def test_read_reports_timezone_and_lock_instant(client, patient, office):
    note = _make_note(client, patient.id, office_id=office.id)
    read = client.get(f"{PREFIX}/progress-notes/{note['id']}").json()
    assert read["timezone"] == "America/New_York"
    assert read["is_locked"] is False
    created = datetime.fromisoformat(read["created_at"])
    local_midnight = datetime.combine(
        created.astimezone(NY).date() + timedelta(days=1), datetime.min.time(), NY
    )
    assert datetime.fromisoformat(read["locks_at"]) == local_midnight.astimezone(timezone.utc)
    assert read["created_at"].endswith("+00:00") or read["created_at"].endswith("Z")  # PN-10


def test_office_falls_back_to_patient_home_office(client, patient, office):
    note = _make_note(client, patient.id)  # no office_id on the note
    read = client.get(f"{PREFIX}/progress-notes/{note['id']}").json()
    assert read["timezone"] == "America/New_York"


def test_locked_error_names_the_zone(client, patient, db_session, office):
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    note = ProgressNote(patient_id=patient.id, office_id=office.id, notes="old",
                        created_at=yesterday, created_by=db_session._admin.id)
    db_session.add(note)
    db_session.commit()
    blocked = client.patch(f"{PREFIX}/progress-notes/{note.id}", json={"notes": "edit"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["timezone"] == "America/New_York"
    # PN-8: the DOS is still correctable on an unsigned prior-day note
    dos = client.patch(f"{PREFIX}/progress-notes/{note.id}", json={"note_date": "2026-09-01"})
    assert dos.status_code == 200, dos.text
    assert dos.json()["note_date"] == "2026-09-01"


# ── PN-11: updated_at / updated_by ───────────────────────────────────────────
def test_update_stamps_modified_actor_only_on_real_change(client, patient, db_session):
    note = _make_note(client, patient.id)
    assert note["updated_at"] is None and note["updated_by"] is None

    same = client.patch(f"{PREFIX}/progress-notes/{note['id']}", json={"notes": "initial"})
    assert same.status_code == 200
    assert same.json()["updated_by"] is None  # MH-20: a no-op PATCH stamps nothing

    changed = client.patch(f"{PREFIX}/progress-notes/{note['id']}", json={"notes": "edited"})
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["updated_by"] == db_session._admin.id
    assert body["updated_by_name"] == db_session._admin.username
    assert body["updated_at"] is not None


def test_dos_correction_stamps_modified(client, patient, db_session):
    note = _make_note(client, patient.id, note_date="2026-09-10")
    fixed = client.patch(f"{PREFIX}/progress-notes/{note['id']}", json={"note_date": "2026-09-03"})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["updated_by"] == db_session._admin.id


# ── PN-8 open question: the DOS correction is audited field-level ────────────
@pytest.fixture
def audit_capture(monkeypatch, client, db_session):
    from app.api.deps import get_current_user
    from app.main import app
    from app.services.auth_service import issue_tokens

    captured: list[dict] = []
    monkeypatch.setattr("app.middleware.audit.write_audit", lambda **kw: captured.append(kw))
    app.dependency_overrides.pop(get_current_user, None)
    tokens = issue_tokens(db_session._admin)
    client.headers.update({"Authorization": f"Bearer {tokens.access_token}"})
    return captured


def test_dos_change_lands_in_audit_log_with_before_after(client, patient, audit_capture):
    note = _make_note(client, patient.id, note_date="2026-09-10")
    client.patch(f"{PREFIX}/progress-notes/{note['id']}", json={"note_date": "2026-09-03"})
    entry = audit_capture[-1]
    assert entry["method"] == "PATCH" and entry["resource_type"] == "progress-notes"
    assert entry["resource_id"] == str(note["id"])
    assert entry["patient_id"] == patient.id
    assert entry["details"]["before"]["note_date"] == "2026-09-10"
    assert entry["details"]["after"]["note_date"] == "2026-09-03"


# ── tenancy: progress_notes has no tenant_id ─────────────────────────────────
@pytest.fixture
def foreign_note(db_session) -> ProgressNote:
    other = Tenant(name="Other Practice", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    p = Patient(tenant_id=other.id, first_name="Else", last_name="Where", chart_no="X-1", is_active=True)
    db_session.add(p)
    db_session.commit()
    n = ProgressNote(patient_id=p.id, notes="theirs")
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    return n


def test_other_tenants_note_is_invisible(client, foreign_note):
    assert client.get(f"{PREFIX}/progress-notes/{foreign_note.id}").status_code == 404
    assert client.patch(f"{PREFIX}/progress-notes/{foreign_note.id}", json={"notes": "x"}).status_code == 404
    assert client.delete(f"{PREFIX}/progress-notes/{foreign_note.id}").status_code == 404
    listed = client.get(f"{PREFIX}/progress-notes").json()
    assert foreign_note.id not in {n["id"] for n in listed["items"]}
    created = client.post(f"{PREFIX}/progress-notes",
                          json={"patient_id": foreign_note.patient_id, "notes": "mine?"})
    assert created.status_code == 404


# ── PN-6: category codes resolve to labels ───────────────────────────────────
def test_macro_categories_are_labelled(client, db_session):
    tid = db_session._tenant_id
    db_session.add_all([
        Definition(tenant_id=tid, legacy_id="179", group_code="NOTESMACROS", key1="", description="DIAGNOSTIC"),
        Definition(tenant_id=tid, legacy_id="181", group_code="NOTESMACROS", key1="181", description="RESTORATIVE"),
    ])
    db_session.commit()
    for name, cat in [("M1", "179"), ("M2", "179"), ("M3", "181"), ("M4", "Hygiene"), ("M5", "999")]:
        r = client.post(f"{PREFIX}/note-macros", json={"name": name, "content": "...", "category": cat})
        assert r.status_code == 201, r.text
        if cat == "179":
            assert r.json()["category_label"] == "DIAGNOSTIC"
        if cat == "999":
            assert r.json()["category_label"] == "999"  # unmapped: as written

    cats = client.get(f"{PREFIX}/note-macros/categories").json()
    assert [(c["category"], c["label"], c["macro_count"]) for c in cats] == [
        ("999", "999", 1), ("179", "DIAGNOSTIC", 2), ("Hygiene", "Hygiene", 1), ("181", "RESTORATIVE", 1),
    ]
