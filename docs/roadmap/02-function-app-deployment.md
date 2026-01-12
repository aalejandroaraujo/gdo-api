# Phase 2: Function App Deployment

**Status:** Not Started

---

## Objective

Deploy the updated Function App code to Azure, replacing NocoDB storage with PostgreSQL and integrating the authentication middleware from Phase 1.

---

## Pre-Deployment Checklist

- [x] Infrastructure deployed (Phase 0)
- [ ] Auth middleware implemented (Phase 1)
- [ ] NocoDB references replaced with PostgreSQL
- [ ] Environment variables configured
- [ ] Local testing passed

---

## Code Changes Required

### 1. Update `src/shared/common.py`

Replace NocoDB client with PostgreSQL:

```python
# Before (NocoDB)
async def nocodb_upsert(session_id: str, summary: str):
    # HTTP calls to NocoDB API
    ...

# After (PostgreSQL)
import asyncpg

async def get_db_pool():
    """Get or create database connection pool."""
    return await asyncpg.create_pool(
        host=os.environ["POSTGRES_HOST"],
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        ssl="require",
        min_size=1,
        max_size=10
    )

async def save_session_summary(session_id: str, user_id: str, summary: str):
    """Save session summary to PostgreSQL."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE sessions
            SET summary = $1, updated_at = NOW()
            WHERE id = $2 AND user_id = $3
        """, summary, session_id, user_id)
```

### 2. Add Dependencies

Update `requirements.txt`:

```txt
azure-functions
azure-durable-functions
openai>=1.0.0
asyncpg>=0.29.0
PyJWT>=2.8.0
```

### 3. Update Function App Settings

```bash
source infrastructure/.env.gdo-health

az functionapp config appsettings set \
    --name func-gdo-health-prod \
    --resource-group rg-gdo-health-prod \
    --settings \
        "POSTGRES_HOST=@Microsoft.KeyVault(VaultName=kv-gdo-health-prod;SecretName=PostgresHost)" \
        "POSTGRES_DB=gdohealth" \
        "POSTGRES_USER=gdoadmin" \
        "POSTGRES_PASSWORD=@Microsoft.KeyVault(VaultName=kv-gdo-health-prod;SecretName=PostgresPassword)" \
        "OPENAI_API_KEY=@Microsoft.KeyVault(VaultName=kv-gdo-health-prod;SecretName=OpenAiApiKey)" \
        "JWT_SIGNING_KEY=@Microsoft.KeyVault(VaultName=kv-gdo-health-prod;SecretName=JwtSigningKey)"
```

---

## Deployment Methods

### Method A: VS Code Azure Extension (Recommended)

1. Install Azure Functions extension in VS Code
2. Sign in to Azure
3. Right-click on `func-gdo-health-prod` → Deploy to Function App
4. Confirm deployment

### Method B: Azure CLI

```bash
cd "f:/VS Projects/gdo-api"

# Create deployment package
func azure functionapp publish func-gdo-health-prod --python
```

### Method C: GitHub Actions (CI/CD)

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Azure Functions

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  AZURE_FUNCTIONAPP_NAME: func-gdo-health-prod
  PYTHON_VERSION: '3.11'

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt --target=".python_packages/lib/site-packages"

      - name: Deploy to Azure Functions
        uses: Azure/functions-action@v1
        with:
          app-name: ${{ env.AZURE_FUNCTIONAPP_NAME }}
          package: .
          publish-profile: ${{ secrets.AZURE_FUNCTIONAPP_PUBLISH_PROFILE }}
```

---

## Post-Deployment Verification

### 1. Health Check

```bash
curl https://func-gdo-health-prod.azurewebsites.net/api/test
# Expected: "Hello World! Function detected successfully!"
```

### 2. Test Protected Endpoint

```bash
# Get a dev token first
TOKEN=$(curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/dev-token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user"}' | jq -r '.token')

# Call protected endpoint
curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/extract_fields_from_input \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "I have been feeling anxious for 2 weeks"}'
```

### 3. Check Logs

```bash
az functionapp log tail \
    --name func-gdo-health-prod \
    --resource-group rg-gdo-health-prod
```

### 4. Verify Database Connectivity

```bash
# Check Application Insights for any connection errors
az monitor app-insights query \
    --app func-gdo-health-prod \
    --resource-group rg-gdo-health-prod \
    --analytics-query "exceptions | take 10"
```

---

## Rollback Plan

If deployment fails:

```bash
# List deployment history
az functionapp deployment list \
    --name func-gdo-health-prod \
    --resource-group rg-gdo-health-prod

# Rollback to previous deployment
az functionapp deployment source config-zip \
    --name func-gdo-health-prod \
    --resource-group rg-gdo-health-prod \
    --src <previous-package.zip>
```

---

## Tasks Checklist

- [ ] Replace NocoDB with PostgreSQL in `src/shared/common.py`
- [ ] Add `asyncpg` and `PyJWT` to `requirements.txt`
- [ ] Integrate auth middleware from Phase 1
- [ ] Update all endpoints to use new auth
- [ ] Test locally with `func start`
- [ ] Deploy to Azure
- [ ] Verify health endpoint
- [ ] Verify protected endpoints with token
- [ ] Monitor logs for errors
- [ ] Update API documentation

---

## Monitoring & Alerts

After deployment, set up alerts:

```bash
# Create alert for function failures
az monitor metrics alert create \
    --name "FunctionAppFailures" \
    --resource-group rg-gdo-health-prod \
    --scopes "/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/rg-gdo-health-prod/providers/Microsoft.Web/sites/func-gdo-health-prod" \
    --condition "count requests/failed > 5" \
    --window-size 5m \
    --evaluation-frequency 1m
```

---

*Previous Phase: [01-simple-auth.md](./01-simple-auth.md)*
*Next Phase: [03-entra-external-id.md](./03-entra-external-id.md)*
