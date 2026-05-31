-- ==================================================
-- SQL Migration Script for Add/Edit User API Contract Update
-- ==================================================
-- This script ensures all required columns exist for the updated API contract
-- Fields: patient_access_level, allowed_days, allowed_from, allowed_until
-- These fields already exist in the users table based on the model, but this script
-- ensures they are properly configured.

-- Check and add patient_access_level column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'patient_access_level'
    ) THEN
        ALTER TABLE public.users 
        ADD COLUMN patient_access_level VARCHAR(50);
        
        COMMENT ON COLUMN public.users.patient_access_level IS 
        'Patient access level: "all_offices" (search all offices) or "home_office" (search assigned offices only)';
    END IF;
END $$;

-- Check and add allowed_days column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'allowed_days'
    ) THEN
        ALTER TABLE public.users 
        ADD COLUMN allowed_days VARCHAR(3)[];
        
        COMMENT ON COLUMN public.users.allowed_days IS 
        'Array of allowed login days: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]. NULL means 24/7 access.';
    END IF;
END $$;

-- Check and add allowed_from column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'allowed_from'
    ) THEN
        ALTER TABLE public.users 
        ADD COLUMN allowed_from TIME;
        
        COMMENT ON COLUMN public.users.allowed_from IS 
        'Allowed login time from (HH:MM format). NULL means 24/7 access or no restriction.';
    END IF;
END $$;

-- Check and add allowed_until column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'allowed_until'
    ) THEN
        ALTER TABLE public.users 
        ADD COLUMN allowed_until TIME;
        
        COMMENT ON COLUMN public.users.allowed_until IS 
        'Allowed login time until (HH:MM format). NULL means 24/7 access or no restriction.';
    END IF;
END $$;

-- Ensure hipaa_compliant_scheduler and is_ortho_assistant exist in user_preferences
DO $$
BEGIN
    -- Check and add hipaa_compliant_scheduler if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_preferences' 
        AND column_name = 'hipaa_compliant_scheduler'
    ) THEN
        ALTER TABLE public.user_preferences 
        ADD COLUMN hipaa_compliant_scheduler BOOLEAN DEFAULT FALSE;
        
        COMMENT ON COLUMN public.user_preferences.hipaa_compliant_scheduler IS 
        'Enable HIPAA compliant scheduler view (hides patient names)';
    END IF;
    
    -- Check and add is_ortho_assistant if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_preferences' 
        AND column_name = 'is_ortho_assistant'
    ) THEN
        ALTER TABLE public.user_preferences 
        ADD COLUMN is_ortho_assistant BOOLEAN DEFAULT FALSE;
        
        COMMENT ON COLUMN public.user_preferences.is_ortho_assistant IS 
        'Flag indicating if user is an orthodontic assistant';
    END IF;
END $$;

-- Summary
SELECT 
    'Migration completed successfully. All required columns for Add/Edit User API contract are now in place.' AS status;
