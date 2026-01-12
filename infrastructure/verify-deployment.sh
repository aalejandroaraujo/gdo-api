#!/bin/bash
#===============================================================================
# GDO Health - Deployment Verification Script
# 
# This script verifies that:
# 1. All expected resources were deployed correctly
# 2. No unexpected resources exist in the resource group
# 3. All configurations are correct
# 4. Services are accessible
#
# Usage: ./verify-deployment.sh
#===============================================================================

set -euo pipefail

#-------------------------------------------------------------------------------
# CONFIGURATION
#-------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.gdo-health"
REPORT_FILE="${SCRIPT_DIR}/verification-report-$(date +%Y%m%d-%H%M%S).txt"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

#-------------------------------------------------------------------------------
# HELPER FUNCTIONS
#-------------------------------------------------------------------------------

log_header() {
    local msg="$1"
    echo -e "\n${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $msg${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}\n"
    echo "" >> "$REPORT_FILE"
    echo "=== $msg ===" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
}

log_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    echo "[PASS] $1" >> "$REPORT_FILE"
    ((PASS_COUNT++))
}

log_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    echo "[FAIL] $1" >> "$REPORT_FILE"
    ((FAIL_COUNT++))
}

log_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    echo "[WARN] $1" >> "$REPORT_FILE"
    ((WARN_COUNT++))
}

log_info() {
    echo -e "${BLUE}ℹ INFO${NC}: $1"
    echo "[INFO] $1" >> "$REPORT_FILE"
}

#-------------------------------------------------------------------------------
# EXPECTED RESOURCES
#-------------------------------------------------------------------------------

# Define exactly what resources should exist
declare -A EXPECTED_RESOURCES=(
    ["Microsoft.Resources/resourceGroups"]="$RESOURCE_GROUP"
    ["Microsoft.DBforPostgreSQL/flexibleServers"]="$POSTGRES_SERVER"
    ["Microsoft.KeyVault/vaults"]="$KEYVAULT_NAME"
    ["Microsoft.Storage/storageAccounts"]="$STORAGE_ACCOUNT"
    ["Microsoft.Web/sites"]="$FUNCTIONAPP_NAME"
    ["Microsoft.Web/serverfarms"]="*"  # Auto-created consumption plan
)

# Resource types that are expected but auto-generated (allow any name)
AUTO_GENERATED_TYPES=(
    "Microsoft.Web/serverfarms"
    "Microsoft.Insights/components"
    "microsoft.insights/actiongroups"
    "microsoft.insights/metricalerts"
    "Microsoft.Insights/autoscalesettings"
)

#-------------------------------------------------------------------------------
# LOAD ENVIRONMENT
#-------------------------------------------------------------------------------

load_environment() {
    log_header "Loading Environment Configuration"
    
    if [ ! -f "$ENV_FILE" ]; then
        log_fail "Environment file not found: $ENV_FILE"
        exit 1
    fi
    
    set -a
    source "$ENV_FILE"
    set +a
    
    # Set derived variables
    export POSTGRES_HOST="${POSTGRES_SERVER}.postgres.database.azure.com"
    
    log_pass "Environment file loaded"
    log_info "Resource Group: $RESOURCE_GROUP"
    log_info "Location: $AZURE_LOCATION"
}

#-------------------------------------------------------------------------------
# CHECK AZURE LOGIN
#-------------------------------------------------------------------------------

check_azure_login() {
    log_header "Checking Azure Authentication"
    
    if ! az account show &>/dev/null; then
        log_fail "Not logged in to Azure CLI"
        exit 1
    fi
    log_pass "Azure CLI authenticated"
    
    # Set subscription
    az account set --subscription "$AZURE_SUBSCRIPTION_ID" 2>/dev/null
    
    local current_sub=$(az account show --query id -o tsv)
    if [ "$current_sub" != "$AZURE_SUBSCRIPTION_ID" ]; then
        log_fail "Wrong subscription. Expected: $AZURE_SUBSCRIPTION_ID, Got: $current_sub"
    else
        log_pass "Correct subscription selected: $(az account show --query name -o tsv)"
    fi
}

#-------------------------------------------------------------------------------
# CHECK RESOURCE GROUP
#-------------------------------------------------------------------------------

check_resource_group() {
    log_header "Checking Resource Group"
    
    if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
        log_pass "Resource group exists: $RESOURCE_GROUP"
        
        local location=$(az group show --name "$RESOURCE_GROUP" --query location -o tsv)
        if [ "$location" == "$AZURE_LOCATION" ]; then
            log_pass "Correct location: $location"
        else
            log_fail "Wrong location. Expected: $AZURE_LOCATION, Got: $location"
        fi
        
        local tags=$(az group show --name "$RESOURCE_GROUP" --query tags -o json)
        if echo "$tags" | grep -q "GDOHealth"; then
            log_pass "Project tag present"
        else
            log_warn "Project tag 'GDOHealth' not found"
        fi
    else
        log_fail "Resource group does not exist: $RESOURCE_GROUP"
    fi
}

#-------------------------------------------------------------------------------
# CHECK POSTGRESQL
#-------------------------------------------------------------------------------

check_postgresql() {
    log_header "Checking PostgreSQL Flexible Server"
    
    if az postgres flexible-server show --name "$POSTGRES_SERVER" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_pass "PostgreSQL server exists: $POSTGRES_SERVER"
        
        # Check SKU
        local sku=$(az postgres flexible-server show --name "$POSTGRES_SERVER" --resource-group "$RESOURCE_GROUP" --query sku.name -o tsv)
        log_info "SKU: $sku"
        if [[ "$sku" == *"B1ms"* ]] || [[ "$sku" == *"Burstable"* ]]; then
            log_pass "Using cost-effective Burstable SKU"
        else
            log_warn "Not using Burstable SKU (higher cost): $sku"
        fi
        
        # Check version
        local version=$(az postgres flexible-server show --name "$POSTGRES_SERVER" --resource-group "$RESOURCE_GROUP" --query version -o tsv)
        log_info "PostgreSQL version: $version"
        
        # Check location
        local location=$(az postgres flexible-server show --name "$POSTGRES_SERVER" --resource-group "$RESOURCE_GROUP" --query location -o tsv)
        if [ "$location" == "$AZURE_LOCATION" ]; then
            log_pass "Correct location: $location"
        else
            log_fail "Wrong location. Expected: $AZURE_LOCATION, Got: $location"
        fi
        
        # Check database exists
        if az postgres flexible-server db show --resource-group "$RESOURCE_GROUP" --server-name "$POSTGRES_SERVER" --database-name "$POSTGRES_DB" &>/dev/null; then
            log_pass "Database exists: $POSTGRES_DB"
        else
            log_fail "Database does not exist: $POSTGRES_DB"
        fi
        
        # Check firewall rules
        local fw_rules=$(az postgres flexible-server firewall-rule list --resource-group "$RESOURCE_GROUP" --name "$POSTGRES_SERVER" -o json)
        if echo "$fw_rules" | grep -q "AllowAzureServices"; then
            log_pass "Azure services firewall rule exists"
        else
            log_warn "Azure services firewall rule not found"
        fi
        
        # Test connectivity
        log_info "Testing database connectivity..."
        export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"
        if psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" -c "SELECT 1;" &>/dev/null; then
            log_pass "Database connectivity verified"
            
            # Check tables
            local tables=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")
            tables=$(echo "$tables" | tr -d ' ')
            log_info "Tables found: $tables"
            
            if [ "$tables" -ge 7 ]; then
                log_pass "Expected tables created (7+ tables)"
            else
                log_fail "Missing tables. Expected at least 7, found $tables"
            fi
            
            # Check experts data
            local experts=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM experts;")
            experts=$(echo "$experts" | tr -d ' ')
            if [ "$experts" -ge 6 ]; then
                log_pass "Expert seed data present ($experts experts)"
            else
                log_warn "Expert seed data may be missing (found $experts)"
            fi
            
            # Check crisis resources
            local crisis=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM crisis_resources;")
            crisis=$(echo "$crisis" | tr -d ' ')
            if [ "$crisis" -ge 6 ]; then
                log_pass "Crisis resources seed data present ($crisis resources)"
            else
                log_warn "Crisis resources seed data may be missing (found $crisis)"
            fi
            
            # Check functions
            local functions=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM pg_proc WHERE pronamespace = 'public'::regnamespace;")
            functions=$(echo "$functions" | tr -d ' ')
            log_info "PostgreSQL functions found: $functions"
            
        else
            log_fail "Cannot connect to database"
        fi
        unset PGPASSWORD
        
    else
        log_fail "PostgreSQL server does not exist: $POSTGRES_SERVER"
    fi
}

#-------------------------------------------------------------------------------
# CHECK KEY VAULT
#-------------------------------------------------------------------------------

check_keyvault() {
    log_header "Checking Key Vault"
    
    if az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_pass "Key Vault exists: $KEYVAULT_NAME"
        
        # Check location
        local location=$(az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" --query location -o tsv)
        if [ "$location" == "$AZURE_LOCATION" ]; then
            log_pass "Correct location: $location"
        else
            log_fail "Wrong location. Expected: $AZURE_LOCATION, Got: $location"
        fi
        
        # Check secrets
        local expected_secrets=("OpenAiApiKey" "PostgresHost" "PostgresPassword" "PostgresConnectionString")
        for secret in "${expected_secrets[@]}"; do
            if az keyvault secret show --vault-name "$KEYVAULT_NAME" --name "$secret" &>/dev/null; then
                log_pass "Secret exists: $secret"
            else
                log_fail "Secret missing: $secret"
            fi
        done
        
    else
        log_fail "Key Vault does not exist: $KEYVAULT_NAME"
    fi
}

#-------------------------------------------------------------------------------
# CHECK STORAGE ACCOUNT
#-------------------------------------------------------------------------------

check_storage() {
    log_header "Checking Storage Account"
    
    if az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_pass "Storage account exists: $STORAGE_ACCOUNT"
        
        local sku=$(az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query sku.name -o tsv)
        log_info "SKU: $sku"
        if [ "$sku" == "Standard_LRS" ]; then
            log_pass "Using cost-effective Standard_LRS"
        else
            log_warn "Not using Standard_LRS (might be higher cost): $sku"
        fi
        
    else
        log_fail "Storage account does not exist: $STORAGE_ACCOUNT"
    fi
}

#-------------------------------------------------------------------------------
# CHECK FUNCTION APP
#-------------------------------------------------------------------------------

check_functionapp() {
    log_header "Checking Function App"
    
    if az functionapp show --name "$FUNCTIONAPP_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_pass "Function App exists: $FUNCTIONAPP_NAME"
        
        # Check runtime
        local runtime=$(az functionapp config show --name "$FUNCTIONAPP_NAME" --resource-group "$RESOURCE_GROUP" --query linuxFxVersion -o tsv)
        log_info "Runtime: $runtime"
        if [[ "$runtime" == *"python"* ]] || [[ "$runtime" == *"Python"* ]]; then
            log_pass "Python runtime configured"
        else
            log_warn "Expected Python runtime, got: $runtime"
        fi
        
        # Check managed identity
        local identity=$(az functionapp identity show --name "$FUNCTIONAPP_NAME" --resource-group "$RESOURCE_GROUP" --query principalId -o tsv 2>/dev/null || echo "")
        if [ -n "$identity" ]; then
            log_pass "Managed identity enabled: $identity"
            
            # Check Key Vault access
            local policies=$(az keyvault show --name "$KEYVAULT_NAME" --query "properties.accessPolicies[?objectId=='$identity']" -o json)
            if [ "$policies" != "[]" ]; then
                log_pass "Key Vault access policy configured"
            else
                log_fail "Key Vault access policy not found for Function App"
            fi
        else
            log_fail "Managed identity not enabled"
        fi
        
        # Check app settings
        local settings=$(az functionapp config appsettings list --name "$FUNCTIONAPP_NAME" --resource-group "$RESOURCE_GROUP" -o json)
        
        if echo "$settings" | grep -q "OPENAI_API_KEY"; then
            log_pass "OPENAI_API_KEY setting configured"
        else
            log_fail "OPENAI_API_KEY setting missing"
        fi
        
        if echo "$settings" | grep -q "POSTGRES_HOST"; then
            log_pass "POSTGRES_HOST setting configured"
        else
            log_fail "POSTGRES_HOST setting missing"
        fi
        
        # Check URL
        local url=$(az functionapp show --name "$FUNCTIONAPP_NAME" --resource-group "$RESOURCE_GROUP" --query defaultHostName -o tsv)
        log_info "Function App URL: https://$url"
        
    else
        log_fail "Function App does not exist: $FUNCTIONAPP_NAME"
    fi
}

#-------------------------------------------------------------------------------
# CHECK FOR UNEXPECTED RESOURCES
#-------------------------------------------------------------------------------

check_unexpected_resources() {
    log_header "Checking for Unexpected Resources"
    
    log_info "Listing all resources in resource group..."
    
    # Get all resources
    local resources=$(az resource list --resource-group "$RESOURCE_GROUP" -o json)
    
    # Expected resource names
    local expected_names=(
        "$POSTGRES_SERVER"
        "$KEYVAULT_NAME"
        "$STORAGE_ACCOUNT"
        "$FUNCTIONAPP_NAME"
    )
    
    # Parse each resource
    local unexpected=()
    local total_count=0
    
    while IFS= read -r line; do
        local name=$(echo "$line" | jq -r '.name')
        local type=$(echo "$line" | jq -r '.type')
        ((total_count++))
        
        # Check if this is an expected resource
        local is_expected=false
        
        for expected in "${expected_names[@]}"; do
            if [[ "$name" == "$expected"* ]]; then
                is_expected=true
                break
            fi
        done
        
        # Check if it's an auto-generated type (like App Service Plan)
        for auto_type in "${AUTO_GENERATED_TYPES[@]}"; do
            if [ "$type" == "$auto_type" ]; then
                is_expected=true
                break
            fi
        done
        
        if [ "$is_expected" = false ]; then
            unexpected+=("$type: $name")
        fi
        
    done < <(echo "$resources" | jq -c '.[]')
    
    log_info "Total resources in resource group: $total_count"
    
    if [ ${#unexpected[@]} -eq 0 ]; then
        log_pass "No unexpected resources found"
    else
        log_warn "Found ${#unexpected[@]} potentially unexpected resource(s):"
        for item in "${unexpected[@]}"; do
            log_warn "  - $item"
        done
        echo ""
        log_info "These may be auto-generated dependencies. Review manually if concerned."
    fi
    
    # List all resources for reference
    echo ""
    log_info "Full resource inventory:"
    az resource list --resource-group "$RESOURCE_GROUP" --query "[].{Name:name, Type:type}" -o table
}

#-------------------------------------------------------------------------------
# CHECK COSTS
#-------------------------------------------------------------------------------

check_estimated_costs() {
    log_header "Cost Estimation"
    
    log_info "Estimated monthly costs (CHF):"
    echo "  ┌─────────────────────────────────┬────────────┐"
    echo "  │ Resource                        │ Est. Cost  │"
    echo "  ├─────────────────────────────────┼────────────┤"
    echo "  │ PostgreSQL Flexible (B1ms)      │ ~12        │"
    echo "  │ Azure Functions (Consumption)   │ ~5-15      │"
    echo "  │ Key Vault (Standard)            │ ~1         │"
    echo "  │ Storage Account (LRS)           │ ~1         │"
    echo "  │ Azure AD B2C (Free tier)        │ 0          │"
    echo "  ├─────────────────────────────────┼────────────┤"
    echo "  │ TOTAL                           │ ~19-29     │"
    echo "  └─────────────────────────────────┴────────────┘"
    echo ""
    log_info "Note: Actual costs depend on usage. Check Azure Cost Management for accurate data."
}

#-------------------------------------------------------------------------------
# GENERATE SUMMARY
#-------------------------------------------------------------------------------

generate_summary() {
    log_header "Verification Summary"
    
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║                         VERIFICATION RESULTS                               ║"
    echo "╠════════════════════════════════════════════════════════════════════════════╣"
    printf "║  ${GREEN}PASSED${NC}: %-66s ║\n" "$PASS_COUNT checks"
    printf "║  ${RED}FAILED${NC}: %-66s ║\n" "$FAIL_COUNT checks"
    printf "║  ${YELLOW}WARNINGS${NC}: %-64s ║\n" "$WARN_COUNT checks"
    echo "╠════════════════════════════════════════════════════════════════════════════╣"
    
    if [ $FAIL_COUNT -eq 0 ]; then
        echo "║  ${GREEN}✓ DEPLOYMENT VERIFIED SUCCESSFULLY${NC}                                       ║"
    else
        echo "║  ${RED}✗ DEPLOYMENT HAS ISSUES - REVIEW FAILURES ABOVE${NC}                         ║"
    fi
    
    echo "╠════════════════════════════════════════════════════════════════════════════╣"
    printf "║  %-74s ║\n" "Report saved to: $REPORT_FILE"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Save summary to report
    echo "" >> "$REPORT_FILE"
    echo "=== SUMMARY ===" >> "$REPORT_FILE"
    echo "PASSED: $PASS_COUNT" >> "$REPORT_FILE"
    echo "FAILED: $FAIL_COUNT" >> "$REPORT_FILE"
    echo "WARNINGS: $WARN_COUNT" >> "$REPORT_FILE"
    echo "Timestamp: $(date)" >> "$REPORT_FILE"
    
    # Return appropriate exit code
    if [ $FAIL_COUNT -gt 0 ]; then
        return 1
    fi
    return 0
}

#-------------------------------------------------------------------------------
# MAIN
#-------------------------------------------------------------------------------

main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║           GDO HEALTH - DEPLOYMENT VERIFICATION                             ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Initialize report file
    echo "GDO Health Deployment Verification Report" > "$REPORT_FILE"
    echo "Generated: $(date)" >> "$REPORT_FILE"
    echo "==========================================" >> "$REPORT_FILE"
    
    load_environment
    check_azure_login
    check_resource_group
    check_postgresql
    check_keyvault
    check_storage
    check_functionapp
    check_unexpected_resources
    check_estimated_costs
    generate_summary
}

# Run main
main "$@"
