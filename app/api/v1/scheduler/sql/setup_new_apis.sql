-- ==================================================
-- Setup Script for New Scheduler, Patient, and Procedure Block APIs
-- ==================================================
-- This script creates all required tables, constraints, indexes, and seed data
-- for the new APIs required by the Add/Edit Appointment page.
--
-- Run this script against your PostgreSQL database to initialize all new tables.
-- ==================================================

-- ==================================================
-- 1. CREATE ENUM TYPES (if not already created)
-- ==================================================
DO $$ BEGIN
    CREATE TYPE tenant_1.treatment_plan_status_enum AS ENUM ('Active', 'Completed', 'Cancelled');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE tenant_1.procedure_status_enum AS ENUM ('Planned', 'Scheduled', 'Completed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ==================================================
-- 2. UPDATE SCHEDULER_APPOINTMENTS TABLE
-- ==================================================
-- Add new fields to existing scheduler_appointments table
ALTER TABLE tenant_1.scheduler_appointments
ADD COLUMN IF NOT EXISTS lab BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS lab_dds VARCHAR(200),
ADD COLUMN IF NOT EXISTS lab_cost DECIMAL(10, 2),
ADD COLUMN IF NOT EXISTS lab_sent_on DATE,
ADD COLUMN IF NOT EXISTS lab_due_on DATE,
ADD COLUMN IF NOT EXISTS lab_recvd_on DATE,
ADD COLUMN IF NOT EXISTS missed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS cancelled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS campaign_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS treatment_plan_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS treatment_plan_phase_id VARCHAR(50);

-- Add foreign keys for treatment plan linkage (will be added after tables are created)
-- ALTER TABLE tenant_1.scheduler_appointments
-- ADD CONSTRAINT fk_appointment_treatment_plan
--     FOREIGN KEY (treatment_plan_id) REFERENCES tenant_1.treatment_plans(id);

-- ==================================================
-- 3. APPOINTMENT STATUSES TABLE
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.appointment_statuses (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    color VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_appointment_statuses_name ON tenant_1.appointment_statuses(name);

-- ==================================================
-- 4. APPOINTMENT TYPES TABLE (Optional)
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.appointment_types (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_appointment_types_name ON tenant_1.appointment_types(name);

-- ==================================================
-- 5. PROCEDURE CATEGORIES TABLE
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.procedure_categories (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_procedure_categories_name ON tenant_1.procedure_categories(name);

-- ==================================================
-- 6. PROCEDURE CODES TABLE
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.procedure_codes (
    code VARCHAR(20) PRIMARY KEY,
    user_code VARCHAR(50),
    description VARCHAR(500) NOT NULL,
    category VARCHAR(100) NOT NULL,
    requires_tooth BOOLEAN DEFAULT FALSE NOT NULL,
    requires_surface BOOLEAN DEFAULT FALSE NOT NULL,
    requires_quadrant BOOLEAN DEFAULT FALSE NOT NULL,
    requires_materials BOOLEAN DEFAULT FALSE NOT NULL,
    default_fee DECIMAL(10, 2) NOT NULL,
    default_duration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_procedure_code_category
        FOREIGN KEY (category) REFERENCES tenant_1.procedure_categories(id)
);

CREATE INDEX IF NOT EXISTS idx_procedure_codes_category ON tenant_1.procedure_codes(category);
CREATE INDEX IF NOT EXISTS idx_procedure_codes_code ON tenant_1.procedure_codes(code);
CREATE INDEX IF NOT EXISTS idx_procedure_codes_user_code ON tenant_1.procedure_codes(user_code);
CREATE INDEX IF NOT EXISTS idx_procedure_codes_description ON tenant_1.procedure_codes(description);

-- ==================================================
-- 7. TREATMENT PLANS TABLE
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.treatment_plans (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    patient_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_treatment_plans_patient_id ON tenant_1.treatment_plans(patient_id);
CREATE INDEX IF NOT EXISTS idx_treatment_plans_status ON tenant_1.treatment_plans(status);

-- ==================================================
-- 8. TREATMENT PLAN PHASES TABLE
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.treatment_plan_phases (
    id VARCHAR(50) PRIMARY KEY,
    treatment_plan_id VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    phase_order INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_treatment_plan_phase_plan
        FOREIGN KEY (treatment_plan_id) REFERENCES tenant_1.treatment_plans(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_treatment_plan_phases_plan_id ON tenant_1.treatment_plan_phases(treatment_plan_id);

-- ==================================================
-- 9. TREATMENT PLAN PROCEDURES TABLE
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.treatment_plan_procedures (
    id VARCHAR(50) PRIMARY KEY,
    phase_id VARCHAR(50) NOT NULL,
    procedure_code VARCHAR(20) NOT NULL,
    description VARCHAR(500) NOT NULL,
    tooth VARCHAR(10),
    surface VARCHAR(50),
    diagnosed_provider VARCHAR(200) NOT NULL,
    fee DECIMAL(10, 2) NOT NULL,
    insurance_estimate DECIMAL(10, 2) DEFAULT 0.00 NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Planned',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_treatment_plan_procedure_phase
        FOREIGN KEY (phase_id) REFERENCES tenant_1.treatment_plan_phases(id) ON DELETE CASCADE,
    CONSTRAINT fk_treatment_plan_procedure_code
        FOREIGN KEY (procedure_code) REFERENCES tenant_1.procedure_codes(code)
);

CREATE INDEX IF NOT EXISTS idx_treatment_plan_procedures_phase_id ON tenant_1.treatment_plan_procedures(phase_id);
CREATE INDEX IF NOT EXISTS idx_treatment_plan_procedures_status ON tenant_1.treatment_plan_procedures(status);

-- ==================================================
-- 10. APPOINTMENT TREATMENTS TABLE
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.appointment_treatments (
    id VARCHAR(50) PRIMARY KEY,
    appointment_id INTEGER NOT NULL,
    procedure_code VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    tooth VARCHAR(10),
    surface VARCHAR(50),
    description VARCHAR(500),
    bill_to VARCHAR(50) DEFAULT 'Patient' NOT NULL,
    duration INTEGER NOT NULL,
    provider VARCHAR(200) NOT NULL,
    provider_units INTEGER DEFAULT 1 NOT NULL,
    est_patient DECIMAL(10, 2),
    est_insurance DECIMAL(10, 2),
    fee DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_appointment_treatment_appointment
        FOREIGN KEY (appointment_id) REFERENCES tenant_1.scheduler_appointments(id) ON DELETE CASCADE,
    CONSTRAINT fk_appointment_treatment_procedure_code
        FOREIGN KEY (procedure_code) REFERENCES tenant_1.procedure_codes(code)
);

CREATE INDEX IF NOT EXISTS idx_appointment_treatments_appointment_id ON tenant_1.appointment_treatments(appointment_id);

-- ==================================================
-- 11. ADD FOREIGN KEY FOR TREATMENT PLAN LINKAGE
-- ==================================================
-- Now that treatment_plans table exists, add the foreign key constraint
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'fk_appointment_treatment_plan'
    ) THEN
        ALTER TABLE tenant_1.scheduler_appointments
        ADD CONSTRAINT fk_appointment_treatment_plan
            FOREIGN KEY (treatment_plan_id) REFERENCES tenant_1.treatment_plans(id);
    END IF;
END $$;

-- ==================================================
-- 12. SEED DATA - APPOINTMENT STATUSES
-- ==================================================
INSERT INTO tenant_1.appointment_statuses (id, name, display_name, color) VALUES
    ('STATUS001', 'Scheduled', 'Scheduled', '#3A6EA5'),
    ('STATUS002', 'Confirmed', 'Confirmed', '#2FB9A7'),
    ('STATUS003', 'Unconfirmed', 'Unconfirmed', '#F59E0B'),
    ('STATUS004', 'Left Message', 'Left Msg', '#8B5CF6'),
    ('STATUS005', 'In Operatory', 'In Operatory', '#10B981'),
    ('STATUS006', 'Available', 'Available', '#6B7280'),
    ('STATUS007', 'In Reception', 'In Reception', '#EC4899'),
    ('STATUS008', 'Checked Out', 'Checked Out', '#14B8A6'),
    ('STATUS009', 'Missed', 'Missed', '#EF4444'),
    ('STATUS010', 'Cancelled', 'Cancelled', '#DC2626')
ON CONFLICT (id) DO NOTHING;

-- ==================================================
-- 13. SEED DATA - APPOINTMENT TYPES
-- ==================================================
INSERT INTO tenant_1.appointment_types (id, name, description) VALUES
    ('TYPE001', 'New Patient', 'First visit appointment'),
    ('TYPE002', 'Follow-up', 'Follow-up appointment'),
    ('TYPE003', 'Emergency', 'Emergency appointment'),
    ('TYPE004', 'Consultation', 'Consultation appointment')
ON CONFLICT (id) DO NOTHING;

-- ==================================================
-- 14. SEED DATA - PROCEDURE CATEGORIES
-- ==================================================
INSERT INTO tenant_1.procedure_categories (id, name, display_name) VALUES
    ('ALL', 'ALL', 'All'),
    ('DIAGNOSTIC', 'DIAGNOSTIC', 'Diagnostic'),
    ('PREVENTIVE', 'PREVENTIVE', 'Preventive'),
    ('RESTORATIVE', 'RESTORATIVE', 'Restorative'),
    ('ENDODONTICS', 'ENDODONTICS', 'Endodontics'),
    ('PERIODONTICS', 'PERIODONTICS', 'Periodontics'),
    ('PROSTHODONTICS', 'PROSTHODONTICS', 'Prosthodontics'),
    ('ORAL_SURGERY', 'ORAL_SURGERY', 'Oral Surgery'),
    ('ORTHODONTICS', 'ORTHODONTICS', 'Orthodontics'),
    ('IMPLANT_SERVICES', 'IMPLANT_SERVICES', 'Implant Services'),
    ('ALL_MEDICAL', 'ALL_MEDICAL', 'All Medical')
ON CONFLICT (id) DO NOTHING;

-- ==================================================
-- 15. SEED DATA - PROCEDURE CODES
-- ==================================================
INSERT INTO tenant_1.procedure_codes (code, user_code, description, category, requires_tooth, requires_surface, requires_quadrant, requires_materials, default_fee, default_duration) VALUES
    -- Diagnostic
    ('D0120', '-', 'Periodic Oral Evaluation', 'DIAGNOSTIC', FALSE, FALSE, FALSE, FALSE, 75.00, 15),
    ('D0140', '-', 'Limited Oral Eval Prob Focused', 'DIAGNOSTIC', FALSE, FALSE, FALSE, FALSE, 85.00, 20),
    ('D0150', '-', 'Comprehensive Oral Evaluation', 'DIAGNOSTIC', FALSE, FALSE, FALSE, FALSE, 120.00, 30),
    ('D0210', '-', 'Intraoral - Complete Series', 'DIAGNOSTIC', FALSE, FALSE, FALSE, FALSE, 150.00, 20),
    ('D0220', '-', 'Intraoral - Periapical First Film', 'DIAGNOSTIC', FALSE, FALSE, FALSE, FALSE, 25.00, 5),
    ('D0272', '-', 'Bitewing - Two Films', 'DIAGNOSTIC', FALSE, FALSE, FALSE, FALSE, 50.00, 10),
    ('D0274', '-', 'Bitewing - Four Films', 'DIAGNOSTIC', FALSE, FALSE, FALSE, FALSE, 75.00, 15),
    
    -- Preventive
    ('D1110', '-', 'Adult Prophylaxis', 'PREVENTIVE', FALSE, FALSE, FALSE, FALSE, 100.00, 30),
    ('D1120', '-', 'Child Prophylaxis', 'PREVENTIVE', FALSE, FALSE, FALSE, FALSE, 75.00, 20),
    ('D1206', '-', 'Topical Fluoride Varnish', 'PREVENTIVE', FALSE, FALSE, FALSE, FALSE, 50.00, 5),
    ('D1351', '-', 'Sealant - Per Tooth', 'PREVENTIVE', TRUE, FALSE, FALSE, FALSE, 60.00, 10),
    
    -- Restorative
    ('D2140', '-', 'Amalgam - Two Surface, Primary', 'RESTORATIVE', TRUE, TRUE, FALSE, FALSE, 150.00, 30),
    ('D2150', '-', 'Amalgam - Two Surface, Permanent', 'RESTORATIVE', TRUE, TRUE, FALSE, FALSE, 175.00, 30),
    ('D2391', '-', 'Resin - One Surface, Anterior', 'RESTORATIVE', TRUE, TRUE, FALSE, FALSE, 200.00, 30),
    ('D2392', '-', 'Resin - Two Surface, Anterior', 'RESTORATIVE', TRUE, TRUE, FALSE, FALSE, 250.00, 45),
    ('D2393', '-', 'Resin - Three Surface, Anterior', 'RESTORATIVE', TRUE, TRUE, FALSE, FALSE, 300.00, 60),
    ('D2394', '-', 'Resin - Four or More Surface, Anterior', 'RESTORATIVE', TRUE, TRUE, FALSE, FALSE, 350.00, 75),
    
    -- Endodontics
    ('D3310', '-', 'Endodontic Therapy - Anterior', 'ENDODONTICS', TRUE, FALSE, FALSE, FALSE, 800.00, 90),
    ('D3320', '-', 'Endodontic Therapy - Bicuspid', 'ENDODONTICS', TRUE, FALSE, FALSE, FALSE, 900.00, 90),
    ('D3330', '-', 'Endodontic Therapy - Molar', 'ENDODONTICS', TRUE, FALSE, FALSE, FALSE, 1200.00, 120),
    
    -- Periodontics
    ('D4341', '-', 'Periodontal Scaling and Root Planing - Per Quadrant', 'PERIODONTICS', FALSE, FALSE, TRUE, FALSE, 300.00, 60),
    ('D4342', '-', 'Periodontal Scaling and Root Planing - Four or More Teeth', 'PERIODONTICS', FALSE, FALSE, FALSE, FALSE, 250.00, 45),
    
    -- Prosthodontics
    ('D2740', '-', 'Crown - Porcelain/Ceramic', 'PROSTHODONTICS', TRUE, FALSE, FALSE, FALSE, 1200.00, 120),
    ('D2750', '-', 'Crown - Porcelain Fused to Metal', 'PROSTHODONTICS', TRUE, FALSE, FALSE, FALSE, 1000.00, 120),
    ('D5213', '-', 'Partial Denture - Maxillary', 'PROSTHODONTICS', FALSE, FALSE, FALSE, FALSE, 2000.00, 180),
    ('D5214', '-', 'Partial Denture - Mandibular', 'PROSTHODONTICS', FALSE, FALSE, FALSE, FALSE, 2000.00, 180),
    
    -- Oral Surgery
    ('D7111', '-', 'Extraction - Coronal Remnants', 'ORAL_SURGERY', TRUE, FALSE, FALSE, FALSE, 150.00, 30),
    ('D7140', '-', 'Extraction - Erupted Tooth', 'ORAL_SURGERY', TRUE, FALSE, FALSE, FALSE, 200.00, 30),
    ('D7210', '-', 'Extraction - Erupted Tooth with Elevation', 'ORAL_SURGERY', TRUE, FALSE, FALSE, FALSE, 250.00, 45),
    
    -- Orthodontics
    ('D8010', '-', 'Limited Orthodontic Treatment', 'ORTHODONTICS', FALSE, FALSE, FALSE, FALSE, 3000.00, 180),
    ('D8070', '-', 'Comprehensive Orthodontic Treatment', 'ORTHODONTICS', FALSE, FALSE, FALSE, FALSE, 5000.00, 240),
    
    -- Implant Services
    ('D6010', '-', 'Surgical Placement of Implant', 'IMPLANT_SERVICES', TRUE, FALSE, FALSE, FALSE, 2000.00, 120),
    ('D6056', '-', 'Abutment Supported Porcelain Crown', 'IMPLANT_SERVICES', TRUE, FALSE, FALSE, FALSE, 1500.00, 90),
    
    -- Special Codes
    ('Z6000', '-', 'Impressions Diagnosed', 'ALL', FALSE, FALSE, FALSE, FALSE, 250.00, 30)
ON CONFLICT (code) DO NOTHING;

-- ==================================================
-- 16. SAMPLE TREATMENT PLAN DATA (Optional - for testing)
-- ==================================================
-- Uncomment and modify as needed for testing
/*
INSERT INTO tenant_1.treatment_plans (id, name, patient_id, status) VALUES
    ('TXP-001', 'Plan 1', '900097', 'Active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tenant_1.treatment_plan_phases (id, treatment_plan_id, name, phase_order) VALUES
    ('PHASE-001', 'TXP-001', 'Phase 1', 1)
ON CONFLICT (id) DO NOTHING;

INSERT INTO tenant_1.treatment_plan_procedures (id, phase_id, procedure_code, description, tooth, surface, diagnosed_provider, fee, insurance_estimate, status) VALUES
    ('PROC-001', 'PHASE-001', 'Z6000', 'Impressions Diagnosed (6963/JN, Ahmed, Mary)', '', '', 'Dr. Ahmed', 250.00, 0.00, 'Planned'),
    ('PROC-002', 'PHASE-001', 'Z6000', 'Impressions Diagnosed (6963/JN, Ahmed, Meier)', '', '', 'Dr. Ahmed', 250.00, 0.00, 'Planned')
ON CONFLICT (id) DO NOTHING;
*/

-- ==================================================
-- 17. CREATE TRIGGERS FOR UPDATED_AT
-- ==================================================
-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION tenant_1.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers to tables with updated_at columns
DROP TRIGGER IF EXISTS update_appointment_statuses_updated_at ON tenant_1.appointment_statuses;
CREATE TRIGGER update_appointment_statuses_updated_at
    BEFORE UPDATE ON tenant_1.appointment_statuses
    FOR EACH ROW
    EXECUTE FUNCTION tenant_1.update_updated_at_column();

DROP TRIGGER IF EXISTS update_procedure_codes_updated_at ON tenant_1.procedure_codes;
CREATE TRIGGER update_procedure_codes_updated_at
    BEFORE UPDATE ON tenant_1.procedure_codes
    FOR EACH ROW
    EXECUTE FUNCTION tenant_1.update_updated_at_column();

DROP TRIGGER IF EXISTS update_treatment_plans_updated_at ON tenant_1.treatment_plans;
CREATE TRIGGER update_treatment_plans_updated_at
    BEFORE UPDATE ON tenant_1.treatment_plans
    FOR EACH ROW
    EXECUTE FUNCTION tenant_1.update_updated_at_column();

DROP TRIGGER IF EXISTS update_treatment_plan_procedures_updated_at ON tenant_1.treatment_plan_procedures;
CREATE TRIGGER update_treatment_plan_procedures_updated_at
    BEFORE UPDATE ON tenant_1.treatment_plan_procedures
    FOR EACH ROW
    EXECUTE FUNCTION tenant_1.update_updated_at_column();

DROP TRIGGER IF EXISTS update_appointment_treatments_updated_at ON tenant_1.appointment_treatments;
CREATE TRIGGER update_appointment_treatments_updated_at
    BEFORE UPDATE ON tenant_1.appointment_treatments
    FOR EACH ROW
    EXECUTE FUNCTION tenant_1.update_updated_at_column();

-- ==================================================
-- END OF SCRIPT
-- ==================================================
-- All tables, constraints, indexes, and seed data have been created.
-- The new APIs should now be fully functional.
-- ==================================================
