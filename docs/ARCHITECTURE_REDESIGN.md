# DentC Frontend — Architecture Review & Redesign Plan

> Status: Proposal / living document. Target: production-grade, multi-developer, scalable React + TypeScript app integrated with a FastAPI backend via generated API clients.
>
> **Locked decisions (2026-05-30):**
> 1. **Schema source = committed `openapi.json`.** The backend exports the spec into the repo; Orval reads the file (deterministic, offline-capable, diffable in PRs). No live-URL generation.
> 2. **Casing = keep snake_case.** Generated TS types mirror FastAPI exactly — no client-side case mapping, fastest migration. UI code reads snake_case fields.
> 3. **Mode = plan only.** No implementation yet; this document is the agreed reference for when work starts.

---

## 0. TL;DR

The codebase is functional but shows classic "many-AI-agents" entropy: **4 different ways to call HTTP**, **manual `useState/useEffect` fetching duplicated across ~15 components**, **manual snake_case↔camelCase mapping in every service**, **fragmented/duplicated types**, **abandoned `.optimized` and `_old` file forks**, and **a hardcoded API URL that ignores the existing `.env`**.

The single highest-leverage change is to **generate the entire API layer (types + TanStack Query hooks + axios calls) from the FastAPI OpenAPI schema using Orval.** That one move deletes most of the hand-written `src/services/*`, `src/mappers/*`, and per-component fetch boilerplate, and makes "backend changed" a one-command regeneration instead of a manual hunt.

---

## 1. Architecture Review

### 1.1 Current stack (confirmed from `package.json`)

| Concern | Current | Notes |
|---|---|---|
| Framework | React 19, Vite 7, TS 5.9 | Modern, good baseline |
| Routing | react-router-dom 7 | Inline auth guards, prop drilling |
| Styling | Tailwind v4 + Radix (shadcn-style `ui/`) | Fine |
| HTTP | axios 1.13 (+ raw `fetch` in one file) | Single instance, hardcoded URL |
| Server state | **none** — manual `useState`+`useEffect` | Biggest gap |
| Client state | Context API + `localStorage` | `AuthContext` overloaded |
| Forms | `react-hook-form` **installed but unused**; hand-rolled `useState`/`useReducer` | Inconsistent |
| Validation | **none** (no zod/yup) | API responses trusted blindly |
| Toasts | `sonner` installed, barely used | Inconsistent error UX |
| Codegen | **none** | Types & mappers hand-written |
| Testing | **none** (no vitest/jest/RTL/playwright) | Zero coverage |

### 1.2 Folder structure issues

- **Three competing "pages" locations:**
  - `src/pages/` — `LoginPage`, `SignUpPage`, `ForgotPasswordPage`
  - `src/components/pages/` — `Dashboard`-style app pages (`Scheduler`, `Patient`, `PatientLedger`, …)
  - `src/components/Login.tsx` — a *second* login implementation
- **Two parallel `setup` trees:** `src/components/pages/setup/` and `src/components/setup/offices/`.
- **No path aliases.** `tsconfig.app.json` has no `paths`, `vite.config.ts` has no `alias`. 17 files reach across the tree with `../../../`. (`src/components/ui/utils.ts` holds `cn()` instead of the conventional `@/lib/utils`.)
- **15 API-contract `.md` files dumped in repo root** — manually maintained, guaranteed to drift from the real OpenAPI schema.

### 1.3 Abandoned forks / dead weight (delete these)

| Keep | Delete (dead fork) |
|---|---|
| `src/App.tsx` | `src/App.optimized.tsx` |
| `vite.config.ts` | `vite.config.optimized.ts` |
| `package.json` | `package.json.optimized` |
| `src/components/pages/setup/UserSetup.tsx` | `UserSetup_old.tsx` |
| one EditPatient modal | `EditPatientModal.tsx` **or** `EditPatientModalRefactored.tsx` (pick one) |
| one postcss config | `postcss.config.cjs` **or** `postcss.config.js` |
| — | `src/services/.ts` (empty/garbage filename) |

> Note: the `.optimized` files actually contain *better* config (code-splitting, lazy routes, terser). Don't just delete — **port their good parts into the canonical files**, then delete the forks.

### 1.4 API layer (the core problem)

Four incompatible HTTP styles coexist:

1. **axios instance** (`src/services/api.ts`) — most services. Auth via request interceptor reading `localStorage`.
2. **raw `fetch`** (`src/api/feeSchedules.ts`) — **no auth token attached**, different base URL (`localhost:3000`), own in-memory cache.
3. **axios wrapper** (`accountSetupApi.ts`) — `getJson<T>` + `extractResponseData` to peel inconsistent `{data:{data:...}}` nesting.
4. **WebSocket class** (`aiChatWebSocket.ts`) — token via query string.

Plus a hardcoded base URL that **ignores the `.env` you already have**:

```ts
// src/services/api.ts — current
const api = axios.create({
  // baseURL: import.meta.env.VITE_API_BASE_URL || "http://34.66.199.55:8000/",
  baseURL: "http://127.0.0.1:8000/",   // <-- hardcoded, .env ignored
});
```

**Manual case-mapping everywhere.** Each service hand-converts snake_case⇄camelCase, with duplicated helpers (`extractOfficeId` exists in ≥2 files with *different* logic), inline `code.user_code || code.userCode || ""` defensive reads, and 4 layers of transformation (service → form mappers → `src/mappers/*` → inline). This is exactly what schema-driven codegen eliminates.

**Inconsistent error handling:** some calls bubble raw, some `try/catch`+`console.error`+rethrow, some swallow to `{}` silently. User-facing errors mix `error.response?.data?.detail` vs `.error.message` vs `.message`.

### 1.5 Data fetching anti-pattern (repeated ~15×)

Every data component reimplements:

```ts
const [loading, setLoading] = useState(true);
const [error, setError]   = useState<string|null>(null);
const [data, setData]     = useState<T[]>([]);
const fetchX = useCallback(async () => {
  setLoading(true); setError(null);
  try { const r = await getX(params); setData(r.map(mapToUI)); }
  catch (e:any) { setError(e.response?.data?.detail || e.message); }
  finally { setLoading(false); }
}, [deps]);
useEffect(() => { fetchX(); }, [fetchX]);
```

No caching, no dedup, no retry, no background refresh, no cancellation. `PatientLedger.tsx` carries **two** independent loading/error pairs.

### 1.6 State management

- `AuthContext` mixes **auth + org/office selection + active patient** and persists each to `localStorage` with per-field `useEffect`s. Should be split.
- Auth propagated by **prop drilling** (`onLogout`, `currentOffice`, `setCurrentOffice`, `user`) into every route element.
- 401 handled by interceptor → `window.dispatchEvent` → `AuthContext` listener → `alert()` → logout, plus a hard `window.location.href`. Works, but fragile and non-idiomatic.

### 1.7 Component health

Several 1,500–2,300-line components (`EditPatientModal` ~2,278, `AddEditAppointmentForm` ~2,215, `AddEditUserModal` ~1,854, `Scheduler` ~1,637, `UserSetup` ~1,476) each mixing fetching + form state + modal control + table rendering + CRUD.

---

## 2. Recommended Target Architecture

**Feature-first (modular) structure.** Group by domain, not by file-type. Shared/cross-cutting code lives in `shared/`. Generated API code is isolated and never edited by hand.

```
src/
├── app/                      # App shell: providers, router, error boundaries
│   ├── App.tsx
│   ├── providers.tsx         # QueryClientProvider, AuthProvider, Theme, Toaster
│   ├── router.tsx            # route tree, lazy() + Suspense, guards
│   └── routes/
│       ├── ProtectedRoute.tsx
│       └── PublicRoute.tsx
│
├── api/                      # ⚙️ GENERATED by Orval — do not edit
│   ├── generated/
│   │   ├── endpoints/        # one file per FastAPI tag → RQ hooks
│   │   └── model/            # TS types/enums from OpenAPI schemas
│   └── mutator/
│       └── axiosInstance.ts  # custom axios (baseURL, auth, refresh, errors)
│
├── features/                 # one folder per domain
│   ├── auth/
│   │   ├── components/       # LoginForm, ...
│   │   ├── hooks/            # useLogin, useCurrentUser
│   │   ├── stores/           # auth store (zustand)
│   │   └── routes/           # LoginPage, ForgotPasswordPage
│   ├── patients/
│   │   ├── components/       # PatientOverview, PatientHeader, ledger tables...
│   │   ├── hooks/            # wrappers around generated hooks if needed
│   │   ├── schemas/          # zod form schemas
│   │   └── routes/           # Patient, PatientLedger pages
│   ├── scheduler/
│   ├── setup/                # account/user/office/tenant setup
│   ├── charting/
│   ├── ai-chat/              # incl. websocket client
│   └── ...
│
├── shared/
│   ├── ui/                   # shadcn/Radix primitives (today's src/components/ui)
│   ├── components/           # cross-feature composites (PageHeader, DataTable...)
│   ├── hooks/                # useDebounce, usePagination, useDisclosure...
│   ├── lib/                  # cn(), formatters, date utils
│   ├── config/               # env.ts (typed), queryClient.ts, constants
│   └── types/                # truly global types only
│
└── main.tsx
```

Rules:
- **A feature may import from `shared/` and `api/`, never from another feature's internals.** Cross-feature needs get promoted to `shared/`.
- **`api/generated/` is build output.** Hand-written tweaks live in the mutator or thin feature hooks.
- **Path aliases**: add `@/*` → `src/*` (and optionally `@features`, `@shared`) so deep `../../../` disappears.

---

## 3. Orval Integration (the centerpiece)

Orval reads your FastAPI OpenAPI document and generates **typed models + TanStack Query hooks + axios calls**, wired through a custom axios instance ("mutator") that you control for auth, refresh, base URL, and error normalization.

### 3.1 Install

```bash
npm i @tanstack/react-query axios
npm i -D orval @tanstack/eslint-plugin-query
# optional: zod schemas generated alongside types
npm i zod
```

### 3.2 Custom axios mutator — `src/api/mutator/axiosInstance.ts`

This becomes the **single** HTTP entry point (replacing `services/api.ts`, the raw `fetch`, and the wrapper).

```ts
import axios, { AxiosError, AxiosRequestConfig } from "axios";
import { env } from "@/shared/config/env";

export const AXIOS_INSTANCE = axios.create({ baseURL: env.apiBaseUrl });

AXIOS_INSTANCE.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token && !config.url?.includes("/auth/login")) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 401 → try refresh once, else broadcast logout
AXIOS_INSTANCE.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/")) {
      // attempt refresh here, then retry; on failure:
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    return Promise.reject(error);
  }
);

// Orval calls this for every endpoint. Supports cancellation.
export const customInstance = <T>(config: AxiosRequestConfig): Promise<T> => {
  const source = axios.CancelToken.source();
  const promise = AXIOS_INSTANCE({ ...config, cancelToken: source.token })
    .then(({ data }) => data);
  // @ts-expect-error attach cancel for RQ
  promise.cancel = () => source.cancel("query cancelled");
  return promise;
};
```

### 3.3 `orval.config.ts` (repo root)

```ts
import { defineConfig } from "orval";

export default defineConfig({
  dentc: {
    input: {
      // DECISION: committed schema file (not a live URL).
      target: "./openapi.json",
    },
    output: {
      mode: "tags-split",            // one folder per FastAPI tag
      target: "./src/api/generated/endpoints",
      schemas: "./src/api/generated/model",
      client: "react-query",
      httpClient: "axios",
      clean: true,                   // wipe stale generated files each run
      prettier: true,
      override: {
        mutator: {
          path: "./src/api/mutator/axiosInstance.ts",
          name: "customInstance",
        },
        query: {
          useQuery: true,
          useInfinite: true,
          useInfiniteQueryParam: "offset",
          options: { staleTime: 30_000 },
        },
      },
    },
    // optional second target: generate zod schemas for runtime validation
    // hooks: { afterAllFilesWrite: "prettier --write" },
  },
});
```

### 3.4 Scripts (`package.json`)

```jsonc
{
  "scripts": {
    "api:fetch": "curl -s http://127.0.0.1:8000/openapi.json -o openapi.json",
    "api:gen": "orval --config orval.config.ts",
    "api:sync": "npm run api:fetch && npm run api:gen"
  }
}
```

### 3.5 What you get — before/after

```ts
// BEFORE — hand-written service + mapper + per-component fetch (~40 lines)
const r = await getPatientLedger(patientId, params);
setData(r.ledger_entries.map(mapLedgerEntryToTransaction));

// AFTER — generated hook, fully typed, cached, deduped, refetching
const { data, isLoading, error } = useGetPatientLedger(patientId, params);
```

Every FastAPI endpoint becomes a `useXxx()` query hook or `useXxxMutation()` — typed end-to-end. **Backend adds a field → `npm run api:sync` → TypeScript shows you exactly what to update.**

> **Prerequisite for clean output:** the FastAPI side must produce a good schema — `operation_id`s set (or use `tags` + clear function names), `response_model=` on every route, and Pydantic models with explicit field types. See §7.

---

## 4. Per-Concern Recommendations

| Concern | Recommendation |
|---|---|
| **API layer** | Orval-generated hooks over one custom axios mutator. Delete `src/services/*` and `src/mappers/*` incrementally as each feature migrates. |
| **Data fetching** | TanStack Query. Configure a shared `QueryClient` (staleTime, retry, `refetchOnWindowFocus`). Use `useInfiniteQuery` for ledger/search paging. |
| **Type safety FE↔BE** | Single source of truth = OpenAPI schema → generated TS. Optionally generate **zod** schemas (`orval` zod client) and validate responses at the boundary in dev. |
| **Client state** | Keep it small. `zustand` for auth/session/workspace (org/office/active-patient) — replaces overloaded `AuthContext` + prop drilling. Server data stays in React Query, *not* in stores. |
| **Form handling** | Standardize on `react-hook-form` (already installed) + `zod` + `@hookform/resolvers`. Co-locate schemas in `features/*/schemas/`. Build a thin `<Form/>` wrapper around your shadcn `ui/form.tsx`. |
| **Error handling** | Normalize errors in the mutator into one `ApiError` shape. Global `QueryCache.onError` → `sonner` toast. Add a route-level `ErrorBoundary`. Stop using `alert()`. |
| **Auth/z** | `zustand` auth store + `<ProtectedRoute>` wrapper reading it. Implement refresh-token rotation in the mutator (queue requests during refresh). Role/permission gating via a `useHasPermission()` selector. |
| **Env config** | One typed module `shared/config/env.ts` that reads `import.meta.env` and validates with zod at startup. Commit `.env.example`. **Make `api.ts`/mutator actually use `VITE_API_BASE_URL`.** |
| **Testing** | Vitest + React Testing Library for units/components; MSW (can be seeded from the same OpenAPI) for network mocking; Playwright for a few critical E2E flows (login, patient search, create appointment). |

### Typed env example — `src/shared/config/env.ts`
```ts
import { z } from "zod";
const schema = z.object({
  VITE_API_BASE_URL: z.string().url(),
  VITE_WS_BASE_URL: z.string().url().optional(),
  VITE_APP_ENV: z.enum(["development", "staging", "production"]).default("development"),
});
const parsed = schema.parse(import.meta.env);
export const env = {
  apiBaseUrl: parsed.VITE_API_BASE_URL,
  wsBaseUrl: parsed.VITE_WS_BASE_URL,
  appEnv: parsed.VITE_APP_ENV,
};
```

---

## 5. Refactoring Priorities (High → Low)

**P0 — Stop the bleeding (½ day, low risk)**
1. Make `api.ts` read `VITE_API_BASE_URL`; remove hardcoded URL. Commit `.env.example`.
2. Delete dead forks: `*.optimized.*`, `UserSetup_old.tsx`, empty `services/.ts`. Port good config from `.optimized` first.
3. Move the 15 root `*_API_CONTRACT.md` into `docs/api-contracts/` (they'll be superseded by OpenAPI later).
4. Add `@/*` path alias (tsconfig + vite) to stop the `../../../` sprawl.

**P1 — Foundation (2–4 days)**
5. Add TanStack Query + `QueryClientProvider` + global error→toast wiring.
6. Stand up Orval against the FastAPI schema; generate into `src/api/generated/`.
7. Build the custom axios mutator; wire auth + refresh + error normalization.

**P2 — Migrate data fetching, feature by feature (incremental, weeks)**
8. Replace `services/*` + manual fetch with generated hooks, one feature at a time (start with a read-only screen like Patient Ledger).
9. Delete each `mappers/*` + service file as its feature is migrated.

**P3 — State & forms**
10. Split `AuthContext` → `zustand` auth/workspace stores; remove auth prop drilling.
11. Standardize forms on RHF + zod; migrate the giant modals.

**P4 — Structure & quality**
12. Reorganize into feature folders; collapse the three "pages" locations.
13. Break up 1,500+ line components.
14. Introduce Vitest + RTL + MSW; add CI.

> Each Px is shippable on its own and doesn't block the next — safe for multiple developers.

---

## 6. Phased Implementation Roadmap (concrete)

### Phase 0 — Cleanup & guardrails
- [ ] `env.ts` + `.env.example`; mutator/`api.ts` use it.
- [ ] Delete forks (after porting optimized config). 
- [ ] `@/*` alias in `tsconfig.app.json`:
  ```jsonc
  { "compilerOptions": { "baseUrl": ".", "paths": { "@/*": ["src/*"] } } }
  ```
  and in `vite.config.ts`:
  ```ts
  resolve: { alias: { "@": path.resolve(__dirname, "src") } }
  ```

### Phase 1 — Query + Orval foundation
- [ ] `npm i @tanstack/react-query orval zod @hookform/resolvers`
- [ ] `providers.tsx` with `QueryClient` (defaults: `staleTime: 30s`, `retry: 1`).
- [ ] `orval.config.ts` + mutator; run `npm run api:sync`; commit generated output.
- [ ] Verify one generated hook compiles and runs against the dev backend.

### Phase 2 — Pilot migration (Patient Ledger)
- [ ] Replace `PatientLedger.tsx` fetching with `useGetPatientLedger…` infinite query.
- [ ] Delete `ledgerApi.ts` + its mapper once parity confirmed.
- [ ] Establish the pattern doc others copy.

### Phase 3 — Roll out per feature
- [ ] patients → scheduler → setup → charting → reports. Delete services/mappers as you go.

### Phase 4 — State, forms, structure, tests
- [ ] zustand auth/workspace; `<ProtectedRoute>`.
- [ ] RHF+zod for top 5 modals.
- [ ] Move files into `features/*`.
- [ ] Vitest + RTL + MSW + Playwright smoke; GitHub Actions CI (lint, typecheck, `api:gen --check`, test, build).

---

## 7. Frontend ↔ FastAPI: loose coupling, easy integration

The OpenAPI schema is the **contract boundary**. Neither side imports the other; they agree on the schema.

**FastAPI hygiene (makes generated code clean):**
- `response_model=` on every route; explicit Pydantic models (no bare `dict`).
- Stable, meaningful `operation_id`s. Either set them explicitly or standardize on `tags` + unique function names; a common trick:
  ```python
  def custom_generate_unique_id(route: APIRoute) -> str:
      return f"{route.tags[0]}-{route.name}"
  app = FastAPI(generate_unique_id_function=custom_generate_unique_id)
  ```
- Use `Enum`s for status fields (they become TS string-literal unions).
- Version the API path (`/api/v1`); breaking changes → `/api/v2`.
- **Casing — DECIDED: stay snake_case.** Orval generates snake_case types that mirror FastAPI exactly, eliminating all hand-mapping. UI components read snake_case fields directly. (If camelCase is ever wanted later, do it via a Pydantic alias generator on the backend so the *schema* is camelCase — never re-introduce client-side mapping.)

**Contract workflow — DECIDED: committed schema file.**
- Backend exports `openapi.json` into the frontend repo (commit it; treat as the contract artifact). A backend script/CI step keeps it fresh — e.g. dump `app.openapi()` to the file on release.
- Frontend regenerates from the committed file via `npm run api:gen`; TS compile surfaces every breaking change. (`api:fetch` is available for manual refresh from a running backend, but the committed file is the source of truth.)

---

## 8. Minimizing manual work when the backend changes

1. **Codegen as the default**: `npm run api:sync` regenerates types + hooks. No hand-edits to `api/generated/`.
2. **Drift detection in CI**: run `orval` then `git diff --exit-code src/api/generated` — fail the build if someone forgot to regenerate. Backend CI can publish the schema as an artifact the frontend pulls.
3. **Runtime validation (optional)**: generate zod schemas too; validate responses at the boundary in non-prod to catch contract violations early.
4. **Shared mock layer**: seed MSW handlers from the OpenAPI schema so tests and local dev use contract-accurate mocks.
5. **API versioning**: additive changes regenerate cleanly; breaking changes go to a new version path so the FE can migrate deliberately.
6. **CI pipeline (GitHub Actions)** for the frontend:
   `install → lint → typecheck → api:gen (drift check) → test → build`.

---

## Appendix A — File disposition cheat-sheet

| Action | Files |
|---|---|
| **Delete** | `App.optimized.tsx`, `vite.config.optimized.ts`, `package.json.optimized`, `UserSetup_old.tsx`, `src/services/.ts`, one of the two postcss configs |
| **Pick one, delete other** | `EditPatientModal.tsx` vs `EditPatientModalRefactored.tsx`; `Login.tsx` vs `LoginPage.tsx` |
| **Replace via Orval** | all of `src/services/*` (except websocket), `src/api/feeSchedules.ts`, all of `src/mappers/*` |
| **Move to `docs/`** | the 15 `*_API_CONTRACT.md` / `*_DEFINITION.md` root files |
| **Keep & relocate** | `src/components/ui/*` → `src/shared/ui/*`; pages → `features/*/routes/` |
