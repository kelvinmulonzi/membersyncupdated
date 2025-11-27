-- Add card design settings to organizations table
ALTER TABLE organizations ADD COLUMN card_primary_color TEXT DEFAULT '#667eea';
ALTER TABLE organizations ADD COLUMN card_secondary_color TEXT DEFAULT '#764ba2';
ALTER TABLE organizations ADD COLUMN card_company_name TEXT DEFAULT 'MemberSync';
ALTER TABLE organizations ADD COLUMN card_logo_url TEXT DEFAULT NULL;
ALTER TABLE organizations ADD COLUMN card_theme TEXT DEFAULT 'default';
