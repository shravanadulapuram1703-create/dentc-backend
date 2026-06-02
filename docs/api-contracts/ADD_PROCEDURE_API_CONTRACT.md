# Add Procedure API Contracts

This document outlines the API contracts used by the AddProcedure component for dynamic, backend-driven procedure entry.

## Existing APIs Used

All APIs are already implemented in `src/services/ledgerApi.ts` and `src/services/schedulerApi.ts`. No new APIs are required.

### 1. Get Procedure Codes

**Endpoint:** `GET /api/v1/metadata/procedure-codes`

**Query Parameters:**
- `category` (optional, string): Filter by procedure category
- `search` (optional, string): Search term for code, user_code, or description
- `limit` (optional, number): Limit number of results

**Response:**
```typescript
{
  procedure_codes: ProcedureCode[];
  categories: string[];
}

interface ProcedureCode {
  code: string;
  user_code: string | null;
  description: string;
  category: string;
  requirements: {
    tooth: boolean;
    surface: boolean;
    quadrant: boolean;
    materials: boolean;
  };
  is_active: boolean;
}
```

**Usage:** Loads all active procedure codes, optionally filtered by category or search term.

---

### 2. Get Procedure Categories

**Endpoint:** `GET /api/v1/procedures/categories`

**Response:**
```typescript
{
  categories: ProcedureCategory[];
}

interface ProcedureCategory {
  id: string;
  name: string;
  displayName: string;
}
```

**Usage:** Loads all available procedure categories for the category filter sidebar.

---

### 3. Get Office Providers

**Endpoint:** `GET /api/v1/offices/{officeId}/providers`

**Path Parameters:**
- `officeId` (required, string): Office ID (extracted from office string like "Office Name [123]")

**Response:**
```typescript
{
  providers: Provider[];
}

interface Provider {
  provider_id: string;
  provider_name: string;
  npi: string | null;
  is_active: boolean;
}
```

**Usage:** Loads all active providers for the selected office to populate the provider dropdown.

---

### 4. Add Procedure to Patient Ledger

**Endpoint:** `POST /api/v1/patients/{patientId}/procedures`

**Path Parameters:**
- `patientId` (required, string): Patient numeric ID

**Request Body:**
```typescript
{
  procedure_code: string;              // Required: Procedure code (e.g., "D0140")
  date_of_service: string;              // Required: YYYY-MM-DD format
  provider_id: string;                  // Required: Provider ID
  office_id: string;                    // Required: Office ID
  tooth?: string | null;                // Optional: Tooth number if required
  surface?: string | null;              // Optional: Surface codes if required
  quadrant?: string | null;             // Optional: Quadrant if required
  materials?: string[] | null;          // Optional: Materials array if required
  duration_minutes?: number;            // Optional: Procedure duration
  fee: number;                          // Required: Procedure fee
  est_patient: number;                  // Required: Estimated patient portion
  est_insurance: number;                 // Required: Estimated insurance portion
  billing_order?: string;               // Optional: Billing order (default: "P")
  notes?: string | null;                // Optional: Procedure notes
  apply_to?: string;                    // Optional: "P" (Patient) or "R" (Responsible Party)
}
```

**Response:**
```typescript
{
  procedure_id: string;
  ledger_entry_id: string;
  transaction_id: string;
  posted_date: string;                  // YYYY-MM-DD
  running_balance: number;
  status: string;
  created_at: string;                   // ISO 8601 timestamp
}
```

**Usage:** Creates a new procedure entry in the patient ledger. The procedure will immediately appear in the ledger after successful creation.

---

## Data Flow

1. **Component Opens:**
   - Loads categories from `GET /api/v1/procedures/categories`
   - Loads providers from `GET /api/v1/offices/{officeId}/providers`
   - Sets default category (first category or "ALL MEDICAL")

2. **Category Selection:**
   - Loads procedure codes from `GET /api/v1/metadata/procedure-codes?category={selectedCategory}`
   - Filters by search terms (code, user_code, description) on client side

3. **Procedure Selection:**
   - Checks `requirements` object to determine if tooth/surface/quadrant/materials are required
   - Opens `ToothSurfaceEnforcement` modal if any requirements are true

4. **Save Procedure:**
   - Validates required fields (procedure code, provider, and any procedure-specific requirements)
   - Formats date to YYYY-MM-DD
   - Calls `POST /api/v1/patients/{patientId}/procedures`
   - On success, triggers `onSave` callback which refreshes the patient ledger
   - Closes modal and resets form

---

## Office ID Extraction

The office string format is: `"Office Name [123]"`

The component extracts the office ID using regex: `/\[(\d+)\]/`

Example:
- Input: `"Cranberry Dental Arts [108]"`
- Extracted ID: `"108"`

---

## Error Handling

All API calls include:
- Loading states (spinners, disabled buttons)
- Error messages displayed in UI
- Console error logging for debugging
- User-friendly error alerts

---

## Integration with Patient Ledger

After a procedure is successfully saved:
1. The `onSave` callback in `PatientLedger.tsx` is triggered
2. `fetchLedgerEntries()` is called to refresh the ledger
3. If the balances tab is active, `fetchBalances()` is also called
4. The new procedure appears in the ledger immediately

---

## Notes

- All procedure codes are filtered to show only `is_active: true`
- All providers are filtered to show only `is_active: true`
- The fee field is editable (user can override default fee)
- Date format conversion handles both MM/DD/YYYY (UI) and YYYY-MM-DD (API)
- Procedure requirements (tooth, surface, quadrant, materials) are enforced based on the procedure code's `requirements` object
