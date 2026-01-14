"""Database module for PostgreSQL connectivity."""

from .postgres import get_pool, close_pool
from .users import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_wp_id,
    get_user_by_reset_token,
    get_or_create_user,
    verify_user_email,
    update_user_password,
    update_user_profile,
    update_last_login,
    set_password_reset_token,
    sync_wordpress_user,
)
from .sessions import save_session_summary, get_user_sessions, create_session

__all__ = [
    "get_pool",
    "close_pool",
    "create_user",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_by_wp_id",
    "get_user_by_reset_token",
    "get_or_create_user",
    "verify_user_email",
    "update_user_password",
    "update_user_profile",
    "update_last_login",
    "set_password_reset_token",
    "sync_wordpress_user",
    "save_session_summary",
    "get_user_sessions",
    "create_session",
]
