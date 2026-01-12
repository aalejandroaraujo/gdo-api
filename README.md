# GDO Health API

Azure Functions backend for mental health chatbot assistance, providing structured intake assessment, safety screening, and session management.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up local environment
cp local.settings.json.example local.settings.json
# Edit local.settings.json with your JWT_SIGNING_KEY

# Run locally
func start --port 9090
```

## What It Does

- **Extracts structured data** from natural language (symptoms, triggers, duration, etc.)
- **Screens for safety concerns** using OpenAI moderation (self-harm, violence)
- **Manages conversation flow** (intake, advice, reflection, summary modes)
- **Persists sessions** to PostgreSQL for continuity
- **Secures endpoints** with JWT Bearer token authentication

## API Endpoints

### Public (No Auth)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/test` | Health check |
| `POST /api/auth/dev-token` | Get development JWT token |

### Protected (Auth Required)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/extract_fields_from_input` | Parse user message into structured fields |
| `POST /api/risk_escalation_check` | Safety screening via moderation API |
| `POST /api/switch_chat_mode` | Determine conversation state |
| `POST /api/evaluate_intake_progress` | Check if enough data collected |
| `POST /api/save_session_summary` | Persist session to database |
| `POST /api/orchestrators/{name}` | Start durable orchestration |

See [docs/API.md](docs/API.md) for full request/response schemas.

## Authentication

All protected endpoints require a JWT Bearer token:

```bash
# 1. Get a token
curl -X POST http://localhost:9090/api/auth/dev-token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user"}'

# 2. Use the token
curl -X POST http://localhost:9090/api/extract_fields_from_input \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "I feel anxious", "session_id": "123"}'
```

## Project Structure

```
function_app.py          # All functions (v2 decorator model)
src/
  auth/                  # JWT authentication module
    middleware.py        # @require_auth decorator
  shared/                # Shared utilities (OpenAI client, DB)
infrastructure/          # Azure deployment scripts
docs/                    # Documentation
  API.md                 # API reference
  ARCHITECTURE.md        # System design
  roadmap/               # Development phases
host.json                # Azure Functions config
requirements.txt         # Python dependencies
```

## Documentation

- [API Reference](docs/API.md) - Endpoint schemas, authentication, examples
- [Architecture](docs/ARCHITECTURE.md) - System design, data flow, infrastructure
- [Roadmap](docs/roadmap/README.md) - Development phases and migration plans

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `JWT_SIGNING_KEY` | Secret key for JWT signing (32+ chars) |
| `OPENAI_API_KEY` | OpenAI API key |
| `AzureWebJobsStorage` | Storage connection for Durable Functions |

### Optional

| Variable | Description |
|----------|-------------|
| `DISABLE_DEV_TOKENS` | Set to `true` to disable dev token endpoint |
| `POSTGRES_CONNECTION_STRING` | PostgreSQL connection string |

## Tech Stack

- **Runtime:** Python 3.11+ / Azure Functions v2
- **AI:** OpenAI gpt-4.1-mini, Moderation API
- **Database:** Azure PostgreSQL Flexible Server
- **Auth:** Self-signed JWT (PyJWT)
- **Secrets:** Azure Key Vault
- **Region:** Switzerland North

## Development Status

See [docs/roadmap/](docs/roadmap/) for current progress:

- **Phase 0:** Infrastructure - Complete
- **Phase 1:** Simple Auth (JWT) - Complete
- **Phase 2:** Function App Deployment - In Progress
- **Phase 3:** Microsoft Entra External ID - Planned
