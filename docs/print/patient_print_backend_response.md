# Patient screen printing — backend response

**Date:** 2026-09-11
**In reply to:** `dentc-frontend/docs/print/patient_print_backend_devreport.md` (2026-09-10)
**Status:** PRINT-1, 2, 3, 6 implemented; PRINT-4, 5, 7, 8, 9, 10 were already closed by earlier
work and are consumed by the new reports — the response says where each lives.
**Migration:** none (one model-only change to `audit_logs.id` for SQLite, see PRINT-1 audit).

## Summary

| # | Gap | Outcome |
|---|---|---|
| PRINT-1 | No server-side report endpoint | **Done.** Four `GET /patients/{id}/reports/*` PDF routes + a print audit row. |
| PRINT-2 | No logo / letterhead on `OfficeRead` | **Done.** `OfficeRead.logo_url` + `OfficeRead.letterhead` (resolved once, shared with the PDFs). |
| PRINT-3 | Ledger feed capped at 500 | **Done.** Cap is 5,000; `page` walks beyond; the ledger PDF has no cap at all. |
| PRINT-4 | `/balance` vs ledger arithmetic | **Already fixed** (AL-9). Both prints now agree. |
| PRINT-5 | Overview composition / 25-member cap | **Closed by PRINT-1.** The Overview PDF walks the whole account server-side. |
| PRINT-6 | Today's Est Ded prints 0.00 | **Done.** `GET /patients/{id}/day-totals?date=` (estimate engine over the day's charges). |
| PRINT-7 | Marital Status / Phone / Sec-Sub relationship | **Already exists** (INS-PT-1/2/3) — the FE is binding the wrong names. |
| PRINT-8 | Plan Effective / Term dates | **Already exists** on the subscriber (INS-PT-6: `plan_effective_date` / `plan_term_date`). |
| PRINT-9 | No ortho patient plan resource | **Already exists** (`/ortho-plans`, `pat_*` columns). The card is filled in both prints. |
| PRINT-10 | No patient photo | **Already exists** (`patients.photo_document_id`, PO-10). Embedded in the Overview PDF header. |

## PRINT-1 — Server-rendered reports

```
GET /api/v1/patients/{id}/reports/overview                                   -> application/pdf
GET /api/v1/patients/{id}/reports/ledger?scope=patient|account&date_from&date_to
        &transaction_type=all|charge|payment|adjustment|claim&include_claims&include_archived
        &sort_by=date|code|provider|amount|patient&order=asc|desc              -> application/pdf
GET /api/v1/patients/{id}/reports/transactions?date=YYYY-MM-DD               -> application/pdf
GET /api/v1/patients/{id}/reports/insurance?category=D|M&order=primary|secondary|tertiary|quaternary
                                                                              -> application/pdf
```

Router: `app/api/v1/patient_reports.py` (tag **Patients**, operation ids
`get_patient_{overview,ledger,transactions,insurance}_report`). Composition:
`app/services/print_service.py`. Layout: `app/services/pdf_report.py`.

* **Same parameters the screens already send.** The ledger route takes exactly the
  `/account-ledger` filter/sort set; the insurance route resolves the slot with the FE's own rule
  (category = `legacy_plan_type` `D`/`M`, order = `insurance_type`, positional fallback within a
  category). A slot that does not exist is **404 `insurance_slot_not_found`**, not a blank report.
* **Same layout.** `pdf_report.py` is the reportlab twin of `src/features/print/patientPdf.ts` —
  the office / patient header, navy section bar, label/value table (2- and 4-column), blue-headed
  data grid with right/centre alignment, fixed column widths and a bold totals row, wrapped
  paragraphs, side-by-side cards, `Page x of y`. Section titles and column headers are the
  legacy names from the four `*Print.ts` files, in the same order. Landscape for Ledger and
  Transactions, portrait for Overview and Insurance, as the FE does.
* **Same data.** Each report reads through the services the screens read (`balance_service`,
  `ledger_service.get_account_ledger`, `estimate_service`, `account_scope`,
  `medical_alert_summary_service`, `patient_overview_service.resolve_responsible_party`), so
  the paper cannot disagree with the screen. The ledger PDF pulls the **whole** window in one
  call, computes the per-member Balance column from the same rows, then applies the display
  filter and sort with `ledger_service.ACCOUNT_SORT_KEYS` — the grid's own sort keys.
* **Printed** timestamp is in the home office's timezone; the Transactions `date` default is
  today in that timezone (`office_today`), not UTC.
* **Audit.** Every print writes an `audit_logs` row: `action='PRINT'`,
  `resource_type='patient_report'`, `resource_id=<report>`, `patient_id`, `user_id` from the
  token, `details.params` = the effective query. `AuditMiddleware` records only mutations, so
  this is the only record of who printed what — the legacy reports had it.
  (`audit_logs.id` is now `BigInteger().with_variant(Integer, "sqlite")`: under the in-memory
  test engine a BIGINT PK never auto-incremented, so every exception-safe audit write in the
  suite was silently failing. Postgres is unchanged — no migration.)
* **Response headers:** `Content-Type: application/pdf`,
  `Content-Disposition: inline; filename="…"` — `window.open(url)` shows the browser viewer with
  its print button, which is the behaviour `doc.autoPrint()` gave you.

### Frontend hand-off

Each `*Print.ts` becomes a one-liner. The generated client gets four `get_patient_*_report`
functions that return a blob; the simplest wiring is
`window.open(`${API_BASE}/patients/${id}/reports/ledger?${qs}`)` with the bearer token in the
usual way, or fetch-as-blob + `URL.createObjectURL`. The Insurance printer icon (which had no
handler) can call `reports/insurance?category=D&order=primary` for the active tab's slot.

## PRINT-2 — Letterhead on `OfficeRead`

`OfficeRead` gains:

```json
"logo_url": "/uploads/office_logos/office_11.png",
"letterhead": {
  "name": "Brookline Family Dentistry", "address_line1": "1256 Brookline Blvd", "address_line2": null,
  "city": "Pittsburgh", "state": "PA", "zip": "15226", "phone": "412-555-0100",
  "logo_url": "/uploads/office_logos/office_11.png", "logo_source": "office"
}
```

Resolution lives once in `print_service.resolve_letterhead` (also what heads every PDF), using
what the practice has already configured on **Setup → Office → Statement**
(`office_statement_settings`): `logo_option` = `office` (the practice logo from Account Info,
`logo_source: "tenant"`) | `custom` (the office's own upload, `"office"`) | `none`;
`address_source` = `office` | `custom` (the statement address block; a blank custom field falls
back to the office row); `correspondence_name` overrides `name`. No new columns — the "statement
header" the report asked for is that tab. A remote logo URL is published as-is; only a local
upload is embedded in the PDF.

## PRINT-3 — Ledger feed cap

`size` on `GET /patients/{id}/ledger` and `/account-ledger` now accepts up to **5,000** (was 500).
Both feeds already compute the whole window in memory and only slice it per page, so a larger page
costs serialisation, not another query. `page` still walks anything longer — the FE does not page
today; the server PDF does not need to.

## PRINT-4 — Balance vs ledger

Fixed by AL-9 (`app/services/ledger_sign.py`): `balance_service` and the ledger feed route the
migrated negative-amount payments through one sign rule. The printed BALANCES table takes
`Balance` from the ledger rows and aging / estimates from `/balance`, exactly as the screen does,
and the two now reconcile.

## PRINT-5 — Overview composition

`GET /patients/{id}/overview` (PO-1) exists. The 25-member enrichment cap is the FE's; the server
roster (`GET /responsible-parties/{id}/patients`) stops at 50. The Overview **PDF** iterates
`account_scope.account_members` with no cap and prices each member through `balance_service`,
so Balances / Account Members print for every member.

## PRINT-6 — Today's Est Ded

```
GET /api/v1/patients/{id}/day-totals?date=YYYY-MM-DD
{ "patient_id", "date", "transaction_count", "total_charges", "insurance_estimate",
  "patient_estimate", "estimated_deductible", "has_active_coverage" }
```

The deductible is not stored on a charge. `print_service.day_totals` runs the estimate engine
(CHG-7) over the day's posted charges, each at its **stored** fee, against the primary slot's
remaining deductible as it stands at call time — the same arithmetic `POST /patients/{id}/estimate`
runs before a charge posts. `date` defaults to today in the home office's timezone. The
Transactions PDF prints this value; the screen can bind `Today's Est Ded` to it and drop the †.

## PRINT-7 / PRINT-8 — Insurance columns

All three exist and are written by the generic resources:
`insurance_subscribers.marital_status`, `insurance_subscribers.sub_phone` (INS-PT-1/2, backfilled
on 46,973 / 42,604 migrated rows) and **`patient_insurance.sec_sub_rel_to_prim_sub`** (INS-PT-3) —
the FE form field is named `sec_rel_to_prim`, which is why it "prints blank after a reload": it is
never sent. Bind it to `sec_sub_rel_to_prim_sub` on the `patient-insurance` record.

Plan-level dates: the legacy Eligibility grid keeps *Plan Date* and *Sub Date* side by side on the
**enrolment**, which is how INS-PT-6 modelled it — `insurance_subscribers.plan_effective_date` /
`plan_term_date` next to `effective_date` / `term_date`. `insurance_plans` deliberately has no
effective/term pair (a plan row is shared by every subscriber on it). The Insurance PDF prints the
Plan Date column from those two columns; the screen should too.

## PRINT-9 — Ortho patient plan

`GET /ortho-plans?patient_id=` (AL-3 needed no work) carries the patient sub-plan as `pat_*`:
`pat_amt_financed`, `pat_down_pay`, `pat_periodic_amt`, `pat_first_due_date`, `pat_rem_amt`,
`pat_rem_payments`, and the insurance sub-plan as `ins_*`. Both prints fill the
*Ortho – Patient Payment Plan* and *Ortho – Insurance Payment Plan* cards from them;
`ledgerContracts.ts` can do the same instead of the hard-coded `null`s.

## PRINT-10 — Patient photo

`patients.photo_document_id` (PO-10) → `patient_documents`. The Overview PDF embeds the photo in
the header when the document is a locally stored image; a bucket-stored photo is skipped (a header
decoration must not add a network round trip). The FE can show it via
`GET /patient-documents/{id}/content`.

## Tests

`tests/test_patient_print_module.py` (11): the four PDFs render (`%PDF-` magic,
`application/pdf`, filename), the PRINT audit row with `details.params`, ledger account scope +
filters, `day-totals` deductible (50 on a $50-remaining plan at 80 %), insurance slot 404, tenant
isolation on every route (no audit row for a foreign patient), query validation, `OfficeRead`
letterhead across the three logo modes + custom address + opt-out, remote logo never resolved to
disk, the 5,000 cap, and photo embedding (local yes, bucket no). Also rendered against the dev DB
for a migrated 594-row two-member account: Overview 2 pages, Ledger 20 pages, Transactions and
Insurance 1 page each.
