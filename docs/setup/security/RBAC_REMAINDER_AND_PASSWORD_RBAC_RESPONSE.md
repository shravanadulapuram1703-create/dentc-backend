# Backend Response — RBAC-6 remainder + Password RBAC (PWD-RBAC-1…3)

> **To:** Frontend · **From:** DentC Backend · **Date:** 2026-11-16
> **Re:** `dentc-frontend/backend_devreport.md` → "RBAC / access-rights enforcement"
> (RBAC-6 remainder) and "Password RBAC — who may change which password".
> **Status:** RBAC-6 remainder — **done** (one item has nothing to gate, see below).
> PWD-RBAC-1 · 2 · 3 — **done**. No migration.

RBAC-1…5 and RBAC-6 phase 1 were already shipped
([ACCESS_RIGHTS_RBAC_GAPS_RESPONSE.md](ACCESS_RIGHTS_RBAC_GAPS_RESPONSE.md)); this
closes what that response left itemised.

The enforcement model is unchanged: `admin`/`super_admin` bypass; a non-admin in
**no group is ungated** (writes fall through); a grouped user without the right
gets **403 `permission_denied`** with `details.required_any_of`.

## RBAC-6 remainder

| Right | Where | How |
|---|---|---|
| `patient_prescription_strike_off` | `PATCH /prescriptions/{id}` with `is_active:false`, and `DELETE /prescriptions/{id}` | Field-scoped (`PrescriptionCRUD.update`): only a PATCH that actually strikes an active Rx off. Re-sending `false` on a struck Rx is not gated. The soft DELETE is the same act, gated via `delete_permissions`. |
| `transactions_treatment_plan_discount` | `PATCH /treatment-plan-items/{id}` (+ `POST` with a non-zero `discount`) | Fires only when the discount **moves**. |
| `transactions_treatment_plan_edit_fee` | `PATCH /treatment-plan-items/{id}` | Fires only when `fee` changes. A new item's fee is pricing, so POST is not gated. |
| `transactions_treatment_plan_change_status_or_ids` | `PATCH /treatment-plan-items/{id}` | Fires when `status`, `plan_id` or `phase_id` changes. Server-driven `scheduled`/`completed` transitions (charge/appointment links) do not go through this check. |
| `patient_medical_history_full_control` | `PUT /patients/{id}/medical-history`, `POST …/medical-history/copy-from/{src}`, `POST …/medical-history/sign`, `POST /patient-medical-alerts/bulk`, `POST /patient-questionnaire-responses/bulk`, and writes on `/patient-medical-alerts` + `/patient-questionnaire-responses` | Route gate. Reads stay open. `POST /patients/register` writes answers through the service, so registering a patient is **not** gated. Note: the Add Patient fallback path (`createPatientMedicalAlert` per row) will report its existing "could not be saved" warning for a grouped user who lacks the right. |
| `imaging_capture_acquire` (or `imaging_full_control`) | `POST /patients/{id}/imaging/captures` | Route gate. |
| `transactions_add_post_adjustments` | `POST /patient-adjustments` | `create_permissions`. |
| `patient_add_progress_notes` / `patient_edit_progress_notes` | `POST` / `PATCH /progress-notes` | `create_permissions` / `update_permissions`. |

**Progress-note "lock override": nothing to gate.** The catalog has no
lock-override right, and the server has no override path: a locked note (signed,
or past the office-local midnight, PN-7/PN-9) refuses text edits for **everyone**,
admins included. The add/edit rights above are the closest real codes. If the
product wants an override, we need a catalog code plus the rule for who holds it.

Rights in `rightCodes.ts` the FE can now treat as server-enforced:
`patient.prescriptionStrikeOff`, `patient.medicalHistoryFull`, `imaging.capture`.

Still not server-gated (no FE ask yet; each is a one-line registry entry when
needed): `transactions_treatment_plan_add`, `..._re_estimate`,
`transactions_change_update_procedure_insurance_benefits_in_treatment_plan`, the
`patient_patient_notes_*` set, `transactions_ledger_note_delete`.

## PWD-RBAC-1 — server-side rule

Admin user writes that carry a password (`PUT /users/{id}/complete`,
`PATCH /users/{id}`) are treated as a reset of **another** user's password:

- **403 `own_password_self_service`** when `user_id` is the caller. Their own
  password goes through `POST /users/me/change-password`, which checks the current
  password. `details.endpoint` names that route. Editing your own record without a
  password still works.
- **403 `password_reset_not_permitted`** when the caller is not an administrator.
  The routes are already admin-only; this check also lives in
  `user_admin_service.assert_can_set_password`, so no other code path can skip it.
- `POST /users/complete` / `POST /users` (new user) is admin-only as before. The
  new user can never be the caller.

**Who counts as an administrator:** `admin` + `super_admin`. That is exactly the set
the Users write routes already admit. The FE's list also includes `owner`, but an
`owner` gets a 403 on `PUT /users/{id}/complete` today (role gate) and always has.
Widening the Users screen to `owner` would be a separate decision. Until then,
please key the button on PWD-RBAC-2 below rather than the hard-coded list.

## PWD-RBAC-2 — `MeFull.can_reset_user_passwords`

New boolean on `GET /auth/me-full`. It is true exactly when PWD-RBAC-1 would let
the caller reset another user's password. Show **Reset Password** when it is true
**and** the record is not your own.

## PWD-RBAC-3 — complexity policy, server-side

The rules are: 8+ characters, a lowercase letter, an uppercase letter, a number and
a symbol. They live in one place, `app/core/password_policy.py`, and are enforced on
**every** endpoint that sets a password:
`POST /users`, `PATCH /users/{id}`, `POST /users/complete`,
`PUT /users/{id}/complete`, `POST /users/me/change-password`,
`POST /auth/reset-password`, the legacy create-password activation, and
`POST /auth/signup`.

- Failure: **422 `password_too_weak`**, with `details.failed_rules` (for example
  `["uppercase","symbol"]`) and `details.field` (`password` or `new_password`).
- `GET /auth/password-policy` (no auth needed, so the reset page can use it) returns
  `{enforced, min_length, rules:[{code,label}]}` in the order to render the
  checklist.
- Login does **not** apply the policy, so existing weaker passwords still sign in.
- `PASSWORD_POLICY_ENFORCED=false` is the ops kill switch.

This also closes **USR-AUTH-5**.

## Verification

[tests/test_rbac_remainder.py](../../../tests/test_rbac_remainder.py) covers every
gate above: the move-only behaviour, the ungated fall-through, both 403 codes, the
`me-full` flag, the policy endpoint and the 422.
