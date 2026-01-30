CREATE TABLE tenant_1.providers (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    provider_type VARCHAR(50) CHECK (provider_type IN ('Dentist', 'Hygienist', 'Assistant')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
);