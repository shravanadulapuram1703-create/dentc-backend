-- ==================================================
-- SQL Migration Script: Add Groups and User Group Memberships
-- ==================================================
-- This script creates the groups and user_group_memberships tables
-- to support storing group memberships for users.
--
-- Created: 2025-01-XX
-- Purpose: Store user group memberships (e.g., "GRP-001", "GRP-002") in database
-- ==================================================

-- ==================================================
-- 1. Create Groups Table
-- ==================================================
CREATE TABLE IF NOT EXISTS public.groups (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    
    CONSTRAINT fk_groups_tenant FOREIGN KEY (tenant_id) 
        REFERENCES public.tenants(id) ON DELETE CASCADE
);

-- Create indexes for groups table
CREATE INDEX IF NOT EXISTS idx_groups_tenant_id ON public.groups(tenant_id);
CREATE INDEX IF NOT EXISTS idx_groups_code ON public.groups(code);
CREATE INDEX IF NOT EXISTS idx_groups_is_active ON public.groups(is_active);

-- Add comments
COMMENT ON TABLE public.groups IS 'Group definitions table. Groups are identified by codes like "GRP-001", "GRP-002", etc.';
COMMENT ON COLUMN public.groups.code IS 'Unique group code (e.g., "GRP-001")';
COMMENT ON COLUMN public.groups.name IS 'Display name of the group';
COMMENT ON COLUMN public.groups.description IS 'Optional description of the group';
COMMENT ON COLUMN public.groups.is_active IS 'Whether the group is currently active';

-- ==================================================
-- 2. Create User Group Memberships Table
-- ==================================================
CREATE TABLE IF NOT EXISTS public.user_group_memberships (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    tenant_id INTEGER NOT NULL,
    assigned_by INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_user_group_memberships_user FOREIGN KEY (user_id) 
        REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_group_memberships_group FOREIGN KEY (group_id) 
        REFERENCES public.groups(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_group_memberships_tenant FOREIGN KEY (tenant_id) 
        REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_group_memberships_assigned_by FOREIGN KEY (assigned_by) 
        REFERENCES public.users(id) ON DELETE SET NULL,
    
    -- Ensure a user can only be in a group once per tenant
    CONSTRAINT uq_user_group_memberships_user_group_tenant UNIQUE (user_id, group_id, tenant_id)
);

-- Create indexes for user_group_memberships table
CREATE INDEX IF NOT EXISTS idx_user_group_memberships_user_id ON public.user_group_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_user_group_memberships_group_id ON public.user_group_memberships(group_id);
CREATE INDEX IF NOT EXISTS idx_user_group_memberships_tenant_id ON public.user_group_memberships(tenant_id);

-- Add comments
COMMENT ON TABLE public.user_group_memberships IS 'Junction table linking users to groups. Represents which groups a user belongs to.';
COMMENT ON COLUMN public.user_group_memberships.user_id IS 'Reference to the user';
COMMENT ON COLUMN public.user_group_memberships.group_id IS 'Reference to the group';
COMMENT ON COLUMN public.user_group_memberships.tenant_id IS 'Tenant context for the membership';
COMMENT ON COLUMN public.user_group_memberships.assigned_by IS 'User who assigned this group membership';

-- ==================================================
-- 3. Insert Sample Groups (Optional - for testing)
-- ==================================================
-- These are example group membership options matching the UI contract:
--  - office   : Office-level membership
--  - tenant   : Tenant/practice-group-level membership
--  - billing  : Billing / RCM team
INSERT INTO public.groups (tenant_id, code, name, description, is_active)
VALUES
    (1, 'office',  'Office',  'Office-level membership (can access office-wide features)', TRUE),
    (1, 'tenant',  'Tenant',  'Tenant-level membership (practice group wide)', TRUE),
    (1, 'billing', 'Billing', 'Billing / RCM team', TRUE)
ON CONFLICT (code) DO NOTHING;

-- ==================================================
-- 4. Migration Complete
-- ==================================================
-- The tables are now ready to store group memberships.
-- 
-- To use:
-- 1. Insert groups into public.groups table with codes like "GRP-001", "GRP-002", etc.
-- 2. Create user_group_memberships records to link users to groups
-- 3. Query group memberships via the UserGroupMembership model in SQLAlchemy
-- ==================================================
