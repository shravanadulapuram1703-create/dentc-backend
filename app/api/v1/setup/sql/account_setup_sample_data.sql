-- Optional seed data for local/dev testing.
-- Update tenant_id/account_id/account_number to match your environment.

INSERT INTO public.account_setups (
    tenant_id,
    account_id,
    account_number,
    account_name,
    email,
    culture_code,
    enable_full_screen,
    max_treatment_plan_discount,
    pgid,
    oid,
    updated_by_user_id,
    updated_by_email
)
VALUES
(
    1,
    'acc-001',
    '100123',
    'Smile Bright Dental Group',
    'billing@smilebright.com',
    'en-US',
    TRUE,
    25,
    'PG-5001',
    'OFF-101',
    NULL,
    'admin@tenant.com'
)
ON CONFLICT (tenant_id) DO UPDATE
SET
    account_name = EXCLUDED.account_name,
    email = EXCLUDED.email,
    culture_code = EXCLUDED.culture_code,
    enable_full_screen = EXCLUDED.enable_full_screen,
    max_treatment_plan_discount = EXCLUDED.max_treatment_plan_discount,
    pgid = EXCLUDED.pgid,
    oid = EXCLUDED.oid,
    updated_by_user_id = EXCLUDED.updated_by_user_id,
    updated_by_email = EXCLUDED.updated_by_email;
