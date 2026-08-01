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

import pytest

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
