# Chat History Feature - Implementation Report

**Implementation Date:** 2026-01-17
**Status:** Completed and Deployed

---

## Overview

This document details the implementation of the Chat History feature for the GDO API, which allows users to control whether their chat sessions are stored and provides endpoints to retrieve their session history.

## Requirements Reference

- Requirements Document: `docs/implementation/chat-history-api-requirements.md`
- Implementation Plan: `C:\Users\aalej\.claude\plans\glittery-meandering-engelbart.md`

---

## Changes Made

### 1. Database Migration

**File:** `infrastructure/migrations/004-chat-history.sql`

Added three new columns to the `users` table:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS store_history BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS store_history_changed_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS history_deletion_scheduled_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_deletion_scheduled
ON users (history_deletion_scheduled_at)
WHERE history_deletion_scheduled_at IS NOT NULL;
```

**Purpose:**
- `store_history`: User preference for storing chat history (default: false)
- `store_history_changed_at`: Timestamp of last preference change
- `history_deletion_scheduled_at`: When history deletion is scheduled (30 days after disabling)
- Partial index optimizes the background deletion job query

---

### 2. Database Functions

#### File: `src/db/users.py`

**Modified `create_user()` function:**
- Added `store_history` parameter (default: `False`)
- Sets `store_history_changed_at` on creation

**Added `get_user_preferences()` function:**
```python
async def get_user_preferences(user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    # Returns: store_history, store_history_changed_at, history_deletion_scheduled_at
```

**Added `update_user_preferences()` function:**
```python
async def update_user_preferences(user_id: uuid.UUID, store_history: bool) -> Optional[Dict[str, Any]]:
    # Handles 30-day deletion scheduling:
    # - true → false: schedules deletion in 30 days
    # - false → true: cancels scheduled deletion
```

#### File: `src/db/sessions.py`

**Added `get_user_sessions_for_history()` function:**
```python
async def get_user_sessions_for_history(
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    # Returns: sessions list with message_count, last_message_preview, total, has_more
```

**Added `get_session_messages()` function:**
```python
async def get_session_messages(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[List[Dict[str, Any]]]:
    # Includes ownership verification
    # Returns None if session not owned by user
```

**Added `delete_user_history()` function:**
```python
async def delete_user_history(user_id: uuid.UUID) -> int:
    # Deletes all sessions for user (cascades to conversation_turns)
    # Returns count of deleted sessions
```

**Added `get_users_pending_deletion()` function:**
```python
async def get_users_pending_deletion(limit: int = 100) -> List[uuid.UUID]:
    # Returns users where store_history=FALSE AND deletion_scheduled <= NOW()
```

**Added `clear_deletion_schedule()` function:**
```python
async def clear_deletion_schedule(user_id: uuid.UUID) -> None:
    # Clears history_deletion_scheduled_at after deletion completes
```

#### File: `src/db/__init__.py`

Updated exports to include all new functions.

---

### 3. API Endpoints

#### File: `function_app.py`

**New Endpoints:**

| Endpoint | Method | Function Name | Description |
|----------|--------|---------------|-------------|
| `/api/users/me/preferences` | GET | `GetUserPreferences` | Get user's history storage preference |
| `/api/users/me/preferences` | PATCH | `UpdateUserPreferences` | Update history preference |
| `/api/users/me/sessions` | GET | `GetUserSessionHistory` | List user's session history |
| `/api/sessions/{session_id}/messages` | GET | `GetSessionMessages` | Get messages from a session |

**Modified Endpoints:**

| Endpoint | Change |
|----------|--------|
| `POST /api/auth/register` | Added optional `store_history_consent` field |

**New Timer Trigger:**

| Function | Schedule | Description |
|----------|----------|-------------|
| `HistoryDeletionJob` | `0 0 3 * * *` (daily 3:00 AM UTC) | Deletes history for users past 30-day grace period |

---

### 4. Security Considerations

1. **Session Ownership Verification**: All session/message endpoints verify `session.user_id == authenticated_user_id`
2. **Atomic Preference Updates**: Database transactions prevent race conditions during deletion scheduling
3. **Deletion Job Safety**: Single atomic query checks both `store_history = false` AND `history_deletion_scheduled_at <= NOW()`
4. **Batch Processing**: Timer trigger processes max 100 users per run to avoid timeout

---

### 5. Documentation

**File:** `docs/API.md`

Updated with:
- New preferences endpoints documentation
- New sessions history endpoints documentation
- Updated registration endpoint with `store_history_consent` field

---

## Testing Report

### Test Environment
- **API URL:** `https://func-gdo-health-prod.azurewebsites.net`
- **Test Date:** 2026-01-17
- **Deployment:** Azure Functions v2

### Test Results

#### Test 1: Registration with store_history_consent=true
**Request:**
```bash
curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "historytest@example.com", "password": "TestPass123!", "display_name": "History Test User", "store_history_consent": true}'
```
**Response:**
```json
{"status": "ok", "user_id": "feccfcad-0817-40f3-9fdb-6b96ee3ea6e3", "message": "Registration successful"}
```
**Result:** PASSED

---

#### Test 2: GET /api/users/me/preferences (history enabled)
**Request:**
```bash
curl https://func-gdo-health-prod.azurewebsites.net/api/users/me/preferences \
  -H "Authorization: Bearer <token>"
```
**Response:**
```json
{
  "store_history": true,
  "store_history_changed_at": "2026-01-17T16:22:27.856611+00:00",
  "history_deletion_scheduled_at": null
}
```
**Result:** PASSED

---

#### Test 3: PATCH /api/users/me/preferences (disable history)
**Request:**
```bash
curl -X PATCH https://func-gdo-health-prod.azurewebsites.net/api/users/me/preferences \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"store_history": false}'
```
**Response:**
```json
{
  "store_history": false,
  "store_history_changed_at": "2026-01-17T16:22:50.249977+00:00",
  "history_deletion_scheduled_at": "2026-02-16T16:22:50.249977+00:00"
}
```
**Verification:** Deletion scheduled exactly 30 days in the future
**Result:** PASSED

---

#### Test 4: PATCH /api/users/me/preferences (re-enable history)
**Request:**
```bash
curl -X PATCH https://func-gdo-health-prod.azurewebsites.net/api/users/me/preferences \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"store_history": true}'
```
**Response:**
```json
{
  "store_history": true,
  "store_history_changed_at": "2026-01-17T16:24:59.457058+00:00",
  "history_deletion_scheduled_at": null
}
```
**Verification:** Scheduled deletion was cancelled (null)
**Result:** PASSED

---

#### Test 5: GET /api/users/me/sessions (empty list)
**Request:**
```bash
curl https://func-gdo-health-prod.azurewebsites.net/api/users/me/sessions \
  -H "Authorization: Bearer <token>"
```
**Response:**
```json
{"sessions": [], "total": 0, "has_more": false}
```
**Result:** PASSED

---

#### Test 6 & 7: GET sessions when history disabled
**Step 1 - Disable history:**
```json
{
  "store_history": false,
  "store_history_changed_at": "2026-01-17T16:26:21.752233+00:00",
  "history_deletion_scheduled_at": "2026-02-16T16:26:21.752233+00:00"
}
```

**Step 2 - GET sessions:**
```json
{
  "sessions": [],
  "total": 0,
  "has_more": false,
  "message": "History storage is disabled"
}
```
**Verification:** Informative message returned when history disabled
**Result:** PASSED

---

#### Test 8: GET session messages (non-existent session)
**Request:**
```bash
curl https://func-gdo-health-prod.azurewebsites.net/api/sessions/00000000-0000-0000-0000-000000000000/messages \
  -H "Authorization: Bearer <token>"
```
**Response:**
```json
{"error": "Session not found or history storage disabled"}
```
**Result:** PASSED

---

#### Test 9: GET session messages (invalid UUID)
**Request:**
```bash
curl https://func-gdo-health-prod.azurewebsites.net/api/sessions/invalid-uuid/messages \
  -H "Authorization: Bearer <token>"
```
**Response:**
```json
{"status": "error", "message": "Invalid session ID"}
```
**Result:** PASSED

---

#### Test 10: Registration WITHOUT store_history_consent
**Request:**
```bash
curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "nohistory@example.com", "password": "TestPass123!", "display_name": "No History User"}'
```
**Response:**
```json
{"status": "ok", "user_id": "f6b3f964-20b3-492d-a5b4-002e700aed49", "message": "Registration successful"}
```
**Result:** PASSED

---

#### Test 11 & 12: Verify default store_history is false
**Login Response:**
```json
{
  "token": "...",
  "user": {"id": "f6b3f964-20b3-492d-a5b4-002e700aed49", "email": "nohistory@example.com", ...}
}
```

**GET preferences Response:**
```json
{
  "store_history": false,
  "store_history_changed_at": "2026-01-17T16:26:47.221187+00:00",
  "history_deletion_scheduled_at": null
}
```
**Verification:** Default value is `false` as expected
**Result:** PASSED

---

## Test Summary

| Test # | Description | Result |
|--------|-------------|--------|
| 1 | Registration with store_history_consent=true | PASSED |
| 2 | GET preferences shows store_history=true | PASSED |
| 3 | PATCH to disable schedules deletion in 30 days | PASSED |
| 4 | PATCH to re-enable cancels scheduled deletion | PASSED |
| 5 | GET sessions returns empty list | PASSED |
| 6-7 | GET sessions when disabled shows message | PASSED |
| 8 | GET messages for non-existent session | PASSED |
| 9 | GET messages with invalid UUID format | PASSED |
| 10 | Registration without consent field | PASSED |
| 11-12 | Default store_history is false | PASSED |

**Overall Result: 12/12 Tests PASSED**

---

## Deployment Information

### Azure Functions Deployed
- **App Name:** `func-gdo-health-prod`
- **Total Functions:** 26
- **New Functions Added:** 5 (4 HTTP triggers + 1 Timer trigger)

### Functions List After Deployment
```
CreateSession: [POST] https://func-gdo-health-prod.azurewebsites.net/api/sessions
EndSession: [POST] https://func-gdo-health-prod.azurewebsites.net/api/sessions/{session_id}/end
ForgotPassword: [POST] https://func-gdo-health-prod.azurewebsites.net/api/auth/forgot-password
GetSessionMessages: [GET] https://func-gdo-health-prod.azurewebsites.net/api/sessions/{session_id}/messages
GetSessionStatus: [GET] https://func-gdo-health-prod.azurewebsites.net/api/sessions/{session_id}/status
GetUserCredits: [GET] https://func-gdo-health-prod.azurewebsites.net/api/users/me/credits
GetUserPreferences: [GET] https://func-gdo-health-prod.azurewebsites.net/api/users/me/preferences
GetUserProfile: [GET] https://func-gdo-health-prod.azurewebsites.net/api/users/me
GetUserSessionHistory: [GET] https://func-gdo-health-prod.azurewebsites.net/api/users/me/sessions
HealthCheck: [GET] https://func-gdo-health-prod.azurewebsites.net/api/health
HistoryDeletionJob: timerTrigger
Login: [POST] https://func-gdo-health-prod.azurewebsites.net/api/auth/login
Register: [POST] https://func-gdo-health-prod.azurewebsites.net/api/auth/register
ResetPassword: [POST] https://func-gdo-health-prod.azurewebsites.net/api/auth/reset-password
SaveSessionSummary: [POST] https://func-gdo-health-prod.azurewebsites.net/api/sessions/summary
SyncWordPressUser: [POST] https://func-gdo-health-prod.azurewebsites.net/api/admin/wp-sync
UpdateUserPreferences: [PATCH] https://func-gdo-health-prod.azurewebsites.net/api/users/me/preferences
UpdateUserProfile: [PATCH] https://func-gdo-health-prod.azurewebsites.net/api/users/me
... (plus Durable Functions orchestrators and activities)
```

---

## Files Modified Summary

| File | Action | Description |
|------|--------|-------------|
| `infrastructure/migrations/004-chat-history.sql` | Created | Database migration |
| `src/db/users.py` | Modified | Added preference functions, updated create_user |
| `src/db/sessions.py` | Modified | Added 5 new session/history functions |
| `src/db/__init__.py` | Modified | Exported new functions |
| `function_app.py` | Modified | Added 4 endpoints + 1 timer trigger |
| `docs/API.md` | Modified | Updated API documentation |

---

## Background Job: HistoryDeletionJob

### Schedule
- **CRON:** `0 0 3 * * *`
- **Frequency:** Daily at 3:00 AM UTC

### Logic
1. Query users where `store_history = FALSE` AND `history_deletion_scheduled_at <= NOW()`
2. Process in batches of 100 users (to avoid Azure Functions timeout)
3. For each user:
   - Delete all sessions (cascades to conversation_turns via FK)
   - Clear `history_deletion_scheduled_at` to prevent re-processing
4. Log: user_id and sessions_deleted count for audit

### Edge Cases Handled
- User re-enables history during 30-day window → deletion cancelled
- Multiple runs don't duplicate deletions (atomic update clears schedule)
- 10-minute timeout → batch processing ensures completion over multiple runs

---

## Notes

1. The timer trigger has not been manually tested as it requires waiting for 30 days or modifying database timestamps directly
2. Session messages endpoint returns 404 in two cases for security (not found vs. not authorized are indistinguishable)
3. All timestamps are returned in ISO 8601 format with timezone

---

## Contact

For questions about this implementation, refer to:
- Requirements: `docs/implementation/chat-history-api-requirements.md`
- API Documentation: `docs/API.md`
