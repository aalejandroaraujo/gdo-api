# Phase 0: Infrastructure

**Status:** COMPLETE

---

## Deployed Resources

| Resource | Name | Region | Status |
|----------|------|--------|--------|
| Resource Group | `rg-gdo-health-prod` | Switzerland North | Deployed |
| PostgreSQL Flexible Server | `psql-gdo-health-prod` | Switzerland North | Deployed |
| PostgreSQL Database | `gdohealth` | Switzerland North | Deployed |
| Key Vault | `kv-gdo-health-prod` | Switzerland North | Deployed |
| Storage Account | `stgdohealthprod` | Switzerland North | Deployed |
| Function App | `func-gdo-health-prod` | Switzerland North | Deployed |

---

## Database Schema

**7 Tables:**
- `users` - User accounts and freemium limits
- `experts` - AI expert personas (6 seeded)
- `sessions` - Chat sessions with intake data
- `conversation_turns` - Individual messages
- `entitlements` - Paid session packs
- `session_audit` - Usage tracking
- `crisis_resources` - Emergency hotlines (6 seeded)

**Functions:**
- `get_available_sessions(user_id)` - Returns remaining sessions
- `use_session(user_id, expert_id)` - Atomic session consumption
- `cleanup_old_turns()` - Removes turns older than 30 days

---

## Key Vault Secrets

| Secret Name | Description |
|-------------|-------------|
| `OpenAiApiKey` | OpenAI API key for GPT-4.1-mini |
| `PostgresHost` | Database hostname |
| `PostgresPassword` | Database admin password |
| `PostgresConnectionString` | Full connection string |

---

## Function App Configuration

- **Runtime:** Python 3.11
- **Plan:** Consumption (serverless)
- **Managed Identity:** Enabled
- **Key Vault Access:** Configured via managed identity

---

## Remaining Manual Step

- **Azure AD B2C:** Skipped (end of sale May 2025)
- **Alternative:** Microsoft Entra External ID (Phase 3)

---

## Verification

```bash
# Check resources
az resource list --resource-group rg-gdo-health-prod --output table

# Test PostgreSQL connection
psql "host=psql-gdo-health-prod.postgres.database.azure.com dbname=gdohealth user=gdoadmin sslmode=require"

# Check Function App
curl https://func-gdo-health-prod.azurewebsites.net/api/test
```

---

*Completed: 2026-01-12*
