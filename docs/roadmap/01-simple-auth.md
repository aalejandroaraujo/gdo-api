# Phase 1: Simple Authentication

**Status:** COMPLETE

---

## Objective

Implement a lightweight bearer token authentication system to secure the API while the mobile app is being developed. This approach allows rapid iteration without the complexity of a full identity provider.

---

## Architecture

```
Mobile App / Test Client
        │
        ▼
   ┌─────────────────┐
   │ Authorization:  │
   │ Bearer <token>  │
   └─────────────────┘
        │
        ▼
┌───────────────────────────────────┐
│       Azure Function App          │
│  ┌─────────────────────────────┐  │
│  │   Auth Middleware           │  │
│  │   - Validate JWT signature  │  │
│  │   - Check expiration        │  │
│  │   - Extract user_id         │  │
│  └─────────────────────────────┘  │
│              │                    │
│              ▼                    │
│  ┌─────────────────────────────┐  │
│  │   Business Logic            │  │
│  └─────────────────────────────┘  │
└───────────────────────────────────┘
```

---

## Implementation Options

### Option A: API Key per User (Simplest)

**Pros:** Fastest to implement, no external dependencies
**Cons:** No expiration, manual rotation, less secure

```python
# Stored in Key Vault or database
API_KEYS = {
    "dev-key-123": {"user_id": "test-user", "role": "developer"},
    "mobile-key-456": {"user_id": "mobile-app", "role": "app"}
}
```

### Option B: Self-Signed JWT (Recommended for Phase 1)

**Pros:** Industry standard, includes expiration, stateless validation
**Cons:** Need to manage signing key

```python
# Generate tokens with PyJWT
import jwt
from datetime import datetime, timedelta

def create_token(user_id: str, secret: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, secret, algorithm="HS256")
```

### Option C: Azure Function Keys (Built-in)

**Pros:** Already configured, Azure-managed
**Cons:** Not user-specific, harder to revoke individually

---

## Recommended Approach: Option B (Self-Signed JWT)

### Step 1: Add JWT Secret to Key Vault

```bash
# Generate a secure secret
JWT_SECRET=$(openssl rand -base64 32)

# Store in Key Vault
az keyvault secret set \
    --vault-name kv-gdo-health-prod \
    --name "JwtSigningKey" \
    --value "$JWT_SECRET"
```

### Step 2: Create Auth Middleware

Create `src/auth/middleware.py`:

```python
import jwt
import os
from functools import wraps
from azure.functions import HttpRequest, HttpResponse
import json

JWT_SECRET = os.environ.get("JWT_SIGNING_KEY")
JWT_ALGORITHM = "HS256"

class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code

def get_token_from_header(req: HttpRequest) -> str:
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthError("Missing or invalid Authorization header")
    return auth_header[7:]  # Remove "Bearer " prefix

def validate_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")

def require_auth(func):
    @wraps(func)
    async def wrapper(req: HttpRequest, *args, **kwargs):
        try:
            token = get_token_from_header(req)
            payload = validate_token(token)
            req.user = payload  # Attach user info to request
            return await func(req, *args, **kwargs)
        except AuthError as e:
            return HttpResponse(
                json.dumps({"error": e.message}),
                status_code=e.status_code,
                mimetype="application/json"
            )
    return wrapper
```

### Step 3: Create Token Endpoint

Create a `/api/auth/token` endpoint for development/testing:

```python
@app.function_name("GetDevToken")
@app.route(route="auth/dev-token", methods=["POST"])
async def get_dev_token(req: HttpRequest) -> HttpResponse:
    """
    Development-only endpoint to generate tokens.
    DISABLE IN PRODUCTION or restrict to admin users.
    """
    body = req.get_json()
    user_id = body.get("user_id")

    if not user_id:
        return HttpResponse(
            json.dumps({"error": "user_id required"}),
            status_code=400
        )

    token = create_token(user_id, JWT_SECRET)
    return HttpResponse(
        json.dumps({"token": token, "expires_in": 86400}),
        mimetype="application/json"
    )
```

### Step 4: Apply Auth to Protected Endpoints

```python
from src.auth.middleware import require_auth

@app.function_name("ExtractFieldsFromInput")
@app.route(route="extract_fields_from_input", methods=["POST"])
@require_auth
async def extract_fields_from_input(req: HttpRequest) -> HttpResponse:
    user_id = req.user["sub"]  # Access authenticated user
    # ... rest of function
```

---

## Tasks Checklist

- [x] Add `PyJWT` to `requirements.txt`
- [x] Generate and store JWT signing key in Key Vault
- [x] Create `src/auth/` module with middleware
- [x] Create dev token endpoint (for testing)
- [x] Apply `@require_auth` decorator to protected endpoints
- [x] Update Function App settings to include `JWT_SIGNING_KEY` reference
- [x] Test with curl/Postman
- [x] Document token usage in API docs

---

## Security Considerations

1. **Token Expiration:** 24 hours for development, reduce for production
2. **HTTPS Only:** Azure Functions enforce HTTPS by default
3. **Key Rotation:** Plan for periodic JWT secret rotation
4. **Rate Limiting:** Consider adding rate limits per user
5. **Disable Dev Endpoint:** Remove `/auth/dev-token` before production

---

## Migration Path to Phase 3

When migrating to Microsoft Entra External ID:

1. Keep the middleware structure
2. Replace self-signed JWT validation with Entra token validation
3. Update `validate_token()` to verify Entra-issued tokens
4. Remove dev token endpoint

---

## Dependencies

```txt
# Add to requirements.txt
PyJWT>=2.8.0
```

---

*Next Phase: [02-function-app-deployment.md](./02-function-app-deployment.md)*
