-- Session Timer Migration
-- GDO Health Database
-- Migration 002: Add session duration and expiration tracking
--
-- Run this migration AFTER the initial schema (001)
-- Apply manually via Azure Portal or psql

-- ============================================
-- ADD SESSION TIMER COLUMNS
-- ============================================

-- Duration in minutes for the session (5 for free, 45 for paid)
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS duration_minutes INTEGER DEFAULT 5;

-- When the session expires
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Session status (replaces using mode='ended' for expiration tracking)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'status'
    ) THEN
        ALTER TABLE sessions ADD COLUMN status TEXT DEFAULT 'active';
        ALTER TABLE sessions ADD CONSTRAINT chk_session_status
            CHECK (status IN ('active', 'expired', 'ended'));
    END IF;
END $$;

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

-- Index for finding active sessions
CREATE INDEX IF NOT EXISTS idx_sessions_status_active
    ON sessions(status) WHERE status = 'active';

-- Index for expiration checks
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
    ON sessions(expires_at) WHERE status = 'active';

-- ============================================
-- ENHANCED USE_SESSION FUNCTION
-- ============================================

-- Enhanced function that returns duration info
CREATE OR REPLACE FUNCTION use_session_with_duration(
    p_user_id UUID,
    p_expert_id UUID DEFAULT NULL
)
RETURNS TABLE(
    success BOOLEAN,
    session_type TEXT,
    duration_minutes INTEGER,
    message TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_freemium_available INTEGER;
    v_entitlement_id UUID;
    v_session_type TEXT;
    v_duration INTEGER;
BEGIN
    -- Lock user row to prevent race conditions
    PERFORM id FROM users WHERE id = p_user_id FOR UPDATE;

    -- Check freemium availability
    SELECT GREATEST(0, freemium_limit - freemium_used)
    INTO v_freemium_available
    FROM users
    WHERE id = p_user_id;

    IF v_freemium_available > 0 THEN
        -- Use freemium session (5 minutes)
        UPDATE users
        SET freemium_used = freemium_used + 1,
            updated_at = NOW()
        WHERE id = p_user_id;

        v_session_type := 'freemium';
        v_duration := 5;
    ELSE
        -- Check paid entitlements
        SELECT id INTO v_entitlement_id
        FROM entitlements
        WHERE user_id = p_user_id
        AND sessions_used < sessions_total
        AND (valid_until IS NULL OR valid_until > NOW())
        ORDER BY valid_until NULLS LAST, created_at ASC
        LIMIT 1
        FOR UPDATE;

        IF v_entitlement_id IS NOT NULL THEN
            -- Use paid entitlement (45 minutes)
            UPDATE entitlements
            SET sessions_used = sessions_used + 1
            WHERE id = v_entitlement_id;

            SELECT CASE WHEN source = 'test' THEN 'test' ELSE 'paid' END
            INTO v_session_type
            FROM entitlements
            WHERE id = v_entitlement_id;

            v_duration := 45;
        ELSE
            -- No sessions available
            RETURN QUERY SELECT FALSE, NULL::TEXT, NULL::INTEGER, 'No sessions available'::TEXT;
            RETURN;
        END IF;
    END IF;

    -- Log consumption to audit table
    INSERT INTO session_audit (user_id, expert_id, session_type, action)
    VALUES (p_user_id, p_expert_id, v_session_type, 'consumed');

    RETURN QUERY SELECT TRUE, v_session_type, v_duration, 'Session consumed successfully'::TEXT;
END;
$$;

-- ============================================
-- GET USER CREDITS FUNCTION
-- ============================================

CREATE OR REPLACE FUNCTION get_user_credits(p_user_id UUID)
RETURNS TABLE(
    free_remaining INTEGER,
    paid_remaining INTEGER,
    total_available INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_free INTEGER;
    v_paid INTEGER;
BEGIN
    -- Get freemium balance
    SELECT GREATEST(0, freemium_limit - freemium_used)
    INTO v_free
    FROM users
    WHERE id = p_user_id;

    -- Get paid entitlements balance
    SELECT COALESCE(SUM(sessions_total - sessions_used), 0)::INTEGER
    INTO v_paid
    FROM entitlements
    WHERE user_id = p_user_id
    AND (valid_until IS NULL OR valid_until > NOW())
    AND sessions_used < sessions_total;

    RETURN QUERY SELECT
        COALESCE(v_free, 0),
        COALESCE(v_paid, 0),
        COALESCE(v_free, 0) + COALESCE(v_paid, 0);
END;
$$;

-- ============================================
-- VERIFICATION
-- ============================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 002 applied successfully!';
    RAISE NOTICE 'Added columns: duration_minutes, expires_at, status';
    RAISE NOTICE 'Created functions: use_session_with_duration, get_user_credits';
END $$;
