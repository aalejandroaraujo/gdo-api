-- Freemium Limit Migration
-- GDO Health Database
-- Migration 003: Change freemium_limit default from 5 to 3
--
-- Run this migration AFTER 002-session-timer.sql
-- Apply manually via Azure Portal or psql

-- ============================================
-- UPDATE DEFAULT FREEMIUM LIMIT
-- ============================================

-- Change the default for new users from 5 to 3
ALTER TABLE users ALTER COLUMN freemium_limit SET DEFAULT 3;

-- ============================================
-- VERIFICATION
-- ============================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 003 applied successfully!';
    RAISE NOTICE 'Changed freemium_limit default from 5 to 3';
    RAISE NOTICE 'Existing users keep their current freemium_limit value';
END $$;
