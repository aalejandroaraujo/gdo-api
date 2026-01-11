# Architecture

## Overview

This platform provides backend services for a mental health chatbot. It uses Azure Durable Functions for orchestration and OpenAI for NLP capabilities.

## System Design

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Chatbot Client │────▶│  Azure Functions │────▶│   OpenAI    │
└─────────────────┘     └──────────────────┘     └─────────────┘
                               │
                               ▼
                        ┌─────────────┐
                        │   NocoDB    │
                        └─────────────┘
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
│ save_session       │  Persist to database
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
| AI | OpenAI gpt-4o-mini, Moderation API |
| Database | NocoDB |
| Deployment | Docker, Azure Container Registry |

## File Structure

```
function_app.py          # All function definitions
src/
  shared/
    common.py            # OpenAI client, NocoDB persistence
    storage.py           # Storage utilities
host.json                # Azure Functions configuration
```

## Orchestrators

Two orchestrators are available:

1. **mental_health_orchestrator** - Full workflow with retry policies
2. **minimal_orchestrator** - Simple test for environment verification

Orchestrators use 3-attempt retry with 5-second intervals.
