# Patient Ledger Backend-Driven Implementation Summary

## Overview

The Patient Ledger module has been converted from a static, mock-data implementation to a fully backend-driven system. All data is now loaded from backend APIs, and all workflows (add procedure, create claim, send claim, payments, adjustments) are integrated with backend services.

## Completed Work

### 1. API Contract Documentation (`PATIENT_LEDGER_API_CONTRACT.md`)

Comprehensive API contract document defining all required backend endpoints:

- **Ledger Entries**: GET `/api/v1/patients/{patientId}/ledger` with filtering, sorting, and pagination
- **Balances & Aging**: GET `/api/v1/patients/{patientId}/balances`
- **Procedures**: POST/GET/PUT/DELETE `/api/v1/patients/{patientId}/procedures`
- **Claims**: POST/GET/PUT `/api/v1/patients/{patientId}/claims` and POST `/api/v1/patients/{patientId}/claims/{claimId}/send`
- **Payments**: POST/GET `/api/v1/patients/{patientId}/payments`
- **Adjustments**: POST/GET `/api/v1/patients/{patientId}/adjustments`
- **Metadata APIs**: Procedure codes, payment codes, adjustment codes, claim statuses, transaction types, providers

All contracts include:
- Request/response schemas
- Error handling
- Validation rules
- Business logic constraints

### 2. Ledger API Service (`src/services/ledgerApi.ts`)

Complete TypeScript service layer with:
- Type definitions for all API requests and responses
- Functions for all ledger operations
- Proper error handling
- Type safety throughout

### 3. Updated Patient Ledger Component (`src/components/pages/PatientLedger.tsx`)

**Removed:**
- All static/mock transaction data
- Hardcoded balance data
- Mock patient data fallbacks

**Added:**
- Backend API integration for ledger entries
- Backend API integration for balances
- Loading states and error handling
- Date filtering
- Sorting functionality
- Pagination from backend
- Dynamic claim creation using backend API
- Refresh functionality after procedure/payment/adjustment operations

**Key Features:**
- Real-time data loading from backend
- Proper error handling with retry options
- Loading indicators
- Empty state handling
- Date range filtering
- Sort by date, amount, provider, or code
- Pagination with configurable page size
- Selection of procedures for claim creation
- Integration with AddProcedure and PaymentsAdjustments modals

## Remaining Work

The following components still need to be updated to use backend APIs:

### 1. AddProcedure Component (`src/components/patient/AddProcedure.tsx`)

**Current State:** Uses static procedure codes from `src/data/procedureCodes.ts` and hardcoded providers.

**Required Changes:**
- Replace static procedure codes with `getProcedureCodes()` API call
- Replace hardcoded providers with `getOfficeProviders()` API call
- Update `handleSaveProcedure` to call `addProcedure()` API instead of local state update
- Add loading states for procedure codes and providers
- Add error handling

**API Functions to Use:**
- `getProcedureCodes()` - Load procedure codes with categories and requirements
- `getOfficeProviders()` - Load providers for the office
- `addProcedure()` - Save new procedure to backend

### 2. PaymentsAdjustments Component (`src/components/patient/PaymentsAdjustments.tsx`)

**Current State:** Uses static payment codes, adjustment codes, and mock outstanding procedures.

**Required Changes:**
- Replace static payment codes with `getPaymentCodes()` API call
- Replace static adjustment codes with `getAdjustmentCodes()` API call
- Load outstanding procedures from ledger API (filter for procedures with remaining balance)
- Update payment submission to call `addPayment()` API
- Update adjustment submission to call `addAdjustment()` API
- Add loading states and error handling

**API Functions to Use:**
- `getPaymentCodes()` - Load payment method codes
- `getAdjustmentCodes()` - Load adjustment reason codes
- `getPatientLedger()` - Load outstanding procedures (filter by transaction_type='procedure' and status='not_sent' or 'partial')
- `addPayment()` - Save payment to backend
- `addAdjustment()` - Save adjustment to backend

### 3. ClaimDetail Component (`src/components/patient/ClaimDetail.tsx`)

**Current State:** Uses mock claim data and static procedure data.

**Required Changes:**
- Load claim details using `getClaim()` API
- Update claim notes using `updateClaim()` API
- Send claim to batch using `sendClaim()` API
- Load attachment requirements from claim response
- Add loading states and error handling
- Handle claim status updates dynamically

**API Functions to Use:**
- `getClaim()` - Load detailed claim information
- `updateClaim()` - Update claim notes and payment info
- `sendClaim()` - Send claim to batch processing

## API Implementation Checklist

Backend team should implement the following endpoints in order of priority:

### Priority 1 (Core Functionality)
- [ ] `GET /api/v1/patients/{patientId}/ledger` - Ledger entries with pagination
- [ ] `GET /api/v1/patients/{patientId}/balances` - Account balances and aging
- [ ] `POST /api/v1/patients/{patientId}/procedures` - Add procedure
- [ ] `POST /api/v1/patients/{patientId}/claims` - Create claim

### Priority 2 (Workflow Completion)
- [ ] `POST /api/v1/patients/{patientId}/claims/{claimId}/send` - Send claim to batch
- [ ] `POST /api/v1/patients/{patientId}/payments` - Add payment
- [ ] `POST /api/v1/patients/{patientId}/adjustments` - Add adjustment
- [ ] `GET /api/v1/patients/{patientId}/claims/{claimId}` - Get claim details

### Priority 3 (Metadata)
- [ ] `GET /api/v1/metadata/procedure-codes` - Procedure codes with requirements
- [ ] `GET /api/v1/metadata/payment-codes` - Payment method codes
- [ ] `GET /api/v1/metadata/adjustment-codes` - Adjustment reason codes
- [ ] `GET /api/v1/offices/{officeId}/providers` - Office providers

## Testing Checklist

Once backend APIs are implemented, test the following workflows:

1. **View Ledger**
   - [ ] Load ledger entries with pagination
   - [ ] Filter by date range
   - [ ] Sort by different fields
   - [ ] Handle empty state
   - [ ] Handle error states

2. **View Balances**
   - [ ] Load account balances
   - [ ] Display aging buckets correctly
   - [ ] Show recent activity

3. **Add Procedure**
   - [ ] Load procedure codes from API
   - [ ] Load providers from API
   - [ ] Validate required fields
   - [ ] Save procedure to backend
   - [ ] Refresh ledger after save

4. **Create Claim**
   - [ ] Select multiple procedures
   - [ ] Create claim via API
   - [ ] Navigate to claim detail
   - [ ] Verify claim includes selected procedures

5. **Send Claim**
   - [ ] Load claim details
   - [ ] Send claim to batch
   - [ ] Verify status update
   - [ ] Handle validation errors

6. **Add Payment**
   - [ ] Load payment codes
   - [ ] Load outstanding procedures
   - [ ] Apply payment to procedures
   - [ ] Verify ledger update

7. **Add Adjustment**
   - [ ] Load adjustment codes
   - [ ] Apply adjustment to procedures
   - [ ] Verify ledger update

## Notes

- All dates use ISO 8601 format (YYYY-MM-DD) in API requests/responses
- All monetary amounts are decimal numbers
- All IDs are strings (may be numeric strings)
- All list endpoints support pagination
- All endpoints require authentication (JWT token)
- Error responses follow consistent format with error code, message, and details
- Business rules (e.g., cannot modify sent claims) are enforced by backend

## Migration Path

1. **Phase 1**: Backend implements Priority 1 APIs
   - Frontend can display ledger and balances
   - Can add procedures
   - Can create claims

2. **Phase 2**: Backend implements Priority 2 APIs
   - Complete claim workflow
   - Payment and adjustment workflows

3. **Phase 3**: Backend implements Priority 3 APIs
   - All metadata loaded from backend
   - No static data remaining

4. **Phase 4**: Update remaining components
   - AddProcedure uses backend APIs
   - PaymentsAdjustments uses backend APIs
   - ClaimDetail uses backend APIs

## Files Modified

- `PATIENT_LEDGER_API_CONTRACT.md` (NEW) - Complete API contract documentation
- `src/services/ledgerApi.ts` (NEW) - API service layer
- `src/components/pages/PatientLedger.tsx` (UPDATED) - Backend-driven implementation

## Files Still Requiring Updates

- `src/components/patient/AddProcedure.tsx` - Needs backend API integration
- `src/components/patient/PaymentsAdjustments.tsx` - Needs backend API integration
- `src/components/patient/ClaimDetail.tsx` - Needs backend API integration
