# API Reference

All endpoints require `x-functions-key` header for authentication (function-level auth).

Base URL: `https://<your-function-app>.azurewebsites.net/api`

---

## extract_fields_from_input

Extracts structured mental health data from natural language using OpenAI.

**Endpoint:** `POST /api/extract_fields_from_input`

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
- `symptoms` - What the user is experiencing
- `duration` - How long symptoms have persisted
- `triggers` - What causes or worsens symptoms
- `intensity` - Severity level
- `frequency` - How often symptoms occur
- `impact_on_life` - Effects on daily functioning
- `coping_mechanisms` - Current strategies used

---

## risk_escalation_check

Safety screening using OpenAI moderation API.

**Endpoint:** `POST /api/risk_escalation_check`

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
  "flag": "self-harm" | "violence" | null
}
```

**Flags:**
- `self-harm` - Self-harm or suicide ideation detected
- `violence` - Violence or threatening content detected
- `null` - No safety concerns

---

## switch_chat_mode

Determines conversation state using AI analysis.

**Endpoint:** `POST /api/switch_chat_mode`

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
  "new_mode": "intake" | "advice" | "reflection" | "summary"
}
```

**Modes:**
- `intake` - Continue asking diagnostic questions
- `advice` - Provide coping strategies and support
- `reflection` - Engage in therapeutic discussion
- `summary` - Prepare closing and session wrap-up

---

## evaluate_intake_progress

Evaluates if sufficient intake data has been collected.

**Endpoint:** `POST /api/evaluate_intake_progress`

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

Threshold: 6 points = intake complete

---

## save_session_summary

Persists session summary to NocoDB.

**Endpoint:** `POST /api/save_session_summary`

**Request:**
```json
{
  "session_id": "abc123",
  "summary": "User expressed concerns about persistent anxiety affecting sleep. Discussed breathing exercises as coping strategy."
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

## test

Health check endpoint.

**Endpoint:** `GET /api/test`

**Response:** `Hello World! Function detected successfully!`

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
- `400` - Bad request (missing fields, invalid JSON)
- `500` - Internal server error (API failures)
