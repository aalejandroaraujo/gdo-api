"""
Azure Functions - Mental Health Triage Platform
================================================
v2 decorator model implementation consolidating all functions.

Functions:
- test_function: Health check endpoint
- get_dev_token: Development token endpoint (Phase 1 auth)
- register: User registration with email/password
- login: User login with email/password
- get_current_user: Get current user profile
- sync_wordpress_user_endpoint: Internal endpoint for WordPress user sync
- evaluate_intake_progress: Scores collected intake data
- extract_fields_from_input: Extracts structured fields using OpenAI
- risk_escalation_check: Safety screening via OpenAI moderation
- save_session_summary: Persists sessions to PostgreSQL
- switch_chat_mode: Determines conversation mode using AI
- mental_health_orchestrator: Durable orchestrator for the workflow
- minimal_orchestrator: Simple test orchestrator
"""

import json
import logging
import os
import uuid
from datetime import timedelta

import azure.functions as func
import azure.durable_functions as df
import asyncpg

from src.shared.common import get_openai_client
from src.auth import require_auth, create_token, AuthError, TOKEN_EXPIRY_HOURS
from src.db import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_reset_token,
    update_last_login,
    update_user_password,
    update_user_profile,
    set_password_reset_token,
    save_session_summary as db_save_session_summary,
    get_user_sessions,
    create_session,
    get_session_by_id,
    update_session_status,
    end_session,
    get_user_credits,
    consume_session_credit,
    sync_wordpress_user,
    get_user_preferences,
    update_user_preferences,
    get_user_sessions_for_history,
    get_session_messages,
    delete_user_history,
    get_users_pending_deletion,
    clear_deletion_schedule,
)
from src.db.users import verify_password
from datetime import datetime, timezone


# Create the Durable Functions app instance
app = df.DFApp()


# =============================================================================
# HTTP FUNCTIONS
# =============================================================================

@app.function_name("TestFunction")
@app.route(route="test", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def test_function(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint to verify Azure Functions detection."""
    return func.HttpResponse("Hello World! Function detected successfully!")


@app.function_name("GetDevToken")
@app.route(route="auth/dev-token", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def get_dev_token(req: func.HttpRequest) -> func.HttpResponse:
    """
    Development token endpoint for testing authentication.

    WARNING: This endpoint should be disabled or restricted in production.
    It allows generating tokens for any user_id without verification.

    Request body:
        {"user_id": "test-user-123"}

    Response:
        {"token": "eyJ...", "expires_in": 3600, "token_type": "Bearer"}
    """
    # Check if dev tokens are enabled (default: enabled for now)
    if os.environ.get("DISABLE_DEV_TOKENS", "").lower() == "true":
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Dev tokens are disabled"}),
            status_code=403,
            mimetype="application/json"
        )

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    user_id = req_body.get("user_id") if req_body else None

    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "user_id is required"}),
            status_code=400,
            mimetype="application/json"
        )

    try:
        token = create_token(user_id.strip())
        return func.HttpResponse(
            json.dumps({
                "token": token,
                "expires_in": TOKEN_EXPIRY_HOURS * 3600,
                "token_type": "Bearer"
            }),
            status_code=200,
            mimetype="application/json"
        )
    except AuthError as e:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": e.message}),
            status_code=e.status_code,
            mimetype="application/json"
        )


@app.function_name("Register")
@app.route(route="auth/register", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def register(req: func.HttpRequest) -> func.HttpResponse:
    """
    Register a new user with email and password.

    Request body:
        {
            "email": "user@example.com",
            "password": "securepassword",
            "display_name": "John Doe" (optional),
            "store_history_consent": true|false (optional, default false)
        }

    Response:
        {"status": "ok", "user_id": "uuid", "message": "Registration successful"}
    """
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json"
            )

        email = req_body.get("email", "").strip().lower() if req_body else ""
        password = req_body.get("password", "") if req_body else ""
        display_name = req_body.get("display_name", "").strip() if req_body else None
        store_history_consent = req_body.get("store_history_consent", False) if req_body else False

        # Validate store_history_consent is boolean
        if not isinstance(store_history_consent, bool):
            store_history_consent = False

        # Validation
        if not email:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Email is required"}),
                status_code=400,
                mimetype="application/json"
            )

        if "@" not in email or "." not in email:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid email format"}),
                status_code=400,
                mimetype="application/json"
            )

        if not password or len(password) < 8:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Password must be at least 8 characters"}),
                status_code=400,
                mimetype="application/json"
            )

        # Check if user already exists
        existing_user = await get_user_by_email(email)
        if existing_user:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Email already registered"}),
                status_code=409,
                mimetype="application/json"
            )

        # Create user with history consent preference
        user = await create_user(email, password, display_name, store_history=store_history_consent)

        logging.info(f"New user registered: {user['id']}, store_history={store_history_consent}")

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "user_id": str(user["id"]),
                "message": "Registration successful"
            }),
            status_code=201,
            mimetype="application/json"
        )

    except asyncpg.UniqueViolationError:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Email already registered"}),
            status_code=409,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Registration error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Registration failed"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("Login")
@app.route(route="auth/login", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def login(req: func.HttpRequest) -> func.HttpResponse:
    """
    Login with email and password.

    Request body:
        {"email": "user@example.com", "password": "securepassword"}

    Response:
        {"token": "eyJ...", "expires_in": 3600, "token_type": "Bearer", "user": {...}}

    Token Refresh (Sliding Expiration):
        Tokens expire in 1 hour. When making authenticated requests, if the token
        has < 30 minutes remaining, the server returns a new token in the
        X-New-Token response header. Client should replace stored token.
    """
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json"
            )

        email = req_body.get("email", "").strip().lower() if req_body else ""
        password = req_body.get("password", "") if req_body else ""

        if not email or not password:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Email and password are required"}),
                status_code=400,
                mimetype="application/json"
            )

        # Get user
        user = await get_user_by_email(email)
        if not user:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid email or password"}),
                status_code=401,
                mimetype="application/json"
            )

        # Verify password
        if not user.get("password_hash") or not verify_password(password, user["password_hash"]):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid email or password"}),
                status_code=401,
                mimetype="application/json"
            )

        # Update last login
        await update_last_login(user["id"])

        # Create token
        token = create_token(str(user["id"]))

        logging.info(f"User logged in: {user['id']}")

        return func.HttpResponse(
            json.dumps({
                "token": token,
                "expires_in": TOKEN_EXPIRY_HOURS * 3600,
                "token_type": "Bearer",
                "user": {
                    "id": str(user["id"]),
                    "email": user["email"],
                    "display_name": user.get("display_name"),
                    "account_type": user.get("account_type", "freemium"),
                }
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Login failed"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("GetCurrentUser")
@app.route(route="users/me", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def get_current_user(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get current user profile.

    Requires: Bearer token authentication

    Response:
        {"status": "ok", "user": {...}, "sessions": {...}}
    """
    try:
        user_id = req.user.get("sub")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        user = await get_user_by_id(user_uuid)
        if not user:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "User not found"}),
                status_code=404,
                mimetype="application/json"
            )

        # Get recent sessions
        sessions = await get_user_sessions(user_uuid, limit=5)

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "user": {
                    "id": str(user["id"]),
                    "email": user["email"],
                    "display_name": user.get("display_name"),
                    "account_type": user.get("account_type", "freemium"),
                    "email_verified": user.get("email_verified", False),
                    "freemium_limit": user.get("freemium_limit", 3),
                    "freemium_used": user.get("freemium_used", 0),
                    "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
                    "last_login": user["last_login"].isoformat() if user.get("last_login") else None,
                },
                "recent_sessions": [
                    {
                        "id": str(s["id"]),
                        "expert_name": s.get("expert_name"),
                        "mode": s.get("mode"),
                        "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
                    }
                    for s in sessions
                ]
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Get user error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to get user profile"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("UpdateCurrentUser")
@app.route(route="users/me", methods=["PATCH"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def update_current_user(req: func.HttpRequest) -> func.HttpResponse:
    """
    Update current user profile.

    Requires: Bearer token authentication

    Request body:
        {"display_name": "New Name"}

    Response:
        {"status": "ok", "user": {...}}
    """
    try:
        user_id = req.user.get("sub")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required"}),
                status_code=400,
                mimetype="application/json"
            )

        display_name = req_body.get("display_name")

        if display_name is not None and (not isinstance(display_name, str) or len(display_name.strip()) == 0):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "display_name must be a non-empty string"}),
                status_code=400,
                mimetype="application/json"
            )

        user = await update_user_profile(user_uuid, display_name=display_name.strip() if display_name else None)

        if not user:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "User not found"}),
                status_code=404,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "user": {
                    "id": str(user["id"]),
                    "email": user["email"],
                    "display_name": user.get("display_name"),
                    "account_type": user.get("account_type", "freemium"),
                    "email_verified": user.get("email_verified", False),
                }
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Update user error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to update user profile"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("ForgotPassword")
@app.route(route="auth/forgot-password", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def forgot_password(req: func.HttpRequest) -> func.HttpResponse:
    """
    Request password reset.

    Request body:
        {"email": "user@example.com"}

    Response:
        {"status": "ok", "message": "If the email exists, a reset link will be sent"}

    Note: Always returns success to prevent email enumeration.
    In production, this would send an email with the reset token.
    """
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json"
            )

        email = req_body.get("email", "").strip().lower() if req_body else ""

        if not email or "@" not in email:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Valid email is required"}),
                status_code=400,
                mimetype="application/json"
            )

        # Generate reset token
        import secrets
        reset_token = secrets.token_urlsafe(32)

        # Try to set the token (will fail silently if email doesn't exist)
        user_exists = await set_password_reset_token(email, reset_token, expires_hours=1)

        if user_exists:
            # TODO: Integrate email service (SendGrid/Azure Communication Services)
            # to send password reset link to user
            logging.info(f"Password reset requested for {email}")

        # Always return success to prevent email enumeration
        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "message": "If the email exists, a reset link will be sent"
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Forgot password error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Request failed"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("ResetPassword")
@app.route(route="auth/reset-password", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def reset_password(req: func.HttpRequest) -> func.HttpResponse:
    """
    Reset password using token.

    Request body:
        {"token": "reset-token", "password": "newpassword123"}

    Response:
        {"status": "ok", "message": "Password reset successfully"}
    """
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required"}),
                status_code=400,
                mimetype="application/json"
            )

        token = req_body.get("token", "").strip()
        password = req_body.get("password", "")

        if not token:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Reset token is required"}),
                status_code=400,
                mimetype="application/json"
            )

        if not password or len(password) < 8:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Password must be at least 8 characters"}),
                status_code=400,
                mimetype="application/json"
            )

        # Validate token and get user
        user = await get_user_by_reset_token(token)
        if not user:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid or expired reset token"}),
                status_code=400,
                mimetype="application/json"
            )

        # Update password
        success = await update_user_password(user["id"], password)
        if not success:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Failed to update password"}),
                status_code=500,
                mimetype="application/json"
            )

        logging.info(f"Password reset for user: {user['id']}")

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "message": "Password reset successfully"
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Reset password error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Password reset failed"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("CreateSession")
@app.route(route="sessions", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def create_session_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Start a new chat session with timer.

    Requires: Bearer token authentication

    Consumes a session credit (free first, then paid).
    Returns 402 if no credits available.

    Request body (optional):
        {"expert_id": "uuid"}

    Response (201):
        {
            "status": "ok",
            "session": {
                "id": "uuid",
                "mode": "intake",
                "session_type": "freemium",
                "duration_minutes": 5,
                "started_at": "2026-01-15T23:00:00Z",
                "expires_at": "2026-01-15T23:05:00Z",
                "status": "active"
            }
        }

    Error (402):
        {
            "error": "NO_CREDITS",
            "message": "No sessions available. Please purchase more.",
            "free_remaining": 0,
            "paid_remaining": 0
        }
    """
    try:
        user_id = req.user.get("sub")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        try:
            req_body = req.get_json()
        except ValueError:
            req_body = {}

        # Parse optional expert_id
        expert_id = None
        if req_body and req_body.get("expert_id"):
            try:
                expert_id = uuid.UUID(req_body["expert_id"])
            except (ValueError, TypeError):
                pass  # Invalid expert_id, ignore

        # Consume a session credit (atomic operation)
        credit_result = await consume_session_credit(user_uuid, expert_id)

        if not credit_result["success"]:
            # No credits available - return 402 Payment Required
            credits = await get_user_credits(user_uuid)
            return func.HttpResponse(
                json.dumps({
                    "error": "NO_CREDITS",
                    "message": "No sessions available. Please purchase more.",
                    "free_remaining": credits["free_remaining"],
                    "paid_remaining": credits["paid_remaining"],
                }),
                status_code=402,
                mimetype="application/json"
            )

        # Create session with timer
        session = await create_session(
            user_uuid,
            expert_id=expert_id,
            session_type=credit_result["session_type"],
            duration_minutes=credit_result["duration_minutes"],
        )

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "session": {
                    "id": str(session["id"]),
                    "mode": session.get("mode", "intake"),
                    "session_type": session.get("session_type"),
                    "duration_minutes": session.get("duration_minutes"),
                    "started_at": session["created_at"].isoformat() if session.get("created_at") else None,
                    "expires_at": session["expires_at"].isoformat() if session.get("expires_at") else None,
                    "status": session.get("status", "active"),
                }
            }),
            status_code=201,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Create session error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to create session"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("GetSession")
@app.route(route="sessions/{session_id}", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def get_session_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get session status with remaining time.

    Requires: Bearer token authentication

    Response (active):
        {
            "session_id": "uuid",
            "status": "active",
            "session_type": "freemium",
            "remaining_seconds": 187,
            "expires_at": "2026-01-15T23:05:00Z",
            "started_at": "2026-01-15T23:00:00Z"
        }

    Response (expired):
        {
            "session_id": "uuid",
            "status": "expired",
            "session_type": "freemium",
            "remaining_seconds": 0,
            "expires_at": "2026-01-15T23:05:00Z",
            "message": "Session has expired"
        }
    """
    try:
        user_id = req.user.get("sub")
        session_id_str = req.route_params.get("session_id")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        try:
            session_uuid = uuid.UUID(session_id_str)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid session ID"}),
                status_code=400,
                mimetype="application/json"
            )

        # Get session
        session = await get_session_by_id(session_uuid)

        if not session:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Session not found"}),
                status_code=404,
                mimetype="application/json"
            )

        # Check ownership
        if str(session["user_id"]) != user_id:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Not authorized"}),
                status_code=403,
                mimetype="application/json"
            )

        now = datetime.now(timezone.utc)
        status = session.get("status", "active")
        expires_at = session.get("expires_at")

        # Check if expired
        if status == "active" and expires_at and now >= expires_at:
            status = "expired"
            await update_session_status(session_uuid, "expired")

        # Calculate remaining time
        remaining_seconds = 0
        if expires_at and status == "active":
            remaining_seconds = max(0, int((expires_at - now).total_seconds()))

        response = {
            "session_id": str(session["id"]),
            "status": status,
            "session_type": session.get("session_type"),
            "remaining_seconds": remaining_seconds,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "started_at": session["created_at"].isoformat() if session.get("created_at") else None,
        }

        if status == "expired":
            response["message"] = "Session has expired"

        return func.HttpResponse(
            json.dumps(response),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Get session error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to get session"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("EndSession")
@app.route(route="sessions/{session_id}/end", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def end_session_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    End a session manually.

    Requires: Bearer token authentication

    Response (200):
        {
            "session_id": "uuid",
            "status": "ended",
            "duration_used_seconds": 180
        }
    """
    try:
        user_id = req.user.get("sub")
        session_id_str = req.route_params.get("session_id")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        try:
            session_uuid = uuid.UUID(session_id_str)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid session ID"}),
                status_code=400,
                mimetype="application/json"
            )

        # Get session to check ownership
        session = await get_session_by_id(session_uuid)

        if not session:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Session not found"}),
                status_code=404,
                mimetype="application/json"
            )

        # Check ownership
        if str(session["user_id"]) != user_id:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Not authorized"}),
                status_code=403,
                mimetype="application/json"
            )

        # Check if already ended
        if session.get("status") == "ended":
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Session already ended"}),
                status_code=400,
                mimetype="application/json"
            )

        # End the session
        result = await end_session(session_uuid)

        if not result:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Failed to end session"}),
                status_code=500,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"End session error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to end session"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("GetUserCredits")
@app.route(route="users/credits", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def get_user_credits_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get user's available session credits.

    Requires: Bearer token authentication

    Response (200):
        {
            "user_id": "uuid",
            "free_remaining": 2,
            "paid_remaining": 5,
            "total_available": 7
        }
    """
    try:
        user_id = req.user.get("sub")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        credits = await get_user_credits(user_uuid)

        return func.HttpResponse(
            json.dumps({
                "user_id": user_id,
                "free_remaining": credits["free_remaining"],
                "paid_remaining": credits["paid_remaining"],
                "total_available": credits["total_available"],
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Get credits error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to get credits"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("GetUserPreferences")
@app.route(route="users/me/preferences", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def get_user_preferences_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get user's chat history preferences.

    Requires: Bearer token authentication

    Response (200):
        {
            "store_history": false,
            "store_history_changed_at": "2026-01-17T10:30:00Z",
            "history_deletion_scheduled_at": "2026-02-16T10:30:00Z"
        }
    """
    try:
        user_id = req.user.get("sub")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        preferences = await get_user_preferences(user_uuid)

        if not preferences:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "User not found"}),
                status_code=404,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "store_history": preferences["store_history"],
                "store_history_changed_at": preferences["store_history_changed_at"].isoformat() if preferences.get("store_history_changed_at") else None,
                "history_deletion_scheduled_at": preferences["history_deletion_scheduled_at"].isoformat() if preferences.get("history_deletion_scheduled_at") else None,
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Get preferences error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to get preferences"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("UpdateUserPreferences")
@app.route(route="users/me/preferences", methods=["PATCH"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def update_user_preferences_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Update user's chat history preference.

    Requires: Bearer token authentication

    Request body:
        {"store_history": true|false}

    Response (200):
        {
            "store_history": true,
            "store_history_changed_at": "2026-01-17T10:30:00Z",
            "history_deletion_scheduled_at": null
        }

    Logic:
    - When store_history changes from true to false: schedules deletion in 30 days
    - When store_history changes from false to true: cancels scheduled deletion
    """
    try:
        user_id = req.user.get("sub")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body or "store_history" not in req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "store_history field is required"}),
                status_code=400,
                mimetype="application/json"
            )

        store_history = req_body.get("store_history")
        if not isinstance(store_history, bool):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "store_history must be a boolean"}),
                status_code=400,
                mimetype="application/json"
            )

        preferences = await update_user_preferences(user_uuid, store_history)

        if not preferences:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "User not found"}),
                status_code=404,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "store_history": preferences["store_history"],
                "store_history_changed_at": preferences["store_history_changed_at"].isoformat() if preferences.get("store_history_changed_at") else None,
                "history_deletion_scheduled_at": preferences["history_deletion_scheduled_at"].isoformat() if preferences.get("history_deletion_scheduled_at") else None,
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Update preferences error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to update preferences"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("GetUserSessionHistory")
@app.route(route="users/me/sessions", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def get_user_session_history_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get user's session history with message counts and previews.

    Requires: Bearer token authentication

    Query params:
        limit: int (default 50, max 100)
        offset: int (default 0)

    Response (200) when store_history = true:
        {
            "sessions": [...],
            "total": 10,
            "has_more": false
        }

    Response (200) when store_history = false:
        {
            "sessions": [],
            "total": 0,
            "has_more": false,
            "message": "History storage is disabled"
        }
    """
    try:
        user_id = req.user.get("sub")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        # Check if history is enabled
        preferences = await get_user_preferences(user_uuid)
        if not preferences:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "User not found"}),
                status_code=404,
                mimetype="application/json"
            )

        if not preferences["store_history"]:
            return func.HttpResponse(
                json.dumps({
                    "sessions": [],
                    "total": 0,
                    "has_more": False,
                    "message": "History storage is disabled"
                }),
                status_code=200,
                mimetype="application/json"
            )

        # Parse pagination params
        limit = min(int(req.params.get("limit", "50")), 100)
        offset = int(req.params.get("offset", "0"))

        result = await get_user_sessions_for_history(user_uuid, limit=limit, offset=offset)

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Invalid pagination parameters"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Get session history error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to get session history"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("GetSessionMessages")
@app.route(route="sessions/{session_id}/messages", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def get_session_messages_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get messages for a specific session.

    Requires: Bearer token authentication

    Response (200):
        {
            "session_id": "uuid",
            "messages": [
                {
                    "id": "uuid",
                    "role": "user",
                    "content": "...",
                    "timestamp": "2026-01-17T10:00:30Z"
                }
            ]
        }

    Error (404):
        - Session not found
        - Session belongs to different user
        - User has store_history = false
    """
    try:
        user_id = req.user.get("sub")
        session_id_str = req.route_params.get("session_id")

        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid user ID"}),
                status_code=400,
                mimetype="application/json"
            )

        try:
            session_uuid = uuid.UUID(session_id_str)
        except (ValueError, TypeError):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid session ID"}),
                status_code=400,
                mimetype="application/json"
            )

        # Check if history is enabled
        preferences = await get_user_preferences(user_uuid)
        if not preferences or not preferences["store_history"]:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Session not found or history storage disabled"}),
                status_code=404,
                mimetype="application/json"
            )

        # Get messages (includes ownership check)
        messages = await get_session_messages(session_uuid, user_uuid)

        if messages is None:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Session not found or history storage disabled"}),
                status_code=404,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "session_id": str(session_uuid),
                "messages": messages
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Get session messages error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Failed to get session messages"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("SyncWordPressUser")
@app.route(route="internal/sync-user", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def sync_wordpress_user_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Internal endpoint for WordPress user synchronization.

    This endpoint is called by WordPress when a new user registers.
    It creates or updates the user in PostgreSQL.

    Security: Protected by X-Internal-Key header (must match WP_SYNC_INTERNAL_KEY env var).

    Request body:
        {
            "wp_user_id": 123,
            "email": "user@example.com",
            "display_name": "John Doe",
            "created_at": "2026-01-13T10:00:00Z" (optional)
        }

    Response:
        {"status": "ok", "user_id": "uuid", "sync_status": "created|updated|linked"}
    """
    # Verify internal key
    internal_key = os.environ.get("WP_SYNC_INTERNAL_KEY")
    if not internal_key:
        logging.error("WP_SYNC_INTERNAL_KEY not configured")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Sync not configured"}),
            status_code=503,
            mimetype="application/json"
        )

    provided_key = req.headers.get("X-Internal-Key")
    if not provided_key or provided_key != internal_key:
        logging.warning("Invalid or missing X-Internal-Key header")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Unauthorized"}),
            status_code=401,
            mimetype="application/json"
        )

    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required"}),
                status_code=400,
                mimetype="application/json"
            )

        wp_user_id = req_body.get("wp_user_id")
        email = req_body.get("email", "").strip()
        display_name = req_body.get("display_name")
        created_at = req_body.get("created_at")

        if not wp_user_id or not isinstance(wp_user_id, int):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "wp_user_id (integer) is required"}),
                status_code=400,
                mimetype="application/json"
            )

        if not email or "@" not in email:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Valid email is required"}),
                status_code=400,
                mimetype="application/json"
            )

        result = await sync_wordpress_user(
            wp_user_id=wp_user_id,
            email=email,
            display_name=display_name,
            created_at=created_at,
        )

        logging.info(f"WordPress user sync: wp_user_id={wp_user_id}, status={result['status']}")

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "user_id": result["user_id"],
                "sync_status": result["status"]
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"WordPress sync error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Sync failed"}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("EvaluateIntakeProgress")
@app.route(route="evaluate_intake_progress", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def evaluate_intake_progress(req: func.HttpRequest) -> func.HttpResponse:
    """
    Evaluate intake progress based on collected fields.
    Calculates a weighted score and determines if enough data has been collected.
    Threshold: 6 out of 12 points.
    """
    logging.info("evaluate_intake_progress function processed a request.")

    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON in request body."}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required."}),
                status_code=400,
                mimetype="application/json"
            )

        if "session_id" not in req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required field: session_id."}),
                status_code=400,
                mimetype="application/json"
            )

        if "fields" not in req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required field: fields."}),
                status_code=400,
                mimetype="application/json"
            )

        fields = req_body["fields"]
        if not isinstance(fields, dict):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid input: fields must be an object."}),
                status_code=400,
                mimetype="application/json"
            )

        field_weights = {
            "symptoms": 3,
            "duration": 2,
            "triggers": 2,
            "intensity": 1,
            "frequency": 1,
            "impact_on_life": 2,
            "coping_mechanisms": 1
        }

        score = 0
        for field_name, weight in field_weights.items():
            field_value = fields.get(field_name)
            if field_value is not None and isinstance(field_value, str) and field_value.strip():
                score += weight

        enough_data = score >= 6

        return func.HttpResponse(
            json.dumps({"status": "ok", "score": score, "enough_data": enough_data}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Unexpected error in evaluate_intake_progress: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error occurred."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("ExtractFieldsFromInput")
@app.route(route="extract_fields_from_input", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def extract_fields_from_input(req: func.HttpRequest) -> func.HttpResponse:
    """Extract structured fields from user messages using OpenAI gpt-4.1-mini."""
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing message field or OpenAI call failed."}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body or not req_body.get("message"):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing message field or OpenAI call failed."}),
                status_code=400,
                mimetype="application/json"
            )

        message = req_body["message"]
        session_id = req_body.get("session_id")

        logging.info(f"Processing field extraction for session: {session_id}")

        system_prompt = "You are a data extractor for a mental health assistant. Extract these fields from the user message: symptoms, duration, triggers, intensity, frequency, impact_on_life, coping_mechanisms. Return null for unmentioned fields. Output as flat JSON. Do not guess."

        client = get_openai_client()

        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.3,
            max_tokens=500,
            timeout=10
        )

        content = response.choices[0].message.content.strip()
        fields = json.loads(content)

        return func.HttpResponse(
            json.dumps({"status": "ok", "fields": fields}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error in extract_fields_from_input: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Missing message field or OpenAI call failed."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("RiskEscalationCheck")
@app.route(route="risk_escalation_check", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def risk_escalation_check(req: func.HttpRequest) -> func.HttpResponse:
    """Evaluate user messages using OpenAI moderation endpoint for safety screening."""
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON in request body."}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required field: message."}),
                status_code=400,
                mimetype="application/json"
            )

        message = req_body.get("message", "").strip()
        session_id = req_body.get("session_id", "")

        if not message:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Message cannot be empty."}),
                status_code=400,
                mimetype="application/json"
            )

        client = get_openai_client()

        try:
            moderation_response = await client.moderations.create(input=message)
            results = moderation_response.results[0]
            categories = results.categories
            flagged = results.flagged

            flag = None
            if flagged:
                if getattr(categories, 'self_harm', False) or getattr(categories, 'self_harm_intent', False):
                    flag = "self-harm"
                elif getattr(categories, 'violence', False) or getattr(categories, 'harassment_threatening', False):
                    flag = "violence"

            logging.info(f"Risk check completed for session: {session_id}, flag: {flag}")

            return func.HttpResponse(
                json.dumps({"status": "ok", "flag": flag}),
                status_code=200,
                mimetype="application/json"
            )

        except Exception as openai_error:
            logging.error(f"OpenAI moderation API error: {str(openai_error)}")
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Moderation API failed."}),
                status_code=500,
                mimetype="application/json"
            )

    except Exception as e:
        logging.error(f"Unexpected error in risk_escalation_check: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("SaveSessionSummary")
@app.route(route="save_session_summary", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def save_session_summary(req: func.HttpRequest) -> func.HttpResponse:
    """Save session summary to PostgreSQL."""
    logging.info('Processing save_session_summary request')

    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON in request body"}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required"}),
                status_code=400,
                mimetype="application/json"
            )

        session_id = req_body.get("session_id")
        summary = req_body.get("summary")

        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing session_id field."}),
                status_code=400,
                mimetype="application/json"
            )

        if not summary or not isinstance(summary, str) or not summary.strip():
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing summary field."}),
                status_code=400,
                mimetype="application/json"
            )

        if len(summary) > 2000:
            summary = summary[:2000]
            logging.info('Summary truncated to 2000 characters')

        # Get user ID from JWT token
        user_id = req.user.get("sub")
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            # For backwards compatibility with dev tokens that use non-UUID user_ids
            # Try to find or create user by the string ID
            logging.warning(f"Non-UUID user_id in token: {user_id}")
            user_uuid = None

        try:
            if user_uuid:
                await db_save_session_summary(session_id.strip(), user_uuid, summary.strip())
            else:
                # Fallback: save without user association (legacy support)
                from src.db.postgres import get_pool
                pool = await get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO sessions (id, convo_id, summary, created_at, updated_at)
                        VALUES (gen_random_uuid(), $1, $2, NOW(), NOW())
                        ON CONFLICT (convo_id) DO UPDATE SET summary = $2, updated_at = NOW()
                        """,
                        session_id.strip(),
                        summary.strip(),
                    )

            logging.info('Successfully saved summary to PostgreSQL')

            return func.HttpResponse(
                json.dumps({"status": "ok"}),
                status_code=200,
                mimetype="application/json"
            )

        except Exception as e:
            logging.error(f'Failed to save summary: {str(e)}')
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Database request failed."}),
                status_code=500,
                mimetype="application/json"
            )

    except Exception as e:
        logging.error(f'Unexpected error in save_session_summary: {str(e)}')
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("SwitchChatMode")
@app.route(route="switch_chat_mode", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@require_auth
async def switch_chat_mode(req: func.HttpRequest) -> func.HttpResponse:
    """Determine chat mode switch using OpenAI analysis."""
    try:
        req_body = req.get_json()
        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required."}),
                status_code=400,
                mimetype="application/json"
            )

        session_id = req_body.get("session_id")
        context = req_body.get("context")

        if not session_id:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required session_id field."}),
                status_code=400,
                mimetype="application/json"
            )

        if not context or not isinstance(context, str):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing or invalid context field."}),
                status_code=400,
                mimetype="application/json"
            )

        client = get_openai_client()

        system_prompt = "You are a conversation controller for a mental health assistant. Based on the user message, decide the mode: intake, advice, reflection, or summary. Only return one word."

        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            max_tokens=10,
            temperature=0.1
        )

        new_mode = response.choices[0].message.content.strip().lower()
        valid_modes = ["intake", "advice", "reflection", "summary"]
        if new_mode not in valid_modes:
            new_mode = "advice"

        return func.HttpResponse(
            json.dumps({"status": "ok", "new_mode": new_mode}),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Invalid JSON in request body."}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception:
        logging.error("Error in switch_chat_mode function")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error."}),
            status_code=500,
            mimetype="application/json"
        )


# =============================================================================
# DURABLE FUNCTIONS - ORCHESTRATORS
# =============================================================================

@app.orchestration_trigger(context_name="context")
def mental_health_orchestrator(context: df.DurableOrchestrationContext):
    """Main orchestrator for mental health assistance workflow."""
    try:
        retry_options = df.RetryOptions(
            first_retry_interval=timedelta(seconds=5),
            max_number_of_attempts=3
        )

        payload = context.get_input()
        context.set_custom_status({'step': 'orchestration_started', 'session_id': payload.get('session_id', 'unknown')})

        validated = yield context.call_activity_with_retry('ActivityIntake', retry_options, payload)
        context.set_custom_status({'step': 'intake_completed', 'result': validated})

        route = yield context.call_activity_with_retry('ActivityRouteDecision', retry_options, validated)
        context.set_custom_status({'step': 'routing_decision', 'route': route})

        assistant_result = yield context.call_activity_with_retry(
            'ActivityInvokeAssistant', retry_options, {'payload': payload, 'route': route}
        )
        context.set_custom_status({'step': 'assistant_invoked', 'assistant_type': route})

        save_status = yield context.call_activity_with_retry(
            'ActivitySaveSummary', retry_options,
            {'session_id': payload['session_id'], 'message': payload['message'],
             'assistant_response': assistant_result, 'routing_decision': route}
        )
        context.set_custom_status({'step': 'summary_saved', 'save_status': save_status})

        context.set_custom_status({'step': 'orchestration_completed', 'session_id': payload.get('session_id', 'unknown')})
        return assistant_result

    except Exception as ex:
        context.set_custom_status({
            'step': 'orchestration_failed', 'error': str(ex),
            'session_id': payload.get('session_id', 'unknown') if 'payload' in locals() else 'unknown'
        })
        raise


@app.orchestration_trigger(context_name="context")
def minimal_orchestrator(context: df.DurableOrchestrationContext):
    """Minimal test orchestrator for environment verification."""
    return "Minimal Orchestrator is running!"


# =============================================================================
# DURABLE FUNCTIONS - HTTP STARTER
# =============================================================================

@app.function_name("StartOrchestration")
@app.route(route="orchestrators/{function_name}", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@app.durable_client_input(client_name="client")
@require_auth
async def start_orchestration(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    """HTTP starter for durable orchestrations."""
    function_name = req.route_params.get('function_name')

    try:
        req_body = req.get_json()
    except ValueError:
        req_body = {}

    instance_id = await client.start_new(function_name, client_input=req_body)
    logging.info(f"Started orchestration '{function_name}' with ID = '{instance_id}'")

    return client.create_check_status_response(req, instance_id)


# =============================================================================
# TIMER FUNCTIONS - BACKGROUND JOBS
# =============================================================================

@app.function_name("HistoryDeletionJob")
@app.timer_trigger(schedule="0 0 3 * * *", arg_name="timer", run_on_startup=False)
async def history_deletion_job(timer: func.TimerRequest) -> None:
    """
    Background job to delete chat history for users who disabled storage 30+ days ago.

    Runs daily at 3:00 AM UTC.

    Logic:
    1. Get users with store_history=false AND history_deletion_scheduled_at <= NOW()
    2. Delete sessions (conversation_turns cascade automatically)
    3. Clear history_deletion_scheduled_at
    4. Log for audit
    """
    logging.info("History deletion job started")

    try:
        # Get users pending deletion (batch of 100 to avoid timeout)
        users = await get_users_pending_deletion(limit=100)

        if not users:
            logging.info("No users pending history deletion")
            return

        logging.info(f"Found {len(users)} users pending history deletion")

        total_sessions_deleted = 0

        for user_id in users:
            try:
                # Delete sessions (cascades to conversation_turns)
                sessions_deleted = await delete_user_history(user_id)
                total_sessions_deleted += sessions_deleted

                # Clear the deletion schedule
                await clear_deletion_schedule(user_id)

                logging.info(f"Deleted {sessions_deleted} sessions for user {user_id}")

            except Exception as e:
                logging.error(f"Error deleting history for user {user_id}: {str(e)}")
                # Continue with next user

        logging.info(f"History deletion job completed. Deleted {total_sessions_deleted} sessions for {len(users)} users")

    except Exception as e:
        logging.error(f"History deletion job failed: {str(e)}")
