-- ==================================================
-- Add/Edit User API Migration Script
-- ==================================================
-- This script ensures all required columns exist for the Add/Edit User APIs
-- ==================================================

-- Verify user_preferences table has all required columns
DO $$
BEGIN
    -- Check if hipaa_compliant_scheduler column exists, if not add it
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_preferences' 
        AND column_name = 'hipaa_compliant_scheduler'
    ) THEN
        ALTER TABLE public.user_preferences ADD COLUMN hipaa_compliant_scheduler BOOLEAN DEFAULT FALSE;
    END IF;
    
    -- Check if is_ortho_assistant column exists, if not add it
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'user_preferences' 
        AND column_name = 'is_ortho_assistant'
    ) THEN
        ALTER TABLE public.user_preferences ADD COLUMN is_ortho_assistant BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Verify users table has updated_by column (should already exist from previous migrations)
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
COMMENT ON COLUMN public.user_preferences.hipaa_compliant_scheduler IS 'Enable HIPAA compliant scheduler view';
COMMENT ON COLUMN public.user_preferences.is_ortho_assistant IS 'Is orthodontic assistant';

-- ==================================================
-- Summary
-- ==================================================
-- This migration ensures:
-- 1. user_preferences.hipaa_compliant_scheduler column exists
-- 2. user_preferences.is_ortho_assistant column exists
-- 3. users.updated_by column exists (for audit trail)
--
-- All other required columns should already exist from previous migrations.
-- ==================================================
