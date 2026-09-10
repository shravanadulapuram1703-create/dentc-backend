"""Help Center support tickets (HELP-1/2/3/4).

Covers the two live modes of the Jira proxy:

* **local** (no Jira configured) — the durable-audit path: the ticket persists
  with a ``LOCAL-<id>`` key and no outbound call is made.
* **jira** (creds configured) — the Atlassian REST calls are stubbed at the
  ``jira_client`` seam so the service's create → attachment → status-sync wiring
  is exercised without a real Atlassian account.
"""

from __future__ import annotations

import base64

from app.core.config import settings
from app.integrations import jira_client

TINY_PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n-fake-bytes").decode()


def _payload(**over):
    body = {
        "project_key": "SUP",
        "summary": "Scheduler slot not saving on first click",
        "issue_type": "Bug",
        "priority": "Medium",
        "description_adf": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}],
        },
        "fields": {"description": "Steps...", "module": "Scheduler"},
        "context": {"user_id": "999", "module": "Scheduler", "app_version": "4.3.0"},
        "attachments": [],
    }
    body.update(over)
    return body


# ── local mode (no Jira configured) ──────────────────────────────────────────

def test_create_ticket_local_mode(client, monkeypatch):
    monkeypatch.setattr(jira_client, "is_configured", lambda: False)

    res = client.post("/api/v1/support/tickets", json=_payload())
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["issue_key"].startswith("LOCAL-")
    assert data["issue_url"] is None

    listed = client.get("/api/v1/support/tickets").json()["tickets"]
    assert len(listed) == 1
    t = listed[0]
    assert t["title"] == "Scheduler slot not saving on first click"
    assert t["module"] == "Scheduler"
    assert t["status"] == "Open"
    assert t["mode"] == "local"


def test_reporter_is_the_token_not_the_client_context(client, monkeypatch):
    """HELP-3: the client-supplied context.user_id (999) must NOT become the
    reporter — the authenticated user id is stamped instead."""
    monkeypatch.setattr(jira_client, "is_configured", lambda: False)
    client.post("/api/v1/support/tickets", json=_payload())
    t = client.get("/api/v1/support/tickets").json()["tickets"][0]
    assert t["reporter_id"] != "999"


# ── jira mode (creds configured, REST stubbed at the client seam) ────────────

def test_create_ticket_jira_mode_with_attachment(client, monkeypatch):
    calls: dict = {"attachments": []}

    monkeypatch.setattr(jira_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        jira_client, "issue_browse_url",
        lambda key: f"https://site.atlassian.net/browse/{key}" if key else None,
    )

    def fake_create(**kw):
        calls["create"] = kw
        return {"key": "SUP-142", "url": "https://site.atlassian.net/browse/SUP-142"}

    def fake_attach(issue_key, filename, content, content_type):
        calls["attachments"].append((issue_key, filename, len(content), content_type))
        return {"content": f"https://site.atlassian.net/attachment/{filename}"}

    monkeypatch.setattr(jira_client, "create_issue", fake_create)
    monkeypatch.setattr(jira_client, "add_attachment", fake_attach)

    body = _payload(attachments=[
        {"name": "shot.png", "type": "image/png", "size": 20, "data_base64": TINY_PNG_B64},
    ])
    res = client.post("/api/v1/support/tickets", json=body)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["issue_key"] == "SUP-142"
    assert data["issue_url"] == "https://site.atlassian.net/browse/SUP-142"

    # The FE-built ADF was forwarded verbatim, and the attachment was uploaded.
    assert calls["create"]["description_adf"] == body["description_adf"]
    assert calls["create"]["project_key"] == "SUP"
    assert calls["attachments"] == [("SUP-142", "shot.png", len(base64.b64decode(TINY_PNG_B64)), "image/png")]

    t = client.get("/api/v1/support/tickets").json()["tickets"][0]
    assert t["mode"] == "proxy"
    assert t["issue_key"] == "SUP-142"


def test_list_syncs_live_jira_status(client, monkeypatch):
    monkeypatch.setattr(jira_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        jira_client, "issue_browse_url",
        lambda key: f"https://site.atlassian.net/browse/{key}" if key else None,
    )
    monkeypatch.setattr(
        jira_client, "create_issue",
        lambda **kw: {"key": "SUP-9", "url": "https://site.atlassian.net/browse/SUP-9"},
    )
    client.post("/api/v1/support/tickets", json=_payload())

    # Bulk lookup returns nothing (e.g. search API unavailable) → per-issue fallback.
    monkeypatch.setattr(jira_client, "get_statuses", lambda keys: {})
    # Agent moved it to "In Progress" in Jira → the list read reflects it.
    monkeypatch.setattr(jira_client, "get_status", lambda key: "In Progress")
    t = client.get("/api/v1/support/tickets").json()["tickets"][0]
    assert t["status"] == "In Progress"

    # A subsequent Jira transition to a Done-family status maps to "Done".
    monkeypatch.setattr(jira_client, "get_status", lambda key: "Resolved")
    t = client.get("/api/v1/support/tickets").json()["tickets"][0]
    assert t["status"] == "Done"


def test_create_ticket_jira_failure_persists_and_502s(client, monkeypatch):
    monkeypatch.setattr(jira_client, "is_configured", lambda: True)

    def boom(**kw):
        raise jira_client.JiraError("Jira create failed (400). project: invalid", status_code=400)

    monkeypatch.setattr(jira_client, "create_issue", boom)

    res = client.post("/api/v1/support/tickets", json=_payload())
    assert res.status_code == 502, res.text

    # HELP-4: the failed attempt is still persisted (audit) as status "Failed".
    listed = client.get("/api/v1/support/tickets").json()["tickets"]
    assert len(listed) == 1
    assert listed[0]["status"] == "Failed"


def test_normalize_adf_moves_version_to_top_level():
    """Regression: the FE historically emitted {type:doc, attrs:{version:1}}, which
    Jira 400s as invalid ADF. The client must lift version to the top level."""
    bad = {"type": "doc", "attrs": {"version": 1}, "content": [{"type": "paragraph"}]}
    fixed = jira_client._normalize_adf(bad)
    assert fixed["version"] == 1
    assert "attrs" not in fixed  # version was the only attr → attrs dropped
    assert fixed["content"] == [{"type": "paragraph"}]

    # Missing version entirely → defaulted to 1; non-doc values pass through.
    assert jira_client._normalize_adf({"type": "doc", "content": []})["version"] == 1
    assert jira_client._normalize_adf(None) is None
    assert jira_client._normalize_adf({"type": "paragraph"}) == {"type": "paragraph"}


def test_issue_type_is_mapped_for_projects_missing_that_type(client, monkeypatch):
    """FE 'New Feature' → Jira 'Story' when the project has no such type (e.g. the
    KAN team-managed board)."""
    monkeypatch.setattr(jira_client, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "JIRA_ISSUE_TYPE_MAP", {"New Feature": "Story"})
    seen: dict = {}

    def fake_create(**kw):
        seen.update(kw)
        return {"key": "KAN-1", "url": "https://site.atlassian.net/browse/KAN-1"}

    monkeypatch.setattr(jira_client, "create_issue", fake_create)
    res = client.post("/api/v1/support/tickets", json=_payload(issue_type="New Feature"))
    assert res.status_code == 200, res.text
    assert seen["issue_type"] == "Story"


def test_unknown_issue_type_falls_back_to_default(client, monkeypatch):
    """A create rejected for a bad issuetype retries once with the default type so
    the ticket is never lost."""
    monkeypatch.setattr(jira_client, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "JIRA_ISSUE_TYPE_MAP", {})
    monkeypatch.setattr(settings, "JIRA_DEFAULT_ISSUE_TYPE", "Bug")
    attempts: list = []

    def fake_create(**kw):
        attempts.append(kw["issue_type"])
        if kw["issue_type"] == "Improvement":
            raise jira_client.JiraError(
                "Jira create failed (400). issuetype: valid issue type is required",
                status_code=400,
            )
        return {"key": "KAN-2", "url": "https://site.atlassian.net/browse/KAN-2"}

    monkeypatch.setattr(jira_client, "create_issue", fake_create)
    res = client.post("/api/v1/support/tickets", json=_payload(issue_type="Improvement"))
    assert res.status_code == 200, res.text
    assert attempts == ["Improvement", "Bug"]  # rejected, then retried with default


# ── HELP-6: reporter-driven status change ────────────────────────────────────

def test_update_status_local_mode(client, monkeypatch):
    monkeypatch.setattr(jira_client, "is_configured", lambda: False)
    client.post("/api/v1/support/tickets", json=_payload())
    t = client.get("/api/v1/support/tickets").json()["tickets"][0]

    res = client.patch(f"/api/v1/support/tickets/{t['id']}", json={"status": "In Progress"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "In Progress"
    assert client.get("/api/v1/support/tickets").json()["tickets"][0]["status"] == "In Progress"

    # Only the FE's mapped set is accepted.
    assert client.patch(f"/api/v1/support/tickets/{t['id']}", json={"status": "Failed"}).status_code == 422
    # Unknown / someone else's ticket → 404.
    assert client.patch("/api/v1/support/tickets/999999", json={"status": "Done"}).status_code == 404


def test_update_status_transitions_jira_first(client, monkeypatch):
    monkeypatch.setattr(jira_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        jira_client, "issue_browse_url",
        lambda key: f"https://site.atlassian.net/browse/{key}" if key else None,
    )
    monkeypatch.setattr(
        jira_client, "create_issue",
        lambda **kw: {"key": "KAN-7", "url": "https://site.atlassian.net/browse/KAN-7"},
    )
    monkeypatch.setattr(jira_client, "get_statuses", lambda keys: {"KAN-7": "To Do"})
    client.post("/api/v1/support/tickets", json=_payload())
    t = client.get("/api/v1/support/tickets").json()["tickets"][0]

    applied: list = []
    monkeypatch.setattr(
        jira_client, "list_transitions",
        lambda key: [
            {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
            {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ],
    )
    monkeypatch.setattr(jira_client, "do_transition", lambda key, tid: applied.append((key, tid)))

    res = client.patch(f"/api/v1/support/tickets/{t['id']}", json={"status": "Done"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "Done"
    assert applied == [("KAN-7", "31")]

    # Jira has no transition into the requested status → 409, nothing persisted.
    monkeypatch.setattr(jira_client, "list_transitions", lambda key: [
        {"id": "11", "name": "Reopen", "to": {"name": "To Do"}},
    ])
    monkeypatch.setattr(jira_client, "get_statuses", lambda keys: {"KAN-7": "Done"})
    res = client.patch(f"/api/v1/support/tickets/{t['id']}", json={"status": "In Progress"})
    assert res.status_code == 409, res.text
    assert client.get("/api/v1/support/tickets").json()["tickets"][0]["status"] == "Done"

    # Jira unreachable → 502, nothing persisted.
    def boom(key):
        raise jira_client.JiraError("Could not reach Jira: timeout")
    monkeypatch.setattr(jira_client, "list_transitions", boom)
    res = client.patch(f"/api/v1/support/tickets/{t['id']}", json={"status": "Open"})
    assert res.status_code == 502, res.text


def test_list_uses_one_bulk_status_lookup(client, monkeypatch):
    """The list read syncs every open Jira-backed ticket with ONE search call,
    not one GET per ticket."""
    monkeypatch.setattr(jira_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        jira_client, "issue_browse_url",
        lambda key: f"https://site.atlassian.net/browse/{key}" if key else None,
    )
    seq = iter(["KAN-1", "KAN-2", "KAN-3"])
    monkeypatch.setattr(
        jira_client, "create_issue",
        lambda **kw: (lambda k: {"key": k, "url": f"https://site.atlassian.net/browse/{k}"})(next(seq)),
    )
    for _ in range(3):
        client.post("/api/v1/support/tickets", json=_payload())

    bulk_calls: list = []
    monkeypatch.setattr(
        jira_client, "get_statuses",
        lambda keys: bulk_calls.append(sorted(keys)) or {"KAN-1": "Done", "KAN-2": "Ready to Test"},
    )
    def no_single(key):
        raise AssertionError("per-issue get_status must not be used when bulk returned data")
    monkeypatch.setattr(jira_client, "get_status", no_single)

    listed = client.get("/api/v1/support/tickets").json()["tickets"]
    assert bulk_calls == [["KAN-1", "KAN-2", "KAN-3"]]
    by_key = {t["issue_key"]: t["status"] for t in listed}
    assert by_key == {"KAN-1": "Done", "KAN-2": "Ready to Test", "KAN-3": "Open"}

    # Done tickets are terminal → excluded from the next sync.
    bulk_calls.clear()
    client.get("/api/v1/support/tickets")
    assert bulk_calls == [["KAN-2", "KAN-3"]]
