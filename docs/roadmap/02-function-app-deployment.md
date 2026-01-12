# Phase 2: Function App Deployment & PostgreSQL Migration

**Status:** In Progress

---

## Objective

Deploy the Function App to Azure and migrate data persistence from NocoDB to PostgreSQL.

**Detailed Migration Plan:** [MIGRATION-PLAN.md](./MIGRATION-PLAN.md)

---

## Progress

### Completed

- [x] Auth middleware implemented (Phase 1)
- [x] `asyncpg` and `PyJWT` added to requirements.txt
- [x] Auth integrated into all protected endpoints
- [x] Function App deployed to Azure
- [x] JWT_SIGNING_KEY configured via Key Vault reference
- [x] OPENAI_API_KEY configured via Key Vault reference
- [x] Health endpoint verified (`/api/test`)
- [x] Protected endpoints working with JWT tokens
- [x] All deployment tests passed

### Remaining

- [ ] Create PostgreSQL client module (`src/db/`)
- [ ] Replace NocoDB with PostgreSQL queries
- [ ] Define and implement user registration flow
- [ ] Test database connectivity from Function App
- [ ] Migrate existing session data (if any)

---

## Part A: Deployment (COMPLETE)

### Deployment Command

```bash
func azure functionapp publish func-gdo-health-prod
```

### App Settings Configured

| Setting | Source |
|---------|--------|
| `JWT_SIGNING_KEY` | Key Vault: `JwtSigningKey` |
| `OPENAI_API_KEY` | Key Vault: `OpenAiApiKey` |
| `POSTGRES_HOST` | `psql-gdo-health-prod.postgres.database.azure.com` |
| `POSTGRES_DB` | `gdohealth` |
| `POSTGRES_USER` | `gdoadmin` |
| `POSTGRES_PASSWORD` | Key Vault: `PostgresPassword` |

### Deployed Endpoints

| Endpoint | Status |
|----------|--------|
| `GET /api/test` | Working |
| `POST /api/auth/dev-token` | Working |
| `POST /api/extract_fields_from_input` | Working (with auth) |
| `POST /api/risk_escalation_check` | Working (with auth) |
| `POST /api/switch_chat_mode` | Working (with auth) |
| `POST /api/evaluate_intake_progress` | Working (with auth) |
| `POST /api/save_session_summary` | Working (with auth) - uses NocoDB |

---

## Part B: PostgreSQL Migration (TODO)

### Current State

The `save_session_summary` endpoint currently uses NocoDB via `nocodb_upsert()` in `src/shared/common.py`. This needs to be replaced with PostgreSQL.

### Step 1: Create Database Module

Create `src/db/__init__.py`:

```python
"""Database module for PostgreSQL connectivity."""
from .postgres import get_pool, close_pool
from .queries import save_session, get_session, create_user, get_user

__all__ = ["get_pool", "close_pool", "save_session", "get_session", "create_user", "get_user"]
```

Create `src/db/postgres.py`:

```python
"""PostgreSQL connection pool management."""
import os
import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    """Get or create the database connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.environ["POSTGRES_HOST"],
            database=os.environ.get("POSTGRES_DB", "gdohealth"),
            user=os.environ.get("POSTGRES_USER", "gdoadmin"),
            password=os.environ["POSTGRES_PASSWORD"],
            ssl="require",
            min_size=1,
            max_size=10
        )
    return _pool

async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
```

Create `src/db/queries.py`:

```python
"""Database query functions."""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from .postgres import get_pool

async def create_user(external_id: str, email: Optional[str] = None) -> Dict[str, Any]:
    """Create a new user and return user data."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_id = uuid.uuid4()
        row = await conn.fetchrow("""
            INSERT INTO users (id, external_id, email, created_at)
            VALUES ($1, $2, $3, NOW())
            RETURNING id, external_id, email, created_at
        """, user_id, external_id, email)
        return dict(row)

async def get_user(external_id: str) -> Optional[Dict[str, Any]]:
    """Get user by external ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, external_id, email, created_at
            FROM users WHERE external_id = $1
        """, external_id)
        return dict(row) if row else None

async def get_or_create_user(external_id: str) -> Dict[str, Any]:
    """Get existing user or create new one."""
    user = await get_user(external_id)
    if user:
        return user
    return await create_user(external_id)

async def save_session(session_id: str, user_id: uuid.UUID, summary: str) -> None:
    """Save or update session summary."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO session_summaries (id, session_id, user_id, summary, created_at)
            VALUES (gen_random_uuid(), $1, $2, $3, NOW())
            ON CONFLICT (session_id)
            DO UPDATE SET summary = $3, created_at = NOW()
        """, session_id, user_id, summary[:2000])  # Truncate to 2000 chars

async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT s.*, ss.summary
            FROM sessions s
            LEFT JOIN session_summaries ss ON s.id = ss.session_id
            WHERE s.id = $1
        """, session_id)
        return dict(row) if row else None
```

### Step 2: Update Function App

Replace NocoDB calls in `function_app.py`:

```python
# Before
from src.shared.common import nocodb_upsert

# After
from src.db import save_session, get_or_create_user
```

### Step 3: Update save_session_summary Endpoint

```python
@app.function_name("SaveSessionSummary")
@app.route(route="save_session_summary", methods=["POST"])
@require_auth
async def save_session_summary(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        session_id = req_body.get("session_id")
        summary = req_body.get("summary", "")

        # Get user from JWT token
        user_id = req.user["sub"]

        # Get or create user in database
        user = await get_or_create_user(user_id)

        # Save session summary
        await save_session(session_id, user["id"], summary)

        return func.HttpResponse(
            json.dumps({"status": "ok"}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Error saving session: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
```

---

## Part C: User Journey Design (TODO)

### Questions to Answer

1. **User Identity Source**
   - Will users come from WordPress, mobile app, or both?
   - Do we need to sync users between WordPress and PostgreSQL?

2. **Registration Flow**
   - Should `/auth/dev-token` create users automatically?
   - Or should there be a separate `/auth/register` endpoint?

3. **User Data**
   - What data do we store? (email, name, preferences)
   - What comes from WordPress vs mobile app?

### Proposed Flow (Simple)

```
Mobile App First Launch
        │
        ▼
Generate device UUID
        │
        ▼
POST /api/auth/dev-token
{"user_id": "device-uuid-123"}
        │
        ▼
Backend: get_or_create_user()
        │
        ▼
Return JWT token
        │
        ▼
App stores token securely
```

This creates "anonymous" users identified by device. Later, with Entra External ID (Phase 3), users can link their account to an email/social login.

---

## Verification Steps

### Test Database Connectivity

```bash
# From Function App logs
az functionapp log tail \
    --name func-gdo-health-prod \
    --resource-group rg-gdo-health-prod

# Look for connection errors after calling save_session_summary
```

### Test Save Session

```bash
TOKEN=$(curl -s -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/dev-token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user"}' | jq -r '.token')

curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/save_session_summary \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-123", "summary": "Test session summary"}'
```

### Verify in Database

```bash
psql "host=psql-gdo-health-prod.postgres.database.azure.com dbname=gdohealth user=gdoadmin sslmode=require"

SELECT * FROM users;
SELECT * FROM session_summaries;
```

---

## Tasks Checklist

### Deployment (DONE)
- [x] Deploy Function App to Azure
- [x] Configure JWT_SIGNING_KEY
- [x] Configure OPENAI_API_KEY
- [x] Verify all endpoints working

### PostgreSQL Migration (TODO)
- [ ] Create `src/db/` module
- [ ] Implement connection pool
- [ ] Implement user queries
- [ ] Implement session queries
- [ ] Replace `nocodb_upsert` with PostgreSQL
- [ ] Test locally
- [ ] Deploy and test in Azure
- [ ] Remove NocoDB code

### User Journey (TODO)
- [ ] Decide on user registration approach
- [ ] Implement user creation in `/auth/dev-token`
- [ ] Document user flow

---

*Previous Phase: [01-simple-auth.md](./01-simple-auth.md)*
*Next Phase: [03-entra-external-id.md](./03-entra-external-id.md)*
