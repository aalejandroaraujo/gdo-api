# Mental Health Triage Platform

Azure Functions backend for mental health chatbot assistance, providing structured intake assessment, safety screening, and session management.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
func start
```

## What It Does

- **Extracts structured data** from natural language (symptoms, triggers, duration, etc.)
- **Screens for safety concerns** using OpenAI moderation (self-harm, violence)
- **Manages conversation flow** (intake, advice, reflection, summary modes)
- **Persists sessions** to NocoDB for continuity

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/extract_fields_from_input` | Parse user message into structured fields |
| `POST /api/risk_escalation_check` | Safety screening via moderation API |
| `POST /api/switch_chat_mode` | Determine conversation state |
| `POST /api/evaluate_intake_progress` | Check if enough data collected |
| `POST /api/save_session_summary` | Persist session to database |
| `GET /api/test` | Health check |

See [docs/API.md](docs/API.md) for full request/response schemas.

## Project Structure

```
function_app.py      # All functions (v2 decorator model)
src/shared/          # Shared utilities (OpenAI client, NocoDB)
host.json            # Azure Functions config
requirements.txt     # Python dependencies
dockerfile           # Container deployment
docs/                # Documentation
```

## Documentation

- [API Reference](docs/API.md) - Endpoint schemas and examples
- [Architecture](docs/ARCHITECTURE.md) - System design and data flow
- [Deployment](docs/DEPLOYMENT.md) - Azure setup and environment variables
- [MCP Integration](docs/MCP_INTEGRATION.md) - Wrapping as agent tools

## Environment Variables

```
OPENAI_API_KEY          # Required
NOCODB_API_URL          # Required for session persistence
NOCODB_API_KEY          # Required for session persistence
AzureWebJobsStorage     # Required for Durable Functions
```

## Tech Stack

- Python 3.11+ / Azure Functions v2
- OpenAI (gpt-4o-mini, moderation API)
- NocoDB (session storage)
- Docker (container deployment)
