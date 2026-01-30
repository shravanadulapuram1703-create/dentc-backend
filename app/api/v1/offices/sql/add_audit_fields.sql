-- ==================================================
-- Add Audit Fields to Offices Table
-- ==================================================
-- This script adds created_by, updated_by columns to the offices table
-- and updates existing records with default values

-- Add created_by column (NOT NULL, but we'll set defaults for existing rows)
ALTER TABLE public.offices 
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255);

-- Add updated_by column (nullable)
ALTER TABLE public.offices 
ADD COLUMN IF NOT EXISTS updated_by VARCHAR(255);

-- Update existing records with default values
-- Set created_by to 'system' for existing offices that don't have a value
UPDATE public.offices 
SET created_by = 'system' 
WHERE created_by IS NULL;

-- Make created_by NOT NULL after setting defaults
ALTER TABLE public.offices 
ALTER COLUMN created_by SET NOT NULL;

-- Ensure created_at is NOT NULL (should already be, but making sure)
ALTER TABLE public.offices 
ALTER COLUMN created_at SET NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN public.offices.created_by IS 'Email or username of user who created the office';
COMMENT ON COLUMN public.offices.updated_by IS 'Email or username of user who last updated the office (null if never updated)';
COMMENT ON COLUMN public.offices.created_at IS 'Timestamp when office was created';
COMMENT ON COLUMN public.offices.updated_at IS 'Timestamp when office was last updated (null if never updated)';
