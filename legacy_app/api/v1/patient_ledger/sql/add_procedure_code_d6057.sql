-- ==================================================
-- Add Procedure Code D6057 (Implant Supported Fixed Prosthesis)
-- ==================================================
-- This script adds procedure code D6057 to the procedure_codes table
-- if it doesn't already exist.
-- 
-- D6057: Implant Supported Fixed Prosthesis - Abutment Supported
-- This procedure typically requires a tooth number to be specified.
-- ==================================================

-- Check if category exists, if not create it
INSERT INTO tenant_1.procedure_categories (id, name, display_name)
VALUES ('PROSTHETIC', 'PROSTHETIC', 'Prosthetic')
ON CONFLICT (id) DO NOTHING;

-- Insert D6057 procedure code if it doesn't exist
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
    'D6057',
    NULL,
    'Implant Supported Fixed Prosthesis - Abutment Supported',
    'PROSTHETIC',
    TRUE,  -- Requires tooth number
    FALSE, -- Does not require surface
    FALSE, -- Does not require quadrant
    FALSE, -- Does not require materials
    2500.00, -- Default fee (adjust as needed)
    120     -- Default duration in minutes (adjust as needed)
)
ON CONFLICT (code) DO UPDATE
SET
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    requires_tooth = EXCLUDED.requires_tooth,
    requires_surface = EXCLUDED.requires_surface,
    requires_quadrant = EXCLUDED.requires_quadrant,
    requires_materials = EXCLUDED.requires_materials,
    default_fee = EXCLUDED.default_fee,
    default_duration = EXCLUDED.default_duration,
    updated_at = CURRENT_TIMESTAMP;

-- Verify it was created/updated
SELECT 
    code, 
    description, 
    category, 
    requires_tooth,
    requires_surface,
    requires_quadrant,
    requires_materials,
    default_fee, 
    default_duration
FROM tenant_1.procedure_codes 
WHERE code = 'D6057';
