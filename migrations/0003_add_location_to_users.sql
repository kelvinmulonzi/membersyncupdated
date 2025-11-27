-- Migration: Add location_id to users table for location-based admin access
-- Date: 2024-10-09
-- Purpose: Enable store-level access control for Organization Admins

-- Add location_id column to users table
ALTER TABLE users ADD COLUMN location_id INTEGER;

-- Create index for faster location-based queries
CREATE INDEX IF NOT EXISTS idx_users_location ON users(location_id);

-- Note: Foreign key constraint will be enforced at application level
-- Organization Superadmins will have location_id = NULL (org-wide access)
-- Organization Admins can be assigned to specific locations

