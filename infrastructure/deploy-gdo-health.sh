#!/bin/bash
#===============================================================================
# GDO Health - Azure Infrastructure Deployment Script
# 
# This script deploys the complete Azure infrastructure for GDO Health:
# - Resource Group (Switzerland North)
# - PostgreSQL Flexible Server with full schema
# - Key Vault with secrets
# - Storage Account
# - Function App with managed identity
# - Firewall rules
#
# MANUAL STEPS REQUIRED AFTER SCRIPT:
# - Azure AD B2C configuration (see deployment guide)
# - Custom domain DNS + SSL binding
#
# Prerequisites:
# - Azure CLI logged in (az login)
# - .env.gdo-health file with required variables
# - psql client installed
#
# Usage: ./deploy-gdo-health.sh
#===============================================================================

set -euo pipefail

#-------------------------------------------------------------------------------
# CONFIGURATION
#-------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.gdo-health"
LOG_FILE="${SCRIPT_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"
SCHEMA_FILE="${SCRIPT_DIR}/schema.sql"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Feature flags
PSQL_AVAILABLE=false

#-------------------------------------------------------------------------------
# HELPER FUNCTIONS
#-------------------------------------------------------------------------------

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Write to log file
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    # Write to console with colors
    case "$level" in
        INFO)  echo -e "${BLUE}ℹ${NC} $message" ;;
        OK)    echo -e "${GREEN}✓${NC} $message" ;;
        WARN)  echo -e "${YELLOW}⚠${NC} $message" ;;
        ERROR) echo -e "${RED}✗${NC} $message" ;;
        STEP)  echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
               echo -e "${GREEN}▸ $message${NC}"
               echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n" ;;
    esac
}

error_exit() {
    log ERROR "$1"
    log ERROR "Deployment failed. Check log file: $LOG_FILE"
    exit 1
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        error_exit "Required command '$1' not found. Please install it first."
    fi
}

wait_for_resource() {
    local resource_type="$1"
    local resource_name="$2"
    local max_attempts="${3:-30}"
    local sleep_seconds="${4:-10}"
    
    log INFO "Waiting for $resource_type '$resource_name' to be ready..."
    
    for ((i=1; i<=max_attempts; i++)); do
        if az "$resource_type" show --name "$resource_name" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
            log OK "$resource_type '$resource_name' is ready"
            return 0
        fi
        echo -n "."
        sleep "$sleep_seconds"
    done
    
    error_exit "Timeout waiting for $resource_type '$resource_name'"
}

#-------------------------------------------------------------------------------
# CLEANUP ON ERROR
#-------------------------------------------------------------------------------

cleanup_on_error() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log ERROR "Script failed with exit code $exit_code"
        log WARN "Resources may have been partially created."
        log WARN "To clean up, run: az group delete --name $RESOURCE_GROUP --yes"
    fi
}

trap cleanup_on_error EXIT

#-------------------------------------------------------------------------------
# PRE-FLIGHT CHECKS
#-------------------------------------------------------------------------------

preflight_checks() {
    log STEP "Step 0/8: Pre-flight Checks"
    
    # Check required commands
    log INFO "Checking required tools..."
    check_command "az"
    check_command "curl"
    log OK "Required tools found (az, curl)"

    # jq is optional - we use az --query instead where possible
    if command -v jq &> /dev/null; then
        log OK "jq found (optional)"
    else
        log WARN "jq not found (optional) - using az --query instead"
    fi

    # psql is optional - schema can be applied later
    if command -v psql &> /dev/null; then
        PSQL_AVAILABLE=true
        log OK "psql found - schema will be applied automatically"
    else
        PSQL_AVAILABLE=false
        log WARN "psql not found - schema will be generated but not applied automatically"
        log WARN "You can apply schema later via Azure Cloud Shell or after installing psql"
    fi
    
    # Check environment file
    if [ ! -f "$ENV_FILE" ]; then
        error_exit "Environment file not found: $ENV_FILE\nCreate it from .env.gdo-health.example"
    fi
    log OK "Environment file found"
    
    # Load environment
    log INFO "Loading environment variables..."
    set -a
    source "$ENV_FILE"
    set +a
    
    # Validate required variables
    local required_vars=(
        "AZURE_SUBSCRIPTION_ID"
        "AZURE_LOCATION"
        "RESOURCE_GROUP"
        "POSTGRES_SERVER"
        "POSTGRES_DB"
        "POSTGRES_ADMIN_USER"
        "POSTGRES_ADMIN_PASSWORD"
        "FUNCTIONAPP_NAME"
        "KEYVAULT_NAME"
        "STORAGE_ACCOUNT"
        "OPENAI_API_KEY"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var:-}" ]; then
            error_exit "Required environment variable '$var' is not set in $ENV_FILE"
        fi
    done
    log OK "All required environment variables set"
    
    # Validate password strength
    if [ ${#POSTGRES_ADMIN_PASSWORD} -lt 16 ]; then
        error_exit "POSTGRES_ADMIN_PASSWORD must be at least 16 characters"
    fi
    log OK "PostgreSQL password meets minimum length requirement"
    
    # Check Azure login
    log INFO "Checking Azure CLI login status..."
    if ! az account show &>/dev/null; then
        error_exit "Not logged in to Azure CLI. Run 'az login' first."
    fi
    log OK "Azure CLI authenticated"
    
    # Set subscription
    log INFO "Setting Azure subscription..."
    az account set --subscription "$AZURE_SUBSCRIPTION_ID"
    local current_sub=$(az account show --query id -o tsv)
    if [ "$current_sub" != "$AZURE_SUBSCRIPTION_ID" ]; then
        error_exit "Failed to set subscription to $AZURE_SUBSCRIPTION_ID"
    fi
    log OK "Subscription set: $(az account show --query name -o tsv)"
    
    # Check if location is valid
    log INFO "Validating location '$AZURE_LOCATION'..."
    if ! az account list-locations --query "[?name=='$AZURE_LOCATION']" -o tsv | grep -q "$AZURE_LOCATION"; then
        error_exit "Invalid Azure location: $AZURE_LOCATION"
    fi
    log OK "Location validated"
    
    # Check if resource group already exists (just warn, continue automatically for idempotent reruns)
    if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
        log WARN "Resource group '$RESOURCE_GROUP' already exists - continuing with existing resources"
    fi
    
    log OK "Pre-flight checks completed"
}

#-------------------------------------------------------------------------------
# STEP 1: RESOURCE GROUP
#-------------------------------------------------------------------------------

create_resource_group() {
    log STEP "Step 1/8: Creating Resource Group"
    
    if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
        log WARN "Resource group '$RESOURCE_GROUP' already exists, skipping creation"
    else
        log INFO "Creating resource group '$RESOURCE_GROUP' in '$AZURE_LOCATION'..."
        az group create \
            --name "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" \
            --tags "Project=GDOHealth" "Environment=Production" "ManagedBy=Script"
        log OK "Resource group created"
    fi
}

#-------------------------------------------------------------------------------
# STEP 2: POSTGRESQL
#-------------------------------------------------------------------------------

create_postgresql() {
    log STEP "Step 2/8: Creating PostgreSQL Flexible Server"
    
    # Check if server exists
    if az postgres flexible-server show --name "$POSTGRES_SERVER" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log WARN "PostgreSQL server '$POSTGRES_SERVER' already exists, skipping creation"
    else
        log INFO "Creating PostgreSQL Flexible Server (this takes 3-5 minutes)..."
        az postgres flexible-server create \
            --resource-group "$RESOURCE_GROUP" \
            --name "$POSTGRES_SERVER" \
            --location "$AZURE_LOCATION" \
            --admin-user "$POSTGRES_ADMIN_USER" \
            --admin-password "$POSTGRES_ADMIN_PASSWORD" \
            --sku-name Standard_B1ms \
            --tier Burstable \
            --storage-size 32 \
            --version 16 \
            --high-availability Disabled \
            --backup-retention 7 \
            --geo-redundant-backup Disabled \
            --public-access 0.0.0.0 \
            --tags "Project=GDOHealth"
        
        log INFO "Waiting for server to be fully provisioned..."
        az postgres flexible-server wait \
            --name "$POSTGRES_SERVER" \
            --resource-group "$RESOURCE_GROUP" \
            --created
        
        log OK "PostgreSQL server created"
    fi
    
    # Create database if it doesn't exist
    log INFO "Creating database '$POSTGRES_DB'..."
    if az postgres flexible-server db show --resource-group "$RESOURCE_GROUP" --server-name "$POSTGRES_SERVER" --database-name "$POSTGRES_DB" &>/dev/null; then
        log WARN "Database '$POSTGRES_DB' already exists"
    else
        az postgres flexible-server db create \
            --resource-group "$RESOURCE_GROUP" \
            --server-name "$POSTGRES_SERVER" \
            --database-name "$POSTGRES_DB"
        log OK "Database created"
    fi
    
    # Export connection info
    export POSTGRES_HOST="${POSTGRES_SERVER}.postgres.database.azure.com"
    log INFO "PostgreSQL host: $POSTGRES_HOST"
}

#-------------------------------------------------------------------------------
# STEP 3: FIREWALL RULES
#-------------------------------------------------------------------------------

configure_firewall() {
    log STEP "Step 3/8: Configuring Firewall Rules"
    
    # Allow Azure services
    log INFO "Creating firewall rule for Azure services..."
    az postgres flexible-server firewall-rule create \
        --resource-group "$RESOURCE_GROUP" \
        --name "$POSTGRES_SERVER" \
        --rule-name "AllowAzureServices" \
        --start-ip-address 0.0.0.0 \
        --end-ip-address 0.0.0.0 \
        2>/dev/null || log WARN "Firewall rule 'AllowAzureServices' may already exist"
    
    # Get current IP and allow it
    log INFO "Detecting your public IP address..."
    MY_IP=$(curl -s --max-time 10 ifconfig.me || curl -s --max-time 10 api.ipify.org || echo "")
    
    if [ -n "$MY_IP" ]; then
        log INFO "Your IP: $MY_IP"
        log INFO "Creating firewall rule for migration access..."
        az postgres flexible-server firewall-rule create \
            --resource-group "$RESOURCE_GROUP" \
            --name "$POSTGRES_SERVER" \
            --rule-name "AllowMigrationIP" \
            --start-ip-address "$MY_IP" \
            --end-ip-address "$MY_IP" \
            2>/dev/null || log WARN "Firewall rule 'AllowMigrationIP' may already exist"
        log OK "Firewall rules configured"
    else
        log WARN "Could not detect public IP. You may need to add firewall rule manually."
    fi
}

#-------------------------------------------------------------------------------
# STEP 4: DATABASE SCHEMA
#-------------------------------------------------------------------------------

apply_schema() {
    log STEP "Step 4/8: Applying Database Schema"
    
    # Generate schema file
    log INFO "Generating schema.sql..."
    cat > "$SCHEMA_FILE" << 'EOSQL'
-- GDO Health Database Schema
-- Azure PostgreSQL Flexible Server
-- Generated by deploy-gdo-health.sh

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- USERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE,
    display_name TEXT,
    age_range TEXT,
    account_type TEXT DEFAULT 'freemium' CHECK (account_type IN ('freemium', 'paid', 'test')),
    country_code TEXT DEFAULT 'ES',
    freemium_limit INTEGER DEFAULT 5,
    freemium_used INTEGER DEFAULT 0,
    freemium_time_limit_minutes INTEGER DEFAULT 15,
    freemium_message_limit INTEGER DEFAULT 20,
    wp_user_id BIGINT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    preferences JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_wp_id ON users(wp_user_id) WHERE wp_user_id IS NOT NULL;

-- ============================================
-- EXPERTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS experts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wp_product_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    specialty TEXT,
    description TEXT,
    image_url TEXT,
    is_active BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experts_active ON experts(is_active) WHERE is_active = true;

-- Seed expert data (upsert)
INSERT INTO experts (wp_product_id, name, specialty, description, sort_order) VALUES
    (321, 'Melisa Green', 'Especialista en Sueño', 'Ayuda con problemas de sueño e insomnio', 1),
    (387, 'Lucía Ramos', 'Acompañamiento en Momentos de Pérdida', 'Apoyo en procesos de duelo', 2),
    (390, 'Leonardo Kim', 'Pensamiento y Comportamiento Obsesivo', 'Especialista en TOC', 3),
    (392, 'Clara Rodrigues', 'Paz en Tus Pensamientos', 'Ansiedad y pensamientos intrusivos', 4),
    (399, 'Beatriz Valle', 'Especialista en Dependencias', 'Adicciones y comportamientos compulsivos', 5),
    (403, 'Roberto Miller', 'Atención y Organización', 'TDAH y productividad', 6)
ON CONFLICT (wp_product_id) DO UPDATE SET
    name = EXCLUDED.name,
    specialty = EXCLUDED.specialty,
    description = EXCLUDED.description,
    sort_order = EXCLUDED.sort_order;

-- ============================================
-- SESSIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expert_id UUID REFERENCES experts(id),
    convo_id TEXT,
    mode TEXT DEFAULT 'intake' CHECK (mode IN ('intake', 'advice', 'reflection', 'summary', 'ended')),
    session_type TEXT CHECK (session_type IN ('freemium', 'test', 'paid')),
    intake_fields JSONB DEFAULT '{}'::jsonb,
    intake_score INTEGER DEFAULT 0,
    summary TEXT,
    sentiment TEXT,
    key_points JSONB DEFAULT '[]'::jsonb,
    duration_seconds INTEGER DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(user_id, mode) WHERE mode != 'ended';

-- ============================================
-- CONVERSATION TURNS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS conversation_turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    content_type TEXT DEFAULT 'text' CHECK (content_type IN ('text', 'audio_transcript')),
    tool_calls JSONB,
    safety_flags JSONB,
    tokens_used INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_created ON conversation_turns(created_at);

-- ============================================
-- ENTITLEMENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS entitlements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('woocommerce', 'test', 'promo', 'stripe', 'admin')),
    product_type TEXT DEFAULT 'session_pack',
    sessions_total INTEGER NOT NULL,
    sessions_used INTEGER DEFAULT 0,
    valid_from TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    order_reference TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entitlements_user ON entitlements(user_id);
CREATE INDEX IF NOT EXISTS idx_entitlements_valid ON entitlements(user_id, valid_until) 
    WHERE sessions_used < sessions_total;

-- ============================================
-- SESSION AUDIT TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS session_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id),
    expert_id UUID REFERENCES experts(id),
    session_type TEXT NOT NULL CHECK (session_type IN ('freemium', 'test', 'paid')),
    action TEXT NOT NULL CHECK (action IN ('consumed', 'refunded', 'expired')),
    ip_address INET,
    user_agent TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user ON session_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON session_audit(created_at DESC);

-- ============================================
-- CRISIS RESOURCES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS crisis_resources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    country_code TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('hotline', 'chat', 'emergency', 'text')),
    name TEXT NOT NULL,
    contact TEXT NOT NULL,
    description TEXT,
    language TEXT DEFAULT 'es',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crisis_country ON crisis_resources(country_code);

-- Seed crisis resources (upsert by country + name)
INSERT INTO crisis_resources (country_code, resource_type, name, contact, description) VALUES
    ('ES', 'hotline', 'Teléfono de la Esperanza', '717 003 717', 'Línea de atención a la conducta suicida 24h'),
    ('MX', 'hotline', 'SAPTEL', '55 5259-8121', 'Línea de la vida'),
    ('AR', 'hotline', 'Centro de Asistencia al Suicida', '135', 'Atención en crisis 24h'),
    ('CO', 'hotline', 'Línea 106', '106', 'Línea de atención en crisis'),
    ('CL', 'hotline', 'Fono Salud Responde', '600 360 7777', 'Orientación en salud mental'),
    ('PE', 'hotline', 'Línea 113', '113', 'Línea de salud mental MINSA')
ON CONFLICT DO NOTHING;

-- ============================================
-- FUNCTIONS
-- ============================================

-- Get available sessions for a user
CREATE OR REPLACE FUNCTION get_available_sessions(p_user_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_freemium_available INTEGER;
    v_entitlement_available INTEGER;
BEGIN
    SELECT GREATEST(0, freemium_limit - freemium_used)
    INTO v_freemium_available
    FROM users
    WHERE id = p_user_id;
    
    SELECT COALESCE(SUM(sessions_total - sessions_used), 0)
    INTO v_entitlement_available
    FROM entitlements
    WHERE user_id = p_user_id
    AND (valid_until IS NULL OR valid_until > NOW())
    AND sessions_used < sessions_total;
    
    RETURN COALESCE(v_freemium_available, 0) + COALESCE(v_entitlement_available, 0);
END;
$$;

-- Use a session (atomic operation)
CREATE OR REPLACE FUNCTION use_session(
    p_user_id UUID, 
    p_expert_id UUID DEFAULT NULL
)
RETURNS TABLE(success BOOLEAN, session_type TEXT, message TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_freemium_available INTEGER;
    v_entitlement_id UUID;
    v_session_type TEXT;
BEGIN
    PERFORM id FROM users WHERE id = p_user_id FOR UPDATE;
    
    SELECT GREATEST(0, freemium_limit - freemium_used)
    INTO v_freemium_available
    FROM users
    WHERE id = p_user_id;
    
    IF v_freemium_available > 0 THEN
        UPDATE users
        SET freemium_used = freemium_used + 1,
            updated_at = NOW()
        WHERE id = p_user_id;
        
        v_session_type := 'freemium';
    ELSE
        SELECT id INTO v_entitlement_id
        FROM entitlements
        WHERE user_id = p_user_id
        AND sessions_used < sessions_total
        AND (valid_until IS NULL OR valid_until > NOW())
        ORDER BY valid_until NULLS LAST, created_at ASC
        LIMIT 1
        FOR UPDATE;
        
        IF v_entitlement_id IS NOT NULL THEN
            UPDATE entitlements
            SET sessions_used = sessions_used + 1
            WHERE id = v_entitlement_id;
            
            SELECT CASE WHEN source = 'test' THEN 'test' ELSE 'paid' END
            INTO v_session_type
            FROM entitlements
            WHERE id = v_entitlement_id;
        ELSE
            RETURN QUERY SELECT FALSE, NULL::TEXT, 'No sessions available'::TEXT;
            RETURN;
        END IF;
    END IF;
    
    INSERT INTO session_audit (user_id, expert_id, session_type, action)
    VALUES (p_user_id, p_expert_id, v_session_type, 'consumed');
    
    RETURN QUERY SELECT TRUE, v_session_type, 'Session consumed successfully'::TEXT;
END;
$$;

-- Auto-update timestamps trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tr_users_updated_at ON users;
CREATE TRIGGER tr_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS tr_sessions_updated_at ON sessions;
CREATE TRIGGER tr_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Cleanup old conversation turns
CREATE OR REPLACE FUNCTION cleanup_old_turns()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_deleted INTEGER;
BEGIN
    DELETE FROM conversation_turns
    WHERE created_at < NOW() - INTERVAL '30 days';
    
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$;

-- ============================================
-- VIEWS
-- ============================================
CREATE OR REPLACE VIEW user_session_summary AS
SELECT 
    u.id as user_id,
    u.email,
    u.display_name,
    u.account_type,
    u.freemium_limit,
    u.freemium_used,
    get_available_sessions(u.id) as available_sessions,
    (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id) as total_sessions,
    (SELECT MAX(created_at) FROM sessions s WHERE s.user_id = u.id) as last_session_at
FROM users u;

-- ============================================
-- VERIFICATION
-- ============================================
DO $$
BEGIN
    RAISE NOTICE 'Schema applied successfully!';
    RAISE NOTICE 'Tables created: users, experts, sessions, conversation_turns, entitlements, session_audit, crisis_resources';
    RAISE NOTICE 'Functions created: get_available_sessions, use_session, update_updated_at, cleanup_old_turns';
END $$;
EOSQL

    log OK "Schema file generated: $SCHEMA_FILE"

    # Apply schema (only if psql is available)
    if [ "$PSQL_AVAILABLE" = true ]; then
        log INFO "Applying schema to PostgreSQL..."
        export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"

        if psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" -f "$SCHEMA_FILE" >> "$LOG_FILE" 2>&1; then
            log OK "Database schema applied successfully"
        else
            error_exit "Failed to apply database schema. Check log file for details."
        fi

        unset PGPASSWORD
    else
        log WARN "Skipping schema application (psql not available)"
        log INFO "To apply schema manually, run in Azure Cloud Shell:"
        log INFO "  psql -h $POSTGRES_HOST -U $POSTGRES_ADMIN_USER -d $POSTGRES_DB -f schema.sql"
    fi
}

#-------------------------------------------------------------------------------
# STEP 5: KEY VAULT
#-------------------------------------------------------------------------------

create_keyvault() {
    log STEP "Step 5/8: Creating Key Vault"
    
    # Check if Key Vault exists
    if az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log WARN "Key Vault '$KEYVAULT_NAME' already exists, skipping creation"
    else
        log INFO "Creating Key Vault '$KEYVAULT_NAME'..."
        az keyvault create \
            --name "$KEYVAULT_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" \
            --sku standard \
            --enable-rbac-authorization false
        log OK "Key Vault created"
    fi
    
    # Add secrets
    log INFO "Storing secrets in Key Vault..."
    
    az keyvault secret set \
        --vault-name "$KEYVAULT_NAME" \
        --name "OpenAiApiKey" \
        --value "$OPENAI_API_KEY" \
        --output none
    log OK "Stored: OpenAiApiKey"
    
    az keyvault secret set \
        --vault-name "$KEYVAULT_NAME" \
        --name "PostgresHost" \
        --value "$POSTGRES_HOST" \
        --output none
    log OK "Stored: PostgresHost"
    
    az keyvault secret set \
        --vault-name "$KEYVAULT_NAME" \
        --name "PostgresPassword" \
        --value "$POSTGRES_ADMIN_PASSWORD" \
        --output none
    log OK "Stored: PostgresPassword"
    
    az keyvault secret set \
        --vault-name "$KEYVAULT_NAME" \
        --name "PostgresConnectionString" \
        --value "host=$POSTGRES_HOST dbname=$POSTGRES_DB user=$POSTGRES_ADMIN_USER password=$POSTGRES_ADMIN_PASSWORD sslmode=require" \
        --output none
    log OK "Stored: PostgresConnectionString"
    
    log OK "All secrets stored in Key Vault"
}

#-------------------------------------------------------------------------------
# STEP 6: STORAGE ACCOUNT
#-------------------------------------------------------------------------------

create_storage() {
    log STEP "Step 6/8: Creating Storage Account"
    
    if az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log WARN "Storage account '$STORAGE_ACCOUNT' already exists, skipping creation"
    else
        log INFO "Creating storage account '$STORAGE_ACCOUNT'..."
        az storage account create \
            --name "$STORAGE_ACCOUNT" \
            --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" \
            --sku Standard_LRS \
            --kind StorageV2 \
            --tags "Project=GDOHealth"
        log OK "Storage account created"
    fi
}

#-------------------------------------------------------------------------------
# STEP 7: FUNCTION APP
#-------------------------------------------------------------------------------

create_functionapp() {
    log STEP "Step 7/8: Creating Function App"
    
    if az functionapp show --name "$FUNCTIONAPP_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log WARN "Function App '$FUNCTIONAPP_NAME' already exists, skipping creation"
    else
        log INFO "Creating Function App '$FUNCTIONAPP_NAME'..."
        az functionapp create \
            --name "$FUNCTIONAPP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --storage-account "$STORAGE_ACCOUNT" \
            --consumption-plan-location "$AZURE_LOCATION" \
            --runtime python \
            --runtime-version 3.11 \
            --functions-version 4 \
            --os-type Linux \
            --tags "Project=GDOHealth"
        log OK "Function App created"
    fi
    
    # Enable managed identity
    log INFO "Enabling managed identity..."
    az functionapp identity assign \
        --name "$FUNCTIONAPP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --output none
    
    # Get identity principal ID
    IDENTITY_ID=$(az functionapp identity show \
        --name "$FUNCTIONAPP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query principalId -o tsv)
    
    if [ -z "$IDENTITY_ID" ]; then
        error_exit "Failed to get Function App managed identity"
    fi
    log OK "Managed identity enabled: $IDENTITY_ID"
    
    # Grant Key Vault access
    log INFO "Granting Key Vault access to Function App..."
    az keyvault set-policy \
        --name "$KEYVAULT_NAME" \
        --object-id "$IDENTITY_ID" \
        --secret-permissions get list \
        --output none
    log OK "Key Vault access granted"
    
    # Configure app settings
    log INFO "Configuring application settings..."
    az functionapp config appsettings set \
        --name "$FUNCTIONAPP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --settings \
            "OPENAI_API_KEY=@Microsoft.KeyVault(VaultName=$KEYVAULT_NAME;SecretName=OpenAiApiKey)" \
            "POSTGRES_HOST=@Microsoft.KeyVault(VaultName=$KEYVAULT_NAME;SecretName=PostgresHost)" \
            "POSTGRES_DB=$POSTGRES_DB" \
            "POSTGRES_USER=$POSTGRES_ADMIN_USER" \
            "POSTGRES_PASSWORD=@Microsoft.KeyVault(VaultName=$KEYVAULT_NAME;SecretName=PostgresPassword)" \
        --output none
    log OK "Application settings configured"
    
    log OK "Function App URL: https://$FUNCTIONAPP_NAME.azurewebsites.net"
}

#-------------------------------------------------------------------------------
# STEP 8: SUMMARY
#-------------------------------------------------------------------------------

print_summary() {
    log STEP "Step 8/8: Deployment Complete!"
    
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║                    GDO HEALTH INFRASTRUCTURE DEPLOYED                      ║"
    echo "╠════════════════════════════════════════════════════════════════════════════╣"
    echo "║                                                                            ║"
    echo "║  RESOURCES CREATED:                                                        ║"
    echo "║  ─────────────────────────────────────────────────────────────────         ║"
    printf "║  %-74s ║\n" "• Resource Group:    $RESOURCE_GROUP"
    printf "║  %-74s ║\n" "• PostgreSQL Server: $POSTGRES_SERVER"
    printf "║  %-74s ║\n" "• PostgreSQL DB:     $POSTGRES_DB"
    printf "║  %-74s ║\n" "• Key Vault:         $KEYVAULT_NAME"
    printf "║  %-74s ║\n" "• Storage Account:   $STORAGE_ACCOUNT"
    printf "║  %-74s ║\n" "• Function App:      $FUNCTIONAPP_NAME"
    echo "║                                                                            ║"
    echo "║  CONNECTION INFO:                                                          ║"
    echo "║  ─────────────────────────────────────────────────────────────────         ║"
    printf "║  %-74s ║\n" "• PostgreSQL Host: $POSTGRES_HOST"
    printf "║  %-74s ║\n" "• Function App URL: https://$FUNCTIONAPP_NAME.azurewebsites.net"
    echo "║                                                                            ║"
    echo "║  MANUAL STEPS REQUIRED:                                                    ║"
    echo "║  ─────────────────────────────────────────────────────────────────         ║"
    echo "║  1. Configure Azure AD B2C tenant (see deployment guide)                   ║"
    echo "║  2. Add DNS CNAME record for custom domain                                 ║"
    echo "║  3. Configure custom domain + SSL in Function App                          ║"
    echo "║  4. Deploy Function App code                                               ║"
    echo "║                                                                            ║"
    printf "║  %-74s ║\n" "Log file: $LOG_FILE"
    echo "║                                                                            ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Save deployment info
    cat > "${SCRIPT_DIR}/deployment-info.json" << EOF
{
    "deployedAt": "$(date -Iseconds)",
    "resourceGroup": "$RESOURCE_GROUP",
    "location": "$AZURE_LOCATION",
    "postgresServer": "$POSTGRES_SERVER",
    "postgresHost": "$POSTGRES_HOST",
    "postgresDatabase": "$POSTGRES_DB",
    "keyVault": "$KEYVAULT_NAME",
    "storageAccount": "$STORAGE_ACCOUNT",
    "functionApp": "$FUNCTIONAPP_NAME",
    "functionAppUrl": "https://$FUNCTIONAPP_NAME.azurewebsites.net"
}
EOF
    
    log OK "Deployment info saved to: ${SCRIPT_DIR}/deployment-info.json"
}

#-------------------------------------------------------------------------------
# MAIN EXECUTION
#-------------------------------------------------------------------------------

main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║           GDO HEALTH - AZURE INFRASTRUCTURE DEPLOYMENT                     ║"
    echo "║                    Switzerland North Region                                 ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    log INFO "Starting deployment at $(date)"
    log INFO "Log file: $LOG_FILE"
    
    preflight_checks
    create_resource_group
    create_postgresql
    configure_firewall
    apply_schema
    create_keyvault
    create_storage
    create_functionapp
    print_summary
    
    log OK "Deployment completed successfully at $(date)"
}

# Run main function
main "$@"
