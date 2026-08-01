# Help Module — modernization + Jira integration

Rebuilt the legacy Help page (static article/video lists, dead `/help/*` menu
links) into a modern, searchable **Help Center** with a first-class
**Report an Issue → Jira** workflow.

Code lives under `src/components/help/**` (mirrors `src/components/reports/**`).

## What shipped

- **Help Center** (`/help`, `HelpCenter.tsx`): hero + global search, category
  chips (All / User Guides / FAQs / Troubleshooting / Release Notes / Contact),
  expandable article accordions, Contact card, System Info, and **My Tickets**.
  Categories are deep-linkable via `?tab=` so the nav menu can jump straight in.
  Content is data-driven in `content/helpContent.ts` — writers extend it without
  touching components.
- **Report an Issue** — reachable from anywhere:
  - global floating button (`ReportIssueFab`, bottom-left, hidden on auth + the
    Help Center which has its own button),
  - the Help nav dropdown ("Report an Issue" → opens the dialog, not a route),
  - the Help Center hero / sidebar / Contact section.
  All routed through `HelpProvider` (`useHelp().openReportIssue()`), mounted once
  in `App.tsx`.
- **Ticket form** (`ReportIssueForm`): Title, Type, Priority, Module/Screen,
  Description, Steps to Reproduce, Expected, Actual, and **attachments**
  (10 MB/file, 25 MB total). Auto-captures **user, role, office, app version,
  browser, OS, timestamp, module (from the current route), and URL**. Inline
  success state shows the **Jira issue ID**; failures show the error with a
  **Retry** button and preserved input.
- **Audit log** (`lib/ticketLog.ts`): every attempt (success or failure) is
  persisted per-user to `localStorage` and mirrored to `console`.

## Legacy items removed

Remote Support, Imaging Remote Support, Downloads & Links, Denticon Learning
Center, Dental/Medical Payer ID lists, My Invoices, About Denticon, and the
static "Video Tutorials" list — all obsolete or dead links. "Submit Product
Suggestion" is subsumed by Report an Issue (issue type = Feature Request).

## Jira integration — configurable, no code changes

Config is entirely env-driven (`src/shared/config/env.ts`, `config/jiraConfig.ts`,
`.env.example`). `env.jira.mode` resolves the transport (`jiraService.ts`):

| Mode | When | Behavior |
|------|------|----------|
| `demo` | nothing configured (default) | Tickets stored locally, synthetic `SUP-N` key. Whole flow is demonstrable. |
| `proxy` | `VITE_JIRA_PROXY_URL` set | POST the ticket JSON (+ base64 attachments + ADF description) to **your backend**, which holds the Jira secret and forwards to Jira. **Production-safe.** |
| `direct` | `VITE_JIRA_BASE_URL`+`EMAIL`+`API_TOKEN` set | Call Jira Cloud REST v3 from the browser (create issue → upload attachments). **Dev/testing only** — exposes the token and needs Jira CORS. |

Issue types, priorities, and modules are plain catalogs in `config/jiraConfig.ts`.
The service builds a proper **ADF** description (narrative + environment block).
A future help-desk (Zendesk/Freshdesk) is a new adapter behind the same shapes.

## Backend gap — HELP-1 (production Jira proxy)

`direct` mode cannot ship (token exposure + CORS). Production needs a backend
proxy the frontend already targets:

- `POST {VITE_JIRA_PROXY_URL}` — body = `buildProxyBody()` output
  (`project_key`, `summary`, `issue_type`, `priority`, `description_adf`,
  `fields`, `context`, `attachments[]` as base64). Auth via the app bearer token.
  Response: `{ issue_key, issue_url }`.
- `GET {VITE_JIRA_PROXY_URL}?reporter=<userId>` — return
  `{ tickets: TicketRecord[] }` so "My Tickets" reflects live Jira status
  (falls back to the local cache today).

The backend holds the Jira API token / OAuth and maps `context` → issue fields.

## Verified (:5173, admin/admin, demo mode)

tsc + eslint clean (0 errors). Live: Help Center renders; Report an Issue opens
from FAB / nav / hero / sidebar; auto-context correct (module auto-detected per
page); submit created **SUP-1**, success screen showed the ID, audit log
recorded it, and **My Tickets** refreshed live.
