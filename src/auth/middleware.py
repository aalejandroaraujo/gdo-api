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
TOKEN_EXPIRY_HOURS = 24


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
    4. Returns 401 if authentication fails
    """

    @wraps(func)
    async def wrapper(req: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            token = get_token_from_header(req)
            payload = validate_token(token)

            # Attach user info to request for use in handler
            req.user = payload

            # Call the actual function
            return await func(req, *args, **kwargs)

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
    """

    @wraps(func)
    def wrapper(req: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            token = get_token_from_header(req)
            payload = validate_token(token)
            req.user = payload
            return func(req, *args, **kwargs)

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
