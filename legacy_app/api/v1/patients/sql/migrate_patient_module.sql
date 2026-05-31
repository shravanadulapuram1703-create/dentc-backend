-- ==================================================
-- Patient Module Database Migration Script
-- ==================================================
-- This script creates/updates all patient-related tables
-- to support the comprehensive Patient Management API
-- ==================================================

-- ==================================================
-- 1. ALTER EXISTING PATIENTS TABLE
-- ==================================================

-- Add new columns to existing patients table
ALTER TABLE tenant_1.patients
ADD COLUMN IF NOT EXISTS preferred_name VARCHAR(100),
ADD COLUMN IF NOT EXISTS title VARCHAR(10),
ADD COLUMN IF NOT EXISTS pronouns VARCHAR(20),
ADD COLUMN IF NOT EXISTS marital_status VARCHAR(50),
ADD COLUMN IF NOT EXISTS ssn VARCHAR(20),
ADD COLUMN IF NOT EXISTS medicaid_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS patient_type VARCHAR(20) DEFAULT 'General',
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS is_ortho BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_child BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_collection_problem BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_employee_family BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_short_notice BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_senior BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_spanish_speaking BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS assign_benefits BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS hipaa_agreement BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS no_correspondence BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS no_auto_email BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS no_auto_sms BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS add_to_quickfill BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS preferred_provider_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS preferred_hygienist_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS fee_schedule_id VARCHAR(50),
ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(50) DEFAULT 'English',
ADD COLUMN IF NOT EXISTS preferred_contact VARCHAR(50),
ADD COLUMN IF NOT EXISTS referral_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS referred_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS referred_to VARCHAR(255),
ADD COLUMN IF NOT EXISTS referral_to_date DATE,
ADD COLUMN IF NOT EXISTS guardian_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS guardian_phone VARCHAR(20),
ADD COLUMN IF NOT EXISTS patient_notes TEXT,
ADD COLUMN IF NOT EXISTS hipaa_sharing VARCHAR(50) DEFAULT 'Full sharing allowed';

-- Update gender column to support more values
ALTER TABLE tenant_1.patients
ALTER COLUMN gender TYPE VARCHAR(10);

-- Add indexes for common search fields
CREATE INDEX IF NOT EXISTS idx_patients_last_name ON tenant_1.patients(last_name);
CREATE INDEX IF NOT EXISTS idx_patients_first_name ON tenant_1.patients(first_name);
CREATE INDEX IF NOT EXISTS idx_patients_chart_no ON tenant_1.patients(chart_no);
CREATE INDEX IF NOT EXISTS idx_patients_dob ON tenant_1.patients(dob);
CREATE INDEX IF NOT EXISTS idx_patients_email ON tenant_1.patients(email);
CREATE INDEX IF NOT EXISTS idx_patients_ssn ON tenant_1.patients(ssn);
CREATE INDEX IF NOT EXISTS idx_patients_medicaid_id ON tenant_1.patients(medicaid_id);
CREATE INDEX IF NOT EXISTS idx_patients_home_office_id ON tenant_1.patients(home_office_id);
CREATE INDEX IF NOT EXISTS idx_patients_patient_type ON tenant_1.patients(patient_type);
CREATE INDEX IF NOT EXISTS idx_patients_is_active ON tenant_1.patients(is_active);

-- ==================================================
-- 2. CREATE PATIENT ADDRESSES TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_addresses (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    address_line_1 VARCHAR(255),
    address_line_2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    zip VARCHAR(20),
    country VARCHAR(50) DEFAULT 'USA',
    address_type VARCHAR(20) DEFAULT 'Home', -- Home, Work, Billing, etc.
    is_primary BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE(patient_id, address_type)
);

CREATE INDEX IF NOT EXISTS idx_patient_addresses_patient_id ON tenant_1.patient_addresses(patient_id);

-- ==================================================
-- 3. CREATE PATIENT CONTACT INFO TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_contact_info (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    home_phone VARCHAR(20),
    cell_phone VARCHAR(20),
    work_phone VARCHAR(20),
    email VARCHAR(255),
    preferred_contact VARCHAR(50), -- Home Phone, Cell Phone, Work Phone, Email
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE(patient_id)
);

CREATE INDEX IF NOT EXISTS idx_patient_contact_info_patient_id ON tenant_1.patient_contact_info(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_contact_info_home_phone ON tenant_1.patient_contact_info(home_phone);
CREATE INDEX IF NOT EXISTS idx_patient_contact_info_cell_phone ON tenant_1.patient_contact_info(cell_phone);
CREATE INDEX IF NOT EXISTS idx_patient_contact_info_work_phone ON tenant_1.patient_contact_info(work_phone);
CREATE INDEX IF NOT EXISTS idx_patient_contact_info_email ON tenant_1.patient_contact_info(email);

-- ==================================================
-- 4. CREATE RESPONSIBLE PARTIES TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.responsible_parties (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    responsible_party_id VARCHAR(50), -- Reference to another patient if self
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50), -- Cash, Insurance, etc.
    relationship VARCHAR(50), -- Self, Spouse, Parent, Guardian, etc.
    phone VARCHAR(20),
    email VARCHAR(255),
    home_office_id INTEGER REFERENCES public.offices(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE(patient_id)
);

CREATE INDEX IF NOT EXISTS idx_responsible_parties_patient_id ON tenant_1.responsible_parties(patient_id);
CREATE INDEX IF NOT EXISTS idx_responsible_parties_name ON tenant_1.responsible_parties(name);
CREATE INDEX IF NOT EXISTS idx_responsible_parties_phone ON tenant_1.responsible_parties(phone);
CREATE INDEX IF NOT EXISTS idx_responsible_parties_email ON tenant_1.responsible_parties(email);

-- ==================================================
-- 5. CREATE PATIENT INSURANCE TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_insurance (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    insurance_type VARCHAR(20) NOT NULL, -- primary_dental, secondary_dental, primary_medical, secondary_medical
    carrier_name VARCHAR(255),
    plan_name VARCHAR(255),
    group_number VARCHAR(100),
    subscriber_id VARCHAR(100),
    subscriber_name VARCHAR(255),
    relationship VARCHAR(50), -- Self, Spouse, Child, etc.
    carrier_phone VARCHAR(20),
    individual_max_remaining DECIMAL(10, 2),
    individual_deductible_remaining DECIMAL(10, 2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE(patient_id, insurance_type)
);

CREATE INDEX IF NOT EXISTS idx_patient_insurance_patient_id ON tenant_1.patient_insurance(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_insurance_subscriber_id ON tenant_1.patient_insurance(subscriber_id);

-- ==================================================
-- 6. CREATE FEE SCHEDULES TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.fee_schedules (
    id SERIAL PRIMARY KEY,
    fee_schedule_id VARCHAR(50) NOT NULL UNIQUE,
    fee_schedule_name VARCHAR(255) NOT NULL,
    description TEXT,
    office_id INTEGER REFERENCES public.offices(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fee_schedules_office_id ON tenant_1.fee_schedules(office_id);
CREATE INDEX IF NOT EXISTS idx_fee_schedules_fee_schedule_id ON tenant_1.fee_schedules(fee_schedule_id);

-- ==================================================
-- 7. CREATE PATIENT TYPES REFERENCE TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==================================================
-- 8. CREATE REFERRAL TYPES REFERENCE TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.referral_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==================================================
-- 9. CREATE RESPONSIBLE PARTY RELATIONSHIPS TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.responsible_party_relationships (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==================================================
-- 10. CREATE CONTACT PREFERENCES TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.contact_preferences (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==================================================
-- 11. CREATE PATIENT ACCOUNT MEMBERS TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_account_members (
    id SERIAL PRIMARY KEY,
    account_patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    member_patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    relationship VARCHAR(50), -- Self, Spouse, Child, etc.
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(account_patient_id, member_patient_id)
);

CREATE INDEX IF NOT EXISTS idx_account_members_account_id ON tenant_1.patient_account_members(account_patient_id);
CREATE INDEX IF NOT EXISTS idx_account_members_member_id ON tenant_1.patient_account_members(member_patient_id);

-- ==================================================
-- 12. CREATE PATIENT BALANCES TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_balances (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    account_balance DECIMAL(10, 2) DEFAULT 0.00,
    current DECIMAL(10, 2) DEFAULT 0.00,
    over_30 DECIMAL(10, 2) DEFAULT 0.00,
    over_60 DECIMAL(10, 2) DEFAULT 0.00,
    over_90 DECIMAL(10, 2) DEFAULT 0.00,
    over_120 DECIMAL(10, 2) DEFAULT 0.00,
    last_insurance_payment DECIMAL(10, 2),
    last_insurance_payment_date DATE,
    last_patient_payment DECIMAL(10, 2),
    last_patient_payment_date DATE,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(patient_id)
);

CREATE INDEX IF NOT EXISTS idx_patient_balances_patient_id ON tenant_1.patient_balances(patient_id);

-- ==================================================
-- 13. CREATE PATIENT CLINICAL INFO TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_clinical_info (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    first_visit DATE,
    last_visit DATE,
    next_visit DATE,
    next_recall DATE,
    last_pano_chart DATE,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(patient_id)
);

CREATE INDEX IF NOT EXISTS idx_patient_clinical_info_patient_id ON tenant_1.patient_clinical_info(patient_id);

-- ==================================================
-- 14. CREATE MEDICAL ALERTS TABLE
-- ==================================================

CREATE TABLE IF NOT EXISTS tenant_1.patient_medical_alerts (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    alert TEXT NOT NULL,
    entered_by VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_medical_alerts_patient_id ON tenant_1.patient_medical_alerts(patient_id);

-- ==================================================
-- 15. INSERT SEED DATA
-- ==================================================

-- Patient Types
INSERT INTO tenant_1.patient_types (code, name, description) VALUES
('CH', 'Child', 'Child patient'),
('CP', 'Collection Problem', 'Patient with collection issues'),
('OR', 'Ortho Patient', 'Orthodontic patient'),
('EF', 'Employee Family', 'Employee family member'),
('SN', 'Short Notice', 'Patient who accepts short notice appointments'),
('SR', 'Senior', 'Senior patient'),
('SS', 'Spanish Speaking', 'Spanish speaking patient')
ON CONFLICT (code) DO NOTHING;

-- Referral Types
INSERT INTO tenant_1.referral_types (code, name, description) VALUES
('PATIENT', 'Patient', 'Self-referred patient'),
('DENTIST', 'Dentist', 'Referred by dentist'),
('PHYSICIAN', 'Physician', 'Referred by physician'),
('FRIEND', 'Friend', 'Referred by friend'),
('ADVERTISING', 'Advertising', 'Found through advertising'),
('OTHER', 'Other', 'Other referral source')
ON CONFLICT (code) DO NOTHING;

-- Responsible Party Relationships
INSERT INTO tenant_1.responsible_party_relationships (code, name, description) VALUES
('SELF', 'Self', 'Patient is responsible party'),
('SPOUSE', 'Spouse', 'Spouse is responsible party'),
('PARENT', 'Parent', 'Parent is responsible party'),
('GUARDIAN', 'Guardian', 'Guardian is responsible party'),
('CHILD', 'Child', 'Child is responsible party'),
('OTHER', 'Other', 'Other relationship')
ON CONFLICT (code) DO NOTHING;

-- Contact Preferences
INSERT INTO tenant_1.contact_preferences (code, name, description) VALUES
('NO_PREFERENCE', 'No Preference', 'No contact preference'),
('HOME_PHONE', 'Home Phone', 'Contact via home phone'),
('CELL_PHONE', 'Cell Phone', 'Contact via cell phone'),
('WORK_PHONE', 'Work Phone', 'Contact via work phone'),
('EMAIL', 'Email', 'Contact via email'),
('SMS', 'SMS', 'Contact via SMS')
ON CONFLICT (code) DO NOTHING;

-- Sample Fee Schedules (if offices exist)
DO $$
DECLARE
    office_record RECORD;
BEGIN
    FOR office_record IN SELECT id FROM public.offices LIMIT 5
    LOOP
        INSERT INTO tenant_1.fee_schedules (fee_schedule_id, fee_schedule_name, description, office_id) VALUES
        ('FS-' || office_record.id || '-001', 'Standard Fee Schedule', 'Standard fee schedule for office', office_record.id),
        ('FS-' || office_record.id || '-002', 'PPO Fee Schedule', 'PPO fee schedule', office_record.id),
        ('FS-' || office_record.id || '-003', 'HMO Fee Schedule', 'HMO fee schedule', office_record.id)
        ON CONFLICT (fee_schedule_id) DO NOTHING;
    END LOOP;
END $$;

-- ==================================================
-- 16. ADD FOREIGN KEY CONSTRAINTS
-- ==================================================

-- Add foreign key for home_office_id if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'patients_home_office_id_fkey' 
        AND table_schema = 'tenant_1'
    ) THEN
        ALTER TABLE tenant_1.patients
        ADD CONSTRAINT patients_home_office_id_fkey 
        FOREIGN KEY (home_office_id) REFERENCES public.offices(id);
    END IF;
END $$;

-- ==================================================
-- 17. CREATE VIEWS FOR COMMON QUERIES
-- ==================================================

-- View for patient search with all related data
CREATE OR REPLACE VIEW tenant_1.v_patient_search AS
SELECT 
    p.id,
    p.chart_no,
    p.first_name,
    p.last_name,
    p.preferred_name,
    p.dob,
    p.gender,
    p.patient_type,
    p.is_active,
    p.home_office_id,
    o.office_name as home_office_name,
    COALESCE(pci.home_phone, pci.cell_phone, pci.work_phone, p.phone) as phone,
    COALESCE(pci.email, p.email) as email,
    p.created_at,
    p.updated_at
FROM tenant_1.patients p
LEFT JOIN public.offices o ON p.home_office_id = o.id
LEFT JOIN tenant_1.patient_contact_info pci ON p.id = pci.patient_id
WHERE p.is_active = TRUE;

-- ==================================================
-- 18. CREATE METADATA REFERENCE TABLES
-- ==================================================

-- Titles reference table
CREATE TABLE IF NOT EXISTS tenant_1.titles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Pronouns reference table
CREATE TABLE IF NOT EXISTS tenant_1.pronouns (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- US States reference table
CREATE TABLE IF NOT EXISTS tenant_1.states (
    id SERIAL PRIMARY KEY,
    code VARCHAR(2) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Marital statuses reference table
CREATE TABLE IF NOT EXISTS tenant_1.marital_statuses (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Genders reference table
CREATE TABLE IF NOT EXISTS tenant_1.genders (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==================================================
-- 19. INSERT SEED DATA FOR METADATA TABLES
-- ==================================================

-- Insert titles
INSERT INTO tenant_1.titles (code, name, description, display_order) VALUES
('MR', 'Mr.', 'Mister', 1),
('MRS', 'Mrs.', 'Missus', 2),
('MS', 'Ms.', 'Miss', 3),
('DR', 'Dr.', 'Doctor', 4),
('PROF', 'Prof.', 'Professor', 5),
('REV', 'Rev.', 'Reverend', 6)
ON CONFLICT (code) DO NOTHING;

-- Insert pronouns
INSERT INTO tenant_1.pronouns (code, name, description, display_order) VALUES
('HE_HIM', 'He/Him', 'He/Him pronouns', 1),
('SHE_HER', 'She/Her', 'She/Her pronouns', 2),
('THEY_THEM', 'They/Them', 'They/Them pronouns', 3),
('SHE_THEY', 'She/They', 'She/They pronouns', 4),
('HE_THEY', 'He/They', 'He/They pronouns', 5),
('ANY', 'Any pronouns', 'Any pronouns', 6),
('PREFER_NOT', 'Prefer not to say', 'Prefer not to say', 7)
ON CONFLICT (code) DO NOTHING;

-- Insert US States
INSERT INTO tenant_1.states (code, name, display_order) VALUES
('AL', 'Alabama', 1),
('AK', 'Alaska', 2),
('AZ', 'Arizona', 3),
('AR', 'Arkansas', 4),
('CA', 'California', 5),
('CO', 'Colorado', 6),
('CT', 'Connecticut', 7),
('DE', 'Delaware', 8),
('FL', 'Florida', 9),
('GA', 'Georgia', 10),
('HI', 'Hawaii', 11),
('ID', 'Idaho', 12),
('IL', 'Illinois', 13),
('IN', 'Indiana', 14),
('IA', 'Iowa', 15),
('KS', 'Kansas', 16),
('KY', 'Kentucky', 17),
('LA', 'Louisiana', 18),
('ME', 'Maine', 19),
('MD', 'Maryland', 20),
('MA', 'Massachusetts', 21),
('MI', 'Michigan', 22),
('MN', 'Minnesota', 23),
('MS', 'Mississippi', 24),
('MO', 'Missouri', 25),
('MT', 'Montana', 26),
('NE', 'Nebraska', 27),
('NV', 'Nevada', 28),
('NH', 'New Hampshire', 29),
('NJ', 'New Jersey', 30),
('NM', 'New Mexico', 31),
('NY', 'New York', 32),
('NC', 'North Carolina', 33),
('ND', 'North Dakota', 34),
('OH', 'Ohio', 35),
('OK', 'Oklahoma', 36),
('OR', 'Oregon', 37),
('PA', 'Pennsylvania', 38),
('RI', 'Rhode Island', 39),
('SC', 'South Carolina', 40),
('SD', 'South Dakota', 41),
('TN', 'Tennessee', 42),
('TX', 'Texas', 43),
('UT', 'Utah', 44),
('VT', 'Vermont', 45),
('VA', 'Virginia', 46),
('WA', 'Washington', 47),
('WV', 'West Virginia', 48),
('WI', 'Wisconsin', 49),
('WY', 'Wyoming', 50),
('DC', 'District of Columbia', 51),
('PR', 'Puerto Rico', 52),
('VI', 'U.S. Virgin Islands', 53),
('AS', 'American Samoa', 54),
('GU', 'Guam', 55),
('MP', 'Northern Mariana Islands', 56)
ON CONFLICT (code) DO NOTHING;

-- Insert marital statuses
INSERT INTO tenant_1.marital_statuses (code, name, description, display_order) VALUES
('SINGLE', 'Single', 'Single marital status', 1),
('MARRIED', 'Married', 'Married marital status', 2),
('WIDOWED', 'Widowed', 'Widowed marital status', 3),
('DIVORCED', 'Divorced', 'Divorced marital status', 4),
('SEPARATED', 'Separated', 'Separated marital status', 5),
('DOMESTIC_PARTNERSHIP', 'Domestic Partnership', 'Domestic Partnership', 6),
('CIVIL_UNION', 'Civil Union', 'Civil Union', 7)
ON CONFLICT (code) DO NOTHING;

-- Insert genders
INSERT INTO tenant_1.genders (code, name, description, display_order) VALUES
('M', 'Male', 'Male gender', 1),
('F', 'Female', 'Female gender', 2),
('O', 'Not Specified / Unknown', 'Not Specified / Unknown', 3),
('NB', 'Non-Binary', 'Non-Binary', 4),
('PREFER_NOT', 'Prefer not to say', 'Prefer not to say', 5)
ON CONFLICT (code) DO NOTHING;

-- ==================================================
-- 20. UPDATE EXISTING METADATA TABLES SEED DATA
-- ==================================================

-- Update responsible_party_relationships with NONE option
INSERT INTO tenant_1.responsible_party_relationships (code, name, description, is_active) VALUES
('NONE', 'None', 'No responsible party', TRUE)
ON CONFLICT (code) DO UPDATE SET is_active = TRUE;

-- Update contact_preferences to match API contract
UPDATE tenant_1.contact_preferences SET code = 'NO_PREFERENCE', name = 'No Preference' WHERE code = 'NO_PREFERENCE' OR name = 'No Preference';
INSERT INTO tenant_1.contact_preferences (code, name, is_active) VALUES
('NO_PREFERENCE', 'No Preference', TRUE),
('CALL_CELL', 'Call my Cell', TRUE),
('CALL_HOME', 'Call my Home', TRUE),
('CALL_WORK', 'Call my Work', TRUE),
('TEXT_CELL', 'Text my Cell', TRUE),
('EMAIL', 'Email me', TRUE)
ON CONFLICT (code) DO UPDATE SET is_active = TRUE;

-- Update patient_types to match API contract
INSERT INTO tenant_1.patient_types (code, name, description, is_active) VALUES
('CH', 'Child', 'Child patient', TRUE),
('CP', 'Collection Problem', 'Collection Problem, See Notes', TRUE),
('EF', 'Employee & Family', 'Employee & Family', TRUE),
('OR', 'Ortho Patient', 'Orthodontic patient', TRUE),
('SN', 'Short Notice Appointment', 'Short Notice Appointment', TRUE),
('SR', 'Senior Citizen', 'Senior Citizen', TRUE),
('SS', 'Spanish Speaking', 'Spanish Speaking', TRUE),
('UP', 'Update Information', 'Update Information', TRUE)
ON CONFLICT (code) DO UPDATE SET is_active = TRUE;

-- ==================================================
-- MIGRATION COMPLETE
-- ==================================================
