-- ==================================================
-- User Details API Migration Script
-- ==================================================
-- This script adds missing columns and tables needed for
-- the View User Details modal APIs

-- ==================================================
-- 1. Add missing columns to users table
-- ==================================================

-- Add password_last_changed timestamp (if not exists)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS password_last_changed TIMESTAMP;

-- Add must_change_password flag (if not exists)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;

-- Add failed_login_attempts counter (if not exists)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;

-- Add account_locked_until timestamp (if not exists)
-- Note: is_locked already exists, but we can add a lock expiration
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS account_locked_until TIMESTAMP;

-- Add created_by username (if not exists as string)
-- Note: created_by already exists as integer FK, but we need username for display
-- We'll derive this from the relationship, but adding a comment for clarity
COMMENT ON COLUMN public.users.created_by IS 'User ID of creator (use JOIN to get username)';

-- ==================================================
-- 2. Add updated_at timestamp to user_ip_rules (if not exists)
-- ==================================================

ALTER TABLE public.user_ip_rules 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_user_ip_rules_user_id ON public.user_ip_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_user_ip_rules_tenant_id ON public.user_ip_rules(tenant_id);

-- ==================================================
-- 3. Add created_at to user_roles (if not exists)
-- ==================================================

ALTER TABLE public.user_roles 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON public.user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_tenant_id ON public.user_roles(tenant_id);

-- ==================================================
-- 4. Create time_clock_entries table (if not exists)
-- ==================================================

CREATE TABLE IF NOT EXISTS public.time_clock_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    entry_date DATE NOT NULL,
    clock_in_time TIME NOT NULL,
    clock_out_time TIME,
    total_hours NUMERIC(5, 2),  -- Calculated field
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    
    -- Ensure one entry per user per date
    CONSTRAINT uq_user_date_entry UNIQUE (user_id, entry_date)
);

-- Add indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_time_clock_entries_user_id ON public.time_clock_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_time_clock_entries_entry_date ON public.time_clock_entries(entry_date);

-- Add comment
COMMENT ON TABLE public.time_clock_entries IS 'Time clock entries for users (clock in/out records)';

-- ==================================================
-- 5. Add missing columns to user_preferences (if needed)
-- ==================================================

-- These fields are optional and can be added if needed:
-- theme, language, date_format, time_format, email_notifications, 
-- sms_notifications, items_per_page
-- For now, we'll use existing fields and map them appropriately

-- ==================================================
-- 6. Add updated_at trigger for user_ip_rules
-- ==================================================

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_user_ip_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_update_user_ip_rules_updated_at ON public.user_ip_rules;
CREATE TRIGGER trigger_update_user_ip_rules_updated_at
    BEFORE UPDATE ON public.user_ip_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_user_ip_rules_updated_at();

-- ==================================================
-- 7. Add updated_at trigger for time_clock_entries
-- ==================================================

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_time_clock_entries_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_update_time_clock_entries_updated_at ON public.time_clock_entries;
CREATE TRIGGER trigger_update_time_clock_entries_updated_at
    BEFORE UPDATE ON public.time_clock_entries
    FOR EACH ROW
    EXECUTE FUNCTION update_time_clock_entries_updated_at();

-- ==================================================
-- 8. Add function to calculate total_hours automatically
-- ==================================================

CREATE OR REPLACE FUNCTION calculate_time_clock_hours()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.clock_out_time IS NOT NULL AND NEW.clock_in_time IS NOT NULL THEN
        -- Calculate hours between clock_in and clock_out
        NEW.total_hours = EXTRACT(EPOCH FROM (NEW.clock_out_time - NEW.clock_in_time)) / 3600.0;
    ELSE
        NEW.total_hours = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-calculate total_hours
DROP TRIGGER IF EXISTS trigger_calculate_time_clock_hours ON public.time_clock_entries;
CREATE TRIGGER trigger_calculate_time_clock_hours
    BEFORE INSERT OR UPDATE ON public.time_clock_entries
    FOR EACH ROW
    EXECUTE FUNCTION calculate_time_clock_hours();

-- ==================================================
-- 9. Add comments for documentation
-- ==================================================

COMMENT ON COLUMN public.users.password_last_changed IS 'Timestamp when user last changed their password';
COMMENT ON COLUMN public.users.must_change_password IS 'Whether user must change password on next login';
COMMENT ON COLUMN public.users.failed_login_attempts IS 'Number of consecutive failed login attempts';
COMMENT ON COLUMN public.users.account_locked_until IS 'Timestamp when account lock expires (null if not locked)';
COMMENT ON COLUMN public.user_ip_rules.updated_at IS 'Timestamp when IP rule was last updated';
COMMENT ON COLUMN public.user_roles.created_at IS 'Timestamp when user was assigned this role';
COMMENT ON COLUMN public.time_clock_entries.entry_date IS 'Date of the time clock entry';
COMMENT ON COLUMN public.time_clock_entries.clock_in_time IS 'Time when user clocked in';
COMMENT ON COLUMN public.time_clock_entries.clock_out_time IS 'Time when user clocked out (null if not clocked out)';
COMMENT ON COLUMN public.time_clock_entries.total_hours IS 'Total hours worked (auto-calculated)';
COMMENT ON COLUMN public.time_clock_entries.notes IS 'Optional notes for the time entry';
