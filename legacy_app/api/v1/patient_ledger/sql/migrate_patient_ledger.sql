-- ==================================================
-- Patient Ledger Module - Schema Migration (tenant_1)
-- Idempotent / safe to run multiple times
-- ==================================================

-- ==================================================
-- 1. Core ledger entries table (contract-driven)
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_ledger_entries (
    id VARCHAR(50) PRIMARY KEY,                       -- e.g., "LED-<uuid>"
    transaction_id VARCHAR(50) NOT NULL,              -- groups related records (procedure+ledger, payment+ledger, etc.)
    posted_date DATE NOT NULL,

    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    patient_name VARCHAR(255) NOT NULL,

    office_id INTEGER NOT NULL REFERENCES public.offices(id) ON DELETE RESTRICT,
    office_name VARCHAR(255) NOT NULL,

    apply_to VARCHAR(1) NOT NULL DEFAULT 'P',         -- 'P' patient, 'R' responsible party
    code VARCHAR(20) NOT NULL,                        -- CDT / PMT / ADJ / CLM-P etc.
    tooth VARCHAR(10),
    surface VARCHAR(20),

    -- "P" (Production) or "C" (Collection)
    type VARCHAR(1) NOT NULL DEFAULT 'P',

    has_notes BOOLEAN NOT NULL DEFAULT FALSE,
    has_eob BOOLEAN NOT NULL DEFAULT FALSE,
    has_attachments BOOLEAN NOT NULL DEFAULT FALSE,

    description TEXT NOT NULL,
    billing_order VARCHAR(10),
    duration_minutes INTEGER,

    provider_id VARCHAR(50),
    provider_name VARCHAR(255),

    est_patient NUMERIC(12, 2) NOT NULL DEFAULT 0,
    est_insurance NUMERIC(12, 2) NOT NULL DEFAULT 0,

    posted_amount NUMERIC(12, 2) NOT NULL,            -- +charges, -payments/-adjustments
    running_balance NUMERIC(12, 2) NOT NULL,          -- running balance at time of posting

    created_by VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    transaction_type VARCHAR(30) NOT NULL,            -- procedure, patient_payment, insurance_payment, adjustment, claim_event
    status VARCHAR(30) NOT NULL DEFAULT '',           -- not_sent, sent, paid, partial, denied, posted, ""

    procedure_id VARCHAR(50),
    claim_id VARCHAR(50),
    payment_id VARCHAR(50),
    adjustment_id VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_patient_ledger_entries_patient_date
ON tenant_1.patient_ledger_entries(patient_id, posted_date DESC);

CREATE INDEX IF NOT EXISTS idx_patient_ledger_entries_transaction_type
ON tenant_1.patient_ledger_entries(patient_id, transaction_type);

CREATE INDEX IF NOT EXISTS idx_patient_ledger_entries_status
ON tenant_1.patient_ledger_entries(patient_id, status);

-- ==================================================
-- 2. Procedures (ledger procedures, not scheduler procedure types)
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_procedures (
    id VARCHAR(50) PRIMARY KEY,                       -- "PRC-<uuid>"
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,

    procedure_code VARCHAR(20) NOT NULL REFERENCES tenant_1.procedure_codes(code) ON DELETE RESTRICT,
    date_of_service DATE NOT NULL,

    provider_id VARCHAR(50) NOT NULL,                 -- scheduler_providers.id (string)
    provider_name VARCHAR(255) NOT NULL,

    office_id INTEGER NOT NULL REFERENCES public.offices(id) ON DELETE RESTRICT,
    office_name VARCHAR(255) NOT NULL,

    tooth VARCHAR(10),
    surface VARCHAR(20),
    quadrant VARCHAR(10),
    materials JSONB,
    duration_minutes INTEGER,

    fee NUMERIC(12, 2) NOT NULL CHECK (fee > 0),
    est_patient NUMERIC(12, 2) NOT NULL DEFAULT 0,
    est_insurance NUMERIC(12, 2) NOT NULL DEFAULT 0,

    billing_order VARCHAR(10),
    notes TEXT,
    apply_to VARCHAR(1) NOT NULL DEFAULT 'P',

    status VARCHAR(30) NOT NULL DEFAULT 'not_sent',   -- not_sent, sent, paid, partial, denied
    claim_id VARCHAR(50),
    ledger_entry_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_ledger_entries(id) ON DELETE RESTRICT,

    created_by VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100) NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_patient_procedures_patient_dos
ON tenant_1.patient_procedures(patient_id, date_of_service DESC);

CREATE INDEX IF NOT EXISTS idx_patient_procedures_claim
ON tenant_1.patient_procedures(claim_id);

-- ==================================================
-- 3. Claims + claim procedures
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_claims (
    id VARCHAR(50) PRIMARY KEY,                       -- "CLM-<uuid>"
    claim_number VARCHAR(50) NOT NULL UNIQUE,          -- auto-generated
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,

    status VARCHAR(30) NOT NULL DEFAULT 'created',     -- created, sent, paid, partial, denied, closed
    claim_type VARCHAR(20) NOT NULL,                   -- dental, medical
    billing_order VARCHAR(20) NOT NULL,                -- primary, secondary, etc.

    date_of_service_from DATE NOT NULL,
    date_of_service_to DATE NOT NULL,

    total_submitted_fees NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_fee NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_est_insurance NUMERIC(12, 2) NOT NULL DEFAULT 0,

    notes TEXT,

    created_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_time TIME NOT NULL DEFAULT CURRENT_TIME,
    created_by VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    last_status_update_date DATE,
    claim_sent_date DATE,
    claim_sent_status VARCHAR(50),
    claim_close_date DATE,
    claim_closed_by VARCHAR(100),
    dxc_attachment_id VARCHAR(100),
    icd10_codes TEXT,

    send_method VARCHAR(20),
    batch_id VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_patient_claims_patient
ON tenant_1.patient_claims(patient_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_patient_claims_status
ON tenant_1.patient_claims(patient_id, status);

CREATE TABLE IF NOT EXISTS tenant_1.patient_claim_procedures (
    id VARCHAR(50) PRIMARY KEY,                       -- "CPR-<uuid>"
    claim_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_claims(id) ON DELETE CASCADE,
    procedure_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_procedures(id) ON DELETE RESTRICT,
    UNIQUE (claim_id, procedure_id)
);

CREATE INDEX IF NOT EXISTS idx_patient_claim_procedures_claim
ON tenant_1.patient_claim_procedures(claim_id);

-- ==================================================
-- 4. Claim events (also posted to ledger as claim_event)
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_claim_events (
    id VARCHAR(50) PRIMARY KEY,                       -- "CEV-<uuid>"
    claim_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_claims(id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL,                  -- created, sent, paid, partial, denied, closed, note_update, etc.
    event_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_by VARCHAR(100) NOT NULL DEFAULT 'system',
    details JSONB
);

CREATE INDEX IF NOT EXISTS idx_patient_claim_events_claim
ON tenant_1.patient_claim_events(claim_id, event_date DESC);

-- ==================================================
-- 5. Claim attachments (placeholder for required attachments workflow)
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_claim_attachments (
    id VARCHAR(50) PRIMARY KEY,                       -- "ATT-<uuid>"
    claim_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_claims(id) ON DELETE CASCADE,
    attachment_type VARCHAR(50) NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    provided BOOLEAN NOT NULL DEFAULT FALSE,
    file_name VARCHAR(255),
    uploaded_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_claim_attachments_claim
ON tenant_1.patient_claim_attachments(claim_id);

-- ==================================================
-- 6. Payments + applications
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_payments (
    id VARCHAR(50) PRIMARY KEY,                       -- "PMT-<uuid>"
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    payment_date DATE NOT NULL,
    payment_amount NUMERIC(12, 2) NOT NULL CHECK (payment_amount > 0),
    payment_type VARCHAR(20) NOT NULL,                -- patient, insurance
    payment_method VARCHAR(50) NOT NULL,              -- e.g., "H0007"
    apply_to VARCHAR(1) NOT NULL,                     -- P or R
    provider_id VARCHAR(50),
    provider_name VARCHAR(255),
    check_number VARCHAR(100),
    bank_number VARCHAR(100),
    notes TEXT,
    ledger_entry_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_ledger_entries(id) ON DELETE RESTRICT,
    created_by VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_payments_patient_date
ON tenant_1.patient_payments(patient_id, payment_date DESC);

CREATE TABLE IF NOT EXISTS tenant_1.patient_payment_applications (
    id VARCHAR(50) PRIMARY KEY,                       -- "PMA-<uuid>"
    payment_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_payments(id) ON DELETE CASCADE,
    procedure_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_procedures(id) ON DELETE RESTRICT,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    UNIQUE (payment_id, procedure_id)
);

-- ==================================================
-- 7. Adjustments + applications
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_adjustments (
    id VARCHAR(50) PRIMARY KEY,                       -- "ADJ-<uuid>"
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    adjustment_date DATE NOT NULL,
    adjustment_amount NUMERIC(12, 2) NOT NULL CHECK (adjustment_amount < 0), -- negative
    adjustment_code VARCHAR(50) NOT NULL,
    adjustment_reason TEXT NOT NULL,
    apply_to VARCHAR(1) NOT NULL,
    notes TEXT,
    ledger_entry_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_ledger_entries(id) ON DELETE RESTRICT,
    created_by VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_adjustments_patient_date
ON tenant_1.patient_adjustments(patient_id, adjustment_date DESC);

CREATE TABLE IF NOT EXISTS tenant_1.patient_adjustment_applications (
    id VARCHAR(50) PRIMARY KEY,                       -- "ADA-<uuid>"
    adjustment_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_adjustments(id) ON DELETE CASCADE,
    procedure_id VARCHAR(50) NOT NULL REFERENCES tenant_1.patient_procedures(id) ON DELETE RESTRICT,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    UNIQUE (adjustment_id, procedure_id)
);

-- ==================================================
-- 8. Metadata reference tables (tenant_1)
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.payment_codes (
    code VARCHAR(50) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS tenant_1.adjustment_codes (
    code VARCHAR(50) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS tenant_1.claim_statuses (
    code VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS tenant_1.transaction_types (
    code VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    description TEXT
);

-- Seed minimal reference values required by contract (idempotent)
INSERT INTO tenant_1.claim_statuses (code, display_name, description) VALUES
('created', 'Claim Created, Not Sent', NULL),
('sent', 'Claim Sent', NULL),
('paid', 'Claim Paid', NULL),
('partial', 'Claim Partially Paid', NULL),
('denied', 'Claim Denied', NULL),
('closed', 'Claim Closed', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO tenant_1.transaction_types (code, display_name, description) VALUES
('procedure', 'Procedure', NULL),
('patient_payment', 'Patient Payment', NULL),
('insurance_payment', 'Insurance Payment', NULL),
('adjustment', 'Adjustment', NULL),
('claim_event', 'Claim Event', NULL)
ON CONFLICT (code) DO NOTHING;

