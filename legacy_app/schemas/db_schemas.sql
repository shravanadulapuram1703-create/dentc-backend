CREATE TABLE IF NOT EXISTS public.tenants (
    id SERIAL PRIMARY KEY,
    tenant_key VARCHAR(50) UNIQUE NOT NULL, -- ex: denticare_abc
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active', -- active | suspended | deleted
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    tenant_id INT REFERENCES public.tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) NOT NULL, -- super_admin, admin, doctor, staff
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.tenant_configs (
    tenant_id INT PRIMARY KEY REFERENCES public.tenants(id) ON DELETE CASCADE,
    timezone VARCHAR(50),
    currency VARCHAR(10),
    branding JSONB,
    created_at TIMESTAMP DEFAULT now()
);

INSERT INTO public.tenants (tenant_key, name, status)
VALUES
('denticare_alpha', 'DentiCare Alpha Dental Group', 'active'),
('denticare_beta',  'DentiCare Beta Clinics', 'active');

INSERT INTO public.tenant_configs (tenant_id, timezone, currency, branding)
VALUES
(
    1,
    'Asia/Kolkata',
    'INR',
    '{
        "logo_url": "https://cdn.denticare.com/alpha/logo.png",
        "primary_color": "#1E88E5",
        "clinic_name": "DentiCare Alpha",
        "support_email": "support@alpha.denticare.com"
    }'
),
(
    2,
    'Asia/Kolkata',
    'INR',
    '{
        "logo_url": "https://cdn.denticare.com/beta/logo.png",
        "primary_color": "#43A047",
        "clinic_name": "DentiCare Beta",
        "support_email": "support@beta.denticare.com"
    }'
);




SELECT * FROM public.tenants;

ALTER TABLE public.tenants
ADD COLUMN pgid INT;


UPDATE public.tenants
SET pgid = 1001
WHERE tenant_key = 'denticare_alpha';

UPDATE public.tenants
SET pgid = 1002
WHERE tenant_key = 'denticare_beta';

ALTER TABLE public.tenants
ALTER COLUMN pgid SET NOT NULL;

ALTER TABLE public.tenants
ADD CONSTRAINT tenants_pgid_unique UNIQUE (pgid);


ALTER TABLE public.tenants
ALTER COLUMN tenant_key TYPE VARCHAR(80);

UPDATE public.tenants
SET tenant_key = CONCAT('pg_', pgid, '_', tenant_key);

SELECT id, pgid, tenant_key, name
FROM public.tenants;


--Step 2

CREATE TABLE IF NOT EXISTS public.roles (
    id SERIAL PRIMARY KEY,
    tenant_id INT REFERENCES public.tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    level INT NOT NULL,                    -- higher = more power
    is_system BOOLEAN DEFAULT FALSE
);


CREATE TABLE IF NOT EXISTS public.permissions (
    id SERIAL PRIMARY KEY,
    code VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    module VARCHAR(50)
);


CREATE TABLE IF NOT EXISTS public.role_permissions (
    role_id INT REFERENCES public.roles(id) ON DELETE CASCADE,
    permission_id INT REFERENCES public.permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);


CREATE TABLE IF NOT EXISTS public.user_roles (
    user_id INT REFERENCES public.users(id) ON DELETE CASCADE,
    role_id INT REFERENCES public.roles(id) ON DELETE CASCADE,
    office_id INT NOT NULL,
    PRIMARY KEY (user_id, role_id, office_id)
);


CREATE TABLE IF NOT EXISTS public.user_permissions (
    user_id INT REFERENCES public.users(id) ON DELETE CASCADE,
    permission_id INT REFERENCES public.permissions(id) ON DELETE CASCADE,
    allowed BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (user_id, permission_id)
);



CREATE TABLE public.offices (
    id SERIAL PRIMARY KEY,
    tenant_id INT REFERENCES public.tenants(id) ON DELETE CASCADE,
    office_name VARCHAR(255),
    timezone VARCHAR(50)
);


--
--CREATE TABLE public.offices (
--    id INT PRIMARY KEY,
--    tenant_id INT REFERENCES public.tenants(id),
--    office_name VARCHAR(255),
--    timezone VARCHAR(50)
--);



CREATE SCHEMA tenant_1;

CREATE SCHEMA tenant_2;






CREATE TABLE tenant_1.patients (
    id SERIAL PRIMARY KEY,
    chart_no VARCHAR(50) UNIQUE,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    dob DATE,
    gender CHAR(1),
    phone VARCHAR(20),
    email VARCHAR(255),
    home_office_id INT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE tenant_2.patients (LIKE tenant_1.patients INCLUDING ALL);


CREATE TABLE tenant_1.appointments (
    id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES tenant_1.patients(id),
    office_id INT,
    provider_id INT,         -- references public.users.id
    operatory VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(30),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE tenant_2.appointments (LIKE tenant_1.appointments INCLUDING ALL);


CREATE TABLE tenant_1.responsible_parties (
    id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    relation VARCHAR(50),           -- self, parent, spouse, guardian, employer
    phone VARCHAR(20),
    email VARCHAR(255)
);


CREATE TABLE tenant_2.responsible_parties (
    id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES tenant_2.patients(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    relation VARCHAR(50),
    phone VARCHAR(20),
    email VARCHAR(255)
);





CREATE TABLE tenant_1.providers (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    provider_type VARCHAR(50) CHECK (provider_type IN ('Dentist', 'Hygienist', 'Assistant')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE tenant_2.providers (LIKE tenant_1.providers INCLUDING ALL);

CREATE TABLE tenant_1.operatories (
    id SERIAL PRIMARY KEY,
    office_id INT NOT NULL,
    name VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE (office_id, name)
);

CREATE TABLE tenant_2.operatories (LIKE tenant_1.operatories INCLUDING ALL);



CREATE TABLE tenant_1.appointments (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    provider_id INT NOT NULL
        REFERENCES tenant_1.providers(id),
    operatory_id INT NOT NULL
        REFERENCES tenant_1.operatories(id),
    office_id INT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (
        status IN (
            'Scheduled',
            'Checked-In',
            'In-Progress',
            'Completed',
            'Cancelled',
            'No-Show'
        )
    ),
    notes TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE tenant_2.appointments (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_2.patients(id) ON DELETE CASCADE,
    provider_id INT NOT NULL
        REFERENCES tenant_2.providers(id),
    operatory_id INT NOT NULL
        REFERENCES tenant_2.operatories(id),
    office_id INT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (
        status IN (
            'Scheduled',
            'Checked-In',
            'In-Progress',
            'Completed',
            'Cancelled',
            'No-Show'
        )
    ),
    notes TEXT,
    created_at TIMESTAMP DEFAULT now()
);


CREATE UNIQUE INDEX uq_provider_time
ON tenant_1.appointments (provider_id, start_time, end_time)
WHERE status NOT IN ('Cancelled', 'No-Show');

CREATE UNIQUE INDEX uq_provider_time
ON tenant_2.appointments (provider_id, start_time, end_time)
WHERE status NOT IN ('Cancelled', 'No-Show');


CREATE UNIQUE INDEX uq_operatory_time
ON tenant_1.appointments (operatory_id, start_time, end_time)
WHERE status NOT IN ('Cancelled', 'No-Show');


CREATE UNIQUE INDEX uq_operatory_time
ON tenant_2.appointments (operatory_id, start_time, end_time)
WHERE status NOT IN ('Cancelled', 'No-Show');


CREATE INDEX idx_appt_office_time
ON tenant_1.appointments (office_id, start_time);

CREATE INDEX idx_appt_office_time
ON tenant_2.appointments (office_id, start_time);





UPDATE tenant_2.appointments
SET status = 'Cancelled'
WHERE provider_id = 5
  AND start_time = '2025-12-22 09:30'
  AND end_time   = '2025-12-22 10:15';




CREATE TABLE tenant_1.ledger (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    office_id INT NOT NULL,
    appointment_id INT
        REFERENCES tenant_1.appointments(id),
    txn_date DATE NOT NULL,
    description TEXT NOT NULL,
    charge NUMERIC(10,2) DEFAULT 0 CHECK (charge >= 0),
    payment NUMERIC(10,2) DEFAULT 0 CHECK (payment >= 0),
    balance NUMERIC(10,2) NOT NULL,
    txn_type VARCHAR(30) NOT NULL CHECK (
        txn_type IN (
            'Charge',
            'Payment',
            'Adjustment',
            'Refund'
        )
    ),
    created_at TIMESTAMP DEFAULT now()
);


CREATE TABLE tenant_2.ledger (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_2.patients(id) ON DELETE CASCADE,
    office_id INT NOT NULL,
    appointment_id INT
        REFERENCES tenant_2.appointments(id),
    txn_date DATE NOT NULL,
    description TEXT NOT NULL,
    charge NUMERIC(10,2) DEFAULT 0 CHECK (charge >= 0),
    payment NUMERIC(10,2) DEFAULT 0 CHECK (payment >= 0),
    balance NUMERIC(10,2) NOT NULL,
    txn_type VARCHAR(30) NOT NULL CHECK (
        txn_type IN (
            'Charge',
            'Payment',
            'Adjustment',
            'Refund'
        )
    ),
    created_at TIMESTAMP DEFAULT now()
);


CREATE INDEX idx_t1_ledger_patient
ON tenant_1.ledger (patient_id, txn_date);

CREATE INDEX idx_t1_ledger_office
ON tenant_1.ledger (office_id, txn_date);




CREATE TABLE tenant_1.procedure_codes (
    code VARCHAR(10) PRIMARY KEY,          -- D0120
    description TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,          -- Diagnostic, Preventive, Restorative
    default_fee NUMERIC(10,2) NOT NULL,
    tooth_required BOOLEAN DEFAULT FALSE,
    surface_required BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
);


CREATE TABLE tenant_2.procedure_codes (
    code VARCHAR(10) PRIMARY KEY,          -- D0120
    description TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,          -- Diagnostic, Preventive, Restorative
    default_fee NUMERIC(10,2) NOT NULL,
    tooth_required BOOLEAN DEFAULT FALSE,
    surface_required BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
);


CREATE TABLE tenant_1.treatment_plans (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    office_id INT NOT NULL,
    created_by INT NOT NULL,               -- public.users.id
    status VARCHAR(30) NOT NULL CHECK (
        status IN ('Draft', 'Presented', 'Accepted', 'Completed', 'Rejected')
    ),
    total_fee NUMERIC(10,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT now()
);



CREATE TABLE tenant_2.treatment_plans (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_2.patients(id) ON DELETE CASCADE,
    office_id INT NOT NULL,
    created_by INT NOT NULL,               -- public.users.id
    status VARCHAR(30) NOT NULL CHECK (
        status IN ('Draft', 'Presented', 'Accepted', 'Completed', 'Rejected')
    ),
    total_fee NUMERIC(10,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT now()
);




CREATE TABLE tenant_1.treatment_plan_procedures (
    id SERIAL PRIMARY KEY,
    treatment_plan_id INT NOT NULL
        REFERENCES tenant_1.treatment_plans(id) ON DELETE CASCADE,
    procedure_code VARCHAR(10) NOT NULL
        REFERENCES tenant_1.procedure_codes(code),
    tooth VARCHAR(5),
    surfaces VARCHAR(10),
    provider_id INT
        REFERENCES tenant_1.providers(id),
    fee NUMERIC(10,2) NOT NULL,
    insurance_estimate NUMERIC(10,2) DEFAULT 0,
    patient_estimate NUMERIC(10,2) DEFAULT 0,
    status VARCHAR(30) NOT NULL CHECK (
        status IN ('Planned', 'Approved', 'Scheduled', 'Completed', 'Rejected')
    ),
    scheduled BOOLEAN DEFAULT FALSE
);




CREATE TABLE tenant_2.treatment_plan_procedures (
    id SERIAL PRIMARY KEY,
    treatment_plan_id INT NOT NULL
        REFERENCES tenant_2.treatment_plans(id) ON DELETE CASCADE,
    procedure_code VARCHAR(10) NOT NULL
        REFERENCES tenant_2.procedure_codes(code),
    tooth VARCHAR(5),
    surfaces VARCHAR(10),
    provider_id INT
        REFERENCES tenant_2.providers(id),
    fee NUMERIC(10,2) NOT NULL,
    insurance_estimate NUMERIC(10,2) DEFAULT 0,
    patient_estimate NUMERIC(10,2) DEFAULT 0,
    status VARCHAR(30) NOT NULL CHECK (
        status IN ('Planned', 'Approved', 'Scheduled', 'Completed', 'Rejected')
    ),
    scheduled BOOLEAN DEFAULT FALSE
);

CREATE TABLE tenant_1.procedures (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_1.patients(id) ON DELETE CASCADE,
    appointment_id INT
        REFERENCES tenant_1.appointments(id),
    procedure_code VARCHAR(10) NOT NULL
        REFERENCES tenant_1.procedure_codes(code),
    tooth VARCHAR(5),
    surfaces VARCHAR(10),
    provider_id INT
        REFERENCES tenant_1.providers(id),
    office_id INT NOT NULL,
    performed_at TIMESTAMP NOT NULL,
    fee NUMERIC(10,2) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (
        status IN ('Completed', 'Rejected', 'Voided')
    ),
    created_at TIMESTAMP DEFAULT now()
);


CREATE TABLE tenant_2.procedures (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL
        REFERENCES tenant_2.patients(id) ON DELETE CASCADE,
    appointment_id INT
        REFERENCES tenant_2.appointments(id),
    procedure_code VARCHAR(10) NOT NULL
        REFERENCES tenant_2.procedure_codes(code),
    tooth VARCHAR(5),
    surfaces VARCHAR(10),
    provider_id INT
        REFERENCES tenant_2.providers(id),
    office_id INT NOT NULL,
    performed_at TIMESTAMP NOT NULL,
    fee NUMERIC(10,2) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (
        status IN ('Completed', 'Rejected', 'Voided')
    ),
    created_at TIMESTAMP DEFAULT now()
);
--###########################################################################################################



CREATE TABLE public.refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id INT NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);


--######################################################################################################################

CREATE TABLE public.audit_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INT,
    user_id INT,
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(100),
    resource_id VARCHAR(50),
    success BOOLEAN NOT NULL,
    reason TEXT,
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_tenant ON audit_logs(tenant_id);
CREATE INDEX idx_audit_action ON audit_logs(action);



--######################################################################################################################



