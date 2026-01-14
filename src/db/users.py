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
                verification_expires = NOW() + $2 * INTERVAL '1 hour'
            WHERE id = $3
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
                password_reset_expires = NOW() + $2 * INTERVAL '1 hour'
            WHERE email = $3
            """,
            token,
            expires_hours,
            email.lower().strip(),
        )

        return result == "UPDATE 1"


async def get_user_by_wp_id(wp_user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get user by WordPress user ID.

    Args:
        wp_user_id: WordPress user ID

    Returns:
        User dict or None if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, display_name, account_type, email_verified,
                   wp_user_id, freemium_limit, freemium_used,
                   created_at, last_login
            FROM users
            WHERE wp_user_id = $1
            """,
            wp_user_id,
        )

        return dict(row) if row else None


async def sync_wordpress_user(
    wp_user_id: int,
    email: str,
    display_name: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sync a WordPress user to PostgreSQL (upsert).

    If user exists by wp_user_id, updates email/display_name.
    If user exists by email, links wp_user_id.
    Otherwise creates new user without password (they'll use forgot-password flow).

    Args:
        wp_user_id: WordPress user ID
        email: User's email address
        display_name: Optional display name
        created_at: Optional WordPress registration date (ISO format)

    Returns:
        Dict with user data and sync status
    """
    pool = await get_pool()
    email = email.lower().strip()

    async with pool.acquire() as conn:
        # Check if user exists by wp_user_id
        existing_by_wp = await conn.fetchrow(
            "SELECT id, email FROM users WHERE wp_user_id = $1",
            wp_user_id,
        )

        if existing_by_wp:
            # Update existing WP-linked user
            await conn.execute(
                """
                UPDATE users
                SET email = $1, display_name = COALESCE($2, display_name)
                WHERE wp_user_id = $3
                """,
                email,
                display_name,
                wp_user_id,
            )
            logging.info(f"Updated existing WP user {wp_user_id}")
            return {"user_id": str(existing_by_wp["id"]), "status": "updated"}

        # Check if user exists by email
        existing_by_email = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1",
            email,
        )

        if existing_by_email:
            # Link wp_user_id to existing email user
            await conn.execute(
                """
                UPDATE users
                SET wp_user_id = $1, display_name = COALESCE($2, display_name)
                WHERE email = $3
                """,
                wp_user_id,
                display_name,
                email,
            )
            logging.info(f"Linked WP user {wp_user_id} to existing email {email}")
            return {"user_id": str(existing_by_email["id"]), "status": "linked"}

        # Create new user without password
        user_id = uuid.uuid4()
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, email, display_name, wp_user_id, created_at)
            VALUES ($1, $2, $3, $4, COALESCE($5::timestamptz, NOW()))
            RETURNING id, email, display_name, created_at
            """,
            user_id,
            email,
            display_name,
            wp_user_id,
            created_at,
        )

        logging.info(f"Created new user {user_id} from WP user {wp_user_id}")
        return {"user_id": str(row["id"]), "status": "created"}


async def get_user_by_reset_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Get user by password reset token if not expired.

    Args:
        token: Password reset token

    Returns:
        User dict or None if not found or expired
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, display_name
            FROM users
            WHERE password_reset_token = $1
              AND password_reset_expires > NOW()
            """,
            token,
        )

        return dict(row) if row else None


async def update_user_profile(
    user_id: uuid.UUID,
    display_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update user profile fields.

    Args:
        user_id: User UUID
        display_name: New display name (if provided)

    Returns:
        Updated user dict or None if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET display_name = COALESCE($2, display_name)
            WHERE id = $1
            RETURNING id, email, display_name, account_type, email_verified,
                      freemium_limit, freemium_used, created_at, last_login
            """,
            user_id,
            display_name,
        )

        return dict(row) if row else None
