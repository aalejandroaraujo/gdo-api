# GDO Health - Infrastructure Preparation Guide

## Quick Reference

| Resource | Name | Region |
|----------|------|--------|
| Resource Group | `rg-gdo-health-prod` | Switzerland North |
| PostgreSQL | `psql-gdo-health-prod` | Switzerland North |
| Key Vault | `kv-gdo-health-prod` | Switzerland North |
| Storage Account | `stgdohealthprod` | Switzerland North |
| Function App | `func-gdo-health-prod` | Switzerland North |
| B2C Tenant | `gdohealthb2c.onmicrosoft.com` | Europe |

---

## Prerequisites Checklist

### Tools Required
- [ ] Azure CLI 2.50+ (`az --version`)
- [ ] PostgreSQL client (`psql --version`)
- [ ] Node.js 20.19+ (`node --version`)
- [ ] Git (`git --version`)

### Azure Access
- [ ] Active Azure subscription (Owner/Contributor role)
- [ ] Logged in (`az login`)
- [ ] Permission to create Azure AD B2C tenant

### Secrets Ready
- [ ] OpenAI API key from https://platform.openai.com/api-keys
- [ ] PostgreSQL password (32 chars, generate below)

```bash
# Generate secure password
openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32
```

---

## Execution Timeline

| Phase | Duration | Type | Description |
|-------|----------|------|-------------|
| 1 | 5 min | Manual | Create `.env.gdo-health` file |
| 2 | 30-45 min | **Script** | Run `deploy-gdo-health.sh` |
| 3 | 1-1.5 hr | Manual | Configure Azure AD B2C in Portal |
| 4 | 15 min | **Script** | Run `verify-deployment.sh` |
| 5 | 30 min | Manual | (Optional) Custom domain + SSL |

**Total: ~2-3 hours**

---

## Phase 1: Environment Setup

### Create `.env.gdo-health`

```bash
# Copy template
cp env.gdo-health.example .env.gdo-health

# Edit with your values
nano .env.gdo-health
```

### Required Variables

```bash
#===============================================================================
# AZURE SUBSCRIPTION
#===============================================================================
AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_LOCATION=switzerlandnorth

#===============================================================================
# RESOURCE NAMING
#===============================================================================
RESOURCE_GROUP=rg-gdo-health-prod
POSTGRES_SERVER=psql-gdo-health-prod
POSTGRES_DB=gdohealth
POSTGRES_ADMIN_USER=gdoadmin
FUNCTIONAPP_NAME=func-gdo-health-prod
KEYVAULT_NAME=kv-gdo-health-prod
STORAGE_ACCOUNT=stgdohealthprod

#===============================================================================
# SECRETS (DO NOT COMMIT)
#===============================================================================
POSTGRES_ADMIN_PASSWORD=<your-32-char-password>
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

#===============================================================================
# AZURE AD B2C (fill after manual setup)
#===============================================================================
B2C_TENANT_NAME=gdohealthb2c
```

### Find Your Subscription ID

```bash
az login
az account list --output table
# Copy the SubscriptionId column
```

---

## Phase 2: Run Deployment Script

```bash
chmod +x deploy-gdo-health.sh
./deploy-gdo-health.sh
```

### What Gets Created

| Step | Resource | Time |
|------|----------|------|
| 1 | Resource Group | 10s |
| 2 | PostgreSQL Flexible Server | **3-5 min** |
| 3 | Firewall Rules | 10s |
| 4 | Database Schema (7 tables, functions, seed data) | 30s |
| 5 | Key Vault + Secrets | 30s |
| 6 | Storage Account | 20s |
| 7 | Function App + Managed Identity | 1-2 min |

### If It Fails

```bash
# Check log file (path shown in output)
cat deploy-*.log

# Common fixes:
az login                          # Re-authenticate
# Edit .env.gdo-health            # Fix variables
./deploy-gdo-health.sh            # Re-run (idempotent)

# Nuclear option - start over:
az group delete --name rg-gdo-health-prod --yes --no-wait
# Wait 5 min, then re-run script
```

---

## Phase 3: Azure AD B2C Configuration (Manual)

> **Cannot be automated** — must use Azure Portal

### Step 3.1: Create B2C Tenant

1. Go to https://portal.azure.com
2. Search "Azure AD B2C" → Create
3. Select "Create a new Azure AD B2C Tenant"
4. Configure:

| Field | Value |
|-------|-------|
| Organization name | `GDO Health` |
| Initial domain name | `gdohealthb2c` |
| Country/Region | `Switzerland` |
| Subscription | Your subscription |
| Resource group | `rg-gdo-health-prod` |

5. Wait ~5-10 minutes

### Step 3.2: Switch to B2C Tenant

1. Click profile icon (top right)
2. "Switch directory"
3. Select `gdohealthb2c.onmicrosoft.com`

### Step 3.3: Register Mobile App

**Azure AD B2C → App registrations → New registration**

| Field | Value |
|-------|-------|
| Name | `GDO Health Mobile App` |
| Supported account types | `Accounts in any identity provider...` |
| Redirect URI (Mobile) | `msauth.com.gdohealth.app://auth` |
| Redirect URI (Dev) | `exp://localhost:8081` |

**Save these values:**
```
Mobile App Client ID: ________________________________
Directory (Tenant) ID: ________________________________
```

### Step 3.4: Register Backend API

**App registrations → New registration**

| Field | Value |
|-------|-------|
| Name | `GDO Health API` |
| Supported account types | `Accounts in this organizational directory only` |

Then:
1. Go to "Expose an API"
2. Set Application ID URI: `https://gdohealthb2c.onmicrosoft.com/api`
3. Add scope:
   - Name: `access_as_user`
   - Admin consent display name: `Access GDO Health API`
   - State: Enabled

**Save:**
```
API Client ID: ________________________________
```

### Step 3.5: Create User Flows

**Azure AD B2C → User flows → New user flow**

#### Sign up and sign in
- Select: "Sign up and sign in" → Recommended
- Name: `signupsignin` (becomes `B2C_1_signupsignin`)
- Identity providers: Email signup
- User attributes: Display Name, Email Address
- Application claims: Display Name, Email Addresses, User's Object ID

#### Password reset
- Select: "Password reset" → Recommended
- Name: `passwordreset`
- Identity providers: Reset password using email address

### Step 3.6: Add B2C Secrets to Key Vault

**Switch back to main directory** (your normal Azure AD, not B2C)

```bash
source .env.gdo-health

az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "B2cTenantName" \
    --value "gdohealthb2c"

az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "B2cClientId" \
    --value "<MOBILE_APP_CLIENT_ID>"

az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "B2cApiClientId" \
    --value "<API_CLIENT_ID>"

# Update Function App settings
az functionapp config appsettings set \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings \
        "B2C_TENANT_NAME=@Microsoft.KeyVault(VaultName=$KEYVAULT_NAME;SecretName=B2cTenantName)" \
        "B2C_CLIENT_ID=@Microsoft.KeyVault(VaultName=$KEYVAULT_NAME;SecretName=B2cApiClientId)"
```

---

## Phase 4: Verify Deployment

```bash
chmod +x verify-deployment.sh
./verify-deployment.sh
```

### Expected Output

```
+==============================================================================+
|                         VERIFICATION RESULTS                                 |
+==============================================================================+
|  PASSED: 25 checks                                                           |
|  FAILED: 0 checks                                                            |
|  WARNINGS: 2 checks                                                          |
+------------------------------------------------------------------------------+
|  DEPLOYMENT VERIFIED SUCCESSFULLY                                            |
+==============================================================================+
```

### What Gets Verified

- Resource Group exists, correct location
- PostgreSQL server + database + schema + seed data
- Key Vault + all secrets
- Storage Account
- Function App + managed identity + Key Vault access
- No unexpected resources

---

## Phase 5: Custom Domain (Optional)

### Add DNS Record

In your DNS provider:

| Type | Name | Value |
|------|------|-------|
| CNAME | `api` | `func-gdo-health-prod.azurewebsites.net` |

### Configure in Azure

```bash
source .env.gdo-health
API_DOMAIN=api.gabinetedeorientacion.com

# Add hostname
az functionapp config hostname add \
    --hostname "$API_DOMAIN" \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP"

# Create certificate
az functionapp config ssl create \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --hostname "$API_DOMAIN"

# Bind certificate
THUMBPRINT=$(az functionapp config ssl list \
    --resource-group "$RESOURCE_GROUP" \
    --query "[?name=='$API_DOMAIN'].thumbprint" -o tsv)

az functionapp config ssl bind \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --certificate-thumbprint "$THUMBPRINT" \
    --ssl-type SNI
```

---

## Estimated Monthly Costs

| Service | Tier | CHF/month |
|---------|------|-----------|
| PostgreSQL Flexible Server | Burstable B1ms | ~12 |
| Azure Functions | Consumption | ~5-15 |
| Key Vault | Standard | ~1 |
| Storage Account | LRS | ~1 |
| Azure AD B2C | Free (50K MAU) | 0 |
| **Azure Total** | | **~19-29** |
| OpenAI API | Pay-as-you-go | ~20-50 |
| **Grand Total** | | **~39-79** |

**Savings:** Typebot EUR 39/month eliminated = EUR 468/year

---

## Files Reference

| File | Purpose |
|------|---------|
| `deploy-gdo-health.sh` | Main deployment script |
| `verify-deployment.sh` | Verification script |
| `.env.gdo-health` | Your configuration (DO NOT COMMIT) |
| `env.gdo-health.example` | Template |
| `schema.sql` | Generated database schema |
| `deployment-info.json` | Deployment output data |
| `deploy-*.log` | Deployment logs |
| `verification-report-*.txt` | Verification results |

---

## Quick Commands Reference

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Check resource group
az group show --name rg-gdo-health-prod

# Connect to PostgreSQL
PGPASSWORD="$POSTGRES_ADMIN_PASSWORD" psql \
    -h psql-gdo-health-prod.postgres.database.azure.com \
    -U gdoadmin \
    -d gdohealth

# View Function App logs
az functionapp log tail \
    --name func-gdo-health-prod \
    --resource-group rg-gdo-health-prod

# List Key Vault secrets
az keyvault secret list --vault-name kv-gdo-health-prod

# Delete everything (careful!)
az group delete --name rg-gdo-health-prod --yes
```

---

## Next Steps After Infrastructure

1. **Deploy Function App code** — Push to `gdo-api` repo
2. **Data Migration** — Run WordPress export + migration scripts
3. **Mobile App** — Continue scaffolding in Claude Code
4. **WordPress Transition** — Activate redirect plugin
5. **Cancel Typebot** — After mobile app is live

---

*Document generated: January 2026*
*Architecture: 100% Azure, Switzerland North*
