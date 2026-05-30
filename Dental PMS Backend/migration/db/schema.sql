-- ============================================================
--  DENTAL PMS — PostgreSQL Schema
--  Generated from schema_complete.dbml
--  Run via: python run_schema.py
--
--  This script is idempotent: safe to re-run.
--  Tables are created only if they do not exist.
--  Run run_schema.py --drop to wipe and recreate everything.
-- ============================================================

-- ============================================================
-- DOMAIN 1 — CORE INFRASTRUCTURE
-- ============================================================

CREATE TABLE IF NOT EXISTS tenants (
    id          SERIAL PRIMARY KEY,
    legacy_id   VARCHAR(20)  UNIQUE,
    name        VARCHAR(255) NOT NULL,
    code        VARCHAR(80)  UNIQUE NOT NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    tenant_id            INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id            VARCHAR(50),
    email                VARCHAR(255) UNIQUE NOT NULL,
    username             VARCHAR(50)  UNIQUE NOT NULL,
    password_hash        TEXT         NOT NULL,
    first_name           VARCHAR(100),
    last_name            VARCHAR(100),
    phone                VARCHAR(20),
    role                 VARCHAR(50)  NOT NULL DEFAULT 'staff',
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN      NOT NULL DEFAULT FALSE,
    last_login_at        TIMESTAMP,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP,
    created_by           INTEGER      REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_tenant    ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_legacy    ON users(legacy_id);
CREATE INDEX IF NOT EXISTS idx_users_email     ON users(email);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER      NOT NULL REFERENCES users(id),
    token_hash  VARCHAR(255) NOT NULL,
    expires_at  TIMESTAMP    NOT NULL,
    revoked     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rtoken_user ON refresh_tokens(user_id);

CREATE TABLE IF NOT EXISTS offices (
    id                     SERIAL PRIMARY KEY,
    tenant_id              INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id              VARCHAR(20)  UNIQUE,
    office_code            VARCHAR(20)  UNIQUE NOT NULL,
    name                   VARCHAR(255) NOT NULL,
    short_id               VARCHAR(20),
    address_line1          VARCHAR(255),
    address_line2          VARCHAR(255),
    city                   VARCHAR(100),
    state                  VARCHAR(50),
    zip                    VARCHAR(20),
    phone                  VARCHAR(20),
    fax                    VARCHAR(20),
    email                  VARCHAR(255),
    timezone               VARCHAR(50)  NOT NULL DEFAULT 'America/New_York',
    slot_interval_minutes  INTEGER      NOT NULL DEFAULT 10,
    schedule_start_hour    INTEGER      NOT NULL DEFAULT 8,
    schedule_end_hour      INTEGER      NOT NULL DEFAULT 17,
    is_active              BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMP,
    created_by             INTEGER      REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_offices_tenant ON offices(tenant_id);

CREATE TABLE IF NOT EXISTS providers (
    id          VARCHAR(50)  PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    office_id   INTEGER      NOT NULL REFERENCES offices(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(255) NOT NULL,
    title       VARCHAR(20),
    short_id    VARCHAR(20),
    role        VARCHAR(50)  NOT NULL DEFAULT 'dentist',
    npi         VARCHAR(50),
    license     VARCHAR(100),
    tax_id      VARCHAR(50),
    dea_id      VARCHAR(50),
    specialty   VARCHAR(100),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_providers_office  ON providers(office_id);
CREATE INDEX IF NOT EXISTS idx_providers_legacy  ON providers(legacy_id);

CREATE TABLE IF NOT EXISTS operatories (
    id            VARCHAR(50)  PRIMARY KEY,
    office_id     INTEGER      NOT NULL REFERENCES offices(id),
    legacy_id     VARCHAR(20),
    name          VARCHAR(100) NOT NULL,
    display_order INTEGER      NOT NULL DEFAULT 0,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operatories_office  ON operatories(office_id);
CREATE INDEX IF NOT EXISTS idx_operatories_legacy  ON operatories(legacy_id);

CREATE TABLE IF NOT EXISTS user_offices (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER   NOT NULL REFERENCES users(id),
    office_id   INTEGER   NOT NULL REFERENCES offices(id),
    is_primary  BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, office_id)
);


-- ============================================================
-- DOMAIN 2 — INSURANCE
-- ============================================================

CREATE TABLE IF NOT EXISTS employers (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20)  UNIQUE,
    name        VARCHAR(255) NOT NULL,
    address     VARCHAR(255),
    city        VARCHAR(100),
    state       VARCHAR(50),
    zip         VARCHAR(20),
    phone       VARCHAR(20),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employers_legacy ON employers(legacy_id);

CREATE TABLE IF NOT EXISTS insurance_carriers (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20)  UNIQUE,
    name        VARCHAR(255) NOT NULL,
    payer_id    VARCHAR(50),
    phone       VARCHAR(20),
    phone2      VARCHAR(20),
    address     VARCHAR(255),
    city        VARCHAR(100),
    state       VARCHAR(50),
    zip         VARCHAR(20),
    website     VARCHAR(255),
    notes       TEXT,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_carriers_legacy ON insurance_carriers(legacy_id);

CREATE TABLE IF NOT EXISTS insurance_plans (
    id                    SERIAL PRIMARY KEY,
    tenant_id             INTEGER      NOT NULL REFERENCES tenants(id),
    carrier_id            INTEGER      NOT NULL REFERENCES insurance_carriers(id),
    employer_id           INTEGER      REFERENCES employers(id),
    legacy_id             VARCHAR(20)  UNIQUE,
    group_number          VARCHAR(100),
    plan_type             VARCHAR(50),
    is_prepaid            BOOLEAN      NOT NULL DEFAULT FALSE,
    individual_max        NUMERIC(10,2),
    individual_deductible NUMERIC(10,2),
    ortho_max             NUMERIC(10,2),
    family_max            NUMERIC(10,2),
    family_deductible     NUMERIC(10,2),
    anniversary_date      DATE,
    coverage_type         VARCHAR(10),
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ins_plans_carrier ON insurance_plans(carrier_id);
CREATE INDEX IF NOT EXISTS idx_ins_plans_legacy  ON insurance_plans(legacy_id);

CREATE TABLE IF NOT EXISTS insurance_subscribers (
    id                    SERIAL PRIMARY KEY,
    tenant_id             INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id             VARCHAR(20)  UNIQUE,
    ins_plan_id           INTEGER      NOT NULL REFERENCES insurance_plans(id),
    subscriber_patient_id INTEGER,    -- FK to patients added below (forward ref)
    office_id             INTEGER      REFERENCES offices(id),
    sub_first_name        VARCHAR(100),
    sub_last_name         VARCHAR(100),
    sub_mi                VARCHAR(10),
    sub_address           VARCHAR(255),
    sub_city              VARCHAR(100),
    sub_state             VARCHAR(50),
    sub_zip               VARCHAR(20),
    sub_dob               DATE,
    sub_gender            VARCHAR(10),
    sub_ssn               VARCHAR(20),
    sub_member_id         VARCHAR(100),
    group_number          VARCHAR(100),
    effective_date        DATE,
    term_date             DATE,
    family_max_remaining  NUMERIC(10,2),
    family_ded_remaining  NUMERIC(10,2),
    ortho_remaining       NUMERIC(10,2),
    anniversary_date      DATE,
    elig_status           VARCHAR(20),
    elig_verified_on      TIMESTAMP,
    elig_verified_by      VARCHAR(100),
    elig_notes            TEXT,
    notes                 TEXT,
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ins_sub_plan   ON insurance_subscribers(ins_plan_id);
CREATE INDEX IF NOT EXISTS idx_ins_sub_legacy ON insurance_subscribers(legacy_id);

CREATE TABLE IF NOT EXISTS insurance_coverage_rules (
    id          SERIAL PRIMARY KEY,
    ins_plan_id INTEGER      NOT NULL REFERENCES insurance_plans(id),
    legacy_id   VARCHAR(20),
    start_code  VARCHAR(20)  NOT NULL,
    end_code    VARCHAR(20)  NOT NULL,
    category    VARCHAR(100),
    description VARCHAR(255),
    coverage_pct NUMERIC(5,2),
    ded_waived  BOOLEAN      NOT NULL DEFAULT FALSE,
    freq_limit  VARCHAR(50),
    age_limit   VARCHAR(50),
    wait_period VARCHAR(50),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cov_rules_plan ON insurance_coverage_rules(ins_plan_id);

CREATE TABLE IF NOT EXISTS fee_schedules (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20)  UNIQUE,
    name        VARCHAR(255) NOT NULL,
    fee_type    VARCHAR(50),
    ins_plan_id INTEGER      REFERENCES insurance_plans(id),
    office_id   INTEGER      REFERENCES offices(id),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fee_sched_legacy ON fee_schedules(legacy_id);


-- ============================================================
-- DOMAIN 4 — CLINICAL REFERENCE  (procedure_codes needed for fee_schedule_entries)
-- ============================================================

CREATE TABLE IF NOT EXISTS procedure_codes (
    code                     VARCHAR(20)  PRIMARY KEY,
    legacy_code              VARCHAR(20),
    description              VARCHAR(500) NOT NULL,
    category                 VARCHAR(100) NOT NULL,
    default_fee              NUMERIC(10,2) NOT NULL DEFAULT 0,
    default_duration_minutes INTEGER,
    requires_tooth           BOOLEAN      NOT NULL DEFAULT FALSE,
    requires_surface         BOOLEAN      NOT NULL DEFAULT FALSE,
    requires_quadrant        BOOLEAN      NOT NULL DEFAULT FALSE,
    requires_lab             BOOLEAN      NOT NULL DEFAULT FALSE,
    is_ortho                 BOOLEAN      NOT NULL DEFAULT FALSE,
    billing_order            VARCHAR(10),
    recall_interval          INTEGER,
    recall_unit              VARCHAR(10),
    is_active                BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at               TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proc_codes_category ON procedure_codes(category);

CREATE TABLE IF NOT EXISTS fee_schedule_entries (
    id              SERIAL PRIMARY KEY,
    fee_schedule_id INTEGER      NOT NULL REFERENCES fee_schedules(id),
    procedure_code  VARCHAR(20)  NOT NULL REFERENCES procedure_codes(code),
    patient_fee     NUMERIC(10,2),
    insurance_fee   NUMERIC(10,2),
    effective_date  DATE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (fee_schedule_id, procedure_code)
);

CREATE TABLE IF NOT EXISTS chart_materials (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(100) NOT NULL,
    pattern     VARCHAR(100),
    color       VARCHAR(50),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS note_macros (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(100) NOT NULL,
    content     TEXT         NOT NULL,
    category    VARCHAR(100),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  INTEGER      REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS code_bundles (
    id           SERIAL PRIMARY KEY,
    tenant_id    INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id    VARCHAR(20),
    name         VARCHAR(100) NOT NULL,
    display_code VARCHAR(50),
    description  VARCHAR(255),
    same_tooth   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by   INTEGER      REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS code_bundle_items (
    id             SERIAL PRIMARY KEY,
    bundle_id      INTEGER      NOT NULL REFERENCES code_bundles(id),
    legacy_id      VARCHAR(20),
    procedure_code VARCHAR(20)  NOT NULL REFERENCES procedure_codes(code),
    tooth          VARCHAR(10),
    sort_order     INTEGER      NOT NULL DEFAULT 1,
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bundle_items_bundle ON code_bundle_items(bundle_id);

CREATE TABLE IF NOT EXISTS prescription_library (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    drug_name   VARCHAR(255) NOT NULL,
    dispense    VARCHAR(255),
    sig         VARCHAR(500),
    refills     INTEGER      NOT NULL DEFAULT 0,
    is_as_written BOOLEAN    NOT NULL DEFAULT FALSE,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP
);


-- ============================================================
-- DOMAIN 3 — PATIENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS patients (
    id                   SERIAL PRIMARY KEY,
    tenant_id            INTEGER      NOT NULL REFERENCES tenants(id),
    home_office_id       INTEGER      REFERENCES offices(id),
    legacy_id            VARCHAR(20)  UNIQUE,
    chart_no             VARCHAR(50)  UNIQUE,
    first_name           VARCHAR(100),
    last_name            VARCHAR(100),
    preferred_name       VARCHAR(100),
    title                VARCHAR(20),
    middle_initial       VARCHAR(10),
    dob                  DATE,
    gender               VARCHAR(20),
    ssn                  VARCHAR(20),
    marital_status       VARCHAR(20),
    phone                VARCHAR(20),
    cell_phone           VARCHAR(20),
    work_phone           VARCHAR(20),
    email                VARCHAR(255),
    preferred_contact    VARCHAR(50),
    address_line1        VARCHAR(255),
    address_line2        VARCHAR(255),
    city                 VARCHAR(100),
    state                VARCHAR(50),
    zip                  VARCHAR(20),
    preferred_provider_id VARCHAR(50) REFERENCES providers(id),
    preferred_language   VARCHAR(50)  NOT NULL DEFAULT 'English',
    first_visit          DATE,
    last_visit           DATE,
    next_recall          DATE,
    is_finance_charge    BOOLEAN      NOT NULL DEFAULT FALSE,
    send_statements      BOOLEAN      NOT NULL DEFAULT TRUE,
    send_collections     BOOLEAN      NOT NULL DEFAULT FALSE,
    no_auto_email        BOOLEAN      NOT NULL DEFAULT FALSE,
    no_auto_sms          BOOLEAN      NOT NULL DEFAULT FALSE,
    is_locked            BOOLEAN      NOT NULL DEFAULT FALSE,
    hipaa_agreement      BOOLEAN      NOT NULL DEFAULT FALSE,
    guardian_name        VARCHAR(255),
    guardian_phone       VARCHAR(20),
    referral_type        VARCHAR(50),
    referred_by          VARCHAR(255),
    patient_notes        TEXT,
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP,
    created_by           INTEGER      REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_patients_legacy    ON patients(legacy_id);
CREATE INDEX IF NOT EXISTS idx_patients_tenant    ON patients(tenant_id);
CREATE INDEX IF NOT EXISTS idx_patients_office    ON patients(home_office_id);
CREATE INDEX IF NOT EXISTS idx_patients_name      ON patients(last_name, first_name);

-- Add forward-ref FK now that patients exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ins_sub_patient'
    ) THEN
        ALTER TABLE insurance_subscribers
            ADD CONSTRAINT fk_ins_sub_patient
            FOREIGN KEY (subscriber_patient_id) REFERENCES patients(id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS patient_insurance (
    id                   SERIAL PRIMARY KEY,
    patient_id           INTEGER      NOT NULL REFERENCES patients(id),
    ins_plan_id          INTEGER      REFERENCES insurance_plans(id),
    subscriber_id        INTEGER      REFERENCES insurance_subscribers(id),
    legacy_plan_type     VARCHAR(5),
    insurance_type       VARCHAR(20)  NOT NULL,
    relationship         VARCHAR(50),
    deductible_remaining NUMERIC(10,2),
    max_remaining        NUMERIC(10,2),
    ortho_remaining      NUMERIC(10,2),
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP,
    UNIQUE (patient_id, insurance_type)
);

CREATE INDEX IF NOT EXISTS idx_pat_ins_patient ON patient_insurance(patient_id);

CREATE TABLE IF NOT EXISTS patient_alerts (
    id             SERIAL PRIMARY KEY,
    patient_id     INTEGER   NOT NULL REFERENCES patients(id),
    legacy_id      VARCHAR(20),
    alert          TEXT      NOT NULL,
    blocks_charges BOOLEAN   NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN   NOT NULL DEFAULT TRUE,
    deactivated_on TIMESTAMP,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by     INTEGER   REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_patient ON patient_alerts(patient_id);

CREATE TABLE IF NOT EXISTS account_notes (
    id           SERIAL PRIMARY KEY,
    patient_id   INTEGER   NOT NULL REFERENCES patients(id),
    legacy_id    VARCHAR(20),
    note_type    VARCHAR(10),
    notes        TEXT      NOT NULL,
    is_struck_off BOOLEAN  NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by   INTEGER   REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_acct_notes_patient ON account_notes(patient_id);

CREATE TABLE IF NOT EXISTS patient_signatures (
    id             SERIAL PRIMARY KEY,
    patient_id     INTEGER   NOT NULL REFERENCES patients(id),
    legacy_id      VARCHAR(20),
    signature_data TEXT,
    signature_len  INTEGER,
    device_source  VARCHAR(20),
    is_user_sig    BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by     INTEGER   REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_sigs_patient ON patient_signatures(patient_id);

CREATE TABLE IF NOT EXISTS medical_history_records (
    id           SERIAL PRIMARY KEY,
    patient_id   INTEGER   NOT NULL REFERENCES patients(id),
    legacy_id    VARCHAR(20),
    signature_id INTEGER   REFERENCES patient_signatures(id),
    is_archived  BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by   INTEGER   REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS referrals (
    id            SERIAL PRIMARY KEY,
    tenant_id     INTEGER      NOT NULL REFERENCES tenants(id),
    office_id     INTEGER      REFERENCES offices(id),
    legacy_id     VARCHAR(20),
    referral_type VARCHAR(10),
    patient_id    INTEGER      REFERENCES patients(id),
    first_name    VARCHAR(100),
    last_name     VARCHAR(100),
    address       VARCHAR(255),
    city          VARCHAR(100),
    state         VARCHAR(50),
    zip           VARCHAR(20),
    phone         VARCHAR(20),
    email         VARCHAR(255),
    npi           VARCHAR(50),
    specialty     VARCHAR(100),
    reason_code   VARCHAR(20),
    notes         TEXT,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by    INTEGER      REFERENCES users(id)
);


-- ============================================================
-- DOMAIN 6 — CLINICAL RECORDS (treatment_plans needed before appointments)
-- ============================================================

CREATE TABLE IF NOT EXISTS treatment_plans (
    id          VARCHAR(50)  PRIMARY KEY,
    patient_id  INTEGER      NOT NULL REFERENCES patients(id),
    office_id   INTEGER      REFERENCES offices(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(200) NOT NULL,
    status      VARCHAR(20)  NOT NULL DEFAULT 'Active',
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP,
    created_by  INTEGER      REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_txplan_patient ON treatment_plans(patient_id);
CREATE INDEX IF NOT EXISTS idx_txplan_legacy  ON treatment_plans(legacy_id);

CREATE TABLE IF NOT EXISTS treatment_plan_items (
    id                 VARCHAR(50)  PRIMARY KEY,
    plan_id            VARCHAR(50)  NOT NULL REFERENCES treatment_plans(id),
    procedure_code     VARCHAR(20)  NOT NULL REFERENCES procedure_codes(code),
    description        VARCHAR(500),
    tooth              VARCHAR(10),
    surface            VARCHAR(50),
    priority           INTEGER      NOT NULL DEFAULT 1,
    fee                NUMERIC(10,2) NOT NULL,
    insurance_estimate NUMERIC(10,2) NOT NULL DEFAULT 0,
    billing_order      VARCHAR(10),
    status             VARCHAR(20)  NOT NULL DEFAULT 'Planned',
    diagnosed_by       VARCHAR(200),
    created_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_txitem_plan ON treatment_plan_items(plan_id);


-- ============================================================
-- DOMAIN 5 — SCHEDULING
-- ============================================================

CREATE TABLE IF NOT EXISTS appointments (
    id                VARCHAR(50) PRIMARY KEY,  -- nanoid from app layer
    patient_id        INTEGER     REFERENCES patients(id),  -- NULL for blocked slots
    provider_id       VARCHAR(50) NOT NULL REFERENCES providers(id),
    operatory_id      VARCHAR(50) REFERENCES operatories(id),
    office_id         INTEGER     NOT NULL REFERENCES offices(id),
    legacy_id         VARCHAR(20),
    is_archived       BOOLEAN     NOT NULL DEFAULT FALSE,
    date              DATE        NOT NULL,
    start_time        TIME        NOT NULL,
    end_time          TIME        NOT NULL,
    duration          INTEGER     NOT NULL,
    status            VARCHAR(30) NOT NULL DEFAULT 'Scheduled',
    is_missed         BOOLEAN     NOT NULL DEFAULT FALSE,
    is_cancelled      BOOLEAN     NOT NULL DEFAULT FALSE,
    is_posted         BOOLEAN     NOT NULL DEFAULT FALSE,
    procedure_label   VARCHAR(200),
    is_new_patient    BOOLEAN     NOT NULL DEFAULT FALSE,
    notes             TEXT,
    has_lab           BOOLEAN     NOT NULL DEFAULT FALSE,
    lab_cost          NUMERIC(10,2),
    lab_sent_on       DATE,
    lab_due_on        DATE,
    lab_received_on   DATE,
    is_blocked        BOOLEAN     NOT NULL DEFAULT FALSE,
    campaign_id       VARCHAR(100),
    treatment_plan_id VARCHAR(50) REFERENCES treatment_plans(id),
    confirmed_on      TIMESTAMP,
    checked_in_on     TIMESTAMP,
    checked_out_on    TIMESTAMP,
    created_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_appt_legacy           ON appointments(legacy_id);
CREATE INDEX IF NOT EXISTS idx_appt_date_office      ON appointments(date, office_id);
CREATE INDEX IF NOT EXISTS idx_appt_patient_date     ON appointments(patient_id, date);
CREATE INDEX IF NOT EXISTS idx_appt_provider_date    ON appointments(provider_id, date);
CREATE INDEX IF NOT EXISTS idx_appt_operatory_date   ON appointments(operatory_id, date);
CREATE INDEX IF NOT EXISTS idx_appt_status           ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appt_archived         ON appointments(is_archived);

CREATE TABLE IF NOT EXISTS appointment_procedures (
    id                 SERIAL PRIMARY KEY,
    appointment_id     VARCHAR(50)  NOT NULL REFERENCES appointments(id),
    procedure_code     VARCHAR(20)  NOT NULL REFERENCES procedure_codes(code),
    provider_id        VARCHAR(50)  REFERENCES providers(id),
    treatment_plan_id  VARCHAR(50)  REFERENCES treatment_plans(id),
    tooth              VARCHAR(10),
    surface            VARCHAR(20),
    description        VARCHAR(500),
    fee                NUMERIC(12,2) NOT NULL DEFAULT 0,
    insurance_estimate NUMERIC(12,2) NOT NULL DEFAULT 0,
    billing_order      VARCHAR(10),
    status             VARCHAR(20)  NOT NULL DEFAULT 'Planned',
    material_id        INTEGER      REFERENCES chart_materials(id),
    notes              TEXT,
    is_archived        BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_appt_proc_appt ON appointment_procedures(appointment_id);


-- ============================================================
-- DOMAIN 6 (cont.) — CLINICAL RECORDS
-- ============================================================

CREATE TABLE IF NOT EXISTS patient_procedures (
    id                VARCHAR(50)   PRIMARY KEY,
    patient_id        INTEGER       NOT NULL REFERENCES patients(id),
    appointment_id    VARCHAR(50)   REFERENCES appointments(id),
    procedure_code    VARCHAR(20)   NOT NULL REFERENCES procedure_codes(code),
    legacy_id         VARCHAR(20),
    is_archived       BOOLEAN       NOT NULL DEFAULT FALSE,
    date_of_service   DATE          NOT NULL,
    provider_id       VARCHAR(50)   NOT NULL REFERENCES providers(id),
    office_id         INTEGER       NOT NULL REFERENCES offices(id),
    tooth             VARCHAR(10),
    surface           VARCHAR(20),
    quadrant          VARCHAR(10),
    fee               NUMERIC(12,2) NOT NULL,
    ucr_fee           NUMERIC(12,2),
    insurance_estimate NUMERIC(12,2) NOT NULL DEFAULT 0,
    patient_estimate  NUMERIC(12,2) NOT NULL DEFAULT 0,
    apply_to          VARCHAR(5),
    billing_order     VARCHAR(10),
    resp_type         VARCHAR(10),
    billing_status    VARCHAR(30)   NOT NULL DEFAULT 'not_billed',
    claim_id          VARCHAR(50),  -- FK added after insurance_claims
    hold_claim        BOOLEAN       NOT NULL DEFAULT FALSE,
    is_void           BOOLEAN       NOT NULL DEFAULT FALSE,
    material_id       INTEGER       REFERENCES chart_materials(id),
    notes             TEXT,
    created_at        TIMESTAMP     NOT NULL DEFAULT NOW(),
    created_by        INTEGER       REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_proc_legacy          ON patient_procedures(legacy_id);
CREATE INDEX IF NOT EXISTS idx_proc_patient_dos     ON patient_procedures(patient_id, date_of_service);
CREATE INDEX IF NOT EXISTS idx_proc_void            ON patient_procedures(is_void);

CREATE TABLE IF NOT EXISTS chart_conditions (
    id             SERIAL PRIMARY KEY,
    patient_id     INTEGER      NOT NULL REFERENCES patients(id),
    office_id      INTEGER      REFERENCES offices(id),
    legacy_id      VARCHAR(20),
    activity_date  DATE,
    tooth          VARCHAR(10),
    surface        VARCHAR(20),
    region         VARCHAR(20),
    area           VARCHAR(20),
    description    VARCHAR(500),
    condition_code VARCHAR(50),
    procedure_code VARCHAR(20)  REFERENCES procedure_codes(code),
    provider_id    VARCHAR(50)  REFERENCES providers(id),
    material_id    INTEGER      REFERENCES chart_materials(id),
    chart_as       VARCHAR(20),
    is_inactive    BOOLEAN      NOT NULL DEFAULT FALSE,
    notes          TEXT,
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chart_cond_patient_tooth ON chart_conditions(patient_id, tooth);

CREATE TABLE IF NOT EXISTS progress_notes (
    id          SERIAL PRIMARY KEY,
    patient_id  INTEGER   NOT NULL REFERENCES patients(id),
    office_id   INTEGER   REFERENCES offices(id),
    legacy_id   VARCHAR(20),
    note_date   DATE,
    notes       TEXT,
    notes_html  TEXT,
    tooth       VARCHAR(255),
    is_deleted  BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by  INTEGER   REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_pnote_patient_date ON progress_notes(patient_id, note_date);

CREATE TABLE IF NOT EXISTS perio_exams (
    id          SERIAL PRIMARY KEY,
    patient_id  INTEGER   NOT NULL REFERENCES patients(id),
    office_id   INTEGER   REFERENCES offices(id),
    legacy_id   VARCHAR(20),
    exam_date   DATE      NOT NULL,
    notes       TEXT,
    is_voided   BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by  INTEGER   REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_perio_patient_date ON perio_exams(patient_id, exam_date);

CREATE TABLE IF NOT EXISTS perio_exam_details (
    id              SERIAL PRIMARY KEY,
    exam_id         INTEGER   NOT NULL REFERENCES perio_exams(id),
    tooth_no        VARCHAR(10) NOT NULL,
    pd1 INTEGER, pd2 INTEGER, pd3 INTEGER, pd4 INTEGER, pd5 INTEGER, pd6 INTEGER,
    fgm1 INTEGER, fgm2 INTEGER, fgm3 INTEGER, fgm4 INTEGER, fgm5 INTEGER, fgm6 INTEGER,
    mgj1 INTEGER, mgj2 INTEGER, mgj3 INTEGER, mgj4 INTEGER, mgj5 INTEGER, mgj6 INTEGER,
    bleed1 BOOLEAN, bleed2 BOOLEAN, bleed3 BOOLEAN,
    bleed4 BOOLEAN, bleed5 BOOLEAN, bleed6 BOOLEAN,
    supp1 BOOLEAN, supp2 BOOLEAN, supp3 BOOLEAN,
    supp4 BOOLEAN, supp5 BOOLEAN, supp6 BOOLEAN,
    furc1 INTEGER, furc2 INTEGER, furc3 INTEGER,
    furc4 INTEGER, furc5 INTEGER, furc6 INTEGER,
    mobility_buccal  INTEGER,
    mobility_lingual INTEGER
);

CREATE INDEX IF NOT EXISTS idx_perio_detail_exam ON perio_exam_details(exam_id);

CREATE TABLE IF NOT EXISTS prescriptions (
    id              SERIAL PRIMARY KEY,
    patient_id      INTEGER      NOT NULL REFERENCES patients(id),
    office_id       INTEGER      REFERENCES offices(id),
    legacy_id       VARCHAR(20),
    library_rx_id   INTEGER      REFERENCES prescription_library(id),
    rx_date         DATE,
    drug_name       VARCHAR(255) NOT NULL,
    dispense        VARCHAR(255),
    sig             VARCHAR(500),
    refills         INTEGER      NOT NULL DEFAULT 0,
    is_as_written   BOOLEAN      NOT NULL DEFAULT FALSE,
    provider_id     VARCHAR(50)  REFERENCES providers(id),
    notes           TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    dosespot_rx_id  VARCHAR(50),
    dosespot_status VARCHAR(50),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      INTEGER      REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_rx_patient_date ON prescriptions(patient_id, rx_date);


-- ============================================================
-- DOMAIN 7 — BILLING
-- ============================================================

CREATE TABLE IF NOT EXISTS patient_payments (
    id             VARCHAR(50)   PRIMARY KEY,
    patient_id     INTEGER       NOT NULL REFERENCES patients(id),
    office_id      INTEGER       REFERENCES offices(id),
    legacy_id      VARCHAR(20),
    is_archived    BOOLEAN       NOT NULL DEFAULT FALSE,
    payment_date   DATE          NOT NULL,
    amount         NUMERIC(12,2) NOT NULL,
    payment_type   VARCHAR(20)   NOT NULL,
    payment_method VARCHAR(50),
    check_number   VARCHAR(100),
    provider_id    VARCHAR(50)   REFERENCES providers(id),
    notes          TEXT,
    is_void        BOOLEAN       NOT NULL DEFAULT FALSE,
    created_by     INTEGER       REFERENCES users(id),
    created_at     TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_legacy           ON patient_payments(legacy_id);
CREATE INDEX IF NOT EXISTS idx_payment_patient_date     ON patient_payments(patient_id, payment_date);

CREATE TABLE IF NOT EXISTS insurance_claims (
    id                    VARCHAR(50)   PRIMARY KEY,
    patient_id            INTEGER       NOT NULL REFERENCES patients(id),
    office_id             INTEGER       REFERENCES offices(id),
    legacy_id             VARCHAR(20)   UNIQUE,
    claim_number          VARCHAR(50)   UNIQUE NOT NULL,
    status                VARCHAR(30)   NOT NULL DEFAULT 'draft',
    claim_type            VARCHAR(20)   NOT NULL DEFAULT 'primary',
    billing_order         VARCHAR(10),
    date_of_service_from  DATE,
    date_of_service_to    DATE,
    total_billed          NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_paid            NUMERIC(12,2) NOT NULL DEFAULT 0,
    est_insurance         NUMERIC(12,2) NOT NULL DEFAULT 0,
    submitted_date        DATE,
    paid_date             DATE,
    close_date            DATE,
    billing_provider_id   VARCHAR(50)   REFERENCES providers(id),
    treating_provider_id  VARCHAR(50)   REFERENCES providers(id),
    carrier_id            INTEGER       REFERENCES insurance_carriers(id),
    ins_plan_id           INTEGER       REFERENCES insurance_plans(id),
    is_preauth            BOOLEAN       NOT NULL DEFAULT FALSE,
    notes                 TEXT,
    is_active             BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMP     NOT NULL DEFAULT NOW(),
    created_by            INTEGER       REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_claim_legacy         ON insurance_claims(legacy_id);
CREATE INDEX IF NOT EXISTS idx_claim_patient_status ON insurance_claims(patient_id, status);

-- Now add the deferred FK on patient_procedures.claim_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_proc_claim'
    ) THEN
        ALTER TABLE patient_procedures
            ADD CONSTRAINT fk_proc_claim
            FOREIGN KEY (claim_id) REFERENCES insurance_claims(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_proc_claim ON patient_procedures(claim_id);

CREATE TABLE IF NOT EXISTS ledger_insurance_details (
    id               SERIAL PRIMARY KEY,
    patient_id       INTEGER       NOT NULL REFERENCES patients(id),
    procedure_id     VARCHAR(50)   REFERENCES patient_procedures(id),
    legacy_ledger_id VARCHAR(20),
    claim_id         VARCHAR(50)   REFERENCES insurance_claims(id),
    office_id        INTEGER       REFERENCES offices(id),
    prim_estimated   NUMERIC(12,2),
    prim_ind_max     NUMERIC(12,2),
    prim_deductible  NUMERIC(12,2),
    prim_ins_paid    NUMERIC(12,2),
    prim_ins_adjust  NUMERIC(12,2),
    sec_estimated    NUMERIC(12,2),
    sec_ins_paid     NUMERIC(12,2),
    sec_ins_adjust   NUMERIC(12,2),
    ter_ins_paid     NUMERIC(12,2),
    prim_ins_plan_id INTEGER       REFERENCES insurance_plans(id),
    sec_ins_plan_id  INTEGER       REFERENCES insurance_plans(id),
    ter_ins_plan_id  INTEGER       REFERENCES insurance_plans(id),
    prim_posted      BOOLEAN       NOT NULL DEFAULT FALSE,
    sec_posted       BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_ins_legacy ON ledger_insurance_details(legacy_ledger_id);
CREATE INDEX IF NOT EXISTS idx_ledger_ins_proc   ON ledger_insurance_details(procedure_id);

CREATE TABLE IF NOT EXISTS payment_allocations (
    id           SERIAL PRIMARY KEY,
    patient_id   INTEGER       NOT NULL REFERENCES patients(id),
    legacy_id    VARCHAR(20),
    procedure_id VARCHAR(50)   REFERENCES patient_procedures(id),
    payment_id   VARCHAR(50)   REFERENCES patient_payments(id),
    claim_id     VARCHAR(50)   REFERENCES insurance_claims(id),
    ins_plan_id  INTEGER       REFERENCES insurance_plans(id),
    provider_id  VARCHAR(50)   REFERENCES providers(id),
    alloc_date   DATE,
    amount       NUMERIC(12,2) NOT NULL,
    alloc_type   VARCHAR(5),
    created_at   TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alloc_patient ON payment_allocations(patient_id);
CREATE INDEX IF NOT EXISTS idx_alloc_payment ON payment_allocations(payment_id);
CREATE INDEX IF NOT EXISTS idx_alloc_proc    ON payment_allocations(procedure_id);

CREATE TABLE IF NOT EXISTS claim_submissions (
    id                SERIAL PRIMARY KEY,
    claim_id          VARCHAR(50)   NOT NULL REFERENCES insurance_claims(id),
    legacy_id         VARCHAR(20),
    batch_id          VARCHAR(50),
    is_preauth        BOOLEAN       NOT NULL DEFAULT FALSE,
    total_charges     NUMERIC(12,2),
    num_lines         INTEGER,
    submission_status VARCHAR(10),
    claim_text        TEXT,
    created_at        TIMESTAMP     NOT NULL DEFAULT NOW(),
    created_by        INTEGER       REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_claim_sub_claim ON claim_submissions(claim_id);


-- ============================================================
-- DOMAIN 8 — COMMUNICATION
-- ============================================================

CREATE TABLE IF NOT EXISTS sms_messages (
    id                SERIAL PRIMARY KEY,
    tenant_id         INTEGER   NOT NULL REFERENCES tenants(id),
    office_id         INTEGER   REFERENCES offices(id),
    patient_id        INTEGER   REFERENCES patients(id),
    appointment_id    VARCHAR(50) REFERENCES appointments(id),
    legacy_id         VARCHAR(20),
    sent_text         TEXT,
    sent_phone        VARCHAR(20),
    send_status       VARCHAR(50),
    delivered_on      TIMESTAMP,
    reply_text        TEXT,
    reply_phone       VARCHAR(20),
    reply_received_on TIMESTAMP,
    message_type      VARCHAR(50),
    is_read           BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by        INTEGER   REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_sms_patient ON sms_messages(patient_id, created_at);

CREATE TABLE IF NOT EXISTS letter_templates (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(255) NOT NULL,
    letter_type VARCHAR(10),
    channel     VARCHAR(20),
    title       VARCHAR(255),
    body_html   TEXT,
    is_editable BOOLEAN      NOT NULL DEFAULT TRUE,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS postcard_templates (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    office_id   INTEGER      REFERENCES offices(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(255) NOT NULL,
    card_type   VARCHAR(10),
    body        TEXT,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);


-- ============================================================
-- DOMAIN 9 — STAFF & OPERATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS time_clock_entries (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    office_id   INTEGER      REFERENCES offices(id),
    user_id     INTEGER      NOT NULL REFERENCES users(id),
    legacy_id   VARCHAR(20),
    clock_in    TIMESTAMP    NOT NULL,
    clock_out   TIMESTAMP,
    total_hours NUMERIC(5,2),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tclock_user_date ON time_clock_entries(user_id, clock_in);


-- ============================================================
-- DOMAIN 10 — CONFIG & REFERENCE DATA
-- ============================================================

CREATE TABLE IF NOT EXISTS definitions (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id      VARCHAR(20),
    group_code     VARCHAR(50)  NOT NULL,
    key1           VARCHAR(50)  NOT NULL,
    key2           VARCHAR(50),
    description    VARCHAR(255) NOT NULL,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    is_flash_alert BOOLEAN      NOT NULL DEFAULT FALSE,
    blocks_charges BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_def_group ON definitions(tenant_id, group_code);

CREATE TABLE IF NOT EXISTS imaging_templates (
    id            SERIAL PRIMARY KEY,
    office_id     INTEGER      NOT NULL REFERENCES offices(id),
    legacy_id     VARCHAR(20),
    name          VARCHAR(255) NOT NULL,
    template_type VARCHAR(20),
    dentition     VARCHAR(5),
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS perio_chart_settings (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER   NOT NULL UNIQUE REFERENCES users(id),
    is_forward   BOOLEAN   NOT NULL DEFAULT TRUE,
    is_indicator BOOLEAN   NOT NULL DEFAULT TRUE,
    is_mgj       BOOLEAN   NOT NULL DEFAULT TRUE,
    pd_level     INTEGER   NOT NULL DEFAULT 4,
    bp_level     INTEGER   NOT NULL DEFAULT 2,
    ip_level     INTEGER   NOT NULL DEFAULT 3,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questionnaire_headers (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id       VARCHAR(20),
    description     VARCHAR(255) NOT NULL,
    is_multi_select BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questionnaire_options (
    id               SERIAL PRIMARY KEY,
    questionnaire_id INTEGER      NOT NULL REFERENCES questionnaire_headers(id),
    legacy_id        VARCHAR(20),
    answer_code      VARCHAR(20)  NOT NULL,
    sort_order       INTEGER      NOT NULL DEFAULT 1,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_q_opts_q ON questionnaire_options(questionnaire_id);


-- ============================================================
-- DOMAIN 11 — ADDITIONS (all remaining source files)
-- Includes: tables with data, empty-but-schema-needed,
-- and logical entities for future migration/entry.
-- ============================================================

-- SOURCE: FeeScheA.txt — fee schedule assignments per plan/carrier/provider/office
CREATE TABLE IF NOT EXISTS fee_schedule_assignments (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id       VARCHAR(20),
    ins_plan_id     INTEGER      REFERENCES insurance_plans(id),
    carrier_id      INTEGER      REFERENCES insurance_carriers(id),
    provider_id     VARCHAR(50)  REFERENCES providers(id),
    office_id       INTEGER      REFERENCES offices(id),
    fee_schedule_id INTEGER      NOT NULL REFERENCES fee_schedules(id),
    specialty_id    VARCHAR(20),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_fee_assign_plan  ON fee_schedule_assignments(ins_plan_id);
CREATE INDEX IF NOT EXISTS idx_fee_assign_sched ON fee_schedule_assignments(fee_schedule_id);

-- SOURCE: InsCustCoverage.txt — per-tenant custom coverage overrides (empty, future)
CREATE TABLE IF NOT EXISTS ins_custom_coverage (
    id           SERIAL PRIMARY KEY,
    tenant_id    INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id    VARCHAR(20),
    start_code   VARCHAR(20)  NOT NULL,
    end_code     VARCHAR(20)  NOT NULL,
    description  VARCHAR(255),
    coverage_pct NUMERIC(5,2),
    ded_waived   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by   VARCHAR(100)
);

-- SOURCE: PROVIDERINSID.txt — provider IDs per carrier (empty, future)
CREATE TABLE IF NOT EXISTS provider_insurance_ids (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    provider_id VARCHAR(50)  NOT NULL REFERENCES providers(id),
    carrier_id  INTEGER      NOT NULL REFERENCES insurance_carriers(id),
    ins_id      VARCHAR(100),
    in_network  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_prov_ins_id_prov    ON provider_insurance_ids(provider_id);
CREATE INDEX IF NOT EXISTS idx_prov_ins_id_carrier ON provider_insurance_ids(carrier_id);

-- SOURCE: PatContractBilling.txt — patient in-house payment plans (empty, future)
CREATE TABLE IF NOT EXISTS patient_payment_plans (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id     INTEGER      NOT NULL REFERENCES patients(id),
    office_id      INTEGER      REFERENCES offices(id),
    legacy_id      VARCHAR(20),
    plan_bal_amt   NUMERIC(12,2),
    tx_plan_number VARCHAR(50),
    setup_date     DATE,
    amt_financed   NUMERIC(12,2),
    down_payment   NUMERIC(12,2),
    apr            NUMERIC(6,4),
    fin_charge     NUMERIC(12,2),
    interval_type  VARCHAR(20),
    num_payments   INTEGER,
    periodic_amt   NUMERIC(12,2),
    first_due_date DATE,
    rem_payments   INTEGER,
    rem_total_amt  NUMERIC(12,2),
    notes          TEXT,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by     VARCHAR(100),
    updated_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pat_payplan_patient ON patient_payment_plans(patient_id);

-- SOURCE: PatInsContractBilling.txt — insurance periodic billing schedule (empty, future)
CREATE TABLE IF NOT EXISTS patient_ins_payment_plans (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id     INTEGER      NOT NULL REFERENCES patients(id),
    legacy_plan_id VARCHAR(20),
    periodic_order INTEGER,
    periodic_date  DATE,
    periodic_amt   NUMERIC(12,2),
    is_billed      BOOLEAN      NOT NULL DEFAULT FALSE,
    billing_code   VARCHAR(50),
    ledger_id      VARCHAR(20),
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by     VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_pat_ins_payplan_patient ON patient_ins_payment_plans(patient_id);

-- SOURCE: PATSECINSCONTRACTBILLING.txt — secondary insurance billing schedule (empty, future)
CREATE TABLE IF NOT EXISTS patient_sec_ins_payment_plans (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id     INTEGER      NOT NULL REFERENCES patients(id),
    legacy_plan_id VARCHAR(20),
    periodic_order INTEGER,
    periodic_date  DATE,
    periodic_amt   NUMERIC(12,2),
    is_billed      BOOLEAN      NOT NULL DEFAULT FALSE,
    billing_code   VARCHAR(50),
    ledger_id      VARCHAR(20),
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by     VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_pat_sec_ins_payplan_patient ON patient_sec_ins_payment_plans(patient_id);

-- SOURCE: PatRegPlan.txt — patient regular/recall payment plan (empty, future)
CREATE TABLE IF NOT EXISTS patient_reg_plans (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id     INTEGER      NOT NULL REFERENCES patients(id),
    office_id      INTEGER      REFERENCES offices(id),
    legacy_id      VARCHAR(20),
    setup_date     DATE,
    amt_financed   NUMERIC(12,2),
    down_payment   NUMERIC(12,2),
    apr            NUMERIC(6,4),
    fin_charge     NUMERIC(12,2),
    interval_type  VARCHAR(20),
    num_payments   INTEGER,
    periodic_amt   NUMERIC(12,2),
    first_due_date DATE,
    rem_payments   INTEGER,
    rem_total_amt  NUMERIC(12,2),
    notes          TEXT,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by     VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_pat_regplan_patient ON patient_reg_plans(patient_id);

-- SOURCE: PATORTHOPLAN.txt — orthodontic treatment + payment plan (empty, future)
CREATE TABLE IF NOT EXISTS ortho_plans (
    id                   SERIAL PRIMARY KEY,
    tenant_id            INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id           INTEGER      NOT NULL REFERENCES patients(id),
    office_id            INTEGER      REFERENCES offices(id),
    legacy_id            VARCHAR(20),
    procedure_code       VARCHAR(20)  REFERENCES procedure_codes(code),
    description          VARCHAR(255),
    total_ortho_amt      NUMERIC(12,2),
    ins_share_amt        NUMERIC(12,2),
    pat_share_amt        NUMERIC(12,2),
    treat_start_date     DATE,
    treat_end_date       DATE,
    banding_date         DATE,
    ins_plan_id          INTEGER      REFERENCES insurance_plans(id),
    ins_setup_date       DATE,
    ins_plan_amount      NUMERIC(12,2),
    ins_down_pay         NUMERIC(12,2),
    ins_interval         VARCHAR(20),
    ins_num_payments     INTEGER,
    ins_periodic_amt     NUMERIC(12,2),
    ins_rem_payments     INTEGER,
    ins_rem_amt          NUMERIC(12,2),
    ins_first_due_date   DATE,
    ins_months_remaining INTEGER,
    ins_notes            TEXT,
    pat_amt_financed     NUMERIC(12,2),
    pat_down_pay         NUMERIC(12,2),
    pat_apr              NUMERIC(6,4),
    pat_fin_charge       NUMERIC(12,2),
    pat_interval         VARCHAR(20),
    pat_num_payments     INTEGER,
    pat_periodic_amt     NUMERIC(12,2),
    pat_rem_payments     INTEGER,
    pat_rem_amt          NUMERIC(12,2),
    pat_first_due_date   DATE,
    sec_ins_plan_id      INTEGER      REFERENCES insurance_plans(id),
    sec_ins_plan_amount  NUMERIC(12,2),
    sec_ins_periodic_amt NUMERIC(12,2),
    sec_ins_notes        TEXT,
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by           VARCHAR(100),
    updated_at           TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ortho_plans_patient ON ortho_plans(patient_id);

-- SOURCE: PatCariesRisk1340.txt — caries risk assessment / ADA 1340 form (empty, future)
CREATE TABLE IF NOT EXISTS caries_risk_assessments (
    id                    SERIAL PRIMARY KEY,
    tenant_id             INTEGER   NOT NULL REFERENCES tenants(id),
    patient_id            INTEGER   NOT NULL REFERENCES patients(id),
    office_id             INTEGER   REFERENCES offices(id),
    legacy_id             VARCHAR(20),
    risk_date             DATE,
    vis_cavities          BOOLEAN,
    les_not_dentin        BOOLEAN,
    surf_white_spots      BOOLEAN,
    rest_in_3yrs          BOOLEAN,
    cav_rad_dentin        BOOLEAN,
    prox_enamel_les       BOOLEAN,
    act_white_spot_surf   BOOLEAN,
    fir_vis_rest_lst_3yrs BOOLEAN,
    foll_up_vis_rest_yr   BOOLEAN,
    vis_plaque            BOOLEAN,
    freq_snack            BOOLEAN,
    pits_and_fissures     BOOLEAN,
    acidic_ph             BOOLEAN,
    atp                   BOOLEAN,
    xerostomia            BOOLEAN,
    cari_read_above_1500  BOOLEAN,
    vis_heavy_plaque      BOOLEAN,
    freq_snack_gt3x       BOOLEAN,
    deep_pits_fissures    BOOLEAN,
    recreat_drug          BOOLEAN,
    saliva_flow_reduced   BOOLEAN,
    ortho_appliance       BOOLEAN,
    fluoride_toothpaste   BOOLEAN,
    fluoride_rinse        BOOLEAN,
    hx_peridex            BOOLEAN,
    office_flour_6mon     BOOLEAN,
    live_work_fw_water    BOOLEAN,
    f_toothpaste_1x       BOOLEAN,
    f_toothpaste_2x       BOOLEAN,
    f_mouth_rinse         BOOLEAN,
    f_toothpaste_5000ppm  BOOLEAN,
    f_varnish_6mon        BOOLEAN,
    office_f_topical_6mon BOOLEAN,
    chx_1wk_per_mon       BOOLEAN,
    xylitol_6mon          BOOLEAN,
    adeaq_saliva_flow     BOOLEAN,
    risk_level            VARCHAR(20),
    created_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by            VARCHAR(100),
    updated_at            TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_caries_risk_patient ON caries_risk_assessments(patient_id, risk_date);

-- LOGICAL ENTITY: PATNOTES / PATNOTES_ARCHIVE — patient notes (no direct export)
CREATE TABLE IF NOT EXISTS patient_notes (
    id          SERIAL PRIMARY KEY,
    patient_id  INTEGER      NOT NULL REFERENCES patients(id),
    office_id   INTEGER      REFERENCES offices(id),
    legacy_id   VARCHAR(20),
    note_date   DATE,
    note_type   VARCHAR(20),
    notes       TEXT         NOT NULL,
    notes_html  TEXT,
    is_archived BOOLEAN      NOT NULL DEFAULT FALSE,
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  INTEGER      REFERENCES users(id),
    updated_at  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pat_notes_patient ON patient_notes(patient_id, note_date);

-- LOGICAL ENTITY: PATRECALL — recall scheduling (no direct export)
CREATE TABLE IF NOT EXISTS patient_recalls (
    id             SERIAL PRIMARY KEY,
    patient_id     INTEGER      NOT NULL REFERENCES patients(id),
    office_id      INTEGER      REFERENCES offices(id),
    legacy_id      VARCHAR(20),
    recall_type    VARCHAR(50),
    procedure_code VARCHAR(20)  REFERENCES procedure_codes(code),
    due_date       DATE,
    interval_months INTEGER,
    last_completed DATE,
    status         VARCHAR(20)  NOT NULL DEFAULT 'due',
    notes          TEXT,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by     INTEGER      REFERENCES users(id),
    updated_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pat_recall_patient ON patient_recalls(patient_id);
CREATE INDEX IF NOT EXISTS idx_pat_recall_due     ON patient_recalls(due_date, status);

-- LOGICAL ENTITY: PATMEDICALHISTORYD — medical history detail answers (no direct export)
CREATE TABLE IF NOT EXISTS medical_history_details (
    id            SERIAL PRIMARY KEY,
    history_id    INTEGER   NOT NULL REFERENCES medical_history_records(id),
    legacy_id     VARCHAR(20),
    question_code VARCHAR(50) NOT NULL,
    question_text TEXT,
    answer_code   VARCHAR(20),
    answer_text   TEXT,
    notes         TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_med_hist_detail_header ON medical_history_details(history_id);

-- SOURCE: CHARTCOLORS.txt — tooth chart color/pattern category definitions
CREATE TABLE IF NOT EXISTS chart_colors (
    id            SERIAL PRIMARY KEY,
    tenant_id     INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id     VARCHAR(20),
    category_type INTEGER,
    name          VARCHAR(100) NOT NULL,
    stroke_color  VARCHAR(50),
    fill_type     VARCHAR(20),
    fill_color    VARCHAR(50),
    fill_color2   VARCHAR(50),
    fill_pattern  TEXT,
    gradient_angle  VARCHAR(20),
    gradient_method VARCHAR(20),
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by    VARCHAR(100),
    updated_at    TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chart_colors_tenant ON chart_colors(tenant_id);

-- SOURCE: CODESVIEW.txt — per-office code visibility
CREATE TABLE IF NOT EXISTS codes_view (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id),
    office_id   INTEGER     NOT NULL REFERENCES offices(id),
    code        VARCHAR(20) NOT NULL REFERENCES procedure_codes(code),
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100),
    UNIQUE (office_id, code)
);
CREATE INDEX IF NOT EXISTS idx_codes_view_office ON codes_view(office_id);

-- SOURCE: PROVIDERROUTESLIP.txt — provider route slip / superbill procedures (empty, future)
CREATE TABLE IF NOT EXISTS provider_route_slips (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER     NOT NULL REFERENCES tenants(id),
    provider_id    VARCHAR(50) NOT NULL REFERENCES providers(id),
    legacy_id      VARCHAR(20),
    procedure_code VARCHAR(20) REFERENCES procedure_codes(code),
    num_times      INTEGER     NOT NULL DEFAULT 1,
    created_at     TIMESTAMP   NOT NULL DEFAULT NOW(),
    created_by     VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_route_slip_provider ON provider_route_slips(provider_id);

-- SOURCE: ChartPerioActivity.txt — perio activity events (empty, future)
CREATE TABLE IF NOT EXISTS perio_chart_activity (
    id            SERIAL PRIMARY KEY,
    patient_id    INTEGER   NOT NULL REFERENCES patients(id),
    office_id     INTEGER   REFERENCES offices(id),
    legacy_id     VARCHAR(20),
    activity_date DATE,
    perio_type    VARCHAR(50),
    orientation   VARCHAR(10),
    arch          VARCHAR(10),
    quadrant      VARCHAR(10),
    tooth_no      VARCHAR(10),
    block_no      VARCHAR(20),
    add_info      TEXT,
    mxy           VARCHAR(50),
    perio_value   VARCHAR(100),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by    VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_perio_activity_patient ON perio_chart_activity(patient_id, activity_date);

-- LOGICAL ENTITY: TREATPLANINSD / TREATPLANINSD_ARCHIVE — treatment plan insurance details
CREATE TABLE IF NOT EXISTS treatment_plan_insurance_details (
    id               SERIAL PRIMARY KEY,
    plan_item_id     VARCHAR(50)   NOT NULL REFERENCES treatment_plan_items(id),
    ins_plan_id      INTEGER       REFERENCES insurance_plans(id),
    legacy_id        VARCHAR(20),
    is_archived      BOOLEAN       NOT NULL DEFAULT FALSE,
    billing_order    VARCHAR(10),
    estimated_ins    NUMERIC(12,2) NOT NULL DEFAULT 0,
    estimated_pat    NUMERIC(12,2) NOT NULL DEFAULT 0,
    deductible       NUMERIC(12,2),
    coverage_pct     NUMERIC(5,2),
    annual_max_rem   NUMERIC(12,2),
    preauth_number   VARCHAR(100),
    preauth_date     DATE,
    preauth_expires  DATE,
    preauth_amount   NUMERIC(12,2),
    notes            TEXT,
    created_at       TIMESTAMP     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tp_ins_detail_item ON treatment_plan_insurance_details(plan_item_id);

-- SOURCE: REFERRALDEMOGH.txt — referral demographics survey headers (empty, future)
CREATE TABLE IF NOT EXISTS referral_demog_headers (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    description VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100)
);

-- SOURCE: REFERRALDEMOGD.txt — referral demographics responses (empty, future)
CREATE TABLE IF NOT EXISTS referral_demog_details (
    id              SERIAL PRIMARY KEY,
    referral_id     INTEGER   REFERENCES referrals(id),
    tenant_id       INTEGER   NOT NULL REFERENCES tenants(id),
    demog_header_id INTEGER   REFERENCES referral_demog_headers(id),
    legacy_id       VARCHAR(20),
    data            TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_ref_demog_detail_ref ON referral_demog_details(referral_id);

-- SOURCE: DEFINITIONSH.txt — metadata describing each definition group
CREATE TABLE IF NOT EXISTS definition_groups (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(50),
    group_code  VARCHAR(50)  NOT NULL,
    description VARCHAR(255) NOT NULL,
    key1_label  VARCHAR(100),
    key2_label  VARCHAR(100),
    is_editable BOOLEAN      NOT NULL DEFAULT TRUE,
    can_add     BOOLEAN      NOT NULL DEFAULT TRUE,
    group_type  VARCHAR(10),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, group_code)
);

-- SOURCE: IMAGEGROUP.txt — patient imaging groups / X-ray series (empty, future)
CREATE TABLE IF NOT EXISTS image_groups (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    office_id   INTEGER      REFERENCES offices(id),
    patient_id  INTEGER      REFERENCES patients(id),
    template_id INTEGER      REFERENCES imaging_templates(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(255),
    group_type  VARCHAR(20),
    ext_id      VARCHAR(50),
    source      VARCHAR(50),
    source2     VARCHAR(50),
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100),
    updated_at  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_image_groups_patient ON image_groups(patient_id);

-- SOURCE: IMAGEDETAIL.txt — individual image files in a group (empty, future)
CREATE TABLE IF NOT EXISTS image_details (
    id             SERIAL PRIMARY KEY,
    tenant_id      INTEGER   NOT NULL REFERENCES tenants(id),
    office_id      INTEGER   REFERENCES offices(id),
    image_group_id INTEGER   REFERENCES image_groups(id),
    legacy_id      VARCHAR(20),
    tile_id        VARCHAR(20),
    filename       VARCHAR(500),
    notes          TEXT,
    teeth          VARCHAR(100),
    file_size      BIGINT,
    is_deleted     BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_image_details_group ON image_details(image_group_id);

-- SOURCE: OGROUP.txt — office groups / multi-location groupings (empty, future)
CREATE TABLE IF NOT EXISTS office_groups (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(255) NOT NULL,
    address     VARCHAR(255),
    address2    VARCHAR(255),
    city        VARCHAR(100),
    state       VARCHAR(50),
    zip         VARCHAR(20),
    phone       VARCHAR(20),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100)
);

-- SOURCE: COLAGENCY.txt — collection agencies (empty, future)
CREATE TABLE IF NOT EXISTS collection_agencies (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    name        VARCHAR(255) NOT NULL,
    address     VARCHAR(255),
    address2    VARCHAR(255),
    city        VARCHAR(100),
    state       VARCHAR(50),
    zip         VARCHAR(20),
    phone       VARCHAR(20),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100)
);
