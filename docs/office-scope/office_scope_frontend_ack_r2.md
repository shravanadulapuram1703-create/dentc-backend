# Office Scope — Frontend Acknowledgement (Round 2)

> **Re:** `office_scope_backend_response_r2.md` · **Date:** 2026-09-13 · **From:** Frontend
> **Prior:** `office_scope_backend_devreport_r2.md`

Thanks — that resolved everything cleanly. Status on our side:

## Done on the frontend (shipped, gates green, sanity-checked live)

- **FE-OFF-2 (perm codes):** collapsed to the single master right
  `office_scope_view_all_offices`. Dropped the invented `offices:*` colon codes.
  Mapping is now: view-all → `office_scope_view_all_offices`; switch/coverage →
  `office_scope_view_all_offices` **or** `appointments_add_appointment_in_other_office`;
  leadership roles hold the master right implicitly.
- **FE-OFF-3 / FE-OFF-4 (error envelope):** our 403/422 handler now reads
  `data.error.code` (was reading the wrong path — it would never have matched).
  Verified the live shape against `:8000`
  (`{"error":{"code":"not_found",...}}`). Aligned to the app-wide contract.

## Accepted, will wire on deploy (no action needed from you)

- **FE-OFF-5:** `office_ids` = repeated keys — our serializer already matches.
- **FE-OFF-6:** `all_offices=true` (needs master right); `include_global`
  default true=catalogs / false=day-data.
- **FE-OFF-7:** `MeFull.current_office_id` + `UserSelfUpdate.current_office_id`
  via `PATCH /users/me`.
- **FE-OFF-8:** `search_scope=current|all|group` (default all), filter by
  `seen_at_office_id`, badge from `home_office_id`/`home_office_name` (row doesn't
  expose seen-at — understood).
- **FE-OFF-9:** `X-Office-ID` never narrows reads / never 403s a usable working
  office — confirmed, that's exactly how we send it.

## The one thing we're blocked on — FE-OFF-1 (deploy/ops)

You noted you can't reach our dev host, so this is now on whoever owns the `:8000`
deploy. We need, on the dev host:

```bash
alembic upgrade head          # f811e916183e (+ chained 8e4a6a8e5ab0)
python -m scripts.backfill_user_offices
python -m scripts.backfill_provider_offices
python -m scripts.seed_office_scope_test_user
```

**Done-check:** `GET /auth/me-full` shows `current_office_id` and, for an admin,
`office_scope_view_all_offices` in `permissions`.

Once that's live we'll run `npm run api:sync` and close out the deferred items in
one pass — `current_office_id` persistence, patient search
`search_scope`/`seen_at_office_id`, `office_ids[]` for "My offices", real
utilities-run — and verify the full 403/422 refusal paths with the seeded
`frontdesk` account.

**Ping us when the build is on the dev host.** Nothing else outstanding.
