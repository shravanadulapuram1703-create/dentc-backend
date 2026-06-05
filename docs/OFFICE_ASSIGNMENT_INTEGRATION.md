# Office Assignment — Integration

Setup → Offices → **Office Assignment** (`/setup/offices/office-assignment`).
Phase 3 of the Setup modernization. Backend gaps: `office_assignment_backend_devreport.md`.

## 1. Screen Analysis

**Purpose.** Manage which catalog entities are assigned to a specific office:
procedures, explosion codes, production types, and users.

**User workflow.** Pick an office from the list → a tabbed detail view opens →
each tab shows an Available ↔ Assigned picker (or a gated placeholder) → edits are
staged locally and persisted per-tab via its own Save.

**Tabs (legacy 9):** Procedures, Exp Codes, Prod Types, Users, Providers, Notes Macros,
RX, Ortho Misc Setup, Letters.

| Tab | Built as | Backend |
|-----|----------|---------|
| Users | Editable dual-list assignment | `user-offices` (M:N) — fully backed |
| Providers | Read-only assigned grid | `listProviders({office_id})` (single-office, no M:N) |
| Notes Macros / RX / Letters | Read-only tenant-wide catalog preview | tenant-wide catalogs, no office scope |
| Procedures / Exp Codes / Prod Types / Ortho Misc | Gated "pending backend" | no usable endpoints |

**UI components.**
- `OfficeAssignment.tsx` — list→detail→tabs shell (mirrors `OfficeSetup.tsx` theme/UX).
- `DualListPicker.tsx` — reusable Available↔Assigned transfer list (search, multi-select,
  `>` `»` `<` `«` move buttons, double-click to move). Used by Users; ready for any tab that
  gains an M:N assignment endpoint.
- `ReadOnlyAssignmentGrid.tsx` — reusable read-only searchable data grid (loading/error/empty).
- `tabs/assignment/UsersAssignmentTab.tsx` — editable Users assignment.
- `tabs/assignment/ProvidersAssignmentTab.tsx` — read-only assigned-provider grid.
- `tabs/assignment/CatalogPreviewTabs.tsx` — `NoteMacrosCatalogTab` / `RxCatalogTab` /
  `LettersCatalogTab` (read-only tenant-wide previews with a "not office-specific" banner).
- `TabNotAvailable` (inline) — gated "pending backend" state for the 4 blocked tabs.

## 2. Existing API Mapping

| Concern | Endpoint | Generated fn | Model |
|---|---|---|---|
| Office list | `GET /api/v1/offices` | `listOffices` | `OfficeRead` |
| All users (master) | `GET /api/v1/users` | `listUsers` | `PaginatedResponseUserRead` |
| Assigned links | `GET /api/v1/user-offices?office_id=` | `listUserOffices` | `UserOfficeRead` |
| Assign user | `POST /api/v1/user-offices` | `createUserOffice` | `UserOfficeCreate` |
| Unassign user | `DELETE /api/v1/user-offices/{id}` | `deleteUserOffice` | — |
| Office providers | `GET /api/v1/providers?office_id=` | `listProviders` | `ProviderRead` |
| Notes macros (tenant) | `GET /api/v1/note-macros` | `listNoteMacros` | `NoteMacroRead` |
| RX library (tenant) | `GET /api/v1/prescription-library` | `listPrescriptionLibrary` | `PrescriptionLibraryRead` |
| Letters (tenant) | `GET /api/v1/letter-templates` | `listLetterTemplates` | `LetterTemplateRead` |

Service wrappers (wrap the generated client — no raw axios; page through `size=200`;
snake_case throughout): `src/services/officeUserAssignmentApi.ts` (Users),
`src/services/officeAssignmentCatalogApi.ts` (Providers + the 3 read-only catalogs).

**Column mapping (Users):** `UserID → UserRead.id`, `First Name → first_name`,
`Last Name → last_name`, `Active → is_active`, `Created On → created_at`,
`Created By →` *no backing field (omitted, gap #27)*.

## 3. Frontend Changes

- **New:** `DualListPicker.tsx`, `OfficeAssignment.tsx`,
  `tabs/assignment/UsersAssignmentTab.tsx`, `services/officeUserAssignmentApi.ts`.
- **Wired:** `App.tsx` — added `OfficeAssignment` import; swapped the line-294
  `<PlaceholderPage title="Office Assignment" />` for `<OfficeAssignment />`
  (nav entry in `GlobalNav.tsx` already existed).
- **Client-side glue (Users):** diff-based save (N POST/DELETE), "Copy Users From"
  emulation, Active/Inactive/All filter, master↔assigned partitioning — all because
  the backend lacks bulk/copy/filter endpoints (gap #27).

## 4. Backend Gaps

See `office_assignment_backend_devreport.md` and `backend_devreport.md` #24–#32:
- #24 Procedures — no office↔procedure-code assignment endpoints (gated).
- #25 Exp Codes — resource absent from API (gated).
- #26 Prod Types — resource absent from API (gated).
- #27 Users — works, but no bulk-set / copy-from endpoints and no `created_by` (degraded).
- #28 Providers — single-office FK (no M:N link), no `first_name`/`last_name`/`created_by` (read-only).
- #29 Notes Macros — tenant-wide, no office assignment (read-only preview).
- #30 RX — tenant-wide prescription library, no office assignment (read-only preview).
- #31 Letters — tenant-wide letter templates, no office assignment (read-only preview).
- #32 Ortho Misc Setup — resource absent from API (gated).

## 5. Validation Checklist

| Item | Status |
|---|---|
| Users — Read (load all users + assigned links, join) | ✅ |
| Users — Create (assign via `createUserOffice`) | ✅ |
| Users — Delete (unassign via `deleteUserOffice`) | ✅ |
| Users — Copy from office (client-side) | ✅ |
| Users — Active/Inactive/All filter (client-side) | ✅ |
| Search / multi-select / move buttons | ✅ |
| Loading / error / empty / saving states | ✅ |
| Success/error notifications (sonner) | ✅ |
| Providers — read assigned grid (`listProviders({office_id})`) | ✅ read-only |
| Notes Macros / RX / Letters — read tenant-wide catalog | ✅ read-only |
| Procedures / Exp Codes / Prod Types / Ortho Misc | ⛔ gated (no backend) |
| No mock/hardcoded business data | ✅ (all grids backend-driven) |
| `npx tsc -b` / `npx eslint` | ✅ clean on all new/changed files |

## 6. Completion Summary

**Completed:** Office Assignment screen wired live with all 9 legacy tabs. Reusable
`DualListPicker` + `ReadOnlyAssignmentGrid`. Fully functional **Users** assignment tab
(assign/unassign/copy/filter). Read-only **Providers** assigned grid (office-scoped).
Read-only tenant-wide catalog previews for **Notes Macros / RX / Letters** with a
"not office-specific" banner. **Procedures / Exp Codes / Prod Types / Ortho Misc Setup**
gated. All backend gaps recorded (#24–#32). `tsc` + `eslint` clean.

**Outstanding (backend-dependent):**
- Editable assignment needs M:N link tables + endpoints: Procedures (#24), Exp Codes (#25),
  Prod Types (#26), Providers (#28), Notes Macros (#29), RX (#30), Letters (#31).
- New resources required: Exp Codes (#25), Prod Types (#26), Ortho Misc Setup (#32).
- A bulk users endpoint (#27) would simplify the Users save path.
When any land: `npm run api:sync`, then wire the tab to `DualListPicker` (component ready).

**Dependencies:** none for Users / Providers / the read-only previews; the editable/gated
tabs depend on backend #24–#32.
