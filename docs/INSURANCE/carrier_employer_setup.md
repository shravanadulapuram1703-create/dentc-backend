# Insurance Setup — Carriers & Employers (Screen Analysis)

Unit 1 of the Insurance modernization phase. Replaces the placeholder Setup
routes with backend-driven master-detail screens.

## Screens delivered
| Route | Component | Backend |
| --- | --- | --- |
| `/setup/insurance/dental-carriers` | `CarrierSetup` (`variant="dental"`) | `insurance-carriers`, `carrier_type="True"` |
| `/setup/insurance/medical-carriers` | `CarrierSetup` (`variant="medical"`) | `insurance-carriers`, `carrier_type="False"` |
| `/setup/insurance/employers` | `EmployerSetup` | `employers` |

Files: `src/components/setup/insurance/{insuranceData.ts, carrierService.ts,
CarrierSetup.tsx, EmployerSetup.tsx}`.

## Screen analysis
- **Purpose:** CRUD management of dental/medical insurance carriers and
  employers used across patient insurance, plans, claims, and fee schedules.
- **Workflow:** Searchable/sortable list ⇄ editable detail (Add / Edit / Save /
  Delete). Mirrors `ProviderSetup` / `OfficeSetup`.
- **UI components:** App design system (cards, `#3A6EA5` primary, lucide icons,
  sonner toasts). One `CarrierSetup` component is parameterized by `variant`;
  Dental and Medical screens differ only in icon/title and the `carrier_type`
  read/write.

## API mapping
- Carriers: `listInsuranceCarriers` (via `carrierService.fetchAllCarriers`),
  `getInsuranceCarrier`, `createInsuranceCarrier`, `updateInsuranceCarrier`,
  `deleteInsuranceCarrier`.
- Employers: `listEmployers`, `getEmployer`, `createEmployer`, `updateEmployer`,
  `deleteEmployer`.
- DTOs: `InsuranceCarrierRead/Create/Update`, `EmployerRead/Create/Update`. Form
  state binds 1:1 to snake_case fields (`insuranceData.ts`) — no camelCase
  aliases, no mapper.

## Legacy → modern decisions
- Legacy splits Dental and Medical into separate screens; we keep that
  navigation but back both with the single `insurance-carriers` table,
  partitioning on `carrier_type` client-side (see devreport **INS-1**).
- Legacy uses a read-only detail panel + separate Edit modal; the modern app
  uses an inline editable detail (consistent with Provider/Office Setup).
- Legacy capability fields (real-time eligibility, claim status, DXC attachment,
  insurance type) and employer salesrep are **omitted** — no backing fields
  (devreport **INS-3**, **INS-5**). Not faked.

## Workaround in place
`carrierService.ts` pages the full carrier list (size=200) and partitions by
`carrier_type`, cached 60s and shared across the Dental/Medical screens, with
`invalidateCarriers()` on every mutation. Remove once the backend adds a
server-side `carrier_type` filter (devreport **INS-1**).

## Validation checklist
- [x] Carrier: create / edit / delete / search / sort / active-filter
- [x] Dental vs Medical partition correct (carrier_type True/False)
- [x] Employer: create / edit / delete / search / sort
- [x] `npx tsc -b` clean · `npx eslint src/components/setup/insurance/` clean
- [ ] Live-verified at :5173 (in progress)

## Outstanding / dependencies (later units of this phase)
- Insurance Plans + Coverage Rules + Custom Coverage setup
- Fee Schedule Manager (carrier/plan assignments — carrier `fee_id` links here)
- Insurance Dashboard (KPIs; no backend aggregation — client-side)
- Verification workflow (tracked on subscriber `elig_*` fields; no dedicated
  endpoint)
