# Database Documentation

## Overview

GDO Health uses Azure Database for PostgreSQL Flexible Server as its primary data store.

**Server:** `psql-gdo-health-prod.postgres.database.azure.com`
**Database:** `gdohealth`
**Application User:** `gdo_app_user`

---

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ gdo-mobile  │ ───► │   gdo-api   │ ───► │  PostgreSQL │
│  (app)      │ HTTP │  (backend)  │  SQL │  (database) │
│             │      │             │      │             │
│ User: Juan  │      │ DB User:    │      │ Tables:     │
│ User: Maria │      │ gdo_app_user│      │ - users     │
│ User: Pedro │      │             │      │ - sessions  │
└─────────────┘      └─────────────┘      └─────────────┘
```

**Key Points:**
- All mobile app users connect through the same backend (gdo-api)
- The backend uses a single database user (`gdo_app_user`) for all operations
- Mobile app users authenticate via JWT tokens, not database credentials
- The database user is transparent to end users

---

## Database Users

### gdoadmin (Admin User)

The PostgreSQL admin user created with the server. Used only for:
- Creating/modifying database schema
- Running migrations
- Creating application users
- Emergency maintenance

**Should NOT be used by applications.**

### gdo_app_user (Application User)

A scoped user with limited permissions for the gdo-api application.

**Permissions granted:**
```sql
-- Basic permissions
GRANT CONNECT ON DATABASE gdohealth TO gdo_app_user;
GRANT USAGE ON SCHEMA public TO gdo_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gdo_app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gdo_app_user;

-- Execute permissions for functions
GRANT EXECUTE ON FUNCTION use_session_with_duration(UUID, UUID) TO gdo_app_user;
GRANT EXECUTE ON FUNCTION get_user_credits(UUID) TO gdo_app_user;

-- For future tables/sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gdo_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO gdo_app_user;
```

**What this user CAN do:**
| Operation | Allowed |
|-----------|---------|
| Register users (INSERT) | ✅ |
| Login (SELECT) | ✅ |
| Create sessions (INSERT) | ✅ |
| Update sessions (UPDATE) | ✅ |
| Check/consume credits (SELECT/UPDATE) | ✅ |
| Save summaries (INSERT/UPDATE) | ✅ |
| Audit logging (INSERT) | ✅ |
| Call PostgreSQL functions | ✅ |

**What this user CANNOT do:**
| Operation | Blocked |
|-----------|---------|
| DROP tables | ❌ |
| CREATE/ALTER tables | ❌ |
| CREATE/DROP users | ❌ |
| TRUNCATE tables | ❌ |
| Access other databases | ❌ |

This follows the **principle of least privilege** - the application can only perform operations it needs.

---

## Connection Configuration

### Azure Function App Settings

The database connection is configured via environment variables:

| Variable | Description | Source |
|----------|-------------|--------|
| `POSTGRES_HOST` | Database server hostname | Key Vault |
| `POSTGRES_PASSWORD` | Application user password | Key Vault |
| `POSTGRES_DB` | Database name | App Setting |
| `POSTGRES_USER` | Application user name | App Setting |

### Key Vault Secrets

Sensitive values are stored in Azure Key Vault (`kv-gdo-health-prod`):

| Secret Name | Description |
|-------------|-------------|
| `PostgresHost` | Database server hostname |
| `PostgresPassword` | Password for `gdoadmin` (admin user) |
| `PostgresUserPassword` | Password for `gdo_app_user` (application user) |

### Updating the Application User Password

1. **Update Key Vault:**
   ```bash
   az keyvault secret set \
     --vault-name kv-gdo-health-prod \
     --name PostgresUserPassword \
     --value 'NEW_PASSWORD_HERE'
   ```

2. **Update PostgreSQL user password:**
   ```sql
   ALTER USER gdo_app_user WITH PASSWORD 'NEW_PASSWORD_HERE';
   ```

3. **Restart Function App:**
   ```bash
   az functionapp restart \
     --name func-gdo-health-prod \
     --resource-group rg-gdo-health-prod
   ```

### Password Requirements

Avoid these characters in passwords to prevent shell escaping issues:
- `$` `!` `` ` `` `"` `'` `;` `(` `)` `*` `?` `\` `&` `|`

Safe characters:
- Letters: `A-Z`, `a-z`
- Numbers: `0-9`
- Special: `@` `#` `%` `^` `-` `_` `+` `=` `.` `,` `:` `/`

---

## Tables

### users

Stores user accounts and freemium credits.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Unique email address |
| password_hash | VARCHAR(255) | bcrypt hashed password |
| display_name | VARCHAR(255) | User's display name |
| account_type | VARCHAR(50) | freemium, premium, etc. |
| email_verified | BOOLEAN | Email verification status |
| wp_user_id | INTEGER | WordPress user ID (if synced) |
| freemium_limit | INTEGER | Total free sessions (default: 3) |
| freemium_used | INTEGER | Free sessions consumed |
| preferences | JSONB | User preferences |
| created_at | TIMESTAMPTZ | Account creation time |
| last_login | TIMESTAMPTZ | Last login time |
| updated_at | TIMESTAMPTZ | Last update time |

### sessions

Stores chat sessions with timer information.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | Foreign key to users |
| expert_id | VARCHAR(100) | Expert/persona identifier |
| mode | VARCHAR(50) | intake, advice, reflection, summary |
| summary | TEXT | Session summary (max 2000 chars) |
| session_type | VARCHAR(50) | freemium, paid, test |
| duration_minutes | INTEGER | Session duration (5 or 45) |
| expires_at | TIMESTAMPTZ | When session expires |
| status | VARCHAR(50) | active, expired, ended |
| created_at | TIMESTAMPTZ | Session start time |
| updated_at | TIMESTAMPTZ | Last update time |

### entitlements

Stores purchased session credits.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | Foreign key to users |
| source | VARCHAR(50) | woocommerce, admin, test, promo |
| sessions_total | INTEGER | Total sessions purchased |
| sessions_used | INTEGER | Sessions consumed |
| order_reference | VARCHAR(255) | External order ID (idempotency) |
| valid_until | TIMESTAMPTZ | Expiration date (optional) |
| created_at | TIMESTAMPTZ | Purchase time |

### session_audit

Audit log for credit consumption.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | Foreign key to users |
| expert_id | UUID | Expert identifier (optional) |
| session_type | VARCHAR(50) | freemium, paid, test |
| action | VARCHAR(50) | consumed, refunded, etc. |
| created_at | TIMESTAMPTZ | Audit timestamp |

---

## PostgreSQL Functions

### use_session_with_duration(user_id, expert_id)

Atomically consumes a session credit and returns duration info.

**Logic:**
1. Lock user row to prevent race conditions
2. Check freemium availability first
3. If freemium available: consume free credit, return 5 minutes
4. If no freemium: check paid entitlements
5. If paid available: consume paid credit, return 45 minutes
6. If nothing available: return failure
7. Log to session_audit table

**Returns:**
| Column | Type | Description |
|--------|------|-------------|
| success | BOOLEAN | Whether credit was consumed |
| session_type | TEXT | freemium, paid, or test |
| duration_minutes | INTEGER | 5 or 45 |
| message | TEXT | Success/error message |

### get_user_credits(user_id)

Returns user's available credit balance.

**Returns:**
| Column | Type | Description |
|--------|------|-------------|
| free_remaining | INTEGER | Available freemium sessions |
| paid_remaining | INTEGER | Available paid sessions |
| total_available | INTEGER | Sum of free + paid |

---

## Migrations

Migrations are stored in `infrastructure/migrations/` and must be applied manually.

| File | Description |
|------|-------------|
| `001-initial-schema.sql` | Initial tables (in deploy script) |
| `002-session-timer.sql` | Session timer columns and functions |
| `003-freemium-limit-3.sql` | Change default freemium_limit to 3 |

### Applying Migrations

Using VS Code PostgreSQL extension:
1. Connect to Azure PostgreSQL as `gdoadmin`
2. Open migration file
3. Select all and run

Using psql:
```bash
psql -h psql-gdo-health-prod.postgres.database.azure.com \
     -U gdoadmin \
     -d gdohealth \
     -f infrastructure/migrations/002-session-timer.sql
```

---

## Troubleshooting

### Authentication Failed

**Error:** `password authentication failed for user "gdoadmin"` or `gdo_app_user`

**Cause:** Password mismatch between Key Vault and PostgreSQL

**Fix:**
1. Verify password in Key Vault matches PostgreSQL
2. Update Key Vault secret if needed
3. Restart Function App

### Connection Timeout

**Error:** `connection timed out`

**Cause:** Firewall blocking connection

**Fix:**
1. Check Azure PostgreSQL firewall rules
2. Ensure Function App's outbound IPs are allowed
3. Or enable "Allow Azure services" option

### Permission Denied

**Error:** `permission denied for table X`

**Cause:** `gdo_app_user` missing permissions

**Fix:**
```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE X TO gdo_app_user;
```

---

*Last updated: 2026-01-16*
