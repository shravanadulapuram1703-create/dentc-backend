-- ==================================================
-- Scheduler Module - Database Schema
-- ==================================================
-- This script creates all necessary tables for the Scheduler module
-- under the tenant_1 schema (tenant-specific data).
-- Run this script against your PostgreSQL database to initialize the scheduler tables.
--
-- Prerequisites:
-- - The 'public' schema exists with 'offices' table
-- - The 'tenant_1' schema exists (create if needed: CREATE SCHEMA IF NOT EXISTS tenant_1;)
-- ==================================================

-- ==================================================
-- 0. CREATE TENANT SCHEMA IF NOT EXISTS
-- ==================================================
CREATE SCHEMA IF NOT EXISTS tenant_1;

-- ==================================================
-- 1. CREATE ENUM TYPE FOR APPOINTMENT STATUS (in tenant_1 schema)
-- ==================================================
DO $$ BEGIN
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
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ==================================================
-- 2. SCHEDULER APPOINTMENTS TABLE (in tenant_1 schema)
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.scheduler_appointments (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR NOT NULL,
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    duration INTEGER NOT NULL CHECK (duration > 0 AND duration <= 480),
    procedure_type VARCHAR NOT NULL,
    operatory_id VARCHAR NOT NULL,
    provider_id VARCHAR NOT NULL,
    status tenant_1.appointment_status_enum NOT NULL DEFAULT 'Scheduled',
    notes TEXT,
    office_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_scheduler_appointments_office 
        FOREIGN KEY (office_id) 
        REFERENCES public.offices(id) 
        ON DELETE CASCADE
);

-- Create indexes for scheduler_appointments
CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_patient_id 
    ON tenant_1.scheduler_appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_date 
    ON tenant_1.scheduler_appointments(date);
CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_operatory_id 
    ON tenant_1.scheduler_appointments(operatory_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_provider_id 
    ON tenant_1.scheduler_appointments(provider_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_status 
    ON tenant_1.scheduler_appointments(status);
CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_office_id 
    ON tenant_1.scheduler_appointments(office_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_date_time 
    ON tenant_1.scheduler_appointments(date, start_time);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_scheduler_appointments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_scheduler_appointments_updated_at ON tenant_1.scheduler_appointments;
CREATE TRIGGER trigger_update_scheduler_appointments_updated_at
    BEFORE UPDATE ON tenant_1.scheduler_appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_scheduler_appointments_updated_at();

-- ==================================================
-- 3. SCHEDULER OPERATORIES TABLE (in tenant_1 schema)
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.scheduler_operatories (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    provider_id VARCHAR NOT NULL,
    office_id INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_scheduler_operatories_office 
        FOREIGN KEY (office_id) 
        REFERENCES public.offices(id) 
        ON DELETE CASCADE
);

-- Create indexes for scheduler_operatories
CREATE INDEX IF NOT EXISTS idx_scheduler_operatories_office_id 
    ON tenant_1.scheduler_operatories(office_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_operatories_provider_id 
    ON tenant_1.scheduler_operatories(provider_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_operatories_is_active 
    ON tenant_1.scheduler_operatories(is_active);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_scheduler_operatories_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_scheduler_operatories_updated_at ON tenant_1.scheduler_operatories;
CREATE TRIGGER trigger_update_scheduler_operatories_updated_at
    BEFORE UPDATE ON tenant_1.scheduler_operatories
    FOR EACH ROW
    EXECUTE FUNCTION update_scheduler_operatories_updated_at();

-- ==================================================
-- 4. SCHEDULER PROVIDERS TABLE (in tenant_1 schema)
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.scheduler_providers (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    office_id INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_scheduler_providers_office 
        FOREIGN KEY (office_id) 
        REFERENCES public.offices(id) 
        ON DELETE CASCADE
);

-- Create indexes for scheduler_providers
CREATE INDEX IF NOT EXISTS idx_scheduler_providers_office_id 
    ON tenant_1.scheduler_providers(office_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_providers_is_active 
    ON tenant_1.scheduler_providers(is_active);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_scheduler_providers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_scheduler_providers_updated_at ON tenant_1.scheduler_providers;
CREATE TRIGGER trigger_update_scheduler_providers_updated_at
    BEFORE UPDATE ON tenant_1.scheduler_providers
    FOR EACH ROW
    EXECUTE FUNCTION update_scheduler_providers_updated_at();

-- ==================================================
-- 5. SCHEDULER PROCEDURE TYPES TABLE (in tenant_1 schema)
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.scheduler_procedure_types (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    color VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for scheduler_procedure_types
CREATE INDEX IF NOT EXISTS idx_scheduler_procedure_types_is_active 
    ON tenant_1.scheduler_procedure_types(is_active);
CREATE INDEX IF NOT EXISTS idx_scheduler_procedure_types_name 
    ON tenant_1.scheduler_procedure_types(name);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_scheduler_procedure_types_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_scheduler_procedure_types_updated_at ON tenant_1.scheduler_procedure_types;
CREATE TRIGGER trigger_update_scheduler_procedure_types_updated_at
    BEFORE UPDATE ON tenant_1.scheduler_procedure_types
    FOR EACH ROW
    EXECUTE FUNCTION update_scheduler_procedure_types_updated_at();

-- ==================================================
-- 6. SCHEDULER CONFIG TABLE (in tenant_1 schema)
-- ==================================================
CREATE TABLE IF NOT EXISTS tenant_1.scheduler_config (
    office_id INTEGER PRIMARY KEY,
    start_hour INTEGER NOT NULL DEFAULT 8 CHECK (start_hour >= 0 AND start_hour <= 23),
    end_hour INTEGER NOT NULL DEFAULT 17 CHECK (end_hour >= 0 AND end_hour <= 23),
    slot_interval INTEGER NOT NULL DEFAULT 10 CHECK (slot_interval > 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_scheduler_config_office 
        FOREIGN KEY (office_id) 
        REFERENCES public.offices(id) 
        ON DELETE CASCADE,
    CONSTRAINT chk_scheduler_config_hours 
        CHECK (end_hour > start_hour)
);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_scheduler_config_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_scheduler_config_updated_at ON tenant_1.scheduler_config;
CREATE TRIGGER trigger_update_scheduler_config_updated_at
    BEFORE UPDATE ON tenant_1.scheduler_config
    FOR EACH ROW
    EXECUTE FUNCTION update_scheduler_config_updated_at();

-- ==================================================
-- 7. SAMPLE DATA (Optional - Comment out if not needed)
-- ==================================================

-- Insert sample procedure types
INSERT INTO tenant_1.scheduler_procedure_types (id, name, color) VALUES
    ('PROC001', 'Cleaning', 'bg-blue-100'),
    ('PROC002', 'New Patient', 'bg-green-100'),
    ('PROC003', 'Crown', 'bg-purple-100'),
    ('PROC004', 'Root Canal', 'bg-red-100'),
    ('PROC005', 'Filling', 'bg-yellow-100')
ON CONFLICT (id) DO NOTHING;

-- Note: Sample providers and operatories should be inserted based on your office setup
-- Example (replace office_id with actual office ID):
-- INSERT INTO tenant_1.scheduler_providers (id, name, office_id) VALUES
--     ('PROV001', 'Dr. Jinna', 1),
--     ('PROV002', 'Dr. Smith', 1)
-- ON CONFLICT (id) DO NOTHING;
--
-- INSERT INTO tenant_1.scheduler_operatories (id, name, provider_id, office_id) VALUES
--     ('OP1', 'OP 1 - Hygiene', 'PROV001', 1),
--     ('OP2', 'OP 2 - Major', 'PROV002', 1)
-- ON CONFLICT (id) DO NOTHING;

-- ==================================================
-- END OF SCRIPT
-- ==================================================
