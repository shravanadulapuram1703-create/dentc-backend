-- Idempotent unique constraints required for migration ON CONFLICT (legacy_id).
-- Safe to re-run on an existing database after the base schema is created.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'employers_legacy_id_key') THEN
        ALTER TABLE employers ADD CONSTRAINT employers_legacy_id_key UNIQUE (legacy_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'insurance_carriers_legacy_id_key') THEN
        ALTER TABLE insurance_carriers ADD CONSTRAINT insurance_carriers_legacy_id_key UNIQUE (legacy_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'insurance_plans_legacy_id_key') THEN
        ALTER TABLE insurance_plans ADD CONSTRAINT insurance_plans_legacy_id_key UNIQUE (legacy_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'insurance_subscribers_legacy_id_key') THEN
        ALTER TABLE insurance_subscribers ADD CONSTRAINT insurance_subscribers_legacy_id_key UNIQUE (legacy_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fee_schedules_legacy_id_key') THEN
        ALTER TABLE fee_schedules ADD CONSTRAINT fee_schedules_legacy_id_key UNIQUE (legacy_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'patients_legacy_id_key') THEN
        ALTER TABLE patients ADD CONSTRAINT patients_legacy_id_key UNIQUE (legacy_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'letter_templates_legacy_id_key') THEN
        ALTER TABLE letter_templates ADD CONSTRAINT letter_templates_legacy_id_key UNIQUE (legacy_id);
    END IF;
END $$;

-- Widen letter_templates.channel (source LType values can exceed 5 chars)
ALTER TABLE letter_templates ALTER COLUMN channel TYPE VARCHAR(20);

-- Blocked appointment slots have no patient
ALTER TABLE appointments ALTER COLUMN patient_id DROP NOT NULL;

-- Progress note tooth field can contain long free-text from misaligned exports
ALTER TABLE progress_notes ALTER COLUMN tooth TYPE VARCHAR(255);

-- treatment_plan_items.billing_order (primary/secondary) from Denticon BILLINGORDER
ALTER TABLE treatment_plan_items ADD COLUMN IF NOT EXISTS billing_order VARCHAR(10);
