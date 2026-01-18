"""
JWT Authentication Middleware for Azure Functions.

Provides bearer token authentication using self-signed JWTs.
Designed to be easily migrated to Microsoft Entra External ID in Phase 3.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Callable, Optional

import jwt
from azure.functions import HttpRequest, HttpResponse

# Configuration
JWT_SECRET = os.environ.get("JWT_SIGNING_KEY", "")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 1  # 1 hour token lifetime
TOKEN_REFRESH_THRESHOLD_MINUTES = 30  # Refresh if less than 30 min remaining


class AuthError(Exception):
    """Authentication error with HTTP status code."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def get_token_from_header(req: HttpRequest) -> str:
    """Extract bearer token from Authorization header."""
    auth_header = req.headers.get("Authorization", "")

    if not auth_header:
        raise AuthError("Missing Authorization header")

    if not auth_header.startswith("Bearer "):
        raise AuthError("Invalid Authorization header format. Expected: Bearer <token>")

    token = auth_header[7:].strip()
    if not token:
        raise AuthError("Empty token")

    return token


def validate_token(token: str) -> dict:
    """
    Validate JWT token and return payload.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload with user claims

    Raises:
        AuthError: If token is invalid or expired
    """
    if not JWT_SECRET:
        logging.error("JWT_SIGNING_KEY not configured")
        raise AuthError("Authentication not configured", status_code=500)

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]}
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError as e:
        logging.warning(f"Invalid token: {str(e)}")
        raise AuthError("Invalid token")


def create_token(user_id: str, extra_claims: Optional[dict] = None) -> str:
    """
    Create a new JWT token for a user.

    Args:
        user_id: Unique user identifier
        extra_claims: Optional additional claims to include

    Returns:
        Encoded JWT token string
    """
    if not JWT_SECRET:
        raise AuthError("JWT_SIGNING_KEY not configured", status_code=500)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(req: HttpRequest) -> Optional[dict]:
    """
    Get current user from request if authenticated.

    Args:
        req: HTTP request object

    Returns:
        User payload dict or None if not authenticated
    """
    return getattr(req, "user", None)


def should_refresh_token(payload: dict) -> bool:
    """
    Check if token should be refreshed (sliding expiration).

    Returns True if token has less than TOKEN_REFRESH_THRESHOLD_MINUTES remaining.
    """
    exp_timestamp = payload.get("exp")
    if not exp_timestamp:
        return False

    now = datetime.now(timezone.utc)
    exp_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    time_remaining = exp_time - now

    return time_remaining < timedelta(minutes=TOKEN_REFRESH_THRESHOLD_MINUTES)


def get_refreshed_token(payload: dict) -> Optional[str]:
    """
    Generate a new token if the current one needs refreshing.

    Args:
        payload: Current token payload

    Returns:
        New token string if refresh needed, None otherwise
    """
    if not should_refresh_token(payload):
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    # Preserve any extra claims from the original token
    extra_claims = {k: v for k, v in payload.items() if k not in ("sub", "iat", "exp")}

    return create_token(user_id, extra_claims if extra_claims else None)


def require_auth(func: Callable) -> Callable:
    """
    Decorator to require authentication on an endpoint.

    Usage:
        @app.route(...)
        @require_auth
        async def my_endpoint(req: HttpRequest) -> HttpResponse:
            user_id = req.user["sub"]
            ...

    The decorator:
    1. Extracts the Bearer token from Authorization header
    2. Validates the JWT signature and expiration
    3. Attaches user claims to req.user
    4. Checks if token needs refresh (sliding expiration)
    5. If refresh needed, adds X-New-Token header to response
    6. Returns 401 if authentication fails

    Sliding Expiration:
    - Tokens expire after TOKEN_EXPIRY_HOURS (1 hour)
    - If token has < TOKEN_REFRESH_THRESHOLD_MINUTES (30 min) remaining,
      a new token is generated and returned in X-New-Token header
    - Client should replace stored token with new one when header is present
    """

    @wraps(func)
    async def wrapper(req: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            token = get_token_from_header(req)
            payload = validate_token(token)

            # Attach user info to request for use in handler
            req.user = payload

            # Check if token needs refresh (sliding expiration)
            new_token = get_refreshed_token(payload)

            # Call the actual function
            response = await func(req, *args, **kwargs)

            # Add refreshed token to response header if needed
            if new_token and response.status_code < 400:
                # Azure Functions HttpResponse doesn't support modifying headers directly
                # We need to create a new response with the header
                response = HttpResponse(
                    body=response.get_body(),
                    status_code=response.status_code,
                    headers={
                        "Content-Type": response.mimetype or "application/json",
                        "X-New-Token": new_token,
                        "X-Token-Expires-In": str(TOKEN_EXPIRY_HOURS * 3600),
                    },
                    mimetype=response.mimetype
                )

            return response

        except AuthError as e:
            logging.warning(f"Authentication failed: {e.message}")
            return HttpResponse(
                json.dumps({"status": "error", "message": e.message}),
                status_code=e.status_code,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Unexpected auth error: {str(e)}")
            return HttpResponse(
                json.dumps({"status": "error", "message": "Authentication failed"}),
                status_code=401,
                mimetype="application/json"
            )

    return wrapper


def require_auth_sync(func: Callable) -> Callable:
    """
    Synchronous version of require_auth decorator.

    Use this for non-async function handlers.
    Includes sliding expiration support.
    """

    @wraps(func)
    def wrapper(req: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            token = get_token_from_header(req)
            payload = validate_token(token)
            req.user = payload

            # Check if token needs refresh (sliding expiration)
            new_token = get_refreshed_token(payload)

            response = func(req, *args, **kwargs)

            # Add refreshed token to response header if needed
            if new_token and response.status_code < 400:
                response = HttpResponse(
                    body=response.get_body(),
                    status_code=response.status_code,
                    headers={
                        "Content-Type": response.mimetype or "application/json",
                        "X-New-Token": new_token,
                        "X-Token-Expires-In": str(TOKEN_EXPIRY_HOURS * 3600),
                    },
                    mimetype=response.mimetype
                )

            return response

        except AuthError as e:
            logging.warning(f"Authentication failed: {e.message}")
            return HttpResponse(
                json.dumps({"status": "error", "message": e.message}),
                status_code=e.status_code,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Unexpected auth error: {str(e)}")
            return HttpResponse(
                json.dumps({"status": "error", "message": "Authentication failed"}),
                status_code=401,
                mimetype="application/json"
            )

    return wrapper
