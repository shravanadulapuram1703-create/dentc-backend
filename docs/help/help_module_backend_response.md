# Help Module — Backend Response (Jira Support Tickets)

**Module:** Help Center → "Report an Issue"
**Gap report answered:** [help_module_backend_devreport.md](help_module_backend_devreport.md) (HELP-1…5)
**Status:** **Implemented.** Runs today in zero-config **local** mode; flips to live
Jira with three env vars — **no code and no frontend change**.

The frontend already targets this contract. Once the Jira team hands over the three
secrets below, set them in `.env`, restart the API, and set `VITE_JIRA_MODE=proxy` +
`VITE_JIRA_PROXY_URL=https://<api-host>/api/v1/support/tickets` on the frontend.

---

## What shipped

| ID | What | Where |
|----|------|-------|
| **HELP-1** | `POST /api/v1/support/tickets` — creates the Jira issue **and uploads attachments**, returns `{issue_key, issue_url}` | [app/api/v1/support.py](../../app/api/v1/support.py), [app/services/support_service.py](../../app/services/support_service.py) |
| **HELP-2** | `GET /api/v1/support/tickets` — the caller's tickets with **live Jira status** (Open · In Progress · Done), synced + persisted on read | same |
| **HELP-3** | Server-held Jira secret + project/issue-type/priority/reporter config | [app/core/config.py](../../app/core/config.py) `JIRA_*`, [app/integrations/jira_client.py](../../app/integrations/jira_client.py) |
| **HELP-4** | **Durable audit** — every submission (success *and* failure) persists to `support_tickets` with the reporter stamped from the token | [app/db/models/platform.py](../../app/db/models/platform.py) |
| **HELP-5** | (Optional webhook) — not built; HELP-2's on-read status sync covers v1 | — |

### Endpoints (both require the app bearer token)

`POST /api/v1/support/tickets` — body is exactly `jiraService.buildProxyBody()`
(`project_key`, `summary`, `issue_type`, `priority`, `description_adf`, `fields`,
`context`, `attachments[]` with `data_base64`). Response `200`:
`{ "issue_key": "SUP-142", "issue_url": "https://…/browse/SUP-142" }`.

`GET /api/v1/support/tickets` — `{ "tickets": [ … ] }`, scoped to the authenticated
user, newest first.

### How it behaves

- **Reporter identity (HELP-3):** the reporter is always the **authenticated user**;
  the client-supplied `context.user_id` is treated as display metadata only and is
  never trusted for authorization. The real end-user (name/role/email/office/module/
  browser/OS/URL) rides along in the issue's **Environment** block via the ADF the
  frontend already builds — so a single Jira service account can file every issue and
  you still see who reported it.
- **Attachments (HELP-1):** each `data_base64` is decoded and uploaded to the created
  issue (`POST /rest/api/3/issue/{key}/attachments`, `X-Atlassian-Token: no-check`).
  A failed attachment is logged but never loses the issue.
- **Status mapping (HELP-2):** Jira workflow statuses collapse to the FE's set —
  `to do/open/backlog/new → Open`, `in progress/in review/reopened → In Progress`,
  `done/closed/resolved → Done` (anything else passes through).
- **Failure path:** when Jira **is** configured and the create call fails, the attempt
  is persisted as `status="Failed"` (audit) and the endpoint returns **502** so the FE
  shows the error and its **Retry** button — no ticket is silently lost.
- **Local mode (default):** when Jira is **not** configured, the ticket persists with a
  `LOCAL-<id>` key and no outbound call is made — dev, CI, and demos work with no
  Atlassian account. `mode` in the list read is `"local"` vs `"proxy"` accordingly.

### Config knobs (`app/core/config.py`)

`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` (all three ⇒ "configured"),
`JIRA_PROJECT_KEY` (default `SUP`), `JIRA_DEFAULT_ISSUE_TYPE`, `JIRA_DEFAULT_PRIORITY`,
`JIRA_INCLUDE_PRIORITY` (omit Priority when a project's create screen doesn't expose
it), `JIRA_REPORTER_ACCOUNT_ID` (optional single service-account reporter),
`JIRA_STATUS_SYNC`, `JIRA_TIMEOUT_SECONDS`. A commented **dummy block** is already in
`.env` — uncomment and fill it in to go live.

---

## ⚠️ What we need from the Jira team (to go live)

The implementation is complete; it just needs these real values. All are held
**server-side only** — none are ever returned to the browser.

1. **Jira site (base) URL** — e.g. `https://reckondental.atlassian.net`
   → `JIRA_BASE_URL`
2. **API-token account email** — the Atlassian account the token belongs to (used as
   the Basic-auth username), e.g. a bot/service account `jira-bot@…`
   → `JIRA_EMAIL`
3. **Atlassian API token** — created at
   `https://id.atlassian.com/manage-profile/security/api-tokens` for that account.
   **This is the secret.** → `JIRA_API_TOKEN`
4. **Project key** — the Jira project support tickets should land in (we assume `SUP`).
   → `JIRA_PROJECT_KEY`
5. **Confirm the issue-type & priority names exist in that project.** The FE sends
   issue types `Bug · Support · Improvement · New Feature · Task` and priorities
   `Highest · High · Medium · Low`. If the project renames or omits any (very common —
   e.g. Priority not on the create screen, or "Support" not a type), tell us the real
   names so we can map them, or we set `JIRA_INCLUDE_PRIORITY=false`.
6. **Reporter policy** — either:
   - the token account can set `reporter` on behalf of others (give us the mapping /
     confirm permission), **or**
   - file everything as one service account — then optionally give us its
     **Atlassian accountId** for `JIRA_REPORTER_ACCOUNT_ID`. (Default: token owner is
     reporter; end-user is captured in the Environment block regardless.)
7. **Permissions** — the token account needs **Create Issues**, **Add Attachments**,
   and **Browse Projects** (for status sync) in that project.

Nice-to-have (not required for v1): a Jira **webhook** to the backend for push status
updates (HELP-5) instead of on-read polling.

Once 1–3 land in `.env` and the API restarts, submit a ticket from Help → Report an
Issue and it appears in Jira; "My Tickets" then reflects live status.

---

### Testing after creds arrive

- `tests/test_support.py` already covers both modes (local + Jira, with the Atlassian
  REST calls stubbed at the `jira_client` seam) — create, attachment upload, status
  sync, and the failure→502 path.
- For a live smoke test: set the three env vars, `POST /api/v1/support/tickets` with a
  small payload, confirm the returned `issue_key` opens in Jira, then `GET` the list
  and confirm the status matches the Jira board.
