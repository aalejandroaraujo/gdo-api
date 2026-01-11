"""
Azure Functions - Mental Health Triage Platform
================================================
v2 decorator model implementation consolidating all functions.

Functions:
- test_function: Health check endpoint
- evaluate_intake_progress: Scores collected intake data
- extract_fields_from_input: Extracts structured fields using OpenAI
- risk_escalation_check: Safety screening via OpenAI moderation
- save_session_summary: Persists sessions to NocoDB
- switch_chat_mode: Determines conversation mode using AI
- mental_health_orchestrator: Durable orchestrator for the workflow
- minimal_orchestrator: Simple test orchestrator
"""

import json
import logging
from datetime import timedelta

import azure.functions as func
import azure.durable_functions as df

from src.shared.common import get_openai_client, nocodb_upsert


# Create the Durable Functions app instance
app = df.DFApp()


# =============================================================================
# HTTP FUNCTIONS
# =============================================================================

@app.function_name("TestFunction")
@app.route(route="test", methods=["GET"])
def test_function(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint to verify Azure Functions detection."""
    return func.HttpResponse("Hello World! Function detected successfully!")


@app.function_name("EvaluateIntakeProgress")
@app.route(route="evaluate_intake_progress", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def evaluate_intake_progress(req: func.HttpRequest) -> func.HttpResponse:
    """
    Evaluate intake progress based on collected fields.
    Calculates a weighted score and determines if enough data has been collected.
    Threshold: 6 out of 12 points.
    """
    logging.info("evaluate_intake_progress function processed a request.")

    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON in request body."}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required."}),
                status_code=400,
                mimetype="application/json"
            )

        if "session_id" not in req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required field: session_id."}),
                status_code=400,
                mimetype="application/json"
            )

        if "fields" not in req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required field: fields."}),
                status_code=400,
                mimetype="application/json"
            )

        fields = req_body["fields"]
        if not isinstance(fields, dict):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid input: fields must be an object."}),
                status_code=400,
                mimetype="application/json"
            )

        field_weights = {
            "symptoms": 3,
            "duration": 2,
            "triggers": 2,
            "intensity": 1,
            "frequency": 1,
            "impact_on_life": 2,
            "coping_mechanisms": 1
        }

        score = 0
        for field_name, weight in field_weights.items():
            field_value = fields.get(field_name)
            if field_value is not None and isinstance(field_value, str) and field_value.strip():
                score += weight

        enough_data = score >= 6

        return func.HttpResponse(
            json.dumps({"status": "ok", "score": score, "enough_data": enough_data}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Unexpected error in evaluate_intake_progress: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error occurred."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("ExtractFieldsFromInput")
@app.route(route="extract_fields_from_input", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def extract_fields_from_input(req: func.HttpRequest) -> func.HttpResponse:
    """Extract structured fields from user messages using OpenAI gpt-4.1-mini."""
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing message field or OpenAI call failed."}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body or not req_body.get("message"):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing message field or OpenAI call failed."}),
                status_code=400,
                mimetype="application/json"
            )

        message = req_body["message"]
        session_id = req_body.get("session_id")

        logging.info(f"Processing field extraction for session: {session_id}")

        system_prompt = "You are a data extractor for a mental health assistant. Extract these fields from the user message: symptoms, duration, triggers, intensity, frequency, impact_on_life, coping_mechanisms. Return null for unmentioned fields. Output as flat JSON. Do not guess."

        client = get_openai_client()

        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.3,
            max_tokens=500,
            timeout=10
        )

        content = response.choices[0].message.content.strip()
        fields = json.loads(content)

        return func.HttpResponse(
            json.dumps({"status": "ok", "fields": fields}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error in extract_fields_from_input: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Missing message field or OpenAI call failed."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("RiskEscalationCheck")
@app.route(route="risk_escalation_check", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def risk_escalation_check(req: func.HttpRequest) -> func.HttpResponse:
    """Evaluate user messages using OpenAI moderation endpoint for safety screening."""
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON in request body."}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required field: message."}),
                status_code=400,
                mimetype="application/json"
            )

        message = req_body.get("message", "").strip()
        session_id = req_body.get("session_id", "")

        if not message:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Message cannot be empty."}),
                status_code=400,
                mimetype="application/json"
            )

        client = get_openai_client()

        try:
            moderation_response = await client.moderations.create(input=message)
            results = moderation_response.results[0]
            categories = results.categories
            flagged = results.flagged

            flag = None
            if flagged:
                if getattr(categories, 'self_harm', False) or getattr(categories, 'self_harm_intent', False):
                    flag = "self-harm"
                elif getattr(categories, 'violence', False) or getattr(categories, 'harassment_threatening', False):
                    flag = "violence"

            logging.info(f"Risk check completed for session: {session_id}, flag: {flag}")

            return func.HttpResponse(
                json.dumps({"status": "ok", "flag": flag}),
                status_code=200,
                mimetype="application/json"
            )

        except Exception as openai_error:
            logging.error(f"OpenAI moderation API error: {str(openai_error)}")
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Moderation API failed."}),
                status_code=500,
                mimetype="application/json"
            )

    except Exception as e:
        logging.error(f"Unexpected error in risk_escalation_check: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("SaveSessionSummary")
@app.route(route="save_session_summary", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def save_session_summary(req: func.HttpRequest) -> func.HttpResponse:
    """Save session summary to NocoDB."""
    logging.info('Processing save_session_summary request')

    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Invalid JSON in request body"}),
                status_code=400,
                mimetype="application/json"
            )

        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required"}),
                status_code=400,
                mimetype="application/json"
            )

        session_id = req_body.get("session_id")
        summary = req_body.get("summary")

        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing session_id field."}),
                status_code=400,
                mimetype="application/json"
            )

        if not summary or not isinstance(summary, str) or not summary.strip():
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing summary field."}),
                status_code=400,
                mimetype="application/json"
            )

        if len(summary) > 2000:
            summary = summary[:2000]
            logging.info('Summary truncated to 2000 characters')

        try:
            await nocodb_upsert(session_id.strip(), summary.strip())
            logging.info('Successfully saved summary')

            return func.HttpResponse(
                json.dumps({"status": "ok"}),
                status_code=200,
                mimetype="application/json"
            )

        except Exception as e:
            logging.error(f'Failed to save summary: {str(e)}')
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "NocoDB request failed."}),
                status_code=500,
                mimetype="application/json"
            )

    except Exception as e:
        logging.error(f'Unexpected error in save_session_summary: {str(e)}')
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error."}),
            status_code=500,
            mimetype="application/json"
        )


@app.function_name("SwitchChatMode")
@app.route(route="switch_chat_mode", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def switch_chat_mode(req: func.HttpRequest) -> func.HttpResponse:
    """Determine chat mode switch using OpenAI analysis."""
    try:
        req_body = req.get_json()
        if not req_body:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Request body is required."}),
                status_code=400,
                mimetype="application/json"
            )

        session_id = req_body.get("session_id")
        context = req_body.get("context")

        if not session_id:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing required session_id field."}),
                status_code=400,
                mimetype="application/json"
            )

        if not context or not isinstance(context, str):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing or invalid context field."}),
                status_code=400,
                mimetype="application/json"
            )

        client = get_openai_client()

        system_prompt = "You are a conversation controller for a mental health assistant. Based on the user message, decide the mode: intake, advice, reflection, or summary. Only return one word."

        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            max_tokens=10,
            temperature=0.1
        )

        new_mode = response.choices[0].message.content.strip().lower()
        valid_modes = ["intake", "advice", "reflection", "summary"]
        if new_mode not in valid_modes:
            new_mode = "advice"

        return func.HttpResponse(
            json.dumps({"status": "ok", "new_mode": new_mode}),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Invalid JSON in request body."}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception:
        logging.error("Error in switch_chat_mode function")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Internal server error."}),
            status_code=500,
            mimetype="application/json"
        )


# =============================================================================
# DURABLE FUNCTIONS - ORCHESTRATORS
# =============================================================================

@app.orchestration_trigger(context_name="context")
def mental_health_orchestrator(context: df.DurableOrchestrationContext):
    """Main orchestrator for mental health assistance workflow."""
    try:
        retry_options = df.RetryOptions(
            first_retry_interval=timedelta(seconds=5),
            max_number_of_attempts=3
        )

        payload = context.get_input()
        context.set_custom_status({'step': 'orchestration_started', 'session_id': payload.get('session_id', 'unknown')})

        validated = yield context.call_activity_with_retry('ActivityIntake', retry_options, payload)
        context.set_custom_status({'step': 'intake_completed', 'result': validated})

        route = yield context.call_activity_with_retry('ActivityRouteDecision', retry_options, validated)
        context.set_custom_status({'step': 'routing_decision', 'route': route})

        assistant_result = yield context.call_activity_with_retry(
            'ActivityInvokeAssistant', retry_options, {'payload': payload, 'route': route}
        )
        context.set_custom_status({'step': 'assistant_invoked', 'assistant_type': route})

        save_status = yield context.call_activity_with_retry(
            'ActivitySaveSummary', retry_options,
            {'session_id': payload['session_id'], 'message': payload['message'],
             'assistant_response': assistant_result, 'routing_decision': route}
        )
        context.set_custom_status({'step': 'summary_saved', 'save_status': save_status})

        context.set_custom_status({'step': 'orchestration_completed', 'session_id': payload.get('session_id', 'unknown')})
        return assistant_result

    except Exception as ex:
        context.set_custom_status({
            'step': 'orchestration_failed', 'error': str(ex),
            'session_id': payload.get('session_id', 'unknown') if 'payload' in locals() else 'unknown'
        })
        raise


@app.orchestration_trigger(context_name="context")
def minimal_orchestrator(context: df.DurableOrchestrationContext):
    """Minimal test orchestrator for environment verification."""
    return "Minimal Orchestrator is running!"


# =============================================================================
# DURABLE FUNCTIONS - HTTP STARTER
# =============================================================================

@app.function_name("StartOrchestration")
@app.route(route="orchestrators/{function_name}", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
@app.durable_client_input(client_name="client")
async def start_orchestration(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    """HTTP starter for durable orchestrations."""
    function_name = req.route_params.get('function_name')

    try:
        req_body = req.get_json()
    except ValueError:
        req_body = {}

    instance_id = await client.start_new(function_name, client_input=req_body)
    logging.info(f"Started orchestration '{function_name}' with ID = '{instance_id}'")

    return client.create_check_status_response(req, instance_id)
