-- Chat History Migration
-- GDO Health Database
-- Migration 004: Add user preferences for chat history storage
--
-- Run this migration AFTER 003-freemium-limit-3.sql
-- Apply manually via Azure Portal or psql

-- ============================================
-- ADD CHAT HISTORY PREFERENCE COLUMNS
-- ============================================

-- Whether user consents to storing chat history
ALTER TABLE users ADD COLUMN IF NOT EXISTS store_history BOOLEAN DEFAULT FALSE;

-- Timestamp when preference was last changed
ALTER TABLE users ADD COLUMN IF NOT EXISTS store_history_changed_at TIMESTAMPTZ;

-- Scheduled deletion date (30 days after disabling history)
ALTER TABLE users ADD COLUMN IF NOT EXISTS history_deletion_scheduled_at TIMESTAMPTZ;

-- ============================================
-- INDEX FOR DELETION JOB
-- ============================================

-- Partial index for efficient deletion job queries
-- Only indexes users who have a pending deletion
CREATE INDEX IF NOT EXISTS idx_users_deletion_scheduled
ON users (history_deletion_scheduled_at)
WHERE history_deletion_scheduled_at IS NOT NULL;

-- ============================================
-- VERIFICATION
-- ============================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 004 applied successfully!';
    RAISE NOTICE 'Added columns: store_history, store_history_changed_at, history_deletion_scheduled_at';
    RAISE NOTICE 'Created index: idx_users_deletion_scheduled';
END $$;
