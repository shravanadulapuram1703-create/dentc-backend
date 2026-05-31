-- Account Setup API schema migration
-- Contract field mapping:
--   accountId                    -> public.account_setups.account_id
--   values.accountNumber         -> public.account_setups.account_number
--   values.accountName           -> public.account_setups.account_name
--   values.email                 -> public.account_setups.email
--   values.cultureCode           -> public.account_setups.culture_code
--   values.enableFullScreen      -> public.account_setups.enable_full_screen
--   values.maxTreatmentPlanDiscount -> public.account_setups.max_treatment_plan_discount
--   metadata.pgid                -> public.account_setups.pgid
--   metadata.oid                 -> public.account_setups.oid
--   metadata.updatedAt           -> public.account_setups.updated_at
--   metadata.updatedBy           -> public.account_setups.updated_by_email

BEGIN;

CREATE TABLE IF NOT EXISTS public.account_setups (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    account_id VARCHAR(50) NOT NULL UNIQUE,
    account_number VARCHAR(50) NOT NULL,
    account_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    culture_code VARCHAR(20) NOT NULL DEFAULT 'en-US',
    enable_full_screen BOOLEAN NOT NULL DEFAULT FALSE,
    max_treatment_plan_discount INTEGER NOT NULL DEFAULT 0,
    pgid VARCHAR(100) NULL,
    oid VARCHAR(100) NULL,
    updated_by_user_id INTEGER NULL REFERENCES public.users(id) ON DELETE SET NULL,
    updated_by_email VARCHAR(255) NULL,
    lock_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_account_setups_tenant_id UNIQUE (tenant_id),
    CONSTRAINT ck_account_setups_discount_range CHECK (
        max_treatment_plan_discount >= 0 AND max_treatment_plan_discount <= 100
    )
);

-- Helpful indexes for common access patterns.
CREATE INDEX IF NOT EXISTS idx_account_setups_tenant_id ON public.account_setups(tenant_id);
CREATE INDEX IF NOT EXISTS idx_account_setups_account_id ON public.account_setups(account_id);

-- Ensure updated_at auto-touch on updates.
CREATE OR REPLACE FUNCTION public.touch_account_setups_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_account_setups_updated_at ON public.account_setups;
CREATE TRIGGER trg_touch_account_setups_updated_at
BEFORE UPDATE ON public.account_setups
FOR EACH ROW
EXECUTE FUNCTION public.touch_account_setups_updated_at();

COMMIT;
