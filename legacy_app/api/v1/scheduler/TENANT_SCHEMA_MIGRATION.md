# Scheduler Module - Tenant Schema Migration

## Overview

The Scheduler module has been updated to store all tenant-specific data in the `tenant_1` schema instead of the `public` schema. This aligns with the multi-tenant architecture where:

- **`public` schema**: Contains shared/global tables (users, offices, tenants)
- **`tenant_1` schema**: Contains tenant-specific data (appointments, operatories, providers, procedure types, scheduler config)

## Changes Made

### 1. SQLAlchemy Models (`app/api/v1/scheduler/models.py`)

All scheduler models now explicitly reference the `tenant_1` schema:

- `SchedulerAppointment` → `{"schema": "tenant_1"}`
- `SchedulerOperatory` → `{"schema": "tenant_1"}`
- `SchedulerProvider` → `{"schema": "tenant_1"}`
- `SchedulerProcedureType` → `{"schema": "tenant_1"}`
- `SchedulerConfig` → `{"schema": "tenant_1"}`

**Foreign Key Relationships:**
- All foreign keys to `public.offices` remain unchanged: `ForeignKey("public.offices.id", ondelete="CASCADE")`
- This ensures proper cross-schema relationships

**Enum Type:**
- `appointment_status_enum` is created in the `tenant_1` schema (via SQL script)
- SQLAlchemy will reference it correctly when the table is in the same schema

### 2. SQL Script (`app/api/v1/scheduler/sql/create_scheduler_tables.sql`)

**Schema Creation:**
- Added: `CREATE SCHEMA IF NOT EXISTS tenant_1;`

**Enum Type:**
- Changed from: `CREATE TYPE appointment_status_enum AS ENUM (...)`
- Changed to: `CREATE TYPE tenant_1.appointment_status_enum AS ENUM (...)`

**All Tables:**
- Changed from: `CREATE TABLE IF NOT EXISTS public.scheduler_*`
- Changed to: `CREATE TABLE IF NOT EXISTS tenant_1.scheduler_*`

**All Indexes:**
- Updated to reference `tenant_1.scheduler_*` tables

**All Triggers:**
- Updated to reference `tenant_1.scheduler_*` tables

**Sample Data:**
- Updated INSERT statements to use `tenant_1.scheduler_*` tables

### 3. Foreign Key Relationships

All foreign keys correctly reference the `public` schema for shared tables:

```sql
office_id INTEGER NOT NULL,
CONSTRAINT fk_scheduler_appointments_office 
    FOREIGN KEY (office_id) 
    REFERENCES public.offices(id) 
    ON DELETE CASCADE
```

This ensures:
- Cross-schema foreign key relationships work correctly
- Data integrity is maintained
- Office references remain in the shared `public` schema

## Database Setup

### Prerequisites

1. Ensure the `public` schema exists with the `offices` table
2. The `tenant_1` schema will be created automatically by the SQL script

### Running the Migration

Execute the SQL script:

```bash
psql -U your_user -d your_database -f app/api/v1/scheduler/sql/create_scheduler_tables.sql
```

Or run it directly in your PostgreSQL client.

### What Gets Created

1. **Schema**: `tenant_1` (if it doesn't exist)
2. **Enum Type**: `tenant_1.appointment_status_enum`
3. **Tables** (all in `tenant_1` schema):
   - `scheduler_appointments`
   - `scheduler_operatories`
   - `scheduler_providers`
   - `scheduler_procedure_types`
   - `scheduler_config`
4. **Indexes**: All indexes on the above tables
5. **Triggers**: Update timestamp triggers
6. **Foreign Keys**: References to `public.offices`

## Multi-Tenant Architecture

### Current Implementation (Tenant 1)

- All scheduler data is stored in `tenant_1` schema
- Foreign keys reference `public.offices` (shared across tenants)
- The middleware sets the search_path to the appropriate tenant schema

### Future Tenant Support

To add support for additional tenants (e.g., `tenant_2`):

1. **Create the schema**: `CREATE SCHEMA IF NOT EXISTS tenant_2;`
2. **Run the SQL script** with schema modifications (replace `tenant_1` with `tenant_2`)
3. **Update models** to dynamically reference the tenant schema (or use a configuration-based approach)

**Note**: The current implementation uses a hardcoded `tenant_1` schema. For production multi-tenant support, consider:
- Using a configuration/settings-based schema name
- Dynamic schema resolution based on tenant context
- Schema-per-tenant isolation strategy

## Verification

After running the SQL script, verify:

1. **Schema exists**:
   ```sql
   SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'tenant_1';
   ```

2. **Tables created**:
   ```sql
   SELECT table_name FROM information_schema.tables 
   WHERE table_schema = 'tenant_1' 
   AND table_name LIKE 'scheduler_%';
   ```

3. **Foreign keys**:
   ```sql
   SELECT 
       tc.table_schema, 
       tc.table_name, 
       kcu.column_name,
       ccu.table_schema AS foreign_table_schema,
       ccu.table_name AS foreign_table_name
   FROM information_schema.table_constraints AS tc
   JOIN information_schema.key_column_usage AS kcu
     ON tc.constraint_name = kcu.constraint_name
   JOIN information_schema.constraint_column_usage AS ccu
     ON ccu.constraint_name = tc.constraint_name
   WHERE tc.constraint_type = 'FOREIGN KEY'
     AND tc.table_schema = 'tenant_1';
   ```

## Important Notes

1. **No scheduler data in public schema**: All scheduler-related tables are now in `tenant_1`
2. **Office references remain in public**: The `offices` table stays in `public` as it's shared across tenants
3. **Enum type is tenant-specific**: The `appointment_status_enum` is created in `tenant_1` schema
4. **Cross-schema queries**: SQLAlchemy handles cross-schema relationships automatically when foreign keys are properly defined

## Testing

After migration, test:

1. Creating appointments
2. Querying appointments by date range
3. Fetching operatories, providers, procedure types
4. Updating scheduler configuration
5. Verifying office filtering works correctly

All operations should work seamlessly with the tenant schema isolation.
