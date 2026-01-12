# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- JWT Bearer token authentication system
  - `src/auth/middleware.py` with `@require_auth` decorator
  - `POST /api/auth/dev-token` endpoint for development tokens
  - 24-hour token expiration
  - Configurable via `DISABLE_DEV_TOKENS` environment variable
- PyJWT and asyncpg dependencies
- Development roadmap documentation (`docs/roadmap/`)
- Azure infrastructure deployment scripts (`infrastructure/`)

### Changed
- All API endpoints now require authentication except `/api/test` and `/api/auth/dev-token`
- Updated to gpt-4.1-mini model
- Migrated from NocoDB to Azure PostgreSQL Flexible Server
- Local development port changed to 9090

### Security
- JWT signing key stored in Azure Key Vault
- Database credentials managed via Key Vault
- SSL required for PostgreSQL connections

## [0.1.0] - 2026-01-12

### Added
- Initial Azure Functions v2 implementation
- Mental health intake assessment endpoints
  - `POST /api/extract_fields_from_input` - Extract structured data from text
  - `POST /api/risk_escalation_check` - Safety screening
  - `POST /api/switch_chat_mode` - Conversation state management
  - `POST /api/evaluate_intake_progress` - Intake completeness scoring
  - `POST /api/save_session_summary` - Session persistence
- Durable Functions orchestrators
  - `mental_health_orchestrator` - Full workflow with retries
  - `minimal_orchestrator` - Environment verification
- OpenAI integration (gpt-4.1-mini, Moderation API)
- Azure infrastructure
  - Resource Group: `rg-gdo-health-prod`
  - PostgreSQL: `psql-gdo-health-prod`
  - Key Vault: `kv-gdo-health-prod`
  - Storage Account: `stgdohealthprod`
  - Function App: `func-gdo-health-prod`
- PostgreSQL schema with 7 tables
  - users, sessions, messages, extracted_fields
  - risk_flags, session_summaries, audit_log

### Infrastructure
- Deployed to Switzerland North region (GDPR compliance)
- PostgreSQL extensions enabled: uuid-ossp, pgcrypto
- Managed identity for Key Vault access
