import logging
import json

def save_session_summary(
    session_id: str,
    user_message: str,
    assistant_reply: str,
    routing_decision: str,
    timestamp: str
) -> None:
    """
    Placeholder stub for saving a chat session summary.
    Currently only logs the input parameters for debugging.
    """
    record = {
        "session_id": session_id,
        "user_message": user_message,
        "assistant_reply": assistant_reply,
        "routing_decision": routing_decision,
        "timestamp": timestamp
    }
    logging.info(f"[save_session_summary] {json.dumps(record)}")

