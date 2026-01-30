-- ==================================================
-- Performance Optimization Indexes
-- ==================================================
-- These indexes are designed to optimize common query patterns
-- Run this script after the main migration script
-- ==================================================

-- Composite indexes for common search patterns
CREATE INDEX IF NOT EXISTS idx_patients_name_search 
ON tenant_1.patients(last_name, first_name) 
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_patients_office_active 
ON tenant_1.patients(home_office_id, is_active) 
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_patients_type_ortho 
ON tenant_1.patients(patient_type, is_ortho, is_active);

-- Index for chart number searches (already exists but ensure it's there)
CREATE INDEX IF NOT EXISTS idx_patients_chart_no_active 
ON tenant_1.patients(chart_no) 
WHERE chart_no IS NOT NULL;

-- Index for date of birth searches
CREATE INDEX IF NOT EXISTS idx_patients_dob_active 
ON tenant_1.patients(dob, is_active) 
WHERE dob IS NOT NULL;

-- Index for email searches
CREATE INDEX IF NOT EXISTS idx_patients_email_lower 
ON tenant_1.patients(LOWER(email)) 
WHERE email IS NOT NULL;

-- Index for phone number searches (normalized)
-- Note: This requires a function-based index or computed column
-- For PostgreSQL, we can use a functional index
CREATE INDEX IF NOT EXISTS idx_patients_phone_normalized 
ON tenant_1.patients(REGEXP_REPLACE(phone, '[^0-9]', '', 'g')) 
WHERE phone IS NOT NULL;

-- Indexes for patient contact info
CREATE INDEX IF NOT EXISTS idx_patient_contact_info_phones 
ON tenant_1.patient_contact_info(patient_id, home_phone, cell_phone, work_phone);

CREATE INDEX IF NOT EXISTS idx_patient_contact_info_email 
ON tenant_1.patient_contact_info(LOWER(email)) 
WHERE email IS NOT NULL;

-- Index for responsible party searches
CREATE INDEX IF NOT EXISTS idx_responsible_party_patient 
ON tenant_1.responsible_parties(patient_id, responsible_party_id);

CREATE INDEX IF NOT EXISTS idx_responsible_party_name 
ON tenant_1.responsible_parties(LOWER(name));

-- Index for insurance searches
CREATE INDEX IF NOT EXISTS idx_patient_insurance_subscriber 
ON tenant_1.patient_insurance(patient_id, subscriber_id, insurance_type);

CREATE INDEX IF NOT EXISTS idx_patient_insurance_active 
ON tenant_1.patient_insurance(patient_id, is_active) 
WHERE is_active = TRUE;

-- Index for patient addresses
CREATE INDEX IF NOT EXISTS idx_patient_addresses_patient_type 
ON tenant_1.patient_addresses(patient_id, address_type, is_primary);

-- Index for patient balances (for financial queries)
CREATE INDEX IF NOT EXISTS idx_patient_balances_account 
ON tenant_1.patient_balances(patient_id, account_balance);

-- Index for clinical info (for visit tracking)
CREATE INDEX IF NOT EXISTS idx_patient_clinical_info_visits 
ON tenant_1.patient_clinical_info(patient_id, last_visit, next_visit);

-- Index for medical alerts
CREATE INDEX IF NOT EXISTS idx_patient_medical_alerts_patient 
ON tenant_1.patient_medical_alerts(patient_id, created_at DESC);

-- Index for account members (for family account queries)
CREATE INDEX IF NOT EXISTS idx_patient_account_members_account 
ON tenant_1.patient_account_members(account_patient_id, member_patient_id);

-- Index for scheduler appointments (if in same schema)
-- CREATE INDEX IF NOT EXISTS idx_scheduler_appointments_patient_date 
-- ON tenant_1.scheduler_appointments(patient_id, date DESC, start_time DESC);

-- Analyze tables to update statistics
ANALYZE tenant_1.patients;
ANALYZE tenant_1.patient_addresses;
ANALYZE tenant_1.patient_contact_info;
ANALYZE tenant_1.responsible_parties;
ANALYZE tenant_1.patient_insurance;
ANALYZE tenant_1.patient_balances;
ANALYZE tenant_1.patient_clinical_info;
ANALYZE tenant_1.patient_medical_alerts;
ANALYZE tenant_1.patient_account_members;

-- ==================================================
-- Query Performance Tips
-- ==================================================
-- 1. Use EXPLAIN ANALYZE to check query plans
-- 2. Monitor slow queries with pg_stat_statements
-- 3. Regularly VACUUM ANALYZE tables
-- 4. Consider partitioning for large tables
-- 5. Use connection pooling (configured in database.py)
-- ==================================================
