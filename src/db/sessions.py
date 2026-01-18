"""Session database operations."""

import logging
import uuid
from datetime import datetime, timezone, timedelta
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
    duration_minutes: int = 5,
) -> Dict[str, Any]:
    """
    Create a new chat session with timer.

    Args:
        user_id: User UUID
        expert_id: Optional expert UUID
        session_type: Type of session (freemium, paid, test)
        duration_minutes: Session duration in minutes (5 for free, 45 for paid)

    Returns:
        Created session dict with timer info
    """
    pool = await get_pool()
    session_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    expires_at = started_at + timedelta(minutes=duration_minutes)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO sessions (
                id, user_id, expert_id, session_type, mode,
                duration_minutes, created_at, expires_at, status
            )
            VALUES ($1, $2, $3, $4, 'intake', $5, $6, $7, 'active')
            RETURNING id, user_id, expert_id, mode, session_type,
                      duration_minutes, created_at, expires_at, status
            """,
            session_id,
            user_id,
            expert_id,
            session_type,
            duration_minutes,
            started_at,
            expires_at,
        )

        logging.info(f"Created session {session_id} for user {user_id} (type={session_type}, duration={duration_minutes}min)")
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


async def end_session(session_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Mark session as ended and return duration used.

    Args:
        session_id: Session UUID

    Returns:
        Dict with session_id, status, duration_used_seconds or None if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE sessions
            SET mode = 'ended', status = 'ended', ended_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING id, status, created_at, ended_at
            """,
            session_id,
        )

        if row:
            duration_used = (row["ended_at"] - row["created_at"]).total_seconds()
            return {
                "session_id": str(row["id"]),
                "status": row["status"],
                "duration_used_seconds": int(duration_used),
            }

        return None


async def get_session_by_id(session_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Get session by UUID with timer info.

    Args:
        session_id: Session UUID

    Returns:
        Session dict with timer info or None if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, expert_id, convo_id, mode, session_type,
                   duration_minutes, created_at, expires_at, status,
                   intake_fields, intake_score, summary, sentiment,
                   duration_seconds, message_count, ended_at
            FROM sessions
            WHERE id = $1
            """,
            session_id,
        )

        return dict(row) if row else None


async def update_session_status(session_id: uuid.UUID, status: str) -> bool:
    """
    Update session status.

    Args:
        session_id: Session UUID
        status: New status (active, expired, ended)

    Returns:
        True if updated
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE sessions
            SET status = $1, updated_at = NOW()
            WHERE id = $2
            """,
            status,
            session_id,
        )

        return result == "UPDATE 1"


async def get_user_sessions_for_history(
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Get user's session history with message counts and previews.

    Args:
        user_id: User UUID
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip

    Returns:
        Dict with sessions list, total count, and has_more flag
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Get total count
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM sessions WHERE user_id = $1",
            user_id,
        )

        # Get sessions with message count and last message preview
        rows = await conn.fetch(
            """
            SELECT
                s.id,
                s.expert_id,
                e.name as expert_name,
                s.created_at as started_at,
                s.ended_at,
                s.session_type,
                (SELECT COUNT(*) FROM conversation_turns ct WHERE ct.session_id = s.id) as message_count,
                (SELECT SUBSTRING(ct.content, 1, 100)
                 FROM conversation_turns ct
                 WHERE ct.session_id = s.id
                 ORDER BY ct.created_at DESC
                 LIMIT 1) as last_message_preview
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

        sessions = []
        for row in rows:
            sessions.append({
                "id": str(row["id"]),
                "expert_id": str(row["expert_id"]) if row["expert_id"] else None,
                "expert_name": row["expert_name"],
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
                "message_count": row["message_count"] or 0,
                "last_message_preview": row["last_message_preview"] or "",
                "session_type": row["session_type"],
            })

        return {
            "sessions": sessions,
            "total": total or 0,
            "has_more": (offset + limit) < (total or 0),
        }


async def get_session_messages(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[List[Dict[str, Any]]]:
    """
    Get messages for a session, with ownership verification.

    Args:
        session_id: Session UUID
        user_id: User UUID (for ownership check)

    Returns:
        List of message dicts or None if session not found or not owned by user
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Verify ownership
        session_owner = await conn.fetchval(
            "SELECT user_id FROM sessions WHERE id = $1",
            session_id,
        )

        if session_owner is None or session_owner != user_id:
            return None

        # Get messages
        rows = await conn.fetch(
            """
            SELECT id, role, content, created_at as timestamp
            FROM conversation_turns
            WHERE session_id = $1
            ORDER BY created_at ASC
            """,
            session_id,
        )

        return [
            {
                "id": str(row["id"]),
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
            }
            for row in rows
        ]


async def delete_user_history(user_id: uuid.UUID) -> int:
    """
    Delete all chat history (sessions and messages) for a user.

    Args:
        user_id: User UUID

    Returns:
        Number of sessions deleted
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Delete sessions (conversation_turns cascade automatically)
        result = await conn.execute(
            "DELETE FROM sessions WHERE user_id = $1",
            user_id,
        )

        # Parse "DELETE X" to get count
        count = int(result.split()[-1]) if result else 0

        logging.info(f"Deleted {count} sessions for user {user_id}")
        return count


async def get_users_pending_deletion(limit: int = 100) -> List[uuid.UUID]:
    """
    Get users whose history deletion is due.

    Args:
        limit: Maximum number of users to return

    Returns:
        List of user UUIDs
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id FROM users
            WHERE store_history = FALSE
              AND history_deletion_scheduled_at IS NOT NULL
              AND history_deletion_scheduled_at <= NOW()
            LIMIT $1
            """,
            limit,
        )

        return [row["id"] for row in rows]


async def clear_deletion_schedule(user_id: uuid.UUID) -> None:
    """
    Clear the deletion schedule for a user after deletion is complete.

    Args:
        user_id: User UUID
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET history_deletion_scheduled_at = NULL
            WHERE id = $1
            """,
            user_id,
        )
