# Chat History Feature - Backend API Requirements

> **Status**: Requirements for gdo-api and gdo-chat teams
>
> **Date**: 2026-01-17

## Overview

The mobile app needs to support user-controlled chat history storage with a 30-day soft deletion grace period. Users must explicitly consent during registration, and can toggle the preference anytime from their profile.

---

## Requirements for gdo-api Team

### 1. User Preferences Endpoint

**New field in user record:**
```json
{
  "store_history": false,
  "store_history_changed_at": "2026-01-17T10:30:00Z",
  "history_deletion_scheduled_at": null  // Set when user disables, cleared when re-enabled
}
```

**Endpoint: Update user preferences**
```
PATCH /api/users/me/preferences
Authorization: Bearer <token>

Request:
{
  "store_history": true | false
}

Response:
{
  "store_history": true,
  "store_history_changed_at": "2026-01-17T10:30:00Z",
  "history_deletion_scheduled_at": null
}
```

**Behavior:**
- When `store_history` changes from `true` → `false`:
  - Set `history_deletion_scheduled_at` to now + 30 days
  - Do NOT delete existing sessions yet
- When `store_history` changes from `false` → `true`:
  - Clear `history_deletion_scheduled_at` (cancel pending deletion)
  - Resume storing new sessions

### 2. Get User Preferences

**Endpoint: Get current preferences**
```
GET /api/users/me/preferences
Authorization: Bearer <token>

Response:
{
  "store_history": false,
  "store_history_changed_at": "2026-01-17T10:30:00Z",
  "history_deletion_scheduled_at": "2026-02-16T10:30:00Z"  // or null
}
```

### 3. Session History Endpoint

**Endpoint: Get user's session history**
```
GET /api/users/me/sessions?limit=50&offset=0
Authorization: Bearer <token>

Response (when store_history = true):
{
  "sessions": [
    {
      "id": "session-uuid",
      "expert_id": "calma",
      "expert_name": "Clara Rodrigues",
      "started_at": "2026-01-17T10:00:00Z",
      "ended_at": "2026-01-17T10:05:00Z",
      "message_count": 12,
      "last_message_preview": "Gracias por tu ayuda...",
      "session_type": "freemium"
    }
  ],
  "total": 1,
  "has_more": false
}

Response (when store_history = false):
{
  "sessions": [],
  "total": 0,
  "has_more": false,
  "message": "History storage is disabled"
}
```

### 4. Session Messages Endpoint (for viewing past sessions)

**Endpoint: Get messages from a specific session**
```
GET /api/sessions/{session_id}/messages
Authorization: Bearer <token>

Response:
{
  "session_id": "session-uuid",
  "messages": [
    {
      "id": "msg-uuid",
      "role": "user",
      "content": "Hola, necesito ayuda...",
      "timestamp": "2026-01-17T10:00:30Z"
    },
    {
      "id": "msg-uuid-2",
      "role": "assistant",
      "content": "Hola, estoy aquí para ayudarte...",
      "timestamp": "2026-01-17T10:00:45Z"
    }
  ]
}
```

**Error Response (when user disabled history or session not found):**
```
HTTP 404
{
  "error": "Session not found or history storage disabled"
}
```

### 5. Scheduled Deletion Background Job

**Requirement:** Create a background job/Azure Function that:
1. Runs daily (or on a schedule)
2. Queries for users where `history_deletion_scheduled_at <= NOW()`
3. For each user:
   - Delete all session records
   - Delete all message records
   - Clear `history_deletion_scheduled_at`
   - Keep `store_history = false`
4. Log deletions for audit purposes

### 6. Registration API Update

**Update to existing registration endpoint:**
```
POST /api/auth/register

Request (add new field):
{
  "email": "user@example.com",
  "password": "...",
  "name": "Usuario",
  "store_history_consent": true | false  // NEW FIELD
}
```

The `store_history_consent` value should be saved as the initial `store_history` preference.

---

## Requirements for gdo-chat Team

### 1. Respect store_history Preference

When processing chat messages:

1. **Before saving a message**, check user's `store_history` preference (via gdo-api)
2. **If `store_history = false`**:
   - Process the chat normally (streaming works)
   - DO NOT persist messages to database
   - DO NOT create session summary records
3. **If `store_history = true`**:
   - Current behavior (save messages and session data)

### 2. Session Creation

**Current behavior should continue** - sessions are created for rate limiting and billing purposes regardless of history preference. What changes:
- `store_history = false`: Session metadata saved, but NO messages saved
- `store_history = true`: Session metadata AND messages saved

### 3. No Changes to Chat Streaming

The SSE streaming endpoint (`POST /api/chat`) does NOT need changes. Messages are streamed in real-time to the client regardless of storage preference.

---

## Database Schema Changes (gdo-api)

### Users table (add columns):
```sql
ALTER TABLE users ADD COLUMN store_history BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN store_history_changed_at TIMESTAMP;
ALTER TABLE users ADD COLUMN history_deletion_scheduled_at TIMESTAMP;
```

### Index for deletion job:
```sql
CREATE INDEX idx_users_deletion_scheduled
ON users (history_deletion_scheduled_at)
WHERE history_deletion_scheduled_at IS NOT NULL;
```

---

## Mobile App Implementation (Complete)

The following has been implemented on the mobile side:

1. ✅ **ConsentScreen**: Added checkbox for history storage consent during registration
2. ✅ **OnboardingData type**: Added `storeHistoryConsent` field
3. ✅ **UserPreferences type**: Added `storeHistory` and `storeHistoryChangedAt` fields
4. ✅ **ProfileScreen**: Added toggle to enable/disable history storage with 30-day warning
5. ✅ **HistoryScreen**: Shows "Historial desactivado" message when storage is off
6. ✅ **appStore**: Preferences updated with `storeHistory` default

**Pending (waiting for backend):**
- Replace empty history with API call to `GET /api/users/me/sessions`
- Call `PATCH /api/users/me/preferences` when toggle changes
- Send `store_history_consent` in registration request

---

## Summary of API Endpoints Needed

| Team | Endpoint | Method | Description |
|------|----------|--------|-------------|
| gdo-api | `/api/users/me/preferences` | GET | Get user preferences |
| gdo-api | `/api/users/me/preferences` | PATCH | Update store_history preference |
| gdo-api | `/api/users/me/sessions` | GET | Get session history list |
| gdo-api | `/api/sessions/{id}/messages` | GET | Get messages for a session |
| gdo-api | `/api/auth/register` | POST | Add store_history_consent field |
| gdo-api | Background Job | - | Delete history after 30 days |

---

## Questions for Backend Teams

1. **gdo-api**: Should we add a `GET /api/users/me` endpoint that returns full user data including preferences? Or keep preferences separate?

2. **gdo-chat**: Is there already a mechanism to check user preferences before saving messages? If not, how should this integration work?

3. **Both**: What's the preferred approach for the 30-day deletion job - Azure Functions timer trigger, or database-level scheduled job?
