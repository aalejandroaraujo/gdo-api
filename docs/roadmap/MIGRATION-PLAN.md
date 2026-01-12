# Migration Plan: WordPress to PostgreSQL

**Document Version:** 1.0
**Created:** 2026-01-12
**Status:** Draft - Awaiting Approval

---

## Executive Summary

This document outlines the phased migration from WordPress as the primary user data store to PostgreSQL, while maintaining WordPress functionality during the transition period.

**Goal:** PostgreSQL becomes the source of truth for all user and session data, with WordPress syncing to it (not the other way around).

---

## Current State

| Component | Current | Target |
|-----------|---------|--------|
| User Registration | WordPress | PostgreSQL (via API) |
| User Authentication | WordPress | JWT from API (Phase 1 done) |
| Session Storage | NocoDB | PostgreSQL |
| Chat (Web) | WordPress/Typebot | WordPress (temporary) |
| Chat (Mobile) | Not available | Mobile App → API → PostgreSQL |

---

## Migration Phases

### Phase 2A: PostgreSQL Integration (Backend)

**Objective:** Connect the API to PostgreSQL and implement user registration endpoints.

**Duration:** 1-2 days

#### Tasks

| # | Task | Success Criteria |
|---|------|------------------|
| 2A.1 | Create `src/db/` module with connection pool | Pool connects to Azure PostgreSQL without errors |
| 2A.2 | Add `password_hash` column to users table | Column exists, accepts bcrypt hashes |
| 2A.3 | Add `email_verified` column to users table | Column exists with default `false` |
| 2A.4 | Implement `POST /api/auth/register` endpoint | Returns 201 with user_id on valid registration |
| 2A.5 | Implement `POST /api/auth/login` endpoint | Returns JWT token on valid credentials |
| 2A.6 | Implement `GET /api/users/me` endpoint | Returns user profile for authenticated user |
| 2A.7 | Replace `nocodb_upsert` with PostgreSQL | `save_session_summary` writes to PostgreSQL |
| 2A.8 | Deploy and test in Azure | All new endpoints working in production |

#### Schema Changes

```sql
-- Add authentication fields to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;

-- Index for login lookups
CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email) WHERE email_verified = TRUE;
```

#### New API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/auth/register` | POST | No | Create new user account |
| `/api/auth/login` | POST | No | Get JWT token with credentials |
| `/api/auth/verify-email` | POST | No | Verify email with token |
| `/api/auth/forgot-password` | POST | No | Request password reset |
| `/api/auth/reset-password` | POST | No | Reset password with token |
| `/api/users/me` | GET | Yes | Get current user profile |
| `/api/users/me` | PATCH | Yes | Update current user profile |

#### Success Criteria

- [ ] New user can register via API with email/password
- [ ] Registered user can login and receive JWT token
- [ ] JWT token works with all existing protected endpoints
- [ ] `save_session_summary` writes to PostgreSQL (not NocoDB)
- [ ] All tests pass locally and in Azure

---

### Phase 2B: WordPress User Migration

**Objective:** Migrate existing WordPress users to PostgreSQL and establish sync.

**Duration:** 1 day (including testing)

#### Pre-Migration Checklist

| # | Task | Owner |
|---|------|-------|
| 2B.1 | Export WordPress users to CSV | Admin |
| 2B.2 | Review data for PII/GDPR compliance | Admin |
| 2B.3 | Create staging backup of PostgreSQL | Admin |
| 2B.4 | Test migration script in staging | Dev |
| 2B.5 | Schedule migration window (if needed) | Admin |

#### Migration Script

```sql
-- Example: Import from CSV (adjust columns as needed)
-- Users will need to reset passwords or use "forgot password" flow

COPY temp_wp_users (wp_user_id, email, display_name, created_at)
FROM '/path/to/wp_users.csv'
WITH (FORMAT csv, HEADER true);

INSERT INTO users (id, wp_user_id, email, display_name, created_at, account_type)
SELECT
    uuid_generate_v4(),
    wp_user_id,
    email,
    display_name,
    created_at,
    'freemium'
FROM temp_wp_users
ON CONFLICT (wp_user_id) DO NOTHING;

DROP TABLE temp_wp_users;
```

#### WordPress Sync Hook

After migration, add a WordPress action hook that creates users in PostgreSQL:

```php
// In WordPress functions.php or custom plugin
add_action('user_register', 'sync_user_to_postgresql', 10, 1);

function sync_user_to_postgresql($user_id) {
    $user = get_userdata($user_id);

    $response = wp_remote_post('https://func-gdo-health-prod.azurewebsites.net/api/internal/sync-user', [
        'headers' => [
            'Content-Type' => 'application/json',
            'X-Internal-Key' => POSTGRESQL_SYNC_KEY  // Defined in wp-config.php
        ],
        'body' => json_encode([
            'wp_user_id' => $user_id,
            'email' => $user->user_email,
            'display_name' => $user->display_name,
            'created_at' => $user->user_registered
        ])
    ]);
}
```

#### Success Criteria

- [ ] All existing WordPress users exist in PostgreSQL
- [ ] `wp_user_id` column correctly maps to WordPress user IDs
- [ ] New WordPress registrations automatically create PostgreSQL users
- [ ] No duplicate users created
- [ ] Users can login via mobile app using their email

---

### Phase 2C: Mobile App Integration

**Objective:** Mobile app fully functional with PostgreSQL backend.

**Duration:** Parallel with mobile development

#### Mobile App Requirements

| Feature | API Endpoint | Notes |
|---------|--------------|-------|
| Registration | `POST /api/auth/register` | Email/password |
| Login | `POST /api/auth/login` | Returns JWT |
| Email Verification | `POST /api/auth/verify-email` | OTP or link |
| Forgot Password | `POST /api/auth/forgot-password` | Email flow |
| View Profile | `GET /api/users/me` | User data |
| Update Profile | `PATCH /api/users/me` | Name, preferences |
| Start Session | `POST /api/sessions` | New endpoint needed |
| Chat | Existing endpoints | Already working |
| Session History | `GET /api/users/me/sessions` | New endpoint needed |

#### Success Criteria

- [ ] User can register via mobile app
- [ ] User can login and maintain session
- [ ] User can chat with experts
- [ ] Session data persists in PostgreSQL
- [ ] User can view session history

---

### Phase 2D: WordPress Chat Deprecation

**Objective:** Transition web users to mobile app, deprecate WordPress chat.

**Duration:** Gradual (weeks/months based on user adoption)

#### Deprecation Steps

| Step | Action | Timing |
|------|--------|--------|
| 1 | Add banner to WordPress chat: "Try our new mobile app!" | Immediate |
| 2 | Stop promoting WordPress chat | Week 1 |
| 3 | Add "WordPress chat will be retired on [date]" notice | Week 2 |
| 4 | Disable new WordPress chat sessions | Week 4 |
| 5 | Remove WordPress chat entirely | Week 6+ |

#### Success Criteria

- [ ] All active users migrated to mobile app
- [ ] No new chat sessions via WordPress
- [ ] WordPress only handles landing pages, blog, marketing
- [ ] PostgreSQL is sole source of truth

---

## Data Flow (Target State)

```
                    ┌─────────────────┐
                    │   Mobile App    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Azure API     │
                    │  (Functions)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │PostgreSQL│   │  OpenAI  │   │Key Vault │
       │  (Data)  │   │  (Chat)  │   │(Secrets) │
       └──────────┘   └──────────┘   └──────────┘
              ▲
              │
              │ Sync (new users only)
              │
       ┌──────────┐
       │WordPress │
       │ (Legacy) │
       └──────────┘
```

---

## Rollback Plan

### Phase 2A Rollback
- Revert API deployment to previous version
- NocoDB still contains historical data
- No data loss

### Phase 2B Rollback
- Keep WordPress as primary (no sync hook)
- PostgreSQL users remain but unused
- Minimal impact

### Phase 2C Rollback
- Mobile app continues using dev tokens
- No user registration until fixed

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| PostgreSQL connection issues | High | Low | Test thoroughly, have connection string in Key Vault |
| Password hash migration | Medium | Low | Users reset passwords via forgot-password flow |
| Duplicate users | Medium | Medium | Use `wp_user_id` as unique constraint |
| Email delivery failures | Medium | Medium | Use reliable email service (SendGrid, Azure Communication) |
| Data loss during migration | High | Low | Full backup before migration, test in staging |

---

## Timeline Summary

| Phase | Name | Duration | Dependencies |
|-------|------|----------|--------------|
| 2A | PostgreSQL Integration | 1-2 days | Phase 1 complete |
| 2B | WordPress Migration | 1 day | Phase 2A complete |
| 2C | Mobile Integration | Parallel | Phase 2A complete |
| 2D | WP Chat Deprecation | Weeks | Phase 2C complete, user adoption |

---

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Technical Lead | | | |
| Product Owner | | | |

---

## Appendix A: Environment Variables Required

```bash
# PostgreSQL (already configured)
POSTGRES_HOST=psql-gdo-health-prod.postgres.database.azure.com
POSTGRES_DB=gdohealth
POSTGRES_USER=gdoadmin
POSTGRES_PASSWORD=@Microsoft.KeyVault(...)

# Email Service (to be added)
EMAIL_SERVICE_API_KEY=@Microsoft.KeyVault(...)
EMAIL_FROM_ADDRESS=noreply@gdohealth.com

# WordPress Sync (to be added)
WP_SYNC_INTERNAL_KEY=@Microsoft.KeyVault(...)
```

---

## Appendix B: Password Hashing

Using bcrypt via Python's `bcrypt` library:

```python
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), hash.encode())
```

Add to `requirements.txt`:
```
bcrypt>=4.0.0
```

---

*Last updated: 2026-01-12*
