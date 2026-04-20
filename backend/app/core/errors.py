# app/core/errors.py
"""Translate raw LLM provider errors into friendly user-facing messages."""

import re
import json
import logging

logger = logging.getLogger("ocin")


def parse_llm_provider_error(exception: Exception) -> dict:
    """
    Parse structured error details from LLM provider exceptions.

    Handles pydantic-ai ModelHTTPError and raw error strings with structured JSON.

    Returns dict with:
    - status_code: HTTP status code (if available)
    - provider: Provider name (extracted from error context)
    - model_id: Model ID (if available)
    - error_category: 'auth', 'rate_limit', 'model_not_found', 'billing', 'unknown', etc.
    - error_message: Human-readable error message from provider
    - user_message: Plain-English message for user
    - raw_body: Full structured body (for debugging)
    """
    result = {
        "status_code": None,
        "provider": "unknown",
        "model_id": None,
        "error_category": "unknown",
        "error_message": str(exception),
        "user_message": "The AI model encountered an error. Please try again or switch models.",
        "raw_body": None,
    }

    exc_str = str(exception)

    # Try to parse structured error from string representation
    # Format: "status_code: 404, model_name: gemini-2.0-flash, body: {...}"
    try:
        # Extract status_code
        status_match = re.search(r'status_code:\s*(\d+)', exc_str)
        if status_match:
            result["status_code"] = int(status_match.group(1))

        # Extract model_id/name
        model_match = re.search(r'model_name:\s*([\w\-\.]+)', exc_str)
        if model_match:
            result["model_id"] = model_match.group(1)

        # Extract provider from model_id
        if result["model_id"]:
            if "gemini" in result["model_id"]:
                result["provider"] = "Google"
            elif "gpt-" in result["model_id"]:
                result["provider"] = "OpenAI"
            elif "claude" in result["model_id"]:
                result["provider"] = "Anthropic"

        # Try to parse body: {...}
        body_match = re.search(r'body:\s*(\{.+\})', exc_str)
        if body_match:
            try:
                body = json.loads(body_match.group(1))
                result["raw_body"] = body

                # Parse provider-specific error formats
                if "error" in body:
                    error = body["error"]

                    # Google Gemini format: {'error': {'code': 404, 'message': '...', 'status': 'NOT_FOUND'}}
                    if isinstance(error, dict):
                        google_error = error
                        code = google_error.get("code")
                        message = google_error.get("message")
                        status = google_error.get("status")

                        if code == 404 or status == "NOT_FOUND":
                            result["error_category"] = "model_not_found"
                            result["error_message"] = message
                            result["user_message"] = f"The model `{result['model_id']}` isn't available on Google. {message}. Please edit this agent and select a different model in its settings."

                        elif code == 401 or status == "UNAUTHENTICATED":
                            result["error_category"] = "auth"
                            result["error_message"] = message
                            result["user_message"] = f"Your Google API key was rejected. Please check your API key configuration in Settings."

                        elif code == 429:
                            result["error_category"] = "rate_limit"
                            result["error_message"] = message
                            result["user_message"] = f"Google is rate-limiting requests. Please wait a moment and try again."

                        else:
                            # Use generic message
                            result["user_message"] = f"Google returned an error: {message}. Please try again."

                    # OpenAI format: often has 'error' or 'message' at top level
                    elif isinstance(body.get("error"), str):
                        message = body["error"]
                        result["error_message"] = message

                        if "api_key" in message.lower() or "invalid" in message.lower() or "401" in exc_str:
                            result["error_category"] = "auth"
                            result["user_message"] = f"Your OpenAI API key was rejected. Please check your API key configuration in Settings."
                        elif "rate" in message.lower() or "429" in exc_str:
                            result["error_category"] = "rate_limit"
                            result["user_message"] = f"OpenAI is rate-limiting requests. Please wait a moment and try again."
                        elif "model" in message.lower() and ("not found" in message.lower() or "does not exist" in message.lower()):
                            result["error_category"] = "model_not_found"
                            result["user_message"] = f"The model configured for this agent is not available on OpenAI. {message}. Please edit the agent and select a different model."
                        else:
                            result["user_message"] = f"OpenAI returned an error: {message}. Please try again or switch models."

                    # Anthropic format: often has 'error' or 'message' with 'type' field
                    elif "anthropic" in exc_str.lower():
                        message = body.get("error", {}).get("message", body.get("message", ""))
                        error_type = body.get("error", {}).get("type", "")
                        result["error_message"] = message

                        if error_type == "authentication_error" or "401" in exc_str:
                            result["error_category"] = "auth"
                            result["user_message"] = f"Your Anthropic API key was rejected. Please check your API key configuration in Settings."
                        elif "rate" in message.lower() or "429" in exc_str:
                            result["error_category"] = "rate_limit"
                            result["user_message"] = f"Anthropic is rate-limiting requests. Please wait a moment and try again."
                        elif "model" in message.lower() and ("not found" in message.lower() or "does not exist" in message.lower()):
                            result["error_category"] = "model_not_found"
                            result["user_message"] = f"The model configured for this agent is not available on Anthropic. {message}. Please edit the agent and select a different model."
                        else:
                            result["user_message"] = f"Anthropic returned an error: {message}. Please try again."

                    else:
                        result["user_message"] = f"The provider returned an error. Please try again or switch models."

            except json.JSONDecodeError as e:
                logger.warning({"event": "error_body_parse_failed", "error": str(e), "raw_error": exc_str})
        else:
            # Fallback to string-based matching if no structured body found
            result["user_message"] = friendly_llm_error(exc_str)["message"]
            result["error_category"] = friendly_llm_error(exc_str)["category"]

    except Exception as e:
        logger.warning({"event": "llm_error_parse_failed", "error": str(e), "raw_error": exc_str})
        result["user_message"] = f"The model call failed: {str(e)[:300]}. Please try again or switch models."

    return result


def friendly_llm_error(raw_error: str) -> dict:
    """
    Given a raw error string from an LLM provider, return a dict with:
      - category: short machine-readable code (e.g. 'billing', 'rate_limit', 'auth', 'model_not_found', 'unknown')
      - message: human-readable message safe to show to user
      - raw: original raw error (for debugging / logs)
    """
    lower = (raw_error or "").lower()

    # Billing / credit issues
    if "credit balance" in lower or "insufficient" in lower or "quota" in lower or "billing" in lower:
        return {
            "category": "billing",
            "message": "The AI provider rejected this request because your account has no credits. Please top up your API credits and try again.",
            "raw": raw_error,
        }

    # Rate limits
    if "rate limit" in lower or "too many requests" in lower or "429" in lower:
        return {
            "category": "rate_limit",
            "message": "The AI provider is rate-limiting requests. Please wait a moment and try again.",
            "raw": raw_error,
        }

    # Auth / invalid API key
    if "authentication" in lower or "invalid api key" in lower or "unauthorized" in lower or "401" in lower:
        return {
            "category": "auth",
            "message": "The AI provider rejected your API key. Please check your API key configuration in Settings.",
            "raw": raw_error,
        }

    # Model not found / invalid
    if "model" in lower and ("not found" in lower or "does not exist" in lower or "invalid" in lower):
        return {
            "category": "model_not_found",
            "message": "The AI model configured for this agent is not available. Please edit the agent and select a different model.",
            "raw": raw_error,
        }

    # Context length
    if "context" in lower and ("length" in lower or "too long" in lower or "exceeds" in lower):
        return {
            "category": "context_length",
            "message": "The conversation is too long for this model. Start a new thread or clear history.",
            "raw": raw_error,
        }

    # Fallback
    return {
        "category": "unknown",
        "message": f"The agent couldn't complete this request. Error: {raw_error[:300]}",
        "raw": raw_error,
    }
