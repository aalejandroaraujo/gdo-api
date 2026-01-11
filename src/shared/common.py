"""
Shared common utilities for Azure Functions in the mental health triage platform.
Provides OpenAI client configuration and NocoDB persistence logic.

This module follows project-wide standards and provides async, reusable functions
for all Azure Functions in the mhtp-chat-backend project.
"""

import os
import logging
from typing import Dict, Any
import httpx
from openai import AsyncOpenAI


def get_openai_client() -> AsyncOpenAI:
    """
    Get configured OpenAI client with retry and timeout settings.
    
    Returns:
        AsyncOpenAI: Configured OpenAI client instance with proper retry,
                    timeout, and connection pooling settings
    
    Raises:
        ValueError: If OPENAI_API_KEY environment variable is missing
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    # Configure HTTP client with timeout and connection limits
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),  # 30s total, 10s connect
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
    )
    
    # Configure OpenAI client with retry settings
    client = AsyncOpenAI(
        api_key=api_key,
        http_client=http_client,
        max_retries=3
    )
    
    return client


async def nocodb_upsert(session_id: str, summary: str) -> Dict[str, Any]:
    """
    Upsert session summary to NocoDB using their REST API.
    
    Implements proper upsert logic by attempting to update an existing record first,
    and creating a new record if the update fails with 404 (not found).
    
    Configuration is handled via environment variables:
    - NOCODB_TABLE_NAME: Table name to use (defaults to "sessions")
    - NOCODB_AUTH_METHOD: Auth method to use ("xc-token" or "bearer", defaults to "xc-token")
    
    Args:
        session_id: Unique session identifier
        summary: Session summary text to store
        
    Returns:
        Dict[str, Any]: Response from NocoDB API containing the created/updated record
        
    Raises:
        ValueError: If required environment variables (NOCODB_API_URL, NOCODB_API_KEY) are missing
        httpx.HTTPError: If the API request fails after retry attempts
        Exception: For any other unexpected errors during the operation
    """
    api_url = os.environ.get("NOCODB_API_URL")
    api_key = os.environ.get("NOCODB_API_KEY")
    
    if not api_url or not api_key:
        raise ValueError("NOCODB_API_URL and NOCODB_API_KEY environment variables are required")
    
    # Get configuration from environment variables
    table_name = os.environ.get("NOCODB_TABLE_NAME", "sessions")
    auth_method = os.environ.get("NOCODB_AUTH_METHOD", "xc-token")
    
    # Prepare headers based on authentication method
    if auth_method.lower() == "bearer":
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    else:  # default to xc-token
        headers = {
            "Content-Type": "application/json",
            "xc-token": api_key
        }
    
    # Prepare data payload
    data = {
        "session_id": session_id,
        "summary": summary
    }
    
    # Add updated_at field based on table type
    if table_name == "sessions":
        data["updated_at"] = None  # NocoDB will auto-populate this for sessions table
    # For summaries table, we could add current timestamp, but keeping it simple per spec
    
    # Configure HTTP client with timeout
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Construct URLs based on table name
            base_url = f"{api_url.rstrip('/')}/api/v1/db/data/noco/{table_name}"
            
            # First, try to update existing record
            if table_name == "summaries":
                # For summaries table, use query parameter approach
                update_url = f"{base_url}?where=(session_id,eq,{session_id})"
                response = await client.patch(
                    update_url,
                    headers=headers,
                    json=data
                )
            else:
                # For sessions table, use direct ID approach
                update_url = f"{base_url}/{session_id}"
                response = await client.patch(
                    update_url,
                    headers=headers,
                    json=data
                )
            
            # If record doesn't exist (404) or conflict (409), create a new one
            if response.status_code in [404, 409, 400]:
                logging.info(f"Session {session_id} not found or conflict, creating new record")
                create_url = base_url
                response = await client.post(
                    create_url,
                    headers=headers,
                    json=data
                )
            
            # Raise exception for any HTTP errors
            response.raise_for_status()
            
            logging.info(f"Successfully upserted session {session_id} to NocoDB {table_name} table")
            return response.json()
            
        except httpx.HTTPError as e:
            error_msg = f"NocoDB API error for session {session_id}: {str(e)}"
            logging.error(error_msg)
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"Response status: {e.response.status_code}, body: {e.response.text}")
            raise
        except Exception as e:
            error_msg = f"Unexpected error in nocodb_upsert for session {session_id}: {str(e)}"
            logging.error(error_msg)
            raise

