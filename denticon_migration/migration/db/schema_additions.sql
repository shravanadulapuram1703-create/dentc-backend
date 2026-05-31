-- ============================================================
--  DENTAL PMS — Schema Additions  (REFERENCE COPY ONLY)
--
--  ⚠  DO NOT RUN THIS FILE DIRECTLY.
--
--  All tables in this file have already been appended to schema.sql
--  (Domain 11 section, starting after questionnaire_options).
--  run_schema.py reads ONLY schema.sql, which contains all 75 tables.
--
--  This file is kept as a standalone reference for the Domain 11
--  additions so they can be reviewed independently.
-- ============================================================


-- ============================================================
-- DOMAIN 2 (additions) — INSURANCE
-- ============================================================

-- SOURCE: FeeScheA.txt — assigns which fee schedule applies to a
-- given combination of plan / carrier / provider / office.
CREATE TABLE IF NOT EXISTS fee_schedule_assignments (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id       VARCHAR(20),                          -- FEESCHEDAID
    ins_plan_id     INTEGER      REFERENCES insurance_plans(id),     -- INSPLANID (0=none)
    carrier_id      INTEGER      REFERENCES insurance_carriers(id),   -- CARRIERID (0=none)
    provider_id     VARCHAR(50)  REFERENCES providers(id),            -- PROVIDERID (0=none)
    office_id       INTEGER      REFERENCES offices(id),              -- OID (0=global)
    fee_schedule_id INTEGER      NOT NULL REFERENCES fee_schedules(id), -- FEEID
    specialty_id    VARCHAR(20),                          -- SPECIALTYID
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_fee_assign_plan   ON fee_schedule_assignments(ins_plan_id);
CREATE INDEX IF NOT EXISTS idx_fee_assign_sched  ON fee_schedule_assignments(fee_schedule_id);

-- SOURCE: InsCustCoverage.txt — per-tenant custom coverage overrides
-- (header-only export, no data; schema for future use)
CREATE TABLE IF NOT EXISTS ins_custom_coverage (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id       VARCHAR(20),                          -- INSCUSTCOVERAGEID
    start_code      VARCHAR(20)  NOT NULL,
    end_code        VARCHAR(20)  NOT NULL,
    description     VARCHAR(255),
    coverage_pct    NUMERIC(5,2),
    ded_waived      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);

-- SOURCE: PROVIDERINSID.txt — provider IDs per carrier (NPI, tax ID overrides per plan)
CREATE TABLE IF NOT EXISTS provider_insurance_ids (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),
    provider_id VARCHAR(50)  NOT NULL REFERENCES providers(id),
    carrier_id  INTEGER      NOT NULL REFERENCES insurance_carriers(id),
    ins_id      VARCHAR(100),                             -- the override ID
    in_network  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_prov_ins_id_prov    ON provider_insurance_ids(provider_id);
CREATE INDEX IF NOT EXISTS idx_prov_ins_id_carrier ON provider_insurance_ids(carrier_id);


-- ============================================================
-- DOMAIN 3 (additions) — PATIENTS
-- ============================================================

-- SOURCE: PatContractBilling.txt — patient-pay in-house payment plan installments
-- (billing schedule for patient portion, no data currently)
CREATE TABLE IF NOT EXISTS patient_payment_plans (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id      INTEGER      NOT NULL REFERENCES patients(id),
    office_id       INTEGER      REFERENCES offices(id),
    legacy_id       VARCHAR(20),                          -- PLANID
    plan_bal_amt    NUMERIC(12,2),
    tx_plan_number  VARCHAR(50),
    setup_date      DATE,
    amt_financed    NUMERIC(12,2),
    down_payment    NUMERIC(12,2),
    apr             NUMERIC(6,4),
    fin_charge      NUMERIC(12,2),
    interval_type   VARCHAR(20),                          -- Monthly, Weekly...
    num_payments    INTEGER,
    periodic_amt    NUMERIC(12,2),
    first_due_date  DATE,
    rem_payments    INTEGER,
    rem_total_amt   NUMERIC(12,2),
    notes           TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100),
    updated_at      TIMESTAMP,
    updated_by      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_pat_payplan_patient ON patient_payment_plans(patient_id);

-- SOURCE: PatInsContractBilling.txt — insurance-portion periodic billing schedule
CREATE TABLE IF NOT EXISTS patient_ins_payment_plans (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id      INTEGER      NOT NULL REFERENCES patients(id),
    legacy_plan_id  VARCHAR(20),
    periodic_order  INTEGER,
    periodic_date   DATE,
    periodic_amt    NUMERIC(12,2),
    is_billed       BOOLEAN      NOT NULL DEFAULT FALSE,
    billing_code    VARCHAR(50),
    ledger_id       VARCHAR(20),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_pat_ins_payplan_patient ON patient_ins_payment_plans(patient_id);

-- SOURCE: PATSECINSCONTRACTBILLING.txt — secondary insurance periodic billing
CREATE TABLE IF NOT EXISTS patient_sec_ins_payment_plans (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id      INTEGER      NOT NULL REFERENCES patients(id),
    legacy_plan_id  VARCHAR(20),
    periodic_order  INTEGER,
    periodic_date   DATE,
    periodic_amt    NUMERIC(12,2),
    is_billed       BOOLEAN      NOT NULL DEFAULT FALSE,
    billing_code    VARCHAR(50),
    ledger_id       VARCHAR(20),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_pat_sec_ins_payplan_patient ON patient_sec_ins_payment_plans(patient_id);

-- SOURCE: PatRegPlan.txt — patient regular/recall payment plan (capitation-style)
CREATE TABLE IF NOT EXISTS patient_reg_plans (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id      INTEGER      NOT NULL REFERENCES patients(id),
    office_id       INTEGER      REFERENCES offices(id),
    legacy_id       VARCHAR(20),                          -- PLANID
    setup_date      DATE,
    amt_financed    NUMERIC(12,2),
    down_payment    NUMERIC(12,2),
    apr             NUMERIC(6,4),
    fin_charge      NUMERIC(12,2),
    interval_type   VARCHAR(20),
    num_payments    INTEGER,
    periodic_amt    NUMERIC(12,2),
    first_due_date  DATE,
    rem_payments    INTEGER,
    rem_total_amt   NUMERIC(12,2),
    notes           TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_pat_regplan_patient ON patient_reg_plans(patient_id);

-- SOURCE: PATORTHOPLAN.txt — orthodontic treatment + payment plan
CREATE TABLE IF NOT EXISTS ortho_plans (
    id                      SERIAL PRIMARY KEY,
    tenant_id               INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id              INTEGER      NOT NULL REFERENCES patients(id),
    office_id               INTEGER      REFERENCES offices(id),
    legacy_id               VARCHAR(20),                  -- PLANID
    procedure_code          VARCHAR(20)  REFERENCES procedure_codes(code),
    description             VARCHAR(255),
    total_ortho_amt         NUMERIC(12,2),
    ins_share_amt           NUMERIC(12,2),
    pat_share_amt           NUMERIC(12,2),
    treat_start_date        DATE,
    treat_end_date          DATE,
    banding_date            DATE,
    -- Insurance portion
    ins_plan_id             INTEGER      REFERENCES insurance_plans(id),
    ins_setup_date          DATE,
    ins_plan_amount         NUMERIC(12,2),
    ins_down_pay            NUMERIC(12,2),
    ins_interval            VARCHAR(20),
    ins_num_payments        INTEGER,
    ins_periodic_amt        NUMERIC(12,2),
    ins_rem_payments        INTEGER,
    ins_rem_amt             NUMERIC(12,2),
    ins_first_due_date      DATE,
    ins_months_remaining    INTEGER,
    ins_notes               TEXT,
    -- Patient portion
    pat_amt_financed        NUMERIC(12,2),
    pat_down_pay            NUMERIC(12,2),
    pat_apr                 NUMERIC(6,4),
    pat_fin_charge          NUMERIC(12,2),
    pat_interval            VARCHAR(20),
    pat_num_payments        INTEGER,
    pat_periodic_amt        NUMERIC(12,2),
    pat_rem_payments        INTEGER,
    pat_rem_amt             NUMERIC(12,2),
    pat_first_due_date      DATE,
    -- Secondary insurance
    sec_ins_plan_id         INTEGER      REFERENCES insurance_plans(id),
    sec_ins_plan_amount     NUMERIC(12,2),
    sec_ins_periodic_amt    NUMERIC(12,2),
    sec_ins_notes           TEXT,
    is_active               BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by              VARCHAR(100),
    updated_at              TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ortho_plans_patient ON ortho_plans(patient_id);

-- SOURCE: PatCariesRisk1340.txt — caries risk assessment (ADA 1340 form)
-- (header-only export, no data; comprehensive schema for future)
CREATE TABLE IF NOT EXISTS caries_risk_assessments (
    id                      SERIAL PRIMARY KEY,
    tenant_id               INTEGER      NOT NULL REFERENCES tenants(id),
    patient_id              INTEGER      NOT NULL REFERENCES patients(id),
    office_id               INTEGER      REFERENCES offices(id),
    legacy_id               VARCHAR(20),                  -- RISKID
    risk_date               DATE,
    -- Risk indicators (boolean flags from ADA form)
    vis_cavities            BOOLEAN,
    les_not_dentin          BOOLEAN,
    surf_white_spots        BOOLEAN,
    rest_in_3yrs            BOOLEAN,
    cav_rad_dentin          BOOLEAN,
    prox_enamel_les         BOOLEAN,
    act_white_spot_surf     BOOLEAN,
    fir_vis_rest_lst_3yrs   BOOLEAN,
    foll_up_vis_rest_yr     BOOLEAN,
    vis_plaque              BOOLEAN,
    freq_snack              BOOLEAN,
    pits_and_fissures       BOOLEAN,
    acidic_ph               BOOLEAN,
    atp                     BOOLEAN,
    xerostomia              BOOLEAN,
    cari_read_above_1500    BOOLEAN,
    vis_heavy_plaque        BOOLEAN,
    freq_snack_gt3x         BOOLEAN,
    deep_pits_fissures      BOOLEAN,
    recreat_drug            BOOLEAN,
    saliva_flow_reduced     BOOLEAN,
    ortho_appliance         BOOLEAN,
    -- Protective factors
    fluoride_toothpaste     BOOLEAN,
    fluoride_rinse          BOOLEAN,
    hx_peridex              BOOLEAN,
    office_flour_6mon       BOOLEAN,
    live_work_fw_water      BOOLEAN,
    f_toothpaste_1x         BOOLEAN,
    f_toothpaste_2x         BOOLEAN,
    f_mouth_rinse           BOOLEAN,
    f_toothpaste_5000ppm    BOOLEAN,
    f_varnish_6mon          BOOLEAN,
    office_f_topical_6mon   BOOLEAN,
    chx_1wk_per_mon         BOOLEAN,
    xylitol_6mon            BOOLEAN,
    adeaq_saliva_flow       BOOLEAN,
    -- Result
    risk_level              VARCHAR(20),                  -- Low, Moderate, High, Extreme
    created_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by              VARCHAR(100),
    updated_at              TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_caries_risk_patient ON caries_risk_assessments(patient_id, risk_date);

-- SOURCE: PATNOTES / PATNOTES_ARCHIVE (logical entity — no direct export file)
-- Patient account-level clinical notes (distinct from progress_notes and account_notes)
CREATE TABLE IF NOT EXISTS patient_notes (
    id          SERIAL PRIMARY KEY,
    patient_id  INTEGER      NOT NULL REFERENCES patients(id),
    office_id   INTEGER      REFERENCES offices(id),
    legacy_id   VARCHAR(20),
    note_date   DATE,
    note_type   VARCHAR(20),                              -- 'clinical', 'account', 'recall'
    notes       TEXT         NOT NULL,
    notes_html  TEXT,
    is_archived BOOLEAN      NOT NULL DEFAULT FALSE,
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  INTEGER      REFERENCES users(id),
    updated_at  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pat_notes_patient ON patient_notes(patient_id, note_date);

-- SOURCE: PATRECALL (logical entity — no direct export file)
-- Recall/recare scheduling: tracks when each patient is due for their next appointment type
CREATE TABLE IF NOT EXISTS patient_recalls (
    id              SERIAL PRIMARY KEY,
    patient_id      INTEGER      NOT NULL REFERENCES patients(id),
    office_id       INTEGER      REFERENCES offices(id),
    legacy_id       VARCHAR(20),
    recall_type     VARCHAR(50),                          -- 'prophy', 'perio', 'exam', etc.
    procedure_code  VARCHAR(20)  REFERENCES procedure_codes(code),
    due_date        DATE,
    interval_months INTEGER,
    last_completed  DATE,
    status          VARCHAR(20)  NOT NULL DEFAULT 'due', -- 'due', 'scheduled', 'overdue', 'completed'
    notes           TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      INTEGER      REFERENCES users(id),
    updated_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pat_recall_patient ON patient_recalls(patient_id);
CREATE INDEX IF NOT EXISTS idx_pat_recall_due     ON patient_recalls(due_date, status);

-- SOURCE: PATMEDICALHISTORYD (logical entity — detail rows for medical history header)
-- Individual medical history question answers
CREATE TABLE IF NOT EXISTS medical_history_details (
    id              SERIAL PRIMARY KEY,
    history_id      INTEGER      NOT NULL REFERENCES medical_history_records(id),
    legacy_id       VARCHAR(20),
    question_code   VARCHAR(50)  NOT NULL,
    question_text   TEXT,
    answer_code     VARCHAR(20),
    answer_text     TEXT,
    notes           TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_med_hist_detail_header ON medical_history_details(history_id);


-- ============================================================
-- DOMAIN 4 (additions) — CLINICAL REFERENCE
-- ============================================================

-- SOURCE: CHARTCOLORS.txt — color/pattern definitions for tooth chart categories
-- (Pre-existing, Completed, Existing, Treatment Plan, etc.)
CREATE TABLE IF NOT EXISTS chart_colors (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id       VARCHAR(20),                          -- CATEGORYID
    category_type   INTEGER,                              -- CATTYPE
    name            VARCHAR(100) NOT NULL,                -- CATNAME
    stroke_color    VARCHAR(50),
    fill_type       VARCHAR(20),
    fill_color      VARCHAR(50),
    fill_color2     VARCHAR(50),
    fill_pattern    VARCHAR(100),
    gradient_angle  VARCHAR(20),
    gradient_method VARCHAR(20),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100),
    updated_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chart_colors_tenant ON chart_colors(tenant_id);

-- SOURCE: CODESVIEW.txt — per-office code visibility (which ADA codes are shown/enabled)
CREATE TABLE IF NOT EXISTS codes_view (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    office_id   INTEGER      NOT NULL REFERENCES offices(id),
    code        VARCHAR(20)  NOT NULL REFERENCES procedure_codes(code),
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100),
    UNIQUE (office_id, code)
);

CREATE INDEX IF NOT EXISTS idx_codes_view_office ON codes_view(office_id);

-- SOURCE: PROVIDERROUTESLIP.txt — route slip / superbill procedure frequency per provider
CREATE TABLE IF NOT EXISTS provider_route_slips (
    id                   SERIAL PRIMARY KEY,
    tenant_id            INTEGER      NOT NULL REFERENCES tenants(id),
    provider_id          VARCHAR(50)  NOT NULL REFERENCES providers(id),
    legacy_id            VARCHAR(20),                     -- PROVIDERROUTESLIPID
    procedure_code       VARCHAR(20)  REFERENCES procedure_codes(code),
    num_times            INTEGER      NOT NULL DEFAULT 1,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by           VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_route_slip_provider ON provider_route_slips(provider_id);


-- ============================================================
-- DOMAIN 5 (additions) — SCHEDULING / PERIO
-- ============================================================

-- SOURCE: ChartPerioActivity.txt — recorded perio activity events
-- (header-only export, no data; schema for future use)
CREATE TABLE IF NOT EXISTS perio_chart_activity (
    id              SERIAL PRIMARY KEY,
    patient_id      INTEGER      NOT NULL REFERENCES patients(id),
    office_id       INTEGER      REFERENCES offices(id),
    legacy_id       VARCHAR(20),                          -- PERIOID
    activity_date   DATE,
    perio_type      VARCHAR(50),
    orientation     VARCHAR(10),
    arch            VARCHAR(10),
    quadrant        VARCHAR(10),
    tooth_no        VARCHAR(10),
    block_no        VARCHAR(20),
    add_info        TEXT,
    mxy             VARCHAR(50),
    perio_value     VARCHAR(100),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_perio_activity_patient ON perio_chart_activity(patient_id, activity_date);


-- ============================================================
-- DOMAIN 6 (additions) — CLINICAL RECORDS
-- ============================================================

-- SOURCE: TREATPLANINSD / TREATPLANINSD_ARCHIVE (logical entity)
-- Insurance detail per treatment plan item (pre-auth estimates)
CREATE TABLE IF NOT EXISTS treatment_plan_insurance_details (
    id                  SERIAL PRIMARY KEY,
    plan_item_id        VARCHAR(50)   NOT NULL REFERENCES treatment_plan_items(id),
    ins_plan_id         INTEGER       REFERENCES insurance_plans(id),
    legacy_id           VARCHAR(20),
    is_archived         BOOLEAN       NOT NULL DEFAULT FALSE,
    billing_order       VARCHAR(10),
    estimated_ins       NUMERIC(12,2) NOT NULL DEFAULT 0,
    estimated_pat       NUMERIC(12,2) NOT NULL DEFAULT 0,
    deductible          NUMERIC(12,2),
    coverage_pct        NUMERIC(5,2),
    annual_max_rem      NUMERIC(12,2),
    preauth_number      VARCHAR(100),
    preauth_date        DATE,
    preauth_expires     DATE,
    preauth_amount      NUMERIC(12,2),
    notes               TEXT,
    created_at          TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tp_ins_detail_item ON treatment_plan_insurance_details(plan_item_id);


-- ============================================================
-- DOMAIN 7 (additions) — BILLING
-- ============================================================

-- (All billing tables already created in main schema.sql)


-- ============================================================
-- DOMAIN 8 (additions) — COMMUNICATION
-- ============================================================

-- SOURCE: REFERRALDEMOGH.txt — referral demographics survey template headers
CREATE TABLE IF NOT EXISTS referral_demog_headers (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),                              -- REFERRALDEMOGHID
    description VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100)
);

-- SOURCE: REFERRALDEMOGD.txt — per-referral demographic survey responses
CREATE TABLE IF NOT EXISTS referral_demog_details (
    id                   SERIAL PRIMARY KEY,
    referral_id          INTEGER      REFERENCES referrals(id),
    tenant_id            INTEGER      NOT NULL REFERENCES tenants(id),
    demog_header_id      INTEGER      REFERENCES referral_demog_headers(id),
    legacy_id            VARCHAR(20),                     -- REFERRALID from source
    data                 TEXT,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by           VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_ref_demog_detail_ref ON referral_demog_details(referral_id);


-- ============================================================
-- DOMAIN 10 (additions) — CONFIG & REFERENCE DATA
-- ============================================================

-- SOURCE: DEFINITIONSH.txt — metadata about each definitions group
-- (describes what KEY1/KEY2 mean, editability, type for each DEFGROUP)
CREATE TABLE IF NOT EXISTS definition_groups (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id       VARCHAR(50),                          -- DEFGROUP value
    group_code      VARCHAR(50)  NOT NULL,
    description     VARCHAR(255) NOT NULL,
    key1_label      VARCHAR(100),
    key2_label      VARCHAR(100),
    is_editable     BOOLEAN      NOT NULL DEFAULT TRUE,
    can_add         BOOLEAN      NOT NULL DEFAULT TRUE,
    group_type      VARCHAR(10),                          -- 'A'=ADA category, 'B'=basic
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, group_code)
);

-- SOURCE: IMAGEDETAIL.txt — individual image files within an image group
CREATE TABLE IF NOT EXISTS image_details (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    office_id       INTEGER      REFERENCES offices(id),
    image_group_id  INTEGER,                              -- FK to image_groups (below)
    legacy_id       VARCHAR(20),                          -- ID (tile ID)
    tile_id         VARCHAR(20),                          -- TILEID
    filename        VARCHAR(500),
    notes           TEXT,
    teeth           VARCHAR(100),                         -- TEETH2
    file_size       BIGINT,
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- SOURCE: IMAGEGROUP.txt — patient imaging groups (X-ray series, photo sets)
CREATE TABLE IF NOT EXISTS image_groups (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER      NOT NULL REFERENCES tenants(id),
    office_id       INTEGER      REFERENCES offices(id),
    patient_id      INTEGER      REFERENCES patients(id),
    template_id     INTEGER      REFERENCES imaging_templates(id),
    legacy_id       VARCHAR(20),                          -- IMAGEGROUPID
    name            VARCHAR(255),
    group_type      VARCHAR(20),                          -- IGTYPE
    ext_id          VARCHAR(50),
    source          VARCHAR(50),
    source2         VARCHAR(50),
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(100),
    updated_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_image_groups_patient ON image_groups(patient_id);

-- Add deferred FK from image_details to image_groups
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_image_detail_group'
    ) THEN
        ALTER TABLE image_details
            ADD CONSTRAINT fk_image_detail_group
            FOREIGN KEY (image_group_id) REFERENCES image_groups(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_image_details_group ON image_details(image_group_id);

-- SOURCE: OGROUP.txt — office groups (for multi-location groupings)
CREATE TABLE IF NOT EXISTS office_groups (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),                              -- OGID
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

-- SOURCE: COLAGENCY.txt — collection agencies used for bad debt
CREATE TABLE IF NOT EXISTS collection_agencies (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id),
    legacy_id   VARCHAR(20),                              -- COLAGENCYID
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
