# Twilio — what to collect from your account before SMS goes live

Everything below comes from the Twilio Console (https://console.twilio.com). Items marked **(secret)**
go only into the backend's environment/secret manager — never into the frontend, git, or a ticket.

## A. Credentials

| # | Item | Where in the console | Used for |
|---|---|---|---|
| 1 | **Account SID** (`AC…`) | Console home → *Account Info* | Identifies the account in every API call |
| 2 | **Auth Token** (secret) | Console home → *Account Info* | Signs/validates webhooks (`X-Twilio-Signature`). Can also authenticate API calls, but prefer #3 |
| 3 | **API Key SID + Secret** (secret) — create a *Standard* key named `dentc-backend` | Account → *API keys & tokens* → *Create API key* | Backend authentication for sending. Rotatable without touching the Auth Token |
| 4 | Decide: **Production account vs. Trial** | Console banner | A trial account can only text **verified** numbers and prefixes every text with "Sent from your Twilio trial account". Upgrade (add billing) before real patients |

## B. Sending number(s)

| # | Item | Notes |
|---|---|---|
| 5 | **Phone number(s)** in E.164 (`+1412…`) — one per office, or one shared | *Phone Numbers → Manage → Active numbers*. For a dental office, a **local 10DLC long code** per office is normal; a **toll-free** number is simpler to register but shows as 8xx |
| 6 | **Messaging Service SID** (`MG…`) — create one, add all numbers to its *Sender Pool* | *Messaging → Services → Create*. Gives sticky sender per patient, automatic STOP/HELP handling, and lets the backend send with `messaging_service_sid` instead of picking a `from` |
| 7 | Enable **Advanced Opt-Out** on the Messaging Service (optional) | Customise STOP/START/HELP replies with the practice name |

## C. US carrier registration (required to actually deliver in the US)

| # | Item | Notes |
|---|---|---|
| 8 | **A2P 10DLC Brand registration** — the practice's legal name, EIN, address, website, contact | *Messaging → Regulatory Compliance → Brands*. Uses the same data already captured in Setup → Account Info → Communications (business name, EIN, address, contact) |
| 9 | **A2P 10DLC Campaign** — use case *"Mixed"* or *"Customer Care"* + *"Appointment reminders"*; sample messages; opt-in description ("Patients provide their mobile number and consent on the intake form / in the patient portal"); opt-out ("Reply STOP") | Approval usually takes 1–7 business days. Unregistered traffic is filtered/blocked by carriers |
| 10 | Link the Campaign to the Messaging Service (#6) | Done from the Campaign page |
| 11 | **If using toll-free instead:** submit *Toll-Free Verification* with the same business info | Also 1–7 days |
| 12 | Keep a copy of the **Brand ID / Campaign ID** for support tickets | |

## D. Webhooks (backend team configures the URLs once SMS-2 is deployed)

| # | Item | Value to set |
|---|---|---|
| 13 | **Inbound message webhook** on the Messaging Service (*Integration → Send a webhook*) | `https://<backend-host>/api/v1/sms/webhooks/inbound` (HTTP POST) |
| 14 | **Status callback URL** | `https://<backend-host>/api/v1/sms/webhooks/status` — set on the Messaging Service or passed per message |
| 15 | Fallback URL (optional) | Same inbound URL on a secondary host, or leave blank |
| 16 | For local testing: an **ngrok / Cloudflare tunnel** URL pointing at `:8000`, and the Twilio **test credentials** (`Account Info → Test credentials`) for unit tests that must not send |

## E. Compliance & operations

| # | Item | Notes |
|---|---|---|
| 17 | **Consent wording** on intake forms / portal ("By providing your mobile number you agree to receive appointment reminders by text; message & data rates may apply; reply STOP to cancel") | Needed for campaign approval (#9) and TCPA. DentC already stores the outcome in `patients.no_auto_sms` |
| 18 | **HIPAA:** sign Twilio's **Business Associate Agreement** (available on paid accounts via *Trust Hub / Compliance* or Twilio sales) and keep message bodies free of PHI beyond appointment date/time | SMS itself is not encrypted in transit on the carrier network |
| 19 | **Billing alerts** (*Billing → Usage triggers*) e.g. > $50/day | Reminder blasts can run up cost quickly |
| 20 | **Geo-permissions** (*Messaging → Settings → Geo permissions*) — enable only US/CA | Prevents accidental international sends |
| 21 | Who owns the account (email/2FA device) and who has **Developer** vs **Billing** roles | So the backend team can be added as *Developer* without sharing the owner login |

## F. Hand-off summary (what the backend needs from you, in one message)

```
TWILIO_ACCOUNT_SID=AC…
TWILIO_API_KEY_SID=SK…
TWILIO_API_KEY_SECRET=…          (secret)
TWILIO_AUTH_TOKEN=…              (secret — webhook signature validation)
TWILIO_MESSAGING_SERVICE_SID=MG…
Office numbers: Moon +1412…, Greentree +1412…   (also entered in Setup → Account Info → Communications)
A2P Brand/Campaign status: approved on <date>  (or: pending)
BAA signed: yes/no
```

Once the backend exposes `POST /api/v1/sms/send` and the two webhooks, the Messages screen switches
from "Twilio gateway not deployed" to **Live** automatically — no frontend change is needed.
