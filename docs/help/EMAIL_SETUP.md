# Outbound email setup (KAN-12 — password reset)

Password-reset mail is sent by [`app/integrations/email.py`](../../app/integrations/email.py),
which picks a transport in this order:

| Priority | Transport | Active when |
|---|---|---|
| 1 | **Microsoft Graph** `sendMail` (app-only) | all `GRAPH_*` settings present |
| 2 | SMTP (`smtplib`) | `SMTP_HOST` set |
| 3 | Log-only (dev) | neither configured |

**Graph is the supported path.** SMTP basic auth is retained only as a fallback
and is a dead end here — see the two sections below.

Delivery is **fail-soft**: `send_email` never raises, so a misconfigured mailbox
degrades to a logged warning and the forgot-password endpoint still returns its
generic success message. That is deliberate (it must not leak whether an account
exists) — but it also means a broken transport looks exactly like KAN-12's
original symptom. **Check the logs, not the API response, when verifying.**
Each send logs `EMAIL sent via <transport>` or
`Email send failed via <transport> (degraded)` with the underlying reason.

## Microsoft Graph (preferred)

```bash
GRAPH_TENANT_ID=<Overview → Directory (tenant) ID>
GRAPH_CLIENT_ID=<Overview → Application (client) ID>
GRAPH_CLIENT_SECRET=<Certificates & secrets → secret VALUE, not the ID>
GRAPH_SENDER=admin@reckondental.com
```

App registration requirements (Entra admin):

1. App registration, e.g. *Reckon Dental Email Service*.
2. API permissions → Microsoft Graph → **Application permissions** → `Mail.Send`.
3. **Grant admin consent** — the permission is inert until this is done.
4. Certificates & secrets → new client secret; copy the **Value** at creation
   (it is never shown again).

The delegated `User.Read` permission that ships on a new registration is unused
by the client-credentials flow and can be ignored or removed.

### Restrict the app to one mailbox

`Mail.Send` as an *application* permission grants send-as rights over **every
mailbox in the tenant**. Scope it down with an application access policy:

```powershell
Connect-ExchangeOnline
New-ApplicationAccessPolicy -AppId <GRAPH_CLIENT_ID> `
  -PolicyScopeGroupId admin@reckondental.com `
  -AccessRight RestrictAccess `
  -Description "DentC password-reset mail only"

# verify
Test-ApplicationAccessPolicy -Identity admin@reckondental.com -AppId <GRAPH_CLIENT_ID>
```

Policies can take ~30 minutes to apply.

### Token handling

Access tokens are cached in-process until 60s before expiry, so a token is
fetched roughly hourly rather than per email. A `401` on send clears the cache so
a rotated secret recovers on the next attempt without a restart.

### Common failures (all fail-soft; read the log line)

| Symptom in logs | Cause |
|---|---|
| `AADSTS7000215: Invalid client secret` | secret wrong, or the **ID** was pasted instead of the **Value** |
| `AADSTS700016: Application not found` | wrong `GRAPH_CLIENT_ID`, or wrong tenant |
| `ErrorAccessDenied` / `Authorization_RequestDenied` | admin consent not granted |
| `ErrorInvalidUser` / `MailboxNotEnabledForRESTAPI` | `GRAPH_SENDER` is not a real licensed mailbox |
| `ErrorAccessDenied` **after** an access policy | the policy excludes this mailbox — re-check with `Test-ApplicationAccessPolicy` |

## SMTP fallback (legacy — do not build on this)

Retained so the transport can be swapped without a code change, but **it cannot
work on this tenant**: Entra Security Defaults blocks basic auth outright, and
Security Defaults also prevents app passwords from being created, so no
credential exists that would authenticate. Verified 2026-08-15 — see the two
findings below. Turning Security Defaults off to make it work would disable
tenant-wide MFA enforcement; use Graph instead.

Sending moved off a personal Gmail account to the shared practice mailbox:

| Setting | Value |
|---|---|
| `SMTP_HOST` | `smtp.office365.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USE_TLS` | `true` (STARTTLS) |
| `SMTP_USER` | `admin@reckondental.com` |
| `EMAIL_FROM` | `admin@reckondental.com` |
| `EMAIL_FROM_NAME` | `Recon Dental PMS` |
| `SMTP_PASSWORD` | **must be set by an admin — never commit it** |

Leaving `SMTP_HOST` unset returns the app to log-only mode, which prints the
reset link to the application log. That is the right setting for local dev.

## Required Microsoft 365 tenant changes

`smtp.office365.com` will **reject the login until SMTP AUTH is explicitly
enabled on this mailbox.** It is off by default for new tenants and whenever
Security Defaults are on. Two things an admin has to do:

1. **Enable SMTP AUTH for the mailbox** — Microsoft 365 admin center → Users →
   Active users → `admin@reckondental.com` → Mail → Manage email apps →
   tick **Authenticated SMTP**.
   (Tenant-wide toggle: `Set-TransportConfig -SmtpClientAuthenticationDisabled $false`,
   then per-mailbox `Set-CASMailbox -SmtpClientAuthenticationDisabled $false`.)
2. **Provide a credential for `SMTP_PASSWORD`.** If the mailbox has MFA — it
   should — the account password will not work; you need an app password, which
   in turn requires Security Defaults to be off and app passwords permitted.

Symptoms if step 1 is skipped — **confirmed against this tenant on 2026-08-15**:

```
535 5.7.139 Authentication unsuccessful, SmtpClientAuthentication is disabled
for the Tenant. Visit https://aka.ms/smtp_auth_disabled
```

Note "for the **Tenant**": the tenant-wide switch is currently off, so a
per-mailbox change alone is not enough unless it explicitly overrides it.
Preferred fix (keeps SMTP AUTH off everywhere except the one mailbox):

```powershell
Connect-ExchangeOnline
Set-CASMailbox -Identity admin@reckondental.com -SmtpClientAuthenticationDisabled $false
```

Blunter alternative, enabling it tenant-wide (not recommended):

```powershell
Set-TransportConfig -SmtpClientAuthenticationDisabled $false
```

Changes can take up to ~60 minutes to propagate.

### Finding 2 — Security Defaults then blocks it anyway (2026-08-15)

With the mailbox setting corrected, the next attempt returned:

```
535 5.7.139 Authentication unsuccessful, user is locked by your
organization's security defaults policy.
```

This is the dead end: Security Defaults blocks legacy auth tenant-wide *and*
prevents app passwords from being issued, so SMTP basic auth cannot be made to
work without disabling MFA enforcement for the whole organisation. This is what
motivated the Graph transport above.

## ⚠️ This approach has a deadline: end of December 2026

Microsoft is retiring Basic authentication for Client Submission (SMTP AUTH) in
Exchange Online. Basic auth against `smtp.office365.com` keeps working until the
**end of December 2026**, after which it is disabled by default for existing
tenants. After that, this integration fails with:

```
550 5.7.30 Basic authentication is not supported for Client Submission
```

That is a permanent `5xx` rejection — the message is **not** queued or retried,
it is dropped immediately. Combined with our fail-soft `send_email`, password
resets would silently stop working again exactly as in KAN-12.

`_send_via_smtp` currently only does basic auth (`server.login(user, password)`),
so **before December 2026 this needs to move to one of**:

- **OAuth2 / XOAUTH2** against SMTP (client-credentials flow, Azure app
  registration with the `SMTP.SendAsApp` permission), or
- **Microsoft Graph** `sendMail` (drops SMTP entirely — usually the cleaner
  option since we already speak REST elsewhere), or
- a **dedicated transactional provider** (SendGrid / SES / Postmark), which also
  buys deliverability reporting and avoids putting practice mail credentials in
  application config.

## Verifying

With the mailbox configured, trigger a reset and watch the log:

```bash
curl -X POST http://localhost:8000/api/v1/auth/forgot-password -H "Content-Type: application/json" -d '{"email":"someone@example.com"}'
```

- `EMAIL sent → ... | Reset your password` — delivered.
- `Email send failed (degraded), ...` — the exception text names the cause.
- `EMAIL (log-only, no SMTP_HOST)` — SMTP isn't configured; the link is in the log.

## Deployment note

`.env` is gitignored and local-only. For the deployed service these must be set
as Cloud Run environment variables, with `SMTP_PASSWORD` held in Secret Manager
rather than a plain env var.

Sources for the retirement timeline:
[Microsoft Exchange Team blog](https://techcommunity.microsoft.com/blog/exchange/exchange-online-to-retire-basic-auth-for-client-submission-smtp-auth/4114750) ·
[Office 365 for IT Pros](https://office365itpros.com/2026/01/29/smtp-auth-basic-retirement/)
