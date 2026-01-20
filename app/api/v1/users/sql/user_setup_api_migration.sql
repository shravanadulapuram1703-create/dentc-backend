-- ==================================================
-- User Setup API Migration Script
-- ==================================================
-- This script ensures all required columns exist for the User Setup APIs
-- No new tables are required, but we verify existing columns are present
-- ==================================================

-- Verify tenants table has required columns
DO $$
BEGIN
    -- Check if code column exists, if not add it
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'tenants' 
        AND column_name = 'code'
    ) THEN
        ALTER TABLE public.tenants ADD COLUMN code VARCHAR(80);
        CREATE UNIQUE INDEX IF NOT EXISTS tenants_code_key ON public.tenants(code);
    END IF;
END $$;

-- Verify offices table has required columns
DO $$
BEGIN
    -- Check if office_code column exists, if not add it
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'offices' 
        AND column_name = 'office_code'
    ) THEN
        ALTER TABLE public.offices ADD COLUMN office_code VARCHAR(255);
        -- Generate office_code if it doesn't exist
        UPDATE public.offices 
        SET office_code = 'O-' || id::text 
        WHERE office_code IS NULL;
        ALTER TABLE public.offices ALTER COLUMN office_code SET NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS offices_office_code_key ON public.offices(office_code);
    END IF;
    
    -- Check if timezone column exists, if not add it
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'offices' 
        AND column_name = 'timezone'
    ) THEN
        ALTER TABLE public.offices ADD COLUMN timezone VARCHAR(100) DEFAULT 'America/Los_Angeles';
    END IF;
END $$;

-- Verify users table has updated_by column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'updated_by'
    ) THEN
        ALTER TABLE public.users ADD COLUMN updated_by VARCHAR(255);
    END IF;
END $$;

-- Add comments for documentation
COMMENT ON COLUMN public.tenants.code IS 'Canonical tenant identifier (e.g., PG-001)';
COMMENT ON COLUMN public.offices.office_code IS 'Office code identifier (e.g., O-5)';
COMMENT ON COLUMN public.offices.timezone IS 'Timezone for the office (e.g., America/Los_Angeles)';
COMMENT ON COLUMN public.users.updated_by IS 'Username of user who last updated this record';

-- ==================================================
-- Summary
-- ==================================================
-- This migration ensures:
-- 1. tenants.code column exists (for TenantListResponse)
-- 2. offices.office_code column exists (for OfficeListResponse)
-- 3. offices.timezone column exists (for OfficeListResponse)
-- 4. users.updated_by column exists (for UserWithHomeOfficeResponse)
--
-- All other required columns should already exist from previous migrations.
-- ==================================================
