# Help Module — Backend Gap Report (Jira Support Tickets)

**Module:** Help Center → "Report an Issue"
**Frontend status:** shipped & working in `demo` mode (tickets stored locally).
**Blocker for production:** there is **no backend endpoint** to file/track Jira
issues. The browser cannot call Jira directly in production (it would expose the
API token and is blocked by Jira CORS), so a server-side proxy is required.

The frontend is already built to call these endpoints — implement them and set
`VITE_JIRA_MODE=proxy` + `VITE_JIRA_PROXY_URL` and it goes live with no FE change.

---

## HELP-1 — Create support ticket (Jira proxy) **[required]**

`POST {VITE_JIRA_PROXY_URL}`  (e.g. `/api/v1/support/tickets`)
Auth: app bearer token (same as all other API calls).

The server holds the Jira secret and creates the issue in the configured project.

**Request body** (exactly what the FE sends — see `jiraService.buildProxyBody`):
```jsonc
{
  "project_key": "SUP",
  "summary": "Scheduler slot not saving on first click",
  "issue_type": "Bug",           // Bug | Support | Improvement | New Feature | Task
  "priority": "Medium",          // Highest | High | Medium | Low
  "description_adf": { /* Atlassian Document Format doc, ready to POST to Jira */ },
  "fields": {                    // raw user input (in case server builds its own body)
    "title": "...", "description": "...", "steps_to_reproduce": "...",
    "expected_behavior": "...", "actual_behavior": "...", "module": "Scheduler"
  },
  "context": {                   // auto-captured, attach to the issue
    "user_name": "...", "user_id": "1", "user_email": "...", "user_role": "super_admin",
    "office": "...", "app_version": "4.3.0", "browser": "Chrome 140",
    "operating_system": "Windows 10/11", "timestamp": "2026-07-05T21:28:22Z",
    "module": "Scheduler", "url": "https://app/.../scheduler"
  },
  "attachments": [               // 0..n; 10 MB/file, 25 MB total (FE-enforced)
    { "name": "screenshot.png", "type": "image/png", "size": 12345, "data_base64": "..." }
  ]
}
```

**Expected response** `200/201`:
```json
{ "issue_key": "SUP-142", "issue_url": "https://your-site.atlassian.net/browse/SUP-142" }
```
On failure return a non-2xx with a JSON `{ "detail": "..." }`; the FE surfaces the
message and offers Retry.

**Server responsibilities**
1. Create the Jira issue (`POST /rest/api/3/issue`) using `description_adf`.
2. Upload each attachment (`POST /rest/api/3/issue/{key}/attachments`,
   `X-Atlassian-Token: no-check`). Decode `data_base64`.
3. Stamp reporter identity from the authenticated user (don't trust `context.user_id`
   for authz — use it as display metadata only).

---

## HELP-2 — List my tickets (status sync) **[required for "My Tickets"]**

`GET {VITE_JIRA_PROXY_URL}?reporter={userId}`
Auth: app bearer token.

Returns the caller's tickets so the Help Center "My Tickets" panel shows **live
Jira status** (today it falls back to a local cache and can't reflect Jira
transitions).

**Expected response** `200`:
```json
{
  "tickets": [
    {
      "id": "SUP-142", "issue_key": "SUP-142",
      "issue_url": "https://.../browse/SUP-142",
      "title": "Scheduler slot not saving on first click",
      "issue_type": "Bug", "priority": "Medium", "module": "Scheduler",
      "status": "In Progress",          // map Jira status → Open|In Progress|Done
      "mode": "proxy", "created_at": "2026-07-05T21:28:22Z", "reporter_id": "1"
    }
  ]
}
```
Map Jira workflow statuses to the FE's set: **Open · In Progress · Done**
(anything else → closest of these). Scope results to the authenticated user via a
Jira JQL like `reporter = <mappedAccount> ORDER BY created DESC`.

---

## HELP-3 — Server-side Jira configuration & secrets **[required]**

The FE only knows a project key. The backend must own, per environment:
- Jira **base URL**, **auth** (API token or OAuth app), and the **reporter mapping**
  (app user → Jira account, or a single service account with the user in a field).
- Project key + **issue-type / priority name mapping** (the FE sends the names in
  the tables above — confirm they exist in the target project, or map them).
- Never return the token to the client.

---

## HELP-4 — (Optional) Ticket audit persistence

Today every submission attempt (success **and** failure) is logged to the user's
`localStorage` + browser console only. If compliance/support wants a durable audit
trail, persist submissions server-side (who filed what, when, outcome, Jira key).

---

## HELP-5 — (Optional) Status webhook / refresh

For real-time status in "My Tickets" without polling, a Jira webhook → backend →
FE (or a lightweight `GET .../tickets/{key}`) would let statuses update as agents
move issues. Not needed for v1 (HELP-2's list read covers it).

---

## Field / enum reference (so the Jira project matches the FE)

| FE issue_type | FE priority | FE status (display) |
|---------------|-------------|---------------------|
| `Bug`, `Support`, `Improvement`, `New Feature`, `Task` | `Highest`, `High`, `Medium`, `Low` | `Open`, `In Progress`, `Done` (+ FE-only `Submitted`, `Failed`) |

**Modules** (FE `context.module` / `fields.module`): Dashboard, Scheduler, Patient,
Transactions, Charting, Treatment Plans, Prescriptions, Lab Tracking, Insurance,
Reports, Utilities, Setup, Imaging, My Page, Login / Authentication, Help, Other.

---

### Summary

| ID | Endpoint | Priority | Purpose |
|----|----------|----------|---------|
| HELP-1 | `POST {proxy}` | **Required** | Create Jira issue + attachments |
| HELP-2 | `GET {proxy}?reporter=` | **Required** | List caller's tickets w/ live status |
| HELP-3 | (config) | **Required** | Server-held Jira secret + project/enum mapping |
| HELP-4 | (persistence) | Optional | Durable submission audit trail |
| HELP-5 | (webhook) | Optional | Push status updates |

Once HELP-1..3 land: set `VITE_JIRA_MODE=proxy` and `VITE_JIRA_PROXY_URL` — no
frontend changes required.
