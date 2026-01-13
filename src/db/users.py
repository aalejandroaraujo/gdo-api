"""User database operations."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import bcrypt

from .postgres import get_pool


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


async def create_user(
    email: str,
    password: str,
    display_name: Optional[str] = None,
    wp_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create a new user with email/password authentication.

    Args:
        email: User's email address
        password: Plain text password (will be hashed)
        display_name: Optional display name
        wp_user_id: Optional WordPress user ID for sync

    Returns:
        Dict with user data (id, email, display_name, created_at)

    Raises:
        asyncpg.UniqueViolationError: If email already exists
    """
    pool = await get_pool()
    user_id = uuid.uuid4()
    password_hash = hash_password(password)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, email, password_hash, display_name, wp_user_id, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id, email, display_name, account_type, email_verified, created_at
            """,
            user_id,
            email.lower().strip(),
            password_hash,
            display_name,
            wp_user_id,
        )

        logging.info(f"Created user {user_id} with email {email}")
        return dict(row)


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Get user by email address.

    Args:
        email: Email address to look up

    Returns:
        User dict or None if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, password_hash, display_name, account_type,
                   email_verified, wp_user_id, freemium_limit, freemium_used,
                   created_at, last_login
            FROM users
            WHERE email = $1
            """,
            email.lower().strip(),
        )

        return dict(row) if row else None


async def get_user_by_id(user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get user by ID.

    Args:
        user_id: User UUID

    Returns:
        User dict or None if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, display_name, account_type, email_verified,
                   wp_user_id, freemium_limit, freemium_used, preferences,
                   created_at, last_login
            FROM users
            WHERE id = $1
            """,
            user_id,
        )

        return dict(row) if row else None


async def get_or_create_user(
    email: str,
    password: Optional[str] = None,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get existing user or create new one.

    Args:
        email: Email address
        password: Password (required if creating new user)
        display_name: Optional display name

    Returns:
        User dict

    Raises:
        ValueError: If user doesn't exist and no password provided
    """
    user = await get_user_by_email(email)

    if user:
        return user

    if not password:
        raise ValueError("Password required for new user registration")

    return await create_user(email, password, display_name)


async def verify_user_email(user_id: uuid.UUID) -> bool:
    """
    Mark user's email as verified.

    Args:
        user_id: User UUID

    Returns:
        True if updated, False if user not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE users
            SET email_verified = TRUE,
                verification_token = NULL,
                verification_expires = NULL
            WHERE id = $1
            """,
            user_id,
        )

        return result == "UPDATE 1"


async def update_user_password(user_id: uuid.UUID, new_password: str) -> bool:
    """
    Update user's password.

    Args:
        user_id: User UUID
        new_password: New plain text password

    Returns:
        True if updated, False if user not found
    """
    pool = await get_pool()
    password_hash = hash_password(new_password)

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE users
            SET password_hash = $1,
                password_reset_token = NULL,
                password_reset_expires = NULL
            WHERE id = $2
            """,
            password_hash,
            user_id,
        )

        return result == "UPDATE 1"


async def update_last_login(user_id: uuid.UUID) -> None:
    """Update user's last login timestamp."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_login = NOW() WHERE id = $1",
            user_id,
        )


async def set_verification_token(
    user_id: uuid.UUID,
    token: str,
    expires_hours: int = 24,
) -> None:
    """Set email verification token for user."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET verification_token = $1,
                verification_expires = NOW() + INTERVAL '%s hours'
            WHERE id = $2
            """,
            token,
            expires_hours,
            user_id,
        )


async def set_password_reset_token(
    email: str,
    token: str,
    expires_hours: int = 1,
) -> bool:
    """
    Set password reset token for user.

    Returns:
        True if user found and token set, False otherwise
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE users
            SET password_reset_token = $1,
                password_reset_expires = NOW() + INTERVAL '%s hours'
            WHERE email = $2
            """,
            token,
            expires_hours,
            email.lower().strip(),
        )

        return result == "UPDATE 1"
