-- ============================================================
-- Account Setup - Enterprise UI Driven Schema
-- Required tables: accounts, account_addresses, account_settings,
--                  holidays, communications, consent_forms
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.accounts (
    id BIGSERIAL PRIMARY KEY,
    account_id VARCHAR(50) NOT NULL UNIQUE,
    tenant_id INTEGER NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    account_number VARCHAR(50) NOT NULL,
    account_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(30) NULL,
    culture_code VARCHAR(20) NOT NULL DEFAULT 'en-US',
    logo_url TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by_user_id INTEGER NULL REFERENCES public.users(id) ON DELETE SET NULL,
    updated_by_email VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_accounts_tenant UNIQUE (tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_accounts_tenant_id ON public.accounts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_accounts_account_id ON public.accounts(account_id);

CREATE TABLE IF NOT EXISTS public.account_addresses (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    address_type VARCHAR(20) NOT NULL, -- corporate | statement
    line1 VARCHAR(255) NOT NULL,
    line2 VARCHAR(255) NULL,
    city VARCHAR(100) NULL,
    state VARCHAR(20) NULL,
    zip VARCHAR(20) NULL,
    country VARCHAR(50) NULL DEFAULT 'US',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_account_addresses_type CHECK (address_type IN ('corporate', 'statement'))
);

CREATE INDEX IF NOT EXISTS idx_account_addresses_account_id ON public.account_addresses(account_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_addresses_unique_type ON public.account_addresses(account_id, address_type);

CREATE TABLE IF NOT EXISTS public.account_settings (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    max_treatment_plan_discount INTEGER NOT NULL DEFAULT 0,
    enable_full_screen BOOLEAN NOT NULL DEFAULT FALSE,
    lock_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_account_settings_discount CHECK (max_treatment_plan_discount >= 0 AND max_treatment_plan_discount <= 100),
    CONSTRAINT uq_account_settings_account_id UNIQUE (account_id)
);

CREATE TABLE IF NOT EXISTS public.holidays (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    holiday_date DATE NOT NULL,
    holiday_name VARCHAR(150) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Active', -- Active | Inactive
    holiday_type VARCHAR(30) NOT NULL DEFAULT 'Custom', -- Federal | Custom
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_holidays_type CHECK (holiday_type IN ('Federal', 'Custom'))
);

CREATE INDEX IF NOT EXISTS idx_holidays_account_date ON public.holidays(account_id, holiday_date);

CREATE TABLE IF NOT EXISTS public.communications (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    country VARCHAR(50) NULL,
    entity_type VARCHAR(50) NULL,
    business_description TEXT NULL,
    business_phone VARCHAR(30) NULL,
    support_email VARCHAR(255) NULL,
    office_assignments JSONB NOT NULL DEFAULT '[]'::jsonb,
    business_type VARCHAR(50) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_communications_account_id UNIQUE (account_id)
);

CREATE TABLE IF NOT EXISTS public.consent_forms (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    consent_header VARCHAR(255) NULL,
    consent_body TEXT NULL,
    compliance_notes TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_consent_forms_account_id UNIQUE (account_id)
);

COMMIT;

-- ============================================================
-- SAMPLE DATA
-- ============================================================

INSERT INTO public.accounts (
    account_id, tenant_id, account_number, account_name, email, phone, culture_code, logo_url, updated_by_email
)
VALUES (
    'acc-001', 1, '100123', 'Smile Bright Dental Group', 'billing@smilebright.com', '(412) 555-1000', 'en-US', NULL, 'admin@tenant.com'
)
ON CONFLICT (account_id) DO UPDATE
SET account_name = EXCLUDED.account_name,
    email = EXCLUDED.email,
    phone = EXCLUDED.phone,
    culture_code = EXCLUDED.culture_code,
    updated_by_email = EXCLUDED.updated_by_email,
    updated_at = NOW();

INSERT INTO public.account_addresses (account_id, address_type, line1, city, state, zip)
SELECT a.id, 'corporate', '123 Main St', 'Cranberry', 'PA', '16066'
FROM public.accounts a
WHERE a.account_id = 'acc-001'
ON CONFLICT (account_id, address_type) DO NOTHING;

INSERT INTO public.account_addresses (account_id, address_type, line1, city, state, zip)
SELECT a.id, 'statement', 'PO Box 222', 'Cranberry', 'PA', '16066'
FROM public.accounts a
WHERE a.account_id = 'acc-001'
ON CONFLICT (account_id, address_type) DO NOTHING;

INSERT INTO public.account_settings (account_id, max_treatment_plan_discount, enable_full_screen, settings_json)
SELECT
    a.id,
    25,
    TRUE,
    '{"ledgerColors":{"current":"green","overdue30":"yellow"},"paymentPortal":{"provider":"stripe","enableGuestCheckout":true}}'::jsonb
FROM public.accounts a
WHERE a.account_id = 'acc-001'
ON CONFLICT (account_id) DO UPDATE
SET max_treatment_plan_discount = EXCLUDED.max_treatment_plan_discount,
    enable_full_screen = EXCLUDED.enable_full_screen,
    settings_json = EXCLUDED.settings_json,
    updated_at = NOW();

INSERT INTO public.holidays (account_id, holiday_date, holiday_name, status, holiday_type)
SELECT a.id, DATE '2026-12-25', 'Christmas Day', 'Active', 'Federal'
FROM public.accounts a
WHERE a.account_id = 'acc-001';

INSERT INTO public.communications (
    account_id, country, entity_type, business_description, business_phone, support_email, office_assignments, business_type
)
SELECT
    a.id, 'US', 'llc', 'Primary communications profile', '(412) 555-2000', 'support@smilebright.com', '[101,102]'::jsonb, 'general'
FROM public.accounts a
WHERE a.account_id = 'acc-001'
ON CONFLICT (account_id) DO NOTHING;

INSERT INTO public.consent_forms (account_id, consent_header, consent_body, compliance_notes)
SELECT
    a.id,
    'Patient Consent Form',
    'I acknowledge receipt of HIPAA notice and consent to treatment.',
    'This block is controlled by compliance and is read-only to non-admin users.'
FROM public.accounts a
WHERE a.account_id = 'acc-001'
ON CONFLICT (account_id) DO NOTHING;

-- ============================================================
-- SAMPLE UPDATE QUERIES FOR SAVING FORM DATA
-- ============================================================

-- Update account basics
UPDATE public.accounts
SET
    account_name = 'New Name',
    email = 'new@email.com',
    phone = '(412) 555-9090',
    culture_code = 'en-US',
    updated_by_email = 'admin@tenant.com',
    updated_at = NOW()
WHERE account_id = 'acc-001';

-- Update account settings
UPDATE public.account_settings s
SET
    enable_full_screen = FALSE,
    max_treatment_plan_discount = 20,
    settings_json = jsonb_set(
        jsonb_set(settings_json, '{paymentPortal,provider}', '"square"'::jsonb, true),
        '{apiCredentials,clientId}', '"client-123"'::jsonb,
        true
    ),
    lock_version = lock_version + 1,
    updated_at = NOW()
FROM public.accounts a
WHERE s.account_id = a.id
  AND a.account_id = 'acc-001';
