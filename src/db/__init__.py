"""Database module for PostgreSQL connectivity."""

from .postgres import get_pool, close_pool
from .users import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_or_create_user,
    verify_user_email,
    update_user_password,
    update_last_login,
)
from .sessions import save_session_summary, get_user_sessions

__all__ = [
    "get_pool",
    "close_pool",
    "create_user",
    "get_user_by_email",
    "get_user_by_id",
    "get_or_create_user",
    "verify_user_email",
    "update_user_password",
    "update_last_login",
    "save_session_summary",
    "get_user_sessions",
]
