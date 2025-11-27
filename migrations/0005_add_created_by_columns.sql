-- Add created_by column to users table
ALTER TABLE users ADD COLUMN created_by INTEGER;

-- Add created_by column to members table
ALTER TABLE members ADD COLUMN created_by INTEGER;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_created_by ON users(created_by);
CREATE INDEX IF NOT EXISTS idx_members_created_by ON members(created_by);

-- Note: created_by references the user_id (not id) of the admin who created the record


