# Responsible Party / Family Accounts — backend response (RP-1 … RP-16)

_Backend, 2026-11-16. Answers `dentc-frontend/docs/patients/responsible_party_backend_devreport.md`.
Alembic `9435491c1d19` (on top of `03bbb54c0b12`) — **applied to `Test_Dental_Group`** (135 patients → 135 Self accounts, 21 NULL relationships → `S`). Tests: `tests/test_responsible_party_accounts.py`._

## TL;DR for the frontend

* Every patient now has an **`account_id`** and a **typed guarantor**. Read
  `patient.guarantor.kind` (`self | patient | responsible_party | unresolved`) — delete the
  guessing in `src/features/patient-overview/guarantor.ts`.
* `responsible_party_id` is a **deprecated alias** = the guarantor's key (the guarantor
  *patient's* id for self/patient, the `responsible_parties.id` for a party, the raw legacy RPID
  when unresolved). It is still accepted on writes, but validated.
* New endpoints: `/accounts…`, `POST /patients/{id}/change-guarantor`,
  `GET /patients/{id}/account`, `GET /patients/{id}/change-log`, `GET /metadata/account-rules`.
* **Behaviour change (RP-10):** `PatientBalance.account_balance` is now the **true account total**.
  The patient's own figure is `balance` (and `patient_balance_total`). Same on the scheduler feed
  (`account_balance` = account, new `patient_balance` = patient).
* **Behaviour change (RP-4/RP-7):** `PATCH /patients/{id}` with all guarantor keys null/blank is
  *not touched* (PE-5 — originally a 422 `guarantor_required`, which sank the whole PATCH); an unknown key → 422 `responsible_party_not_found`.

## The model

```
accounts (id, tenant_id, account_no, legacy_key, primary_guarantor_patient_id | primary_guarantor_party_id,
          home_office_id, send_statements, no_email_statement, send_collections, collection_agency_id,
          is_finance_charge, statement_message, financial_notes, notes, is_active,
          merged_into_account_id, merged_at, created_by, updated_by, timestamps)
account_parties (account_id, patient_id | responsible_party_id, role secondary|billing_contact,
                 responsibility_pct, receives_statements, sort_order, is_active)
account_change_events (append-only audit, RP-16)
patients.account_id / guarantor_patient_id / guarantor_party_id   (+ CHECK at most one guarantor)
patient_payments.account_id / account_payment_id                 (stamped at posting)
patient_statements.account_id / statement_scope ('patient'|'account')
```

## Gap by gap

| ID | Status | What shipped |
|---|---|---|
| RP-1 | ✅ | Typed columns above. Self = `guarantor_patient_id = id`. `responsible_party_id` kept as a computed alias for one release. **Deviation:** the CHECK is *at most one* guarantor, not *exactly one* — a self-guarantor's own id does not exist at INSERT time and Postgres CHECKs are not deferrable, so Self is stamped in the same flush. Both-NULL only occurs for a migrated, still-unresolved RPID (`kind: "unresolved"`). `account_id` is nullable at the DB level only because the Denticon importer writes patients by raw SQL; every app write gets one (see RP-4). |
| RP-2 | ✅ | `guarantor` (the discriminated shape you proposed, plus `id`, `account_id`, `first_name`, `last_name`, `home_phone`) on `PatientRead`, `/patients/{id}/overview`, `/patients/{id}/context`, `/patients/{id}/account`, `/account-balance`, `/patients/register`. Letters, prints and payment-plan contracts resolve the guarantor from the typed columns (a `Patient` or a `ResponsibleParty`), so a self key can no longer print another family's guarantor. `overview.responsible_party` is now **only** the RP row when the guarantor is a non-patient (null for self/head of household). |
| RP-3 | ✅ | `accounts` table. `GET /accounts` (search by account no / RPID / member or guarantor name), `GET /accounts/{id}` (account + primary guarantor + parties + members with dob/age/sex/relationship/is_guarantor/next & last visit/recall/balance/aging), `PATCH /accounts/{id}` (billing flags, account_no — 409 `duplicate_account_no`), `GET /patients/{id}/account`. Account flags are **canonical for account statements**; they are seeded from the guarantor at creation and never mirrored back to `patients` / `responsible_parties`. |
| RP-4 | ✅ | Backfill ran inside the migration: NULL keys → Self (new account, relationship `S`). Every ORM patient insert gets an account (hook in `app/db/models/accounts.py`): `POST /patients` and `/patients/register` default to Self when no guarantor is sent. `PATCH` with a null guarantor = not touched (PE-5). |
| RP-5 | ✅ | `ResponsiblePartyIn` gains `guarantor_patient_id` and `account_id`. Precedence `is_self > guarantor_patient_id > account_id > person > responsible_party_id`. Guarantor patient must be same tenant + active (422 `guarantor_patient_not_found` / `guarantor_patient_inactive`); a closed account → 422 `account_inactive`. `POST /patients` accepts the same typed keys. |
| RP-6 | ✅ | `POST /patients/{id}/change-guarantor` `{is_self | guarantor_patient_id | account_id | person | responsible_party_id, relationship, move_open_balance=true, include_dependents=false, new_account=false, effective_date}`. Moving a patient who is someone's guarantor → 409 `guarantor_has_dependents` (with the list) unless `include_dependents`. `move_open_balance=false` leaves the balance with the old account as a `balance_transfer` adjustment pair (credit on the mover, debit on the old account's guarantor/remaining member; one `account_payment_id`). If nobody remains on the old account there is nothing to leave it with, so the balance moves (`balance_left_with_old_account: false`). An emptied account is closed. Cache invalidated for every affected member. `POST /accounts/{id}/merge {source_account_id}`: members move, the source's guarantor becomes a secondary party, source closed with `merged_into_account_id` (409 `account_parties_limit` if that exceeds 3). |
| RP-7 | ✅ | `responsible_party_id` on PATCH/POST is validated: an RP row id, a patient id (head of household), or a known legacy account key; else 422. Re-sending the patient's current alias is a no-op (so the Edit form's round-trip still saves). Typed `guarantor_patient_id` / `guarantor_party_id` / `account_id` are FK-enforced. |
| RP-8 | ✅ | Primary guarantor lives on the account (so "exactly one primary" is structural); `account_parties` holds up to two more (`secondary`, `billing_contact`), max 3 total → 409 `account_parties_limit`. `GET/POST /accounts/{id}/parties`, `PATCH/DELETE …/{party_id}`, `POST …/{party_id}/make-primary` (swap). `responsibility_pct` 0–100, additional parties may not exceed 100 % in total. A party that is still some member's guarantor cannot be removed (409 `party_is_member_guarantor`). |
| RP-9 | ✅ (statements/payments) · ⚠️ (collections) | `POST /accounts/{id}/payments {amount, tender, distribute: oldest_first|by_member, allocations?}` → one `patient_payments` row per member slice, stamped with `account_id` + shared `account_payment_id`. `by_member` must reconcile to the cent (422 `allocations_not_reconciled`, `patient_not_on_account`). `oldest_first` pays members by oldest open charge up to their balance; any remainder is a credit on the guarantor member. `POST /accounts/{id}/statements` → one statement for the whole account (`statement_scope='account'`, addressed to the primary guarantor + parties with `receives_statements`, member sections in `snapshot.members`); the PDF route renders the member block. `POST /offices/{id}/statements/batch` takes `scope: "account"`. Account aging = sum of members (on `/account-balance` and the statement). **Not done:** there is no finance-charge or collections *engine* in the backend to move to account level — the flags are on the account, ready for one. |
| RP-10 | ✅ | `account_balance` = true account total; `patient_balance_total` = patient's own; `account_id`, `account_member_count` added. `/account-balance` returns `account_id`, `account_no`, `guarantor`. `/responsible-parties/{id}/patients` returns `dob`, `relationship`, `guarantor_kind`, `is_guarantor`, `next_recall`, `account_id` and now resolves to **accounts** (a numeric RP id → that party's accounts; anything else → the accounts of patients holding that alias). |
| RP-11 | ✅ | `PatientRead.guarantor` + `account_no` (batched; `account_id`/`guarantor_*_id` are columns). Scheduler feed: `account_id`, `guarantor {kind, id, name, relationship}`, `patient_balance`. Patient search uses `PatientRead`, so it carries both. |
| RP-12 | ✅ | `GET /patients?account_id=&account_no=&guarantor_name=&guarantor_patient_id=&guarantor_party_id=`. `search=` also matches patients whose guarantor's name matches (≥ 2 chars; ranked below direct matches). `account_no` also matches the migrated RPID. |
| RP-13 | ✅ (exposed) | `GET /accounts/{id}/insurance` → distinct plan/subscriber pairs used by members, the members on each, `subscriber_is_account_member`. **Not enforced**: a subscriber may legitimately sit outside the account (an ex-spouse's employer plan), so it is reported, not refused. |
| RP-14 | 🛠 tooling | `scripts/import_legacy_responsible_parties.py` imports `RespParty.txt` (insert-only, keyed `(tenant, legacy_id=RPID)`), fills `RELTORESP` relationships, then resolves unresolved legacy accounts (Self member first, else the RP row). Dry run by default. **Not applied** on `Test_Dental_Group` — it holds no migrated patients (0 legacy keys); run it on a migrated DB. |
| RP-14 (read side) | ✅ | Until the script links them, an *unresolved* RPID whose guarantor row was imported later is resolved **at read time** by `responsible_parties.legacy_id` (the pre-RP behaviour), reported as `kind: "responsible_party"`. `/letter-context` gains `guarantor`; its `responsible_party` is the RP row only. |
| RP-15 | ✅ | All write paths fold the relationship through `normalize_resp_party_relationship`; Self is always `S`; the backfill set `S` on every self row that had NULL. Vocabulary + precedence + limits published at `GET /metadata/account-rules`. |
| RP-16 | ✅ | `account_change_events` written by change-guarantor, PATCH guarantor moves, merge, party add/update/remove/make-primary, account updates and account payments. `GET /patients/{id}/change-log`, `GET /accounts/{id}/change-log` (with `user_name`). |

## Error codes

`guarantor_required`, `guarantor_patient_not_found`, `guarantor_patient_inactive`,
`responsible_party_not_found`, `responsible_party_inactive`, `account_inactive`,
`account_has_no_guarantor`, `guarantor_not_on_account`, `guarantor_cycle`,
`guarantor_has_dependents` (409), `account_parties_limit` (409), `party_already_on_account` (409),
`party_is_member_guarantor` (409), `invalid_party_role`, `responsibility_pct_range`,
`responsibility_pct_total`, `duplicate_account_no` (409), `merge_same_account`,
`amount_must_be_positive`, `allocations_required`, `allocations_not_reconciled`,
`patient_not_on_account`, `duplicate_allocation`, `account_empty`.

## Migration notes

The backfill (`app/services/account_backfill.py`, re-runnable via
`python -m scripts.backfill_patient_accounts --apply`) classifies `responsible_party_id`:
NULL / own id → Self; app-created numeric key = RP row → party; = another self patient → that
patient; everything else (every migrated RPID) → grouped by the key, guarantor = the group's `S`
member, else an imported RP row, else unresolved. Migrated rows skip the numeric-id checks — their
key is a Denticon RPID and a coincidental match is exactly the RP-1 collision.
