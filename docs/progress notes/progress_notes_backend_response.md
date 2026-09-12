# Progress Notes — backend response (round 2: PN-6, PN-8, PN-9, PN-11, PN-12)

Date: 2026-09-11 · Module: Patient → Progress Notes · Report:
`docs/progress notes/progress_notes_backend_devreport.md` (status update of
2026-09-07 + PN-8..PN-12)

**Everything still open in the report is closed.** PN-1..5, PN-7, PN-8 and
PN-10 had already landed (PN-1 as `GET|PUT /users/me/signature`, PN-10 as the
API-wide `UtcDatetime` serialiser — `created_at` ends in `+00:00`). This round
ships PN-6, PN-9, PN-11, PN-12, answers the PN-8 audit question, and fixes a
tenancy hole found on the way.

Alembic `17559b3b70d4` (two nullable columns) — **applied to the dev DB**, along
with both data repairs below. Frontend action: `npm run api:sync`; then
`noteContent.ts`'s legacy decode becomes a no-op on the migrated tenant (keep
it — it is harmless and still right for a tenant migrated with the old
importer), `Restore`/edit gating can read `locks_at`, and the Category dropdown
can bind to `label`.

---

## PN-12 — Legacy note bodies (`~^^~`) — fixed at the source, repaired in place

### What was wrong

`s35_progress_notes.py` stored the export's `NOTESHTML` verbatim. The export
holds the markup entity-escaped once **and** with every `&` replaced by the
token `~^^~` (a delimiter-survival trick). Live counts on the dev DB before
the repair:

| Symptom | Rows |
|---|---|
| `notes_html` carries `~^^~` | **30,322** of 35,286 legacy rows (86 %) |
| `notes` carries `~^^~` | 13 |
| `notes_html` is Restorative stroke JSON (`{"type":"rx-draw",…}`) | 4 |
| Trailing `<p>&nbsp;</p>` spacer | 11,184 |
| `<p><p>…</p></p>` double wrap | 3 |

The plain `notes` export is lossy on its own: a literal `?` where the source
had `&nbsp;`, and a fifth of the rows with every line break gone — so it was
not a fallback for display *or* for `search=`.

### The decode is one entity level, deliberately

`&amp;lt;` after `~^^~ → &` is a `<` the clinician typed (`pocket <3mm`): the
editor stored `&lt;`, the export escaped it again. One pass gives `&lt;`, the
correct HTML; a second pass would turn it into a real `<` and break the markup.
47 rows hold `&amp;amp;nbsp;` (a literal "&nbsp;" the legacy editor already
showed on screen) and come out exactly as Denticon rendered them. Only
`lt`/`gt`/`amp`/`quot`/`#39`/`#34` are decoded — the same set as
`noteContent.ts`, so server and browser agree byte for byte.

### One module, three callers

`app/services/progress_note_content.py` (pure stdlib, a Python twin of
`noteContent.ts`): `decode_legacy_markup`, `tidy_note_html` (drops the
`<p><p>` wrap, the `\r\n` between paragraphs, empty and trailing spacer
paragraphs), `html_to_text` (block tags → newline, entities decoded, `&nbsp;`
→ space), `drawing_payload`, `repair_note_content`.

1. **Importer** — `s35` now runs `repair_note_content(..., regenerate_text=True)`
   on every row, so a future migration never re-introduces the token (item 3).
2. **Write path** — `ProgressNoteCRUD.create/update` derive `notes` from
   `notes_html` when a client sends only the rich body (an explicit `notes`
   always wins). The searchable column can no longer drift from the screen.
3. **Repair** — `scripts/repair_progress_note_content.py` (items 1, 2, 4):

```
python -m scripts.repair_progress_note_content            # dry run + tallies
python -m scripts.repair_progress_note_content --apply    # writes, backs up first
python -m scripts.repair_progress_note_content --restore backups/progress_note_content_<ts>.jsonl
```

Applied on the dev DB:

| Tally | Rows |
|---|---|
| `html_decoded` | 30,322 |
| `notes_decoded` | 13 |
| `notes_regenerated` (plain column rebuilt from the repaired HTML) | 23,305 |
| `drawing_moved` (rx-draw JSON → `drawing_strokes`, `notes_html` cleared) | 4 |
| rows changed | 31,029 |

Design points worth knowing:
- **`updated_at` is not stamped** by the repair (explicit in the UPDATE so the
  ORM `onupdate` stays quiet). A data repair is not a clinical edit; "Modified
  today" on 30,000 notes would be a lie in the new Created/Modified column.
- **Reversible**: every changed row's original `notes`/`notes_html`/
  `drawing_strokes`/`content_hash` goes to a JSONL backup before the first
  write; `--restore` puts them back.
- A repaired row that carries a signature `content_hash` is **re-hashed** to the
  repaired body — the signer saw the decoded text (the FE decoded on render), so
  that is what the signature attests to; leaving the old hash would flip every
  such note to `stale`. (None of the legacy rows were signed; the path is there
  for a tenant that signed through the app before this ran.)
- `notes` is regenerated for **every legacy row whose plain column disagrees
   with its HTML**, not only the 791/384 the sample flagged — the `?` and the
   collapsed newlines are the visible symptoms of one lossy export, and the
   HTML is the authoritative copy.

Run note: the first `--apply` pass dropped its connection halfway (2,000
wide-text rows per round-trip exceeded the session's 30 s statement timeout)
and, through the ORM `JSON` type, wrote a JSON `null` instead of SQL NULL into
`drawing_strokes` on the rows it did commit — which the restorative chart's
`IS NOT NULL` query would have read as "has a drawing". Both are fixed in the
script (500-row batches, `--batch-size`, `none_as_null`), the 16,000 JSON
nulls were converted back before the resume, and a re-run is idempotent, so
the second pass simply picked up where the first stopped (one backup file).

Acceptance, verified live: no `notes`/`notes_html` contains `~^^~`; rows
20001/20002/20003 have newlines and no `?` before "Periodic"/"severe";
`GET /progress-notes?search=Periodic%20Exam` matches 20002.

---

## PN-6 — Macro category labels — **not blocked after all** (also closes NM-2)

The Notes-Macros report (NM-2) recorded that "the label lookup was never
exported". It was: `DEFINITIONS.txt` carries group `NOTESMACROS`, one row per
`Macrocat` code (`179 → DIAGNOSTIC`, `180 → PREVENTIVE`, … 15 codes), and those
rows have been in `definitions` since the first migration — under `legacy_id`,
with a blank `key1`. `s13_note_macros.py` simply wrote the code and never
joined it.

- **Importer** — `s13` resolves `Macrocat` through `DEFINITIONS.txt` at import
  time; an unmapped code is stored as written.
- **Data** — `scripts/normalize_note_macro_categories.py` (dry run by default)
  rewrites the stored code to the label (`updated_at` untouched) and fills the
  blank `key1` on the `NOTESMACROS` definitions so the generic
  `GET /definitions?group_code=NOTESMACROS` dropdown has a key like every other
  group. Applied: **121/121 macros relabelled, 0 unmapped, 16 definitions keyed**.
  The 15 categories now read `DIAGNOSTIC (28)`, `RESTORATIVE (17)`,
  `IMPLANT SERVICES (12)`, ….
- **API, defensive** — `NoteMacroRead.category_label` and `label` on
  `GET /note-macros/categories` resolve a leftover code through the tenant's
  `NOTESMACROS` definitions (`legacy_id` or `key1`), so a tenant migrated with
  the old importer never renders `179`. `category` stays the stored value (the
  filter key); the list is sorted by label. The NM-5 duplicate guard keys on
  `name + category` and fires on a **move** only, so the relabel cannot
  collide two existing macros.

---

## PN-9 — Lock day is the office's day, not UTC's

`_note_is_locked` compared `created_at.date()` (UTC) with the UTC date. A
US-Eastern note written at 3 PM locked at 8 PM local, and one written after
8 PM read as created "tomorrow" — the window in which the editor opened as
editable and Save failed with the 409.

Now: `note_timezones()` resolves each note's zone — the note's `office_id`,
else the patient's `home_office_id`, else the default (`America/New_York`) —
in two batched statements per page, and the day comparison converts the UTC
`created_at` into that zone. **Storage stays UTC** (`created_at`/`signed_at`
are stamped as before; PN-10's serialiser labels them `+00:00`), so nothing
else in the app changes; only the *judgement* of "today" moved.

`ProgressNoteRead` gains:
- `timezone` — the IANA zone the lock was judged in (`"America/New_York"`).
- `locks_at` — the UTC instant the text locks (office-local midnight after
  creation); `null` once the note is locked or signed. The editor can show
  "editable until 11:59 PM" and pre-disable without re-deriving anything.

The 409 `details` now carry `timezone` beside `locked_fields`.

---

## PN-11 — `updated_at` / `updated_by` (+ `updated_by_name`)

`ProgressNote` moved from `CreatedAtMixin` to `TimestampMixin` and gained
`updated_by` (FK users). `ProgressNoteCRUD.update` now **delegates to
`CRUDBase.update`** instead of assigning columns itself, so the engine's rules
apply to notes too:

- a real change stamps `updated_by`/`updated_at`; a PATCH that re-sends the
  stored values stamps **nothing** (MH-20) — the list's Modified column will
  not read "today" because someone opened and closed the editor;
- the before/after diff is handed to the audit context (MH-19).

`updated_by_name` is resolved in the same batch as the other actor names.

## PN-8 open question — yes, a DOS correction is audited

With the delegation above, `PATCH {"note_date": …}` writes an `audit_logs`
row with `details.before.note_date` / `details.after.note_date`,
`resource_type = "progress-notes"`, `resource_id = <note id>` and
`patient_id` — readable by any tenant user at
`GET /patients/{id}/audit-logs?resource_type=progress-notes&resource_id={note_id}`
(admin: `GET /audit-logs?resource_id=`). No dedicated `note_date_changed_*`
columns: the audit row already answers who/when/from/to, and the note itself
now shows `updated_by`/`updated_at`. Behaviour otherwise as patched locally:
DOS editable on an unsigned prior-day note (200), 409 once signed, text fields
409 on any locked note.

---

## Rides along — tenancy on `progress_notes`

`progress_notes` carries no `tenant_id`, and the generic engine only scopes
models that do. `ProgressNoteCRUD` had no `_scope_tenant` override, so
`GET|PATCH|DELETE /progress-notes/{id}` accepted any tenant's note id, the
unfiltered list returned every tenant's notes, and a note could be created on
another tenant's patient. Now scoped through the patient (the perio pattern);
all four are 404 across tenants. The sign/attachment routes already did this.

---

## Not changed

- **PN-10** — already API-wide via `UtcDatetime`; the round-2 tests pin
  `created_at` ending in an offset.
- **`notes_html` is not sanitised server-side.** The repair removes only the
  import artefacts; the FE allow-list still runs on render. A server allow-list
  would be a separate decision (it can drop clinical text).
- The 700 legacy rows whose `notes_html` never carried the token (re-saved
  through the app, or exported clean) were tidied only where the plain column
  disagreed with the HTML.

## Tests

`tests/test_progress_notes_round2.py` (18) — the content rules on the report's
sample row, single-level decode incl. the `&amp;lt;` chain, tidy scope,
write-path derivation + `search=`, office-local lock (pure, with injected
`now`, and the UTC-date bug reproduced), `locks_at`/`timezone` on the read,
home-office fallback, DOS-after-lock, `updated_by` on real change only, the
audit row's before/after, cross-tenant 404s, and category labels. The original
`test_progress_notes_module.py` (14) and `test_note_macros.py` still pass.
