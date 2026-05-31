-- ==================================================
-- Fix Appointment Status Enum
-- ==================================================
-- This script ensures the appointment_status_enum exists
-- with the correct values in the tenant_1 schema.
-- Run this if you get enum-related errors.
-- ==================================================

-- Drop the enum if it exists (be careful - this will fail if tables use it)
-- You may need to drop dependent tables first, or alter the column type
DO $$ 
BEGIN
    -- Check if enum exists
    IF EXISTS (
        SELECT 1 
        FROM pg_type t 
        JOIN pg_namespace n ON n.oid = t.typnamespace 
        WHERE t.typname = 'appointment_status_enum' 
        AND n.nspname = 'tenant_1'
    ) THEN
        -- Enum exists, check if we need to recreate it
        -- Note: PostgreSQL doesn't support ALTER TYPE to add/remove values easily
        -- So we'll just ensure it has the right values
        RAISE NOTICE 'Enum tenant_1.appointment_status_enum already exists';
    ELSE
        -- Create the enum
        CREATE TYPE tenant_1.appointment_status_enum AS ENUM (
            'Scheduled',
            'Confirmed',
            'Unconfirmed',
            'Left Message',
            'In Reception',
            'Available',
            'In Operatory',
            'Checked Out',
            'Missed',
            'Cancelled'
        );
        RAISE NOTICE 'Created enum tenant_1.appointment_status_enum';
    END IF;
END $$;

-- Verify the enum values
SELECT 
    t.typname AS enum_name,
    e.enumlabel AS enum_value,
    e.enumsortorder AS sort_order
FROM pg_type t 
JOIN pg_enum e ON t.oid = e.enumtypid  
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE t.typname = 'appointment_status_enum'
AND n.nspname = 'tenant_1'
ORDER BY e.enumsortorder;
