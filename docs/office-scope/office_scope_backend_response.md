# Office Scope — Backend Response (OFF-SCOPE-1 … 19)

> **Module:** cross-cutting (office context) · **Backend:** DentC Backend v1.0.0 (`/api/v1`)
> Implements `docs/office-scope/office_scope_backend_devreport.md`. Alembic
> `f811e916183e` (`current_office_id`, `audit_logs.office_id`,
> `patient_payments.created_office_id`).

## The model, exactly as the frontend states it

**Office = the user's working context, not a fence. Tenant is the security
boundary.** The enforcement below is only ever about things a client could
bypass by editing a query string. Two escape hatches, mirroring
`permission_service`'s "a user in no group is ungated":

- a caller holding `offices:view_all` / `offices:switch_any` is never narrowed
  and never office-blocked;
- a caller with **zero** `user_offices` rows is *ungated* (tenant-wide) — a
  migrated tenant whose assignments are not seeded yet must not lose access.

The whole layer is gated by `settings.OFFICE_SCOPE_ENFORCED` (default **on**) as
an ops kill switch. The seeded `super_admin` holds every office right, which is
why the existing test suite is unaffected.

The engine home is [app/services/office_scope_service.py](../../app/services/office_scope_service.py):
one `OfficeScopeSpec` on a `CrudConfig` opts a resource into scoping, and the
CRUD router applies list narrowing + create/update validation + the default
write-stamp uniformly.

## What shipped, per requirement

| Id | Status | How |
|---|---|---|
| **OFF-SCOPE-1** | ✅ | `validate_target_office` — an explicit `?office_id=`/`?home_office_id=`, an `office_ids[]`, the `X-Office-ID` header, an `/offices/{id}/*` path, and any create/update body office are **403 `office_not_assigned`** unless assigned or privileged. Wired into the CRUD engine, `get_office_context`, and `office_assignment._office_scope`. |
| **OFF-SCOPE-2** | ✅ | `resolve_list_office_filter` on every office-scoped list: omitted = the caller's assigned offices; `all_offices=true` = tenant-wide, needing `offices:view_all` (`reports:all_offices` on report/dashboard routes) else 403. Each list route now documents `all_offices`/`office_ids`/`office_group_id`/`include_global` in OpenAPI. A **patient-scoped** list (`?patient_id=`) is never narrowed — the chart/ledger are org-wide. |
| **OFF-SCOPE-3** | ✅ | `X-Office-ID` header, validated against assignments, recorded on the audit row + used as the default write-stamp when a create omits `office_id`. `MeFull.current_office_id` (validated, falls back to the primary assignment) + `UserSelfUpdate.current_office_id` + `last_patient_id` writable (`users.current_office_id` column). CORS already reflects the header (`allow_headers=["*"]`). |
| **OFF-SCOPE-4** | ✅ | `include_global` flag on nullable-office lists — default **true** for catalogs (`fee-schedules`, `labs`, `referrals`, `place-of-service-codes`, `explosion-codes`, `sms-templates`, `postcard-templates`, `campaigns`, …), **false** for day-data. Fixes the PLAN-8 "`?office_id=N` hides null-office rows". |
| **OFF-SCOPE-5** | ✅ | `GET /patients` gains `seen_at_office_id` (join appointments ∪ procedures) and `search_scope=current\|all\|group`, resolved in `PatientCRUD` against the caller's working office/group. Patients stay **All offices** by default (`default_narrow=False`). |
| **OFF-SCOPE-6** | ✅ | `GET /patients/{id}` — a caller without `patients:view_cross_office` gets **403 `patient_not_in_office`** unless the chart's home office is theirs or the patient was seen at one of theirs (`assert_patient_visible`). |
| **OFF-SCOPE-7** | ✅ | `office_id` honoured (filter + default narrowing) on `patient-notes`, `patient-recalls`, `chart-conditions`, `prescriptions`, `ortho-plans`, `patient-payment-plans`, `patient-reg-plans`, `ledger-insurance-details`, `image-details`, `caries-risk-assessments`, `perio-chart-activity`, `patient-procedures`, `perio-exams`, `sms-messages`. Patient-scoped reads stay org-wide. |
| **OFF-SCOPE-8** | ✅ | Repeatable `office_ids[]` + `office_group_id` on every office-scoped list, the dashboard summary, and the AppointNow inbox. `GET /offices?assigned_to_me=true` (opt-in; the default list stays tenant-wide — it is the badge label table). |
| **OFF-SCOPE-9** | ✅ | `/offices/{id}/{procedure-codes,exp-codes,production-types,note-macros,prescription-library}/effective` (unassigned = full catalog, the LTR-7 semantic). `only_show_office_items` = the FE passes the patient's home office to `/effective`; the coverage-% fix (FEE-1) already shipped. |
| **OFF-SCOPE-10** | ✅/data | `OfficeAssignment` enriched with `short_id`, `is_active`, `office_group_id`, `timezone`. `scripts/backfill_provider_offices.py` (existing) reconstructs `provider_offices`; `scripts/backfill_user_offices.py` (new) seeds `user_offices` from evidence for the data-hygiene note. |
| **OFF-SCOPE-11** | ✅ (flag) | `require_on_create` on point-of-service creates (payments, adjustments, claims, notes, recalls, prescriptions, treatment plans, time clock) → **422 `office_id_required`** when off *and* no `X-Office-ID` default, gated by `OFFICE_REQUIRE_POS_OFFICE` (default **off** so it does not 422 legitimate creates before the FE always supplies an office). `patient_payments.created_office_id` records the posting office. |
| **OFF-SCOPE-12** | ✅ | `AppointmentCRUD` validates `operatory.office_id == office_id` (**422 `operatory_office_mismatch`**), derives `office_id` from the operatory and `provider_id` from `operatory.provider_id` when omitted. |
| **OFF-SCOPE-13** | ✅ | `offices:view_all`, `offices:switch_any`, `patients:view_cross_office`, `reports:all_offices` defined in `permission_service`; owner/admin/manager/super_admin hold all; the legacy `appointments_add_appointment_in_other_office` maps to view/switch. Surfaced in `MeFull.permissions`. |
| **OFF-SCOPE-14** | ✅ | `POST /sms/send` defaults a new thread's office from `X-Office-ID` (validated); `sms-messages` list is office-scoped; messaging conversations stay tenant-wide. |
| **OFF-SCOPE-15** | ✅ | AppointNow inbox gains `office_ids[]`; `office_code` already non-null (AN-17). WS still rides the messaging tenant topic (AN-6). |
| **OFF-SCOPE-16** | ✅ | `POST /utilities/{id}/run` validates the office against assignments (403) and requires an office for office-scoped utilities (**422 `office_id_required`**, `OFFICE_SCOPED_UTILITIES` set); the per-(utility, office) duplicate guard already existed. |
| **OFF-SCOPE-17** | ✅ | `audit_logs.office_id` (indexed) stamped from `X-Office-ID` (else the row's office); `?office_id=` on `GET /audit-logs` and `GET /patients/{id}/audit-logs`. |
| **OFF-SCOPE-18** | ✅ | `GET /dashboard/summary?office_id=&office_ids=&office_group_id=&all_offices=&date=` — sums the DASH-1/DASH-2 office roll-ups across the resolved office set **server-side** (never a client loop). |
| **OFF-SCOPE-19** | ✅/doc | `OfficeRead.timezone` already exists and now rides `OfficeAssignment`; the `payment_portal_posting_office` sentinel and `model_office_id` are documented below; account-settings PATCH is already partial-preserving. |

## Notes for the frontend

- Flip `OFFICE_ASSIGNMENT_ENFORCED` on in `officeScopeModel.ts` — the server now
  enforces OFF-SCOPE-1/2. Keep sending `all_offices=true` on deliberate
  all-office reads (nothing narrows silently otherwise).
- Send `X-Office-ID` on mutations so the posting office and the audit trail are
  correct; it is validated, so only send an office the user is assigned to (or
  one they can switch to).
- `patient_not_in_office` (403) on `GET /patients/{id}` means the chart is
  outside the caller's offices and they lack `patients:view_cross_office`.
- `OFFICE_REQUIRE_POS_OFFICE` stays **off** until the FE always supplies an
  office on point-of-service creates; the default-stamp from `X-Office-ID` works
  regardless.

## OFF-SCOPE-19 documentation

- `AccountSettings.payment_portal_posting_office` is a **string** holding either
  an office id or a sentinel (e.g. the patient's home office) — it is stored and
  returned verbatim; the resolver that consumes it lives with the payment-portal
  posting logic.
- `AccountSettings.model_office_id` is the "model office" a new office is cloned
  from in Setup; it is a plain FK to `offices`, nullable.
- `AccountSettings.only_show_office_items` (OFF-SCOPE-9) = filter office-owned
  catalog pickers by the **patient's home-office** assignment; the backend
  enabler is the `/effective` routes, and the FE decides which office id to pass.
