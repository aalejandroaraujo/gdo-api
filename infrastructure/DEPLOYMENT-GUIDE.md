# GDO Health - Deployment Execution Guide

## Overview

This guide walks you through deploying GDO Health infrastructure to Azure. The process combines automated script execution with manual configuration steps that cannot be automated (primarily Azure AD B2C).

**Total Time Required:** ~2-3 hours
- Script execution: ~30-45 minutes (mostly waiting)
- Manual B2C configuration: ~1-1.5 hours
- Verification: ~15 minutes

---

## Prerequisites Checklist

Before starting, ensure you have:

### Tools Installed
```bash
# Check all required tools
az --version          # Azure CLI 2.50+
psql --version        # PostgreSQL client
curl --version        # cURL
jq --version          # JSON processor

# If missing, install:
# Azure CLI: curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
# PostgreSQL client: sudo apt install postgresql-client
# jq: sudo apt install jq
```

### Azure Access
- [ ] Active Azure subscription with Owner or Contributor role
- [ ] Logged in to Azure CLI (`az login`)
- [ ] Permission to create Azure AD B2C tenant (requires Global Administrator or subscription Owner)

### Secrets Ready
- [ ] OpenAI API key (get from https://platform.openai.com/api-keys)
- [ ] Generated PostgreSQL password (32+ characters recommended)

---

## Phase 1: Environment Setup (5 minutes)

### Step 1.1: Create Your Environment File

```bash
# Navigate to deployment directory
cd /path/to/deployment

# Copy the template
cp env.gdo-health.example .env.gdo-health

# Edit with your values
nano .env.gdo-health  # or your preferred editor
```

### Step 1.2: Fill In Required Values

| Variable | Where to Find It | Example |
|----------|------------------|---------|
| `AZURE_SUBSCRIPTION_ID` | `az account list --output table` | `12345678-1234-1234-1234-123456789abc` |
| `AZURE_LOCATION` | Keep as `switzerlandnorth` for GDPR | `switzerlandnorth` |
| `POSTGRES_ADMIN_PASSWORD` | Generate: `openssl rand -base64 24 \| tr -dc 'a-zA-Z0-9' \| head -c 32` | `aB3dE5fG7hI9jK1L...` |
| `OPENAI_API_KEY` | OpenAI Platform dashboard | `sk-...` |

### Step 1.3: Validate Environment

```bash
# Quick validation
source .env.gdo-health
echo "Subscription: $AZURE_SUBSCRIPTION_ID"
echo "Password length: ${#POSTGRES_ADMIN_PASSWORD} chars (should be 16+)"
```

---

## Phase 2: Run Deployment Script (30-45 minutes)

### Step 2.1: Make Scripts Executable

```bash
chmod +x deploy-gdo-health.sh
chmod +x verify-deployment.sh
```

### Step 2.2: Run the Deployment

```bash
./deploy-gdo-health.sh
```

### What the Script Does (Automatically)

| Step | Resource | Time | Notes |
|------|----------|------|-------|
| 1 | Pre-flight checks | 10s | Validates env, tools, Azure login |
| 2 | Resource Group | 10s | `rg-gdo-health-prod` in Switzerland North |
| 3 | PostgreSQL Server | **3-5 min** | Longest step - be patient |
| 4 | Firewall Rules | 10s | Azure services + your IP |
| 5 | Database Schema | 30s | Tables, functions, seed data |
| 6 | Key Vault | 30s | Secrets storage |
| 7 | Storage Account | 20s | For Function App |
| 8 | Function App | 1-2 min | With managed identity |

### Expected Output

```
╔════════════════════════════════════════════════════════════════════════════╗
║           GDO HEALTH - AZURE INFRASTRUCTURE DEPLOYMENT                     ║
║                    Switzerland North Region                                 ║
╚════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
▸ Step 0/8: Pre-flight Checks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ℹ Checking required tools...
✓ All required tools found
...
```

### If Something Fails

1. **Check the log file** - path shown in output
2. **Common issues:**
   - `Not logged in` → Run `az login`
   - `Subscription not found` → Check `AZURE_SUBSCRIPTION_ID`
   - `Name already exists` → Resource names must be globally unique, change in `.env.gdo-health`
   - `Connection timeout` → Your IP may have changed, re-run script

3. **To retry after fixing:**
   ```bash
   ./deploy-gdo-health.sh
   # Script handles existing resources gracefully
   ```

4. **To completely start over:**
   ```bash
   az group delete --name rg-gdo-health-prod --yes --no-wait
   # Wait 5 minutes, then re-run script
   ```

---

## Phase 3: Azure AD B2C Configuration (1-1.5 hours)

> **⚠️ MANUAL STEPS REQUIRED**
> 
> Azure AD B2C cannot be fully automated via CLI or Terraform. These steps must be done in the Azure Portal.

### Step 3.1: Create B2C Tenant

1. **Go to Azure Portal:** https://portal.azure.com

2. **Search:** Type "Azure AD B2C" in the search bar

3. **Click:** "Create a resource" or "Create new B2C Tenant"

4. **Select:** "Create a new Azure AD B2C Tenant"

5. **Configure:**
   | Field | Value |
   |-------|-------|
   | Organization name | `GDO Health` |
   | Initial domain name | `gdohealthb2c` |
   | Country/Region | `Switzerland` |
   | Subscription | Your subscription |
   | Resource group | `rg-gdo-health-prod` |

6. **Click:** "Review + Create" → "Create"

7. **Wait:** ~5-10 minutes for tenant creation

### Step 3.2: Switch to B2C Tenant

1. **Click** your profile icon (top right)
2. **Click** "Switch directory"
3. **Select** "gdohealthb2c.onmicrosoft.com"

### Step 3.3: Register Mobile App

1. **Navigate:** Azure AD B2C → App registrations → New registration

2. **Configure:**
   | Field | Value |
   |-------|-------|
   | Name | `GDO Health Mobile App` |
   | Supported account types | `Accounts in any identity provider...` |

3. **Add Redirect URIs:**
   - Platform: `Mobile and desktop applications`
   - URI 1: `msauth.com.gdohealth.app://auth`
   - URI 2: `exp://localhost:8081` (for Expo dev)

4. **Click:** "Register"

5. **📝 Note these values:**
   ```
   Application (client) ID: ________________________________
   Directory (tenant) ID:   ________________________________
   ```

### Step 3.4: Register Backend API

1. **Navigate:** App registrations → New registration

2. **Configure:**
   | Field | Value |
   |-------|-------|
   | Name | `GDO Health API` |
   | Supported account types | `Accounts in this organizational directory only` |

3. **Click:** "Register"

4. **Go to:** "Expose an API"

5. **Set Application ID URI:** Click "Set" → Accept default or use `https://gdohealthb2c.onmicrosoft.com/api`

6. **Add a scope:**
   | Field | Value |
   |-------|-------|
   | Scope name | `access_as_user` |
   | Admin consent display name | `Access GDO Health API` |
   | Admin consent description | `Allows the app to access the GDO Health API` |
   | State | `Enabled` |

7. **📝 Note:**
   ```
   API Client ID: ________________________________
   Scope: api://[client-id]/access_as_user
   ```

### Step 3.5: Create User Flows

1. **Navigate:** Azure AD B2C → User flows → New user flow

2. **Create Sign up and sign in flow:**
   - Select: "Sign up and sign in" → "Recommended"
   - Name: `signupsignin` (becomes `B2C_1_signupsignin`)
   - Identity providers: ✓ Email signup
   - User attributes to collect: ✓ Display Name, ✓ Email Address
   - Application claims: ✓ Display Name, ✓ Email Addresses, ✓ User's Object ID
   - Click: "Create"

3. **Create Password reset flow:**
   - Select: "Password reset" → "Recommended"
   - Name: `passwordreset`
   - Identity providers: ✓ Reset password using email address
   - Click: "Create"

### Step 3.6: Add B2C Secrets to Key Vault

**Switch back to main directory** (click profile → Switch directory → your main tenant)

```bash
# Add B2C configuration to Key Vault
source .env.gdo-health

az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "B2cTenantName" \
    --value "gdohealthb2c"

az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "B2cClientId" \
    --value "<MOBILE_APP_CLIENT_ID>"  # From step 3.3

az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "B2cApiClientId" \
    --value "<API_CLIENT_ID>"  # From step 3.4

# Update Function App settings
az functionapp config appsettings set \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings \
        "B2C_TENANT_NAME=@Microsoft.KeyVault(VaultName=$KEYVAULT_NAME;SecretName=B2cTenantName)" \
        "B2C_CLIENT_ID=@Microsoft.KeyVault(VaultName=$KEYVAULT_NAME;SecretName=B2cApiClientId)"
```

---

## Phase 4: Run Verification (15 minutes)

### Step 4.1: Execute Verification Script

```bash
./verify-deployment.sh
```

### Expected Output

```
╔════════════════════════════════════════════════════════════════════════════╗
║                         VERIFICATION RESULTS                               ║
╠════════════════════════════════════════════════════════════════════════════╣
║  PASSED: 25 checks                                                         ║
║  FAILED: 0 checks                                                          ║
║  WARNINGS: 2 checks                                                        ║
╠════════════════════════════════════════════════════════════════════════════╣
║  ✓ DEPLOYMENT VERIFIED SUCCESSFULLY                                        ║
╚════════════════════════════════════════════════════════════════════════════╝
```

### What Gets Verified

| Check | What It Verifies |
|-------|------------------|
| Resource Group | Exists, correct location, proper tags |
| PostgreSQL | Server exists, database created, schema applied, seed data present, connectivity works |
| Key Vault | Exists, all secrets present |
| Storage Account | Exists, correct SKU |
| Function App | Exists, managed identity, Key Vault access, app settings |
| Unexpected Resources | No rogue resources in resource group |

### Interpreting Results

- **PASS**: Resource deployed correctly
- **WARN**: Non-critical issue (e.g., auto-generated resources)
- **FAIL**: Critical issue that needs fixing

---

## Phase 5: Optional - Custom Domain (30 minutes)

### Step 5.1: Add DNS Record

In your DNS provider (e.g., Cloudflare, Route53):

| Type | Name | Value | TTL |
|------|------|-------|-----|
| CNAME | `api` | `func-gdo-health-prod.azurewebsites.net` | 300 |

### Step 5.2: Configure in Azure

```bash
source .env.gdo-health

# Add custom hostname
az functionapp config hostname add \
    --hostname "$API_DOMAIN" \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP"

# Create managed certificate
az functionapp config ssl create \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --hostname "$API_DOMAIN"

# Get certificate thumbprint
THUMBPRINT=$(az functionapp config ssl list \
    --resource-group "$RESOURCE_GROUP" \
    --query "[?name=='$API_DOMAIN'].thumbprint" -o tsv)

# Bind certificate
az functionapp config ssl bind \
    --name "$FUNCTIONAPP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --certificate-thumbprint "$THUMBPRINT" \
    --ssl-type SNI

echo "✓ Custom domain configured: https://$API_DOMAIN"
```

---

## Troubleshooting

### Script won't run
```bash
# Check permissions
ls -la deploy-gdo-health.sh
# If not executable:
chmod +x deploy-gdo-health.sh
```

### Azure CLI authentication issues
```bash
# Force re-login
az logout
az login

# If using service principal:
az login --service-principal -u <app-id> -p <password> --tenant <tenant-id>
```

### PostgreSQL connection fails
```bash
# Check your public IP
curl ifconfig.me

# Add firewall rule manually
az postgres flexible-server firewall-rule create \
    --resource-group rg-gdo-health-prod \
    --name psql-gdo-health-prod \
    --rule-name "MyIP" \
    --start-ip-address <YOUR_IP> \
    --end-ip-address <YOUR_IP>
```

### Key Vault access denied
```bash
# Get your user object ID
USER_ID=$(az ad signed-in-user show --query id -o tsv)

# Grant yourself access
az keyvault set-policy \
    --name kv-gdo-health-prod \
    --object-id "$USER_ID" \
    --secret-permissions get list set delete
```

---

## What's Next?

After successful deployment:

1. **Phase 2: Data Migration** - Run WordPress data export and migration scripts
2. **Phase 3: Backend Code** - Deploy Function App code  
3. **Phase 4: Mobile App** - Configure and deploy Expo/React Native app
4. **Phase 5: WordPress Transition** - Activate redirect plugin

See the full migration guide for details on each phase.

---

## Quick Reference

### Resource Names
| Resource | Name |
|----------|------|
| Resource Group | `rg-gdo-health-prod` |
| PostgreSQL Server | `psql-gdo-health-prod` |
| PostgreSQL Host | `psql-gdo-health-prod.postgres.database.azure.com` |
| Key Vault | `kv-gdo-health-prod` |
| Storage Account | `stgdohealthprod` |
| Function App | `func-gdo-health-prod` |
| Function App URL | `https://func-gdo-health-prod.azurewebsites.net` |

### Files Generated
| File | Purpose |
|------|---------|
| `deploy-*.log` | Detailed deployment log |
| `deployment-info.json` | Machine-readable deployment data |
| `verification-report-*.txt` | Verification results |
| `schema.sql` | Applied database schema |
