-- ==================================================
-- Add UNKNOWN Procedure Code
-- ==================================================
-- This script adds an "UNKNOWN" procedure code to the procedure_codes table
-- to support treatments that don't have a specific procedure code.
--
-- Run this script if you're getting foreign key constraint errors when
-- creating treatments without procedure_code.
-- ==================================================

-- Insert UNKNOWN procedure code if it doesn't exist
INSERT INTO tenant_1.procedure_codes (
    code,
    user_code,
    description,
    category,
    requires_tooth,
    requires_surface,
    requires_quadrant,
    requires_materials,
    default_fee,
    default_duration
) VALUES (
    'UNKNOWN',
    'UNKNOWN',
    'Unknown Procedure',
    'ALL',
    FALSE,
    FALSE,
    FALSE,
    FALSE,
    0.00,
    NULL
)
ON CONFLICT (code) DO NOTHING;

-- Verify it was created
SELECT code, description, category, default_fee 
FROM tenant_1.procedure_codes 
WHERE code = 'UNKNOWN';
