# Architecture

## Overview

This platform provides backend services for a mental health chatbot. It uses Azure Durable Functions for orchestration, OpenAI for NLP capabilities, and PostgreSQL for data persistence.

## System Design

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Mobile App /   │────▶│  Azure Functions │────▶│   OpenAI    │
│  Chatbot Client │     │  (with Auth)     │     │  gpt-4.1    │
└─────────────────┘     └──────────────────┘     └─────────────┘
        │                       │
        │                       ▼
        │               ┌─────────────┐
        │               │ PostgreSQL  │
        │               │ (Azure)     │
        │               └─────────────┘
        │                       │
        ▼                       ▼
   ┌─────────────────────────────────────┐
   │          Azure Key Vault            │
   │  (JWT Key, DB Password, API Keys)   │
   └─────────────────────────────────────┘
```

## Authentication Flow

```
Client Request
     │
     ▼
┌────────────────────┐
│ Authorization:     │
│ Bearer <JWT>       │
└────────────────────┘
     │
     ▼
┌────────────────────┐
│ Auth Middleware    │  Validate JWT signature & expiration
│ @require_auth      │  Extract user claims (sub, iat, exp)
└────────────────────┘
     │
     ├─── Invalid ──▶ 401 Unauthorized
     │
     ▼ Valid
┌────────────────────┐
│ req.user = payload │  Attach user to request
└────────────────────┘
     │
     ▼
┌────────────────────┐
│ Business Logic     │  Protected endpoint executes
└────────────────────┘
```

## Data Flow

```
User Message
     │
     ▼
┌────────────────────┐
│ switch_chat_mode   │  Determine conversation state
└────────────────────┘
     │
     ▼
┌────────────────────┐
│ extract_fields     │  Parse into structured data
└────────────────────┘
     │
     ▼
┌────────────────────┐
│ risk_escalation    │  Safety screening
└────────────────────┘
     │
     ▼
┌────────────────────┐
│ evaluate_progress  │  Check if intake complete
└────────────────────┘
     │
     ▼
┌────────────────────┐
│ save_session       │  Persist to PostgreSQL
└────────────────────┘
```

## Mental Health Dimensions

The system tracks 7 dimensions with weighted scoring:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| symptoms | 3 | What the user is experiencing |
| duration | 2 | How long symptoms have persisted |
| triggers | 2 | What causes or worsens symptoms |
| impact_on_life | 2 | Effects on daily functioning |
| intensity | 1 | Severity level |
| frequency | 1 | How often symptoms occur |
| coping_mechanisms | 1 | Current strategies used |

**Total possible:** 12 points
**Threshold:** 6 points = sufficient data collected

## Conversation Modes

| Mode | Purpose |
|------|---------|
| `intake` | Gather information about symptoms |
| `advice` | Provide coping strategies |
| `reflection` | Therapeutic discussion |
| `summary` | Session wrap-up |

## Technology Stack

| Component | Technology |
|-----------|------------|
| Runtime | Python 3.11+ |
| Framework | Azure Functions v2 (decorator model) |
| AI | OpenAI gpt-4.1-mini, Moderation API |
| Database | Azure PostgreSQL Flexible Server |
| Auth | Self-signed JWT (PyJWT) |
| Secrets | Azure Key Vault |
| Deployment | Azure (Switzerland North region) |

## Azure Infrastructure

| Resource | Name | Purpose |
|----------|------|---------|
| Resource Group | rg-gdo-health-prod | Container for all resources |
| PostgreSQL | psql-gdo-health-prod | Session and user data storage |
| Key Vault | kv-gdo-health-prod | Secrets management |
| Storage Account | stgdohealthprod | Durable Functions state |
| Function App | func-gdo-health-prod | API hosting |

## File Structure

```
function_app.py          # All function definitions
src/
  auth/
    __init__.py          # Auth module exports
    middleware.py        # JWT validation & @require_auth decorator
  shared/
    common.py            # OpenAI client, database persistence
    storage.py           # Storage utilities
infrastructure/
  deploy-gdo-health.sh   # Azure deployment script
  schema.sql             # PostgreSQL schema
docs/
  API.md                 # API reference
  ARCHITECTURE.md        # This file
  roadmap/               # Development phases
host.json                # Azure Functions configuration
local.settings.json      # Local dev configuration
```

## Database Schema

PostgreSQL with 7 tables:

- `users` - User accounts
- `sessions` - Chat sessions per user
- `messages` - Individual messages in sessions
- `extracted_fields` - Structured intake data
- `risk_flags` - Safety screening results
- `session_summaries` - AI-generated session summaries
- `audit_log` - Security and compliance logging

Extensions enabled: `uuid-ossp`, `pgcrypto`

## Orchestrators

Two orchestrators are available:

1. **mental_health_orchestrator** - Full workflow with retry policies
2. **minimal_orchestrator** - Simple test for environment verification

Orchestrators use 3-attempt retry with 5-second intervals.

## Security

- **Authentication:** JWT Bearer tokens required for all protected endpoints
- **Token Expiration:** 24 hours
- **Secrets:** Stored in Azure Key Vault with managed identity access
- **HTTPS:** Enforced by Azure Functions
- **Database:** SSL required, credentials in Key Vault

---

*See [roadmap/](roadmap/) for development phases and migration plans.*
