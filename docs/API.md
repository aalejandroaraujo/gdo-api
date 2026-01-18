# API Reference

## Base URL

**Production:** `https://func-gdo-health-prod.azurewebsites.net/api`

---

## Authentication

All protected endpoints require JWT Bearer token authentication.

### Getting a Token

Use the login endpoint to get a token:

**Endpoint:** `POST /api/auth/login`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "yourpassword"
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "User Name",
    "account_type": "freemium"
  }
}
```

### Using the Token

Include the token in the `Authorization` header for all protected endpoints:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Token Expiration & Sliding Refresh

Tokens use a sliding expiration mechanism for optimal security and user experience:

| Setting | Value |
|---------|-------|
| Token lifetime | 1 hour |
| Refresh threshold | 30 minutes remaining |

**How it works:**

1. Tokens expire 1 hour after creation
2. On each authenticated API request, the server checks remaining time
3. If token has **less than 30 minutes** remaining, a new token is generated
4. New token is returned in response headers:
   - `X-New-Token`: The refreshed JWT token
   - `X-Token-Expires-In`: Seconds until new token expires (3600)
5. Client should replace stored token with the new one

**Client Implementation:**

```javascript
// Example: Axios interceptor for token refresh
axios.interceptors.response.use((response) => {
  const newToken = response.headers['x-new-token'];
  if (newToken) {
    // Store the refreshed token
    localStorage.setItem('token', newToken);
  }
  return response;
});
```

**Benefits:**
- Users stay logged in during active sessions (no mid-session logout)
- 1-hour window limits exposure if token is compromised
- No separate refresh token endpoint needed
- Seamless UX - refresh happens automatically in background

### Authentication Errors

| HTTP Code | Message | Cause |
|-----------|---------|-------|
| 401 | Missing Authorization header | No header provided |
| 401 | Invalid Authorization header format | Missing "Bearer " prefix |
| 401 | Token has expired | Token past expiration |
| 401 | Invalid token | Signature verification failed |

---

## Endpoints Overview

### Public Endpoints (No Auth Required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/test` | GET | Health check |
| `/api/auth/register` | POST | User registration |
| `/api/auth/login` | POST | User login |
| `/api/auth/dev-token` | POST | Get development token |
| `/api/auth/forgot-password` | POST | Request password reset |
| `/api/auth/reset-password` | POST | Reset password with token |

### Protected Endpoints (Auth Required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/users/me` | GET | Get current user profile |
| `/api/users/me` | PUT | Update current user profile |
| `/api/users/me/preferences` | GET | Get chat history preferences |
| `/api/users/me/preferences` | PATCH | Update chat history preferences |
| `/api/users/me/sessions` | GET | Get session history (paginated) |
| `/api/users/credits` | GET | Get session credits balance |
| `/api/sessions` | POST | Create new session (consumes credit) |
| `/api/sessions/{id}` | GET | Get session status with timer |
| `/api/sessions/{id}/end` | POST | End session manually |
| `/api/sessions/{id}/messages` | GET | Get messages for a session |
| `/api/extract_fields_from_input` | POST | Extract structured fields from text |
| `/api/risk_escalation_check` | POST | Safety screening |
| `/api/switch_chat_mode` | POST | Determine conversation mode |
| `/api/evaluate_intake_progress` | POST | Check intake completeness |
| `/api/save_session_summary` | POST | Persist session summary |
| `/api/orchestrators/{name}` | POST | Start durable orchestration |

### Internal Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/internal/sync-user` | POST | WordPress user sync (internal use) |

---

## Authentication Endpoints

### POST /api/auth/register

Register a new user account.

**Authentication:** None

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "User Name",
  "store_history_consent": true
}
```

**Response (201):**
```json
{
  "status": "ok",
  "user_id": "uuid",
  "message": "Registration successful"
}
```

**Errors:**
- `400` - Email already registered
- `400` - Invalid email format
- `400` - Password too weak

---

### POST /api/auth/login

Authenticate and get a JWT token.

**Authentication:** None

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response (200):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "User Name",
    "account_type": "freemium"
  }
}
```

**Errors:**
- `401` - Invalid email or password

---

### POST /api/auth/dev-token

Generate a JWT token for development/testing.

**Authentication:** None

**Request:**
```json
{
  "user_id": "test-user-123"
}
```

**Response (200):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

**Notes:**
- Tokens expire after 1 hour (with sliding refresh on authenticated requests)
- Can be disabled via `DISABLE_DEV_TOKENS=true` environment variable

---

### POST /api/auth/forgot-password

Request a password reset email.

**Authentication:** None

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "message": "If the email exists, a reset link has been sent"
}
```

---

### POST /api/auth/reset-password

Reset password using token from email.

**Authentication:** None

**Request:**
```json
{
  "token": "reset-token-from-email",
  "new_password": "NewSecurePass123!"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "message": "Password reset successful"
}
```

---

## User Endpoints

### GET /api/users/me

Get current authenticated user's profile.

**Authentication:** Required

**Response (200):**
```json
{
  "status": "ok",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "User Name",
    "account_type": "freemium",
    "email_verified": true,
    "freemium_limit": 3,
    "freemium_used": 1,
    "created_at": "2026-01-15T10:00:00Z",
    "last_login": "2026-01-16T14:30:00Z"
  },
  "recent_sessions": [
    {
      "id": "session-uuid",
      "expert_name": "obsesiones",
      "mode": "intake",
      "created_at": "2026-01-16T14:00:00Z"
    }
  ]
}
```

---

### PUT /api/users/me

Update current user's profile.

**Authentication:** Required

**Request:**
```json
{
  "display_name": "New Name",
  "preferences": {
    "theme": "dark",
    "notifications": true
  }
}
```

**Response (200):**
```json
{
  "status": "ok",
  "message": "Profile updated"
}
```

---

### GET /api/users/credits

Get user's available session credits.

**Authentication:** Required

**Response (200):**
```json
{
  "user_id": "uuid",
  "free_remaining": 2,
  "paid_remaining": 5,
  "total_available": 7
}
```

**Credit Types:**
- `free_remaining` - Freemium sessions (5 minutes each, 3 per new user)
- `paid_remaining` - Purchased sessions (45 minutes each)
- `total_available` - Sum of free + paid

---

### GET /api/users/me/preferences

Get user's chat history storage preferences.

**Authentication:** Required

**Response (200):**
```json
{
  "store_history": false,
  "store_history_changed_at": "2026-01-17T10:30:00Z",
  "history_deletion_scheduled_at": "2026-02-16T10:30:00Z"
}
```

**Fields:**
- `store_history` - Whether chat history is being stored
- `store_history_changed_at` - When the preference was last changed
- `history_deletion_scheduled_at` - When history will be deleted (null if not scheduled)

---

### PATCH /api/users/me/preferences

Update user's chat history storage preference.

**Authentication:** Required

**Request:**
```json
{
  "store_history": true
}
```

**Response (200):**
```json
{
  "store_history": true,
  "store_history_changed_at": "2026-01-17T10:30:00Z",
  "history_deletion_scheduled_at": null
}
```

**Behavior:**
- `true → false`: Schedules deletion in 30 days
- `false → true`: Cancels scheduled deletion

---

### GET /api/users/me/sessions

Get user's session history with message counts and previews.

**Authentication:** Required

**Query Parameters:**
- `limit` - Max sessions to return (default 50, max 100)
- `offset` - Number of sessions to skip (default 0)

**Response (200) - History Enabled:**
```json
{
  "sessions": [
    {
      "id": "session-uuid",
      "expert_id": "expert-uuid",
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
```

**Response (200) - History Disabled:**
```json
{
  "sessions": [],
  "total": 0,
  "has_more": false,
  "message": "History storage is disabled"
}
```

---

## Session Endpoints

### POST /api/sessions

Create a new chat session. Consumes one session credit.

**Authentication:** Required

**Request:** Empty body or optional expert_id
```json
{
  "expert_id": "obsesiones"
}
```

**Response (201) - Free Session:**
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

**Response (201) - Paid Session:**
```json
{
  "status": "ok",
  "session": {
    "id": "uuid",
    "mode": "intake",
    "session_type": "paid",
    "duration_minutes": 45,
    "started_at": "2026-01-16T17:18:13Z",
    "expires_at": "2026-01-16T18:03:13Z",
    "status": "active"
  }
}
```

**Response (402) - No Credits:**
```json
{
  "error": "NO_CREDITS",
  "message": "No sessions available. Please purchase more.",
  "free_remaining": 0,
  "paid_remaining": 0
}
```

**Session Types:**
| Type | Duration | Source |
|------|----------|--------|
| `freemium` | 5 minutes | Free sessions for new users |
| `paid` | 45 minutes | Purchased via WooCommerce |
| `test` | 45 minutes | Test/admin-granted sessions |

---

### GET /api/sessions/{session_id}

Get session status including timer information.

**Authentication:** Required

**Response (200) - Active:**
```json
{
  "session_id": "uuid",
  "status": "active",
  "session_type": "freemium",
  "remaining_seconds": 187,
  "expires_at": "2026-01-16T17:23:13Z",
  "started_at": "2026-01-16T17:18:13Z"
}
```

**Response (200) - Expired:**
```json
{
  "session_id": "uuid",
  "status": "expired",
  "session_type": "freemium",
  "remaining_seconds": 0,
  "expires_at": "2026-01-16T17:23:13Z",
  "started_at": "2026-01-16T17:18:13Z",
  "message": "Session has expired"
}
```

**Status Values:**
| Status | Description |
|--------|-------------|
| `active` | Session is in progress |
| `expired` | Time limit reached |
| `ended` | Manually ended by user |

---

### POST /api/sessions/{session_id}/end

Manually end an active session.

**Authentication:** Required

**Response (200):**
```json
{
  "session_id": "uuid",
  "status": "ended",
  "duration_used_seconds": 180
}
```

**Errors:**
- `404` - Session not found
- `400` - Session already ended/expired

---

### GET /api/sessions/{session_id}/messages

Get messages from a specific session.

**Authentication:** Required

**Response (200):**
```json
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

**Error (404):**
Returns 404 if:
- Session not found
- Session belongs to another user
- User has `store_history = false`

```json
{
  "error": "Session not found or history storage disabled"
}
```

---

## AI Processing Endpoints

### POST /api/extract_fields_from_input

Extracts structured mental health data from natural language using OpenAI.

**Authentication:** Required

**Request:**
```json
{
  "message": "I have been feeling overwhelmed for a few weeks. It gets worse at work.",
  "session_id": "abc123"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "fields": {
    "symptoms": "overwhelmed",
    "duration": "a few weeks",
    "triggers": "work",
    "intensity": null,
    "frequency": null,
    "impact_on_life": null,
    "coping_mechanisms": null
  }
}
```

**Fields extracted:**

| Field | Description |
|-------|-------------|
| `symptoms` | What the user is experiencing |
| `duration` | How long symptoms have persisted |
| `triggers` | What causes or worsens symptoms |
| `intensity` | Severity level |
| `frequency` | How often symptoms occur |
| `impact_on_life` | Effects on daily functioning |
| `coping_mechanisms` | Current strategies used |

---

### POST /api/risk_escalation_check

Safety screening using OpenAI moderation API.

**Authentication:** Required

**Request:**
```json
{
  "session_id": "abc123",
  "message": "User message to check for safety concerns"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "flag": null
}
```

**Flags:**

| Flag | Description |
|------|-------------|
| `self-harm` | Self-harm or suicide ideation detected |
| `violence` | Violence or threatening content detected |
| `null` | No safety concerns |

---

### POST /api/switch_chat_mode

Determines conversation state using AI analysis.

**Authentication:** Required

**Request:**
```json
{
  "session_id": "abc123",
  "context": "Conversation history or user message"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "new_mode": "advice"
}
```

**Modes:**

| Mode | Purpose |
|------|---------|
| `intake` | Continue asking diagnostic questions |
| `advice` | Provide coping strategies and support |
| `reflection` | Engage in therapeutic discussion |
| `summary` | Prepare closing and session wrap-up |

---

### POST /api/evaluate_intake_progress

Evaluates if sufficient intake data has been collected.

**Authentication:** Required

**Request:**
```json
{
  "session_id": "abc123",
  "fields": {
    "symptoms": "anxiety",
    "duration": "2 weeks",
    "triggers": null,
    "intensity": null,
    "frequency": null,
    "impact_on_life": "difficulty sleeping",
    "coping_mechanisms": null
  }
}
```

**Response (200):**
```json
{
  "status": "ok",
  "score": 7,
  "enough_data": true
}
```

**Scoring:**

| Field | Weight |
|-------|--------|
| symptoms | 3 |
| duration | 2 |
| triggers | 2 |
| impact_on_life | 2 |
| intensity | 1 |
| frequency | 1 |
| coping_mechanisms | 1 |

**Threshold:** 6 points = intake complete

---

### POST /api/save_session_summary

Persists session summary to the database.

**Authentication:** Required

**Request:**
```json
{
  "session_id": "abc123",
  "summary": "User expressed concerns about persistent anxiety affecting sleep."
}
```

**Response (200):**
```json
{
  "status": "ok"
}
```

**Notes:**
- Summary truncated to 2000 characters if longer
- Uses upsert logic (creates or updates)

---

### POST /api/orchestrators/{function_name}

Start a durable orchestration workflow.

**Authentication:** Required

**Path Parameters:**
- `function_name` - Name of the orchestrator (`mental_health_orchestrator` or `minimal_orchestrator`)

**Request:** Orchestrator-specific payload

**Response:** Durable Functions status URLs for tracking

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "status": "error",
  "message": "Description of what went wrong"
}
```

**HTTP Status Codes:**

| Code | Description |
|------|-------------|
| 400 | Bad request (missing fields, invalid JSON) |
| 401 | Unauthorized (missing or invalid token) |
| 402 | Payment required (no session credits) |
| 403 | Forbidden (feature disabled) |
| 404 | Not found (session/user doesn't exist) |
| 500 | Internal server error |

---

## Example Flows

### Complete Session Flow

```bash
# 1. Login
TOKEN=$(curl -s -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"pass"}' | jq -r '.token')

# 2. Check credits
curl -H "Authorization: Bearer $TOKEN" \
  https://func-gdo-health-prod.azurewebsites.net/api/users/credits

# 3. Create session
SESSION=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  https://func-gdo-health-prod.azurewebsites.net/api/sessions | jq -r '.session.id')

# 4. Check session status (poll for timer)
curl -H "Authorization: Bearer $TOKEN" \
  https://func-gdo-health-prod.azurewebsites.net/api/sessions/$SESSION

# 5. End session
curl -X POST -H "Authorization: Bearer $TOKEN" \
  https://func-gdo-health-prod.azurewebsites.net/api/sessions/$SESSION/end
```

---

*Last updated: 2026-01-18*
