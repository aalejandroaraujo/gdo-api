"""Session database operations."""

import logging
import uuid
from typing import Optional, Dict, Any, List

from .postgres import get_pool


async def save_session_summary(
    session_id: str,
    user_id: uuid.UUID,
    summary: str,
) -> None:
    """
    Save or update session summary.

    Args:
        session_id: Session identifier (UUID string or conversation ID)
        user_id: User UUID
        summary: Session summary text (truncated to 2000 chars)
    """
    pool = await get_pool()

    # Truncate summary to 2000 characters
    summary = summary[:2000] if summary else ""

    async with pool.acquire() as conn:
        # Try to find session by UUID first, then by convo_id
        session_uuid = None

        # Check if session_id is a valid UUID
        try:
            test_uuid = uuid.UUID(session_id)
            session_uuid = await conn.fetchval(
                "SELECT id FROM sessions WHERE id = $1",
                test_uuid,
            )
        except (ValueError, TypeError):
            # Not a UUID, try convo_id lookup
            session_uuid = await conn.fetchval(
                "SELECT id FROM sessions WHERE convo_id = $1",
                session_id,
            )

        if session_uuid:
            # Update existing session
            await conn.execute(
                """
                UPDATE sessions
                SET summary = $1, updated_at = NOW()
                WHERE id = $2
                """,
                summary,
                session_uuid,
            )
            logging.info(f"Updated session summary for {session_uuid}")
        else:
            # Create new session with summary
            new_session_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO sessions (id, user_id, convo_id, summary, created_at, updated_at)
                VALUES ($1, $2, $3, $4, NOW(), NOW())
                """,
                new_session_id,
                user_id,
                session_id,
                summary,
            )
            logging.info(f"Created new session {new_session_id} for user {user_id}")


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get session by ID or convo_id.

    Args:
        session_id: Session UUID or conversation ID

    Returns:
        Session dict or None if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, expert_id, convo_id, mode, session_type,
                   intake_fields, intake_score, summary, sentiment,
                   duration_seconds, message_count, created_at, ended_at
            FROM sessions
            WHERE id = $1::uuid OR convo_id = $1
            """,
            session_id,
        )

        return dict(row) if row else None


async def get_user_sessions(
    user_id: uuid.UUID,
    limit: int = 10,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Get sessions for a user.

    Args:
        user_id: User UUID
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip

    Returns:
        List of session dicts
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.expert_id, e.name as expert_name, s.mode, s.session_type,
                   s.intake_score, s.summary, s.sentiment, s.duration_seconds,
                   s.message_count, s.created_at, s.ended_at
            FROM sessions s
            LEFT JOIN experts e ON s.expert_id = e.id
            WHERE s.user_id = $1
            ORDER BY s.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id,
            limit,
            offset,
        )

        return [dict(row) for row in rows]


async def create_session(
    user_id: uuid.UUID,
    expert_id: Optional[uuid.UUID] = None,
    session_type: str = "freemium",
) -> Dict[str, Any]:
    """
    Create a new chat session.

    Args:
        user_id: User UUID
        expert_id: Optional expert UUID
        session_type: Type of session (freemium, paid, test)

    Returns:
        Created session dict
    """
    pool = await get_pool()
    session_id = uuid.uuid4()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO sessions (id, user_id, expert_id, session_type, mode, created_at)
            VALUES ($1, $2, $3, $4, 'intake', NOW())
            RETURNING id, user_id, expert_id, mode, session_type, created_at
            """,
            session_id,
            user_id,
            expert_id,
            session_type,
        )

        logging.info(f"Created session {session_id} for user {user_id}")
        return dict(row)


async def update_session_mode(session_id: uuid.UUID, mode: str) -> bool:
    """
    Update session mode.

    Args:
        session_id: Session UUID
        mode: New mode (intake, advice, reflection, summary, ended)

    Returns:
        True if updated
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE sessions
            SET mode = $1, updated_at = NOW()
            WHERE id = $2
            """,
            mode,
            session_id,
        )

        return result == "UPDATE 1"


async def end_session(session_id: uuid.UUID) -> bool:
    """
    Mark session as ended.

    Args:
        session_id: Session UUID

    Returns:
        True if updated
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE sessions
            SET mode = 'ended', ended_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            session_id,
        )

        return result == "UPDATE 1"
