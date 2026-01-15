"""Credit management database operations."""

import logging
import uuid
from typing import Dict, Any, Optional

from .postgres import get_pool


async def get_user_credits(user_id: uuid.UUID) -> Dict[str, int]:
    """
    Get user's available session credits.

    Args:
        user_id: User UUID

    Returns:
        Dict with free_remaining, paid_remaining, total_available
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM get_user_credits($1)",
            user_id,
        )

        if row:
            return {
                "free_remaining": row["free_remaining"] or 0,
                "paid_remaining": row["paid_remaining"] or 0,
                "total_available": row["total_available"] or 0,
            }

        return {
            "free_remaining": 0,
            "paid_remaining": 0,
            "total_available": 0,
        }


async def consume_session_credit(
    user_id: uuid.UUID,
    expert_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Consume a session credit (free first, then paid).

    Uses the use_session_with_duration() PostgreSQL function for atomic operation.

    Args:
        user_id: User UUID
        expert_id: Optional expert UUID

    Returns:
        Dict with success, session_type, duration_minutes, message
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM use_session_with_duration($1, $2)",
            user_id,
            expert_id,
        )

        if row:
            return {
                "success": row["success"],
                "session_type": row["session_type"],
                "duration_minutes": row["duration_minutes"],
                "message": row["message"],
            }

        return {
            "success": False,
            "session_type": None,
            "duration_minutes": None,
            "message": "Failed to check credits",
        }


async def add_paid_credits(
    user_id: uuid.UUID,
    sessions_count: int,
    source: str = "woocommerce",
    order_reference: Optional[str] = None,
    valid_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Add paid session credits to a user.

    Args:
        user_id: User UUID
        sessions_count: Number of sessions to add
        source: Credit source (woocommerce, admin, promo, etc.)
        order_reference: External order ID for idempotency
        valid_days: Optional validity period in days

    Returns:
        Dict with entitlement_id, sessions_added, new_balance
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Check idempotency if order_reference provided
        if order_reference:
            existing = await conn.fetchval(
                """
                SELECT id FROM entitlements
                WHERE order_reference = $1
                """,
                order_reference,
            )
            if existing:
                logging.info(f"Order {order_reference} already processed")
                return {
                    "entitlement_id": str(existing),
                    "sessions_added": 0,
                    "already_processed": True,
                }

        # Calculate valid_until if valid_days provided
        valid_until_clause = ""
        params = [uuid.uuid4(), user_id, source, sessions_count, order_reference]

        if valid_days:
            valid_until_clause = ", valid_until = NOW() + $6 * INTERVAL '1 day'"
            params.append(valid_days)

        # Create entitlement
        query = f"""
            INSERT INTO entitlements (id, user_id, source, sessions_total, order_reference{', valid_until' if valid_days else ''})
            VALUES ($1, $2, $3, $4, $5{', NOW() + $6 * INTERVAL \'1 day\'' if valid_days else ''})
            RETURNING id
        """

        entitlement_id = await conn.fetchval(query, *params)

        # Get new balance
        credits = await conn.fetchrow(
            "SELECT * FROM get_user_credits($1)",
            user_id,
        )

        logging.info(f"Added {sessions_count} credits to user {user_id} (source: {source})")

        return {
            "entitlement_id": str(entitlement_id),
            "sessions_added": sessions_count,
            "new_balance": credits["total_available"] if credits else sessions_count,
            "already_processed": False,
        }
