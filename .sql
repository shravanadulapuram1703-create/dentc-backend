INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Will assume transactional DDL.
BEGIN;

INFO  [alembic.runtime.migration] Running upgrade a6b7c8d9e0f1 -> a2b3c4d5e6f7, Patient Medical History — MH-4/5/6/7/8/13/14/16.
-- Running upgrade a6b7c8d9e0f1 -> a2b3c4d5e6f7

ALTER TABLE patient_medical_alerts ADD COLUMN updated_by INTEGER;

ALTER TABLE patient_medical_alerts ADD COLUMN answered_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE patient_medical_alerts ADD CONSTRAINT fk_patient_medical_alerts_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id);

ALTER TABLE patient_questionnaire_responses ADD COLUMN updated_by INTEGER;

ALTER TABLE patient_questionnaire_responses ADD COLUMN answered_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE patient_questionnaire_responses ADD CONSTRAINT fk_patient_questionnaire_responses_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id);

ALTER TABLE patient_signatures ADD COLUMN signature_type VARCHAR(30);

ALTER TABLE patient_signatures ADD COLUMN signed_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE patient_signatures ADD COLUMN signed_by_user_id INTEGER;

ALTER TABLE patient_signatures ADD COLUMN content_hash VARCHAR(64);

ALTER TABLE patient_signatures ADD COLUMN is_active BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE patient_signatures ADD COLUMN superseded_by_id INTEGER;

ALTER TABLE patient_signatures ADD COLUMN voided_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE patient_signatures ADD COLUMN voided_by INTEGER;

ALTER TABLE patient_signatures ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE patient_signatures ADD COLUMN updated_by INTEGER;

CREATE INDEX ix_patient_signatures_signature_type ON patient_signatures (signature_type);

ALTER TABLE patient_signatures ADD CONSTRAINT fk_patient_signatures_signed_by_user_id_users FOREIGN KEY(signed_by_user_id) REFERENCES users (id);

ALTER TABLE patient_signatures ADD CONSTRAINT fk_patient_signatures_voided_by_users FOREIGN KEY(voided_by) REFERENCES users (id);

ALTER TABLE patient_signatures ADD CONSTRAINT fk_patient_signatures_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id);

ALTER TABLE patient_signatures ADD CONSTRAINT fk_patient_signatures_superseded_by_id_patient_signatures FOREIGN KEY(superseded_by_id) REFERENCES patient_signatures (id);

ALTER TABLE medical_history_records ADD COLUMN tenant_id INTEGER;

ALTER TABLE medical_history_records ADD COLUMN scope VARCHAR(20);

ALTER TABLE medical_history_records ADD COLUMN content_hash VARCHAR(64);

ALTER TABLE medical_history_records ADD COLUMN item_count INTEGER;

ALTER TABLE medical_history_records ADD COLUMN comments TEXT;

ALTER TABLE medical_history_records ADD COLUMN completed_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE medical_history_records ADD COLUMN completed_by INTEGER;

ALTER TABLE medical_history_records ADD COLUMN source_patient_id INTEGER;

ALTER TABLE medical_history_records ADD COLUMN copied_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE medical_history_records ADD COLUMN updated_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE medical_history_records ADD COLUMN updated_by INTEGER;

CREATE INDEX ix_medical_history_records_tenant_id ON medical_history_records (tenant_id);

CREATE INDEX ix_medical_history_records_content_hash ON medical_history_records (content_hash);

ALTER TABLE medical_history_records ADD CONSTRAINT fk_medical_history_records_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id);

ALTER TABLE medical_history_records ADD CONSTRAINT fk_medical_history_records_completed_by_users FOREIGN KEY(completed_by) REFERENCES users (id);

ALTER TABLE medical_history_records ADD CONSTRAINT fk_medical_history_records_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id);

ALTER TABLE medical_history_records ADD CONSTRAINT fk_medical_history_records_source_patient_id_patients FOREIGN KEY(source_patient_id) REFERENCES patients (id);

UPDATE medical_history_records AS r SET tenant_id = p.tenant_id FROM patients AS p WHERE p.id = r.patient_id AND r.tenant_id IS NULL;

ALTER TABLE medical_history_details ADD COLUMN answer_type VARCHAR(20);

ALTER TABLE medical_history_details ADD COLUMN section VARCHAR(100);

CREATE INDEX ix_medical_history_details_answer_type ON medical_history_details (answer_type);

ALTER TABLE patient_alerts ADD COLUMN is_flash_alert BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE patient_alerts ADD COLUMN source_medical_alert_id INTEGER;

CREATE INDEX ix_patient_alerts_source_medical_alert_id ON patient_alerts (source_medical_alert_id);

ALTER TABLE patient_alerts ADD CONSTRAINT fk_patient_alerts_source_medical_alert_id FOREIGN KEY(source_medical_alert_id) REFERENCES patient_medical_alerts (id);

CREATE TABLE patient_medical_history (
    id SERIAL NOT NULL, 
    tenant_id INTEGER NOT NULL, 
    patient_id INTEGER NOT NULL, 
    comments TEXT, 
    alerts_completed_at TIMESTAMP WITHOUT TIME ZONE, 
    alerts_completed_by INTEGER, 
    dental_completed_at TIMESTAMP WITHOUT TIME ZONE, 
    dental_completed_by INTEGER, 
    medical_completed_at TIMESTAMP WITHOUT TIME ZONE, 
    medical_completed_by INTEGER, 
    last_signature_id INTEGER, 
    last_version_id INTEGER, 
    copied_from_patient_id INTEGER, 
    copied_at TIMESTAMP WITHOUT TIME ZONE, 
    copied_by INTEGER, 
    created_by INTEGER, 
    updated_by INTEGER, 
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE, 
    CONSTRAINT pk_patient_medical_history PRIMARY KEY (id), 
    CONSTRAINT fk_patient_medical_history_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
    CONSTRAINT uq_patient_medical_history_patient_id UNIQUE (patient_id), 
    CONSTRAINT fk_patient_medical_history_patient_id_patients FOREIGN KEY(patient_id) REFERENCES patients (id), 
    CONSTRAINT fk_patient_medical_history_alerts_completed_by_users FOREIGN KEY(alerts_completed_by) REFERENCES users (id), 
    CONSTRAINT fk_patient_medical_history_dental_completed_by_users FOREIGN KEY(dental_completed_by) REFERENCES users (id), 
    CONSTRAINT fk_patient_medical_history_medical_completed_by_users FOREIGN KEY(medical_completed_by) REFERENCES users (id), 
    CONSTRAINT fk_patient_medical_history_last_signature_id_patient_signatures FOREIGN KEY(last_signature_id) REFERENCES patient_signatures (id), 
    CONSTRAINT fk_patient_medical_history_last_version_id_medical_hist_e228 FOREIGN KEY(last_version_id) REFERENCES medical_history_records (id), 
    CONSTRAINT fk_patient_medical_history_copied_from_patient_id_patients FOREIGN KEY(copied_from_patient_id) REFERENCES patients (id), 
    CONSTRAINT fk_patient_medical_history_copied_by_users FOREIGN KEY(copied_by) REFERENCES users (id), 
    CONSTRAINT fk_patient_medical_history_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_patient_medical_history_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_patient_medical_history_tenant_id ON patient_medical_history (tenant_id);

CREATE INDEX ix_patient_medical_history_patient_id ON patient_medical_history (patient_id);

CREATE TABLE patient_medical_history_events (
    id SERIAL NOT NULL, 
    tenant_id INTEGER NOT NULL, 
    patient_id INTEGER NOT NULL, 
    entity_type VARCHAR(20) NOT NULL, 
    entity_id INTEGER, 
    code VARCHAR(50), 
    label TEXT, 
    action VARCHAR(20) NOT NULL, 
    old_value TEXT, 
    new_value TEXT, 
    source_patient_id INTEGER, 
    changed_by INTEGER, 
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_patient_medical_history_events PRIMARY KEY (id), 
    CONSTRAINT fk_patient_medical_history_events_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
    CONSTRAINT fk_patient_medical_history_events_patient_id_patients FOREIGN KEY(patient_id) REFERENCES patients (id), 
    CONSTRAINT fk_patient_medical_history_events_source_patient_id_patients FOREIGN KEY(source_patient_id) REFERENCES patients (id), 
    CONSTRAINT fk_patient_medical_history_events_changed_by_users FOREIGN KEY(changed_by) REFERENCES users (id)
);

CREATE INDEX ix_patient_medical_history_events_tenant_id ON patient_medical_history_events (tenant_id);

CREATE INDEX ix_patient_medical_history_events_patient_id ON patient_medical_history_events (patient_id);

CREATE INDEX ix_patient_medical_history_events_entity_type ON patient_medical_history_events (entity_type);

UPDATE alembic_version SET version_num='a2b3c4d5e6f7' WHERE alembic_version.version_num = 'a6b7c8d9e0f1';

COMMIT;

