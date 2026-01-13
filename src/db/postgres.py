"""PostgreSQL connection pool management."""

import os
import logging
import ssl
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """
    Get or create the database connection pool.

    Returns:
        asyncpg.Pool: Database connection pool

    Raises:
        ValueError: If required environment variables are missing
        asyncpg.PostgresError: If connection fails
    """
    global _pool

    if _pool is None:
        host = os.environ.get("POSTGRES_HOST")
        password = os.environ.get("POSTGRES_PASSWORD")

        if not host or not password:
            raise ValueError("POSTGRES_HOST and POSTGRES_PASSWORD environment variables are required")

        database = os.environ.get("POSTGRES_DB", "gdohealth")
        user = os.environ.get("POSTGRES_USER", "gdoadmin")

        # Create SSL context for Azure PostgreSQL
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE  # Azure uses self-signed certs

        logging.info(f"Creating PostgreSQL connection pool to {host}/{database}")

        _pool = await asyncpg.create_pool(
            host=host,
            database=database,
            user=user,
            password=password,
            ssl=ssl_context,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )

        logging.info("PostgreSQL connection pool created successfully")

    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        logging.info("PostgreSQL connection pool closed")


async def health_check() -> bool:
    """
    Check if database connection is healthy.

    Returns:
        bool: True if connection is healthy
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logging.error(f"Database health check failed: {e}")
        return False
