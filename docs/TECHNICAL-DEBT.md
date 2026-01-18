# Technical Debt & Incomplete Features

**Last Updated:** 2026-01-18
**Audit Performed By:** Development Team

---

## Critical Items (Security/Production Risk)

### 1. ~~Password Reset Token Logged in Production~~ FIXED (2026-01-17)
**Location:** [function_app.py:519](function_app.py#L519)
**Status:** RESOLVED - Token no longer logged, only email address logged for audit

---

### 1b. ~~JWT Token Expiry Too Long (24h)~~ FIXED (2026-01-18)
**Location:** [src/auth/middleware.py](src/auth/middleware.py)
**Previous:** Tokens expired after 24 hours - excessive exposure window if compromised
**Status:** RESOLVED - Implemented 1-hour tokens with sliding expiration
**Details:**
- Token lifetime: 1 hour
- Refresh threshold: 30 minutes remaining
- When token has < 30 min left, new token returned in `X-New-Token` header
- Client updates stored token automatically
- See [docs/API.md](API.md#token-expiration--sliding-refresh) for client implementation

---

### 2. Email Sending Not Implemented (TODO)
**Location:** [function_app.py:517](function_app.py#L517)
```python
# TODO: Send email with reset link
```
**Impact:** Password reset flow is incomplete - users cannot actually reset passwords
**Action Required:** Integrate email service (SendGrid, Azure Communication Services, etc.)
**Endpoints Affected:**
- `POST /api/auth/forgot-password` - generates token but doesn't send email

---

## Stubs & Placeholders

### 3. Legacy Storage Stub (Unused)
**Location:** [src/shared/storage.py](src/shared/storage.py)
```python
def save_session_summary(...):
    """Placeholder stub for saving a chat session summary."""
    # Only logs, doesn't actually save
```
**Status:** This file appears to be legacy/unused - actual session storage uses `src/db/sessions.py`
**Action:** Verify not used anywhere and remove, OR implement if needed

---

## Incomplete Features

### 4. Email Verification Flow Not Exposed
**Database:** Has columns `verification_token`, `verification_expires`
**DB Function:** `set_verification_token()` exists in [src/db/users.py:224](src/db/users.py#L224)
**API:** No endpoint to:
- Send verification email
- Verify email via token link

**Status:** Database and helper function ready, but no API endpoint
**Impact:** `email_verified` column always stays `FALSE` for self-registered users

---

### 5. Experts Table Not Populated
**Evidence:**
- Sessions reference `expert_id` foreign key
- Code uses `LEFT JOIN experts` to handle NULL
- No migration creates expert data
- No admin endpoint to manage experts

**Impact:** `expert_name` always returns `null` in session history
**Action:** Create migration to seed experts OR admin endpoint to manage them

---

## Technical Debt

### 6. No Automated Tests
**Location:** No `tests/` directory in project (only `.venv` has vendor tests)
**Risk:** MEDIUM - No unit tests, integration tests, or API tests
**Impact:** Regressions can go unnoticed; refactoring is risky
**Recommendation:** Add pytest with:
- Unit tests for `src/db/*.py` functions
- Integration tests for API endpoints
- Mock database for CI/CD

---

### 7. Durable Functions Orchestrators Exist But Unclear Usage
**Location:** [function_app.py](function_app.py) contains:
- `ExpertRoutingOrchestrator`
- `GracefulExitOrchestrator`
- Various activity functions

**Status:** These appear to be for the chat/AI workflow, but the HTTP trigger (`StartOrchestration`) is generic
**Question:** Are these actively used or legacy from initial setup?
**Action:** Document or remove if not used

---

### 8. ~~Inconsistent Error Response Format~~ FIXED (2026-01-17)
**Status:** RESOLVED - All endpoints now use `{"status": "error", "message": "..."}`

---

## Documentation TODOs (In Roadmap Files)

**Location:** [docs/roadmap/02-function-app-deployment.md](docs/roadmap/02-function-app-deployment.md)

- Line 72: `## Part B: PostgreSQL Migration (TODO)`
- Line 234: `## Part C: User Journey Design (TODO)`
- Line 321: `### PostgreSQL Migration (TODO)`
- Line 331: `### User Journey (TODO)`

**Status:** These are documentation placeholders, not code issues

---

## Low Priority / Future Improvements

### 9. Invalid expert_id Silently Ignored
**Location:** [function_app.py:684](function_app.py#L684)
```python
pass  # Invalid expert_id, ignore
```
**Context:** When creating session with invalid expert UUID
**Current behavior:** Silently ignores, creates session without expert
**Alternative:** Return 400 Bad Request
**Recommendation:** Keep as-is (graceful degradation) but add logging

---

### 10. History Deletion Job Not Manually Testable
**Location:** `HistoryDeletionJob` timer trigger
**Issue:** Can only test by:
1. Waiting 30 days, OR
2. Manually updating `history_deletion_scheduled_at` in database

**Recommendation:** Add admin endpoint for manual trigger (development only)

---

## Summary Table

| Item | Severity | Type | Status |
|------|----------|------|--------|
| ~~Password reset token logged~~ | HIGH | Security | FIXED 2026-01-17 |
| ~~JWT 24h expiry too long~~ | MEDIUM | Security | FIXED 2026-01-18 |
| Email sending TODO | HIGH | Missing feature | Needs implementation |
| Legacy storage.py stub | LOW | Dead code | Verify & remove |
| Email verification not exposed | MEDIUM | Incomplete | Needs API endpoint |
| Experts table empty | LOW | Data | Needs seeding |
| No automated tests | MEDIUM | Technical debt | Add pytest |
| Orchestrator usage unclear | LOW | Documentation | Clarify or remove |
| ~~Inconsistent error format~~ | LOW | Technical debt | FIXED 2026-01-17 |

---

## Recommended Priority Order

1. **Before Production:**
   - ~~Remove password reset token logging~~ DONE
   - ~~Reduce JWT token expiry (24h → 1h with sliding refresh)~~ DONE
   - Implement email sending (SendGrid/ACS)
   - Add email verification endpoint

2. **Soon After Launch:**
   - Add automated tests
   - Seed experts table
   - ~~Standardize error responses~~ DONE

3. **Future Maintenance:**
   - Clean up legacy storage.py
   - Document or remove unused orchestrators
   - Complete roadmap documentation
