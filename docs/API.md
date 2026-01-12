# API Reference

## Base URL

**Production:** `https://func-gdo-health-prod.azurewebsites.net/api`

---

## Authentication

All protected endpoints require JWT Bearer token authentication.

### Getting a Token

**Endpoint:** `POST /api/auth/dev-token`

> **Note:** This is a development endpoint. In production, tokens will be issued by Microsoft Entra External ID.

**Request:**
```json
{
  "user_id": "your-user-id"
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

### Using the Token

Include the token in the `Authorization` header for all protected endpoints:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

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
| `/api/auth/dev-token` | POST | Get development token |

### Protected Endpoints (Auth Required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/extract_fields_from_input` | POST | Extract structured fields from text |
| `/api/risk_escalation_check` | POST | Safety screening |
| `/api/switch_chat_mode` | POST | Determine conversation mode |
| `/api/evaluate_intake_progress` | POST | Check intake completeness |
| `/api/save_session_summary` | POST | Persist session summary |
| `/api/orchestrators/{name}` | POST | Start durable orchestration |

---

## Endpoint Details

### GET /api/test

Health check endpoint to verify the API is running.

**Authentication:** None

**Response:** `Hello World! Function detected successfully!`

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

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

**Notes:**
- Tokens expire after 24 hours
- Can be disabled via `DISABLE_DEV_TOKENS=true` environment variable

---

### POST /api/extract_fields_from_input

Extracts structured mental health data from natural language using OpenAI gpt-4.1-mini.

**Authentication:** Required

**Request:**
```json
{
  "message": "I have been feeling overwhelmed for a few weeks. It gets worse at work.",
  "session_id": "abc123"
}
```

**Response:**
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

**Response:**
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

Determines conversation state using AI analysis (gpt-4.1-mini).

**Authentication:** Required

**Request:**
```json
{
  "session_id": "abc123",
  "context": "Conversation history or user message"
}
```

**Response:**
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

**Response:**
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

**Response:**
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
| 403 | Forbidden (feature disabled) |
| 500 | Internal server error (API failures) |

---

## Example: Complete Authentication Flow

```bash
# 1. Get a token
TOKEN=$(curl -s -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/dev-token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "my-user"}' | jq -r '.token')

# 2. Call a protected endpoint
curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/evaluate_intake_progress \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "fields": {"symptoms": "anxiety"}}'
```

---

*Last updated: 2026-01-12*
