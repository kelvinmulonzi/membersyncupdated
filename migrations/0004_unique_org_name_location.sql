-- Migration: Change organizations table to allow same name with different locations
-- Date: 2024-10-09
-- Purpose: Organizations with same name can exist if they have different locations
--          e.g., "Planet Fitness" can exist in NYC and LA as separate organizations

-- Note: This migration recreates the organizations table with UNIQUE(name, location) instead of UNIQUE(name)

-- Step 1: Create new organizations table with updated constraint
CREATE TABLE organizations_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    industry TEXT,
    location TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    subscription_package_id INTEGER DEFAULT 1,
    created_by_user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    card_company_name TEXT DEFAULT 'MemberSync',
    card_primary_color TEXT DEFAULT '#667eea',
    card_secondary_color TEXT DEFAULT '#764ba2',
    card_logo_url TEXT DEFAULT NULL,
    card_theme TEXT DEFAULT 'default',
    FOREIGN KEY (subscription_package_id) REFERENCES subscription_packages(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(name, location)
);

-- Step 2: Copy all data from old table to new table
INSERT INTO organizations_new 
SELECT id, name, industry, location, status, subscription_package_id, created_by_user_id, created_at,
       card_company_name, card_primary_color, card_secondary_color, card_logo_url, card_theme
FROM organizations;

-- Step 3: Drop old table
DROP TABLE organizations;

-- Step 4: Rename new table to original name
ALTER TABLE organizations_new RENAME TO organizations;

-- Step 5: Recreate indexes if any
CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(status);
CREATE INDEX IF NOT EXISTS idx_organizations_package ON organizations(subscription_package_id);

