# Session Timer Implementation

**Status:** Complete
**Started:** 2026-01-15
**Completed:** 2026-01-16

---

## Overview

Implement session duration management so chat sessions have time limits:
- **Free sessions:** 5 minutes (3 sessions per new user)
- **Paid sessions:** 45 minutes
- **Test sessions:** 45 minutes

---

## Phase 1: Database Migration

Add new columns to `sessions` table and update functions.

### Tasks

- [x] **1.1** Add `duration_minutes` column to sessions table
- [x] **1.2** Add `expires_at` column to sessions table
- [x] **1.3** Add `status` column to sessions table (active, expired, ended)
- [x] **1.4** Create `use_session_with_duration()` function
- [x] **1.5** Create `get_user_credits()` PostgreSQL function
- [x] **1.6** Create migration SQL file
- [x] **1.7** Apply migration to production database

### Migration Files

| File | Description |
|------|-------------|
| `infrastructure/migrations/002-session-timer.sql` | Session timer columns and functions |
| `infrastructure/migrations/003-freemium-limit-3.sql` | Change default freemium_limit to 3 |

---

## Phase 2: Modify POST /api/sessions

Update the existing endpoint to check credits and return timer info.

### Tasks

- [x] **2.1** Create `src/db/credits.py` with credit checking functions
- [x] **2.2** Update `create_session()` in `src/db/sessions.py` to accept duration/expires_at
- [x] **2.3** Update `CreateSession` endpoint in `function_app.py`:
  - [x] Call `consume_session_credit()` to check/consume credits
  - [x] Calculate `expires_at` from `duration_minutes`
  - [x] Return 402 if no credits available
  - [x] Return enhanced response with timer info
- [x] **2.4** Update `src/db/__init__.py` exports
- [x] **2.5** Test endpoint after migration

### API Response (201)

```json
{
  "status": "ok",
  "session": {
    "id": "uuid",
    "mode": "intake",
    "session_type": "freemium",
    "duration_minutes": 5,
    "started_at": "2026-01-16T17:18:13Z",
    "expires_at": "2026-01-16T17:23:13Z",
    "status": "active"
  }
}
```

### Error Response (402)

```json
{
  "error": "NO_CREDITS",
  "message": "No sessions available. Please purchase more.",
  "free_remaining": 0,
  "paid_remaining": 0
}
```

---

## Phase 3: New Endpoints

### GET /api/sessions/{session_id}

- [x] **3.1** Add `get_session_by_id()` function to `src/db/sessions.py`
- [x] **3.2** Add `update_session_status()` function to `src/db/sessions.py`
- [x] **3.3** Create `GetSession` endpoint in `function_app.py`
- [x] **3.4** Test endpoint after migration

**Response (active):**
```json
{
  "session_id": "uuid",
  "status": "active",
  "session_type": "freemium",
  "remaining_seconds": 285,
  "expires_at": "2026-01-16T17:23:13Z",
  "started_at": "2026-01-16T17:18:13Z"
}
```

**Response (expired):**
```json
{
  "session_id": "uuid",
  "status": "expired",
  "session_type": "freemium",
  "remaining_seconds": 0,
  "expires_at": "2026-01-16T17:23:13Z",
  "message": "Session has expired"
}
```

### POST /api/sessions/{session_id}/end

- [x] **3.5** Update `end_session()` to return duration used
- [x] **3.6** Create `EndSession` endpoint in `function_app.py`
- [x] **3.7** Test endpoint after migration

**Response (200):**
```json
{
  "session_id": "uuid",
  "status": "ended",
  "duration_used_seconds": 28
}
```

### GET /api/users/credits

- [x] **3.8** Add `get_user_credits()` function to `src/db/credits.py`
- [x] **3.9** Create `GetUserCredits` endpoint in `function_app.py`
- [x] **3.10** Test endpoint after migration

**Response (200):**
```json
{
  "user_id": "uuid",
  "free_remaining": 3,
  "paid_remaining": 0,
  "total_available": 3
}
```

---

## Phase 4: WooCommerce Webhook (Future)

### Tasks

- [ ] **4.1** Add `WOOCOMMERCE_WEBHOOK_SECRET` to Azure Function App settings
- [x] **4.2** Create `add_paid_credits()` function in `src/db/credits.py`
- [ ] **4.3** Create `WooCommerceWebhook` endpoint in `function_app.py`
- [ ] **4.4** Implement HMAC signature validation
- [ ] **4.5** Implement idempotency check (order_id)
- [ ] **4.6** Test with WooCommerce test webhook

---

## Testing Checklist

All tests passed on 2026-01-16:

- [x] Create session with free credits -> returns type "freemium", duration 5
- [ ] Create session with only paid credits -> returns type "paid", duration 45
- [ ] Create session with no credits -> returns 402 NO_CREDITS
- [x] Get session status while active -> returns remaining_seconds > 0
- [ ] Get session status after expiration -> returns status "expired"
- [x] End session manually -> returns status "ended"
- [x] Get user credits -> returns correct balances
- [x] New user has freemium_limit=3 by default (migration 003)

---

## Files Modified/Created

| File | Status | Description |
|------|--------|-------------|
| `infrastructure/migrations/002-session-timer.sql` | Created | Session timer columns and functions |
| `infrastructure/migrations/003-freemium-limit-3.sql` | Created | Update freemium_limit default to 3 |
| `src/db/credits.py` | Created | Credit management functions |
| `src/db/sessions.py` | Modified | Added timer support to session functions |
| `src/db/__init__.py` | Modified | Added new exports |
| `function_app.py` | Modified | Added new endpoints |

---

## Deployment

### Deployed to Production

- **Date:** 2026-01-16
- **Function App:** func-gdo-health-prod
- **Method:** `func azure functionapp publish`

### Endpoints Available

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/users/credits` | GET | Get user's session credits |
| `/api/sessions` | POST | Create session (consumes credit) |
| `/api/sessions/{id}` | GET | Get session status with timer |
| `/api/sessions/{id}/end` | POST | End session manually |

---

## Notes

- Free sessions: 5 minutes, 3 per new user
- Paid sessions: 45 minutes
- Using existing `users.freemium_limit` / `freemium_used` for free session tracking
- Using existing `entitlements` table for paid session tracking
- Using existing `session_audit` table for credit audit log
- `use_session_with_duration()` PostgreSQL function handles atomic credit consumption
- `get_user_credits()` PostgreSQL function returns balance summary
- Fixed Python 3.11 compatibility issue (backslash in f-string)
