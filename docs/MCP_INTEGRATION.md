# MCP Integration Guide

How to wrap these Azure Functions as MCP tools for your wellbeing platform chatbots.

## Reusable Functions

These functions are ready to use as agent tools:

| Function | MCP Tool Name | Use Case |
|----------|---------------|----------|
| `extract_fields_from_input` | `extract_wellbeing_fields` | Parse sleep patterns, anxiety symptoms, mood data |
| `risk_escalation_check` | `safety_check` | Crisis detection for vulnerable users |
| `switch_chat_mode` | `determine_conversation_mode` | Adaptive chatbot state management |
| `save_session_summary` | `persist_session` | Session continuity across conversations |
| `evaluate_intake_progress` | `evaluate_assessment_progress` | Track questionnaire completion |

## MCP Server Example

```python
from mcp.server import Server
import httpx

server = Server("wellbeing-tools")

FUNCTION_APP_URL = "https://your-function-app.azurewebsites.net/api"
FUNCTION_KEY = "your-function-key"

@server.tool()
async def extract_wellbeing_fields(message: str, session_id: str) -> dict:
    """Extract structured wellbeing data from user message."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FUNCTION_APP_URL}/extract_fields_from_input",
            json={"message": message, "session_id": session_id},
            headers={"x-functions-key": FUNCTION_KEY}
        )
        return response.json()

@server.tool()
async def safety_check(message: str, session_id: str) -> dict:
    """Check for crisis indicators in user message."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FUNCTION_APP_URL}/risk_escalation_check",
            json={"message": message, "session_id": session_id},
            headers={"x-functions-key": FUNCTION_KEY}
        )
        return response.json()

@server.tool()
async def determine_conversation_mode(context: str, session_id: str) -> dict:
    """Determine the appropriate conversation mode."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FUNCTION_APP_URL}/switch_chat_mode",
            json={"context": context, "session_id": session_id},
            headers={"x-functions-key": FUNCTION_KEY}
        )
        return response.json()

@server.tool()
async def persist_session(session_id: str, summary: str) -> dict:
    """Save session summary for continuity."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FUNCTION_APP_URL}/save_session_summary",
            json={"session_id": session_id, "summary": summary},
            headers={"x-functions-key": FUNCTION_KEY}
        )
        return response.json()

if __name__ == "__main__":
    server.run()
```

## Customization for Wellbeing Platform

### Sleep Tracking

Modify the field extraction prompt for sleep-specific data:
- sleep_quality
- sleep_duration
- wake_times
- sleep_environment
- bedtime_routine

### Anxiety Management

Adapt for anxiety screening (GAD-7 style):
- worry_frequency
- control_difficulty
- restlessness
- fatigue
- concentration_issues

### Mood Tracking

Track emotional states:
- current_mood
- mood_triggers
- energy_level
- social_interaction
- physical_symptoms

## Integration Options

### Option 1: Direct HTTP Calls
Call Azure Functions directly from your chatbot. Simplest approach.

### Option 2: MCP Server Wrapper
Wrap functions in MCP protocol for standardized tool interfaces.

### Option 3: Port to Native MCP
Rewrite core logic as native MCP tools (removes Azure dependency).

## Authentication

Use function-level keys:
```
x-functions-key: your-function-key
```

Get keys from Azure Portal > Function App > App Keys
