-- Migration: Add authentication columns to users table
-- Date: 2026-01-12
-- Description: Adds password_hash and email verification fields for user registration

-- Add authentication columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;

-- Add index for verified email lookups
CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email) WHERE email_verified = TRUE;

-- Verification
DO $$
BEGIN
    RAISE NOTICE 'Migration 001_add_auth_columns completed successfully';
END $$;
