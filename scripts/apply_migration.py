"""Apply database migration to Azure PostgreSQL."""

import os
import sys
import ssl
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg


MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email) WHERE email_verified = TRUE;
"""


async def apply_migration():
    """Apply the migration to the database."""
    host = os.environ.get("POSTGRES_HOST")
    password = os.environ.get("POSTGRES_PASSWORD")
    database = os.environ.get("POSTGRES_DB", "gdohealth")
    user = os.environ.get("POSTGRES_USER", "gdoadmin")

    if not host or not password:
        print("ERROR: POSTGRES_HOST and POSTGRES_PASSWORD environment variables required")
        print("Set them or run: source infrastructure/.env.gdo-health")
        sys.exit(1)

    print(f"Connecting to {host}/{database}...")

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        conn = await asyncpg.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            ssl=ssl_context,
        )

        print("Connected. Applying migration...")

        # Execute each statement
        for statement in MIGRATION_SQL.strip().split(";"):
            statement = statement.strip()
            if statement:
                print(f"  Executing: {statement[:60]}...")
                await conn.execute(statement)

        print("Migration completed successfully!")

        # Verify columns exist
        result = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name IN ('password_hash', 'email_verified', 'last_login')
        """)

        print("\nVerification - New columns:")
        for row in result:
            print(f"  {row['column_name']}: {row['data_type']}")

        await conn.close()

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(apply_migration())
