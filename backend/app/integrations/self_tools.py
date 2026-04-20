"""
Self-call tools for agents to invoke OCIN's own API endpoints.

These tools allow agents to manage schedules, access memory, trigger runs,
and manage threads on behalf of the owning user.
"""

import logging
from typing import Any, Optional, Callable
from functools import wraps
import httpx
from sqlalchemy import select

from app.models.tool import Tool
from app.core.security import decrypt_value
from app.integrations.intent_resolver import resolve_integration_intent, IntentResolution

logger = logging.getLogger("ocin")


class ApprovalRequestedError(Exception):
    """Exception raised when an agent requests approval for an action."""
    def __init__(self, kind: str, title: str, description: str, payload: dict | None = None):
        self.kind = kind
        self.title = title
        self.description = description
        self.payload = payload or {}
        super().__init__(f"Approval requested for: {title}")

# Global storage for the current user's JWT token
# Set by agent_runner.py before running an agent
_current_jwt_token: str | None = None
_current_user_id: str | None = None
_current_api_base: str = "http://api:8000"


def set_self_call_context(jwt_token: str, user_id: str, api_base: str = "http://api:8000"):
    """Set the authentication context for self-call tools."""
    global _current_jwt_token, _current_user_id, _current_api_base
    _current_jwt_token = jwt_token
    _current_user_id = user_id
    _current_api_base = api_base


def clear_self_call_context():
    """Clear the authentication context."""
    global _current_jwt_token, _current_user_id
    _current_jwt_token = None
    _current_user_id = None


def log_self_call(tool_name: str):
    """Decorator to log self-call actions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger.info({
                "event": "agent_self_call",
                "tool": tool_name,
                "user_id": _current_user_id,
            })
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def _make_request(
    method: str,
    endpoint: str,
    data: dict | None = None,
    params: dict | None = None,
) -> tuple[dict | None, str | None]:
    """
    Make an authenticated HTTP request to the OCIN API.

    Returns:
        Tuple of (response_data, error_message)
        error_message is None on success, formatted string on failure
    """
    global _current_jwt_token, _current_api_base

    if not _current_jwt_token:
        return None, "ERROR: No authentication token available"

    url = f"{_current_api_base}{endpoint}"
    headers = {
        "Authorization": f"Bearer {_current_jwt_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                json=data if data else None,
                params=params,
                headers=headers,
            )

            if response.status_code < 400:
                return response.json(), None
            else:
                error_msg = f"ERROR: API returned {response.status_code}"
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict) and "detail" in error_data:
                        error_msg = f"ERROR: {error_data['detail']}"
                    elif isinstance(error_data, dict) and "error" in error_data:
                        error_msg = f"ERROR: {error_data['error']}"
                    else:
                        error_msg = f"ERROR: {response.text[:200]}"
                except Exception:
                    error_msg = f"ERROR: {response.text[:200]}"
                return None, error_msg

    except httpx.TimeoutException:
        return None, "ERROR: Request timed out"
    except httpx.ConnectError:
        return None, "ERROR: Could not connect to API"
    except Exception as e:
        logger.error({"event": "self_call_request_error", "error": str(e)})
        return None, f"ERROR: {str(e)}"


# ============================================================================
# INTEGRATION SETUP TOOL
# ============================================================================

@log_self_call("resolve_integration")
async def resolve_integration(user_description: str) -> dict:
    """
    Resolve a vague integration description to a canonical provider and app name.
    Call this whenever a user mentions connecting, adding, or setting up an
    integration before calling create_tool. Always show confirmation_message
    to the user and wait for their confirmation before proceeding.
    """
    global _current_user_id, _current_api_base

    if not _current_user_id:
        return {"error": "ERROR: No user context available"}

    # Call to intent resolver - now uses PydanticAI with user's coordinator model
    try:
        resolution: IntentResolution = await resolve_integration_intent(
            db=db,
            user_id=_current_user_id,
            user_input=user_description,
        )

        return {
            "provider": resolution.provider,
            "app": resolution.app,
            "confidence": resolution.confidence,
            "display_name": resolution.display_name,
            "confirmation_message": resolution.confirmation_message,
            "clarification_message": resolution.clarification_message,
        }
    except Exception as e:
        logger.error({"event": "resolve_integration_tool_error", "error": str(e)})
        return {
            "error": f"ERROR: {str(e)}",
            "provider": None,
            "app": None,
            "confidence": "low",
            "display_name": user_description,
        }


# ============================================================================
# SCHEDULE MANAGEMENT TOOLS
# ============================================================================

@log_self_call("create_schedule")
async def create_schedule(
    label: str,
    agent_name: str,
    trigger_type: str = "cron",
    payload: dict | None = None,
) -> str:
    """
    Create a new schedule for an agent.

    Args:
        label: Plain language schedule description (e.g., "every day at 9am")
        agent_name: Name of the agent to schedule
        trigger_type: Type of trigger (default: "cron")
        payload: Optional payload data for the schedule

    Returns:
        Success message with schedule ID, or error message starting with "ERROR:"
    """
    # First, get the agent ID by name
    agents_result = await list_agents()
    if isinstance(agents_result, str):
        return agents_result  # error message
    agents = agents_result

    agent_id = None
    for agent in agents:
        if agent.get("name") == agent_name:
            agent_id = agent.get("id")
            break

    if not agent_id:
        return f"ERROR: Agent '{agent_name}' not found"

    data = {
        "agent_id": agent_id,
        "label": label,
        "trigger_type": trigger_type,
        "payload": payload or {},
    }

    result, error = await _make_request("POST", "/api/v1/schedules", data=data)
    if error:
        return error

    schedule_id = result.get("id", "unknown")
    return f"Created schedule '{label}' with ID: {schedule_id}"


@log_self_call("list_schedules")
async def list_schedules() -> list[dict] | str:
    """
    List all schedules for the current user.

    Returns:
        List of schedule dictionaries, or error message starting with "ERROR:"
    """
    result, error = await _make_request("GET", "/api/v1/schedules")
    if error:
        return error

    schedules = result.get("schedules", result.get("items", []))
    return schedules if schedules else []


@log_self_call("get_schedule")
async def get_schedule(schedule_id: str) -> dict | str:
    """
    Get details of a specific schedule.

    Args:
        schedule_id: The ID of the schedule

    Returns:
        Schedule dictionary, or error message starting with "ERROR:"
    """
    result, error = await _make_request("GET", f"/api/v1/schedules/{schedule_id}")
    if error:
        return error

    return result


@log_self_call("pause_schedule")
async def pause_schedule(schedule_id: str) -> str:
    """
    Pause a schedule.

    Args:
        schedule_id: The ID of the schedule to pause

    Returns:
        Success message, or error message starting with "ERROR:"
    """
    result, error = await _make_request("POST", f"/api/v1/schedules/{schedule_id}/pause")
    if error:
        return error

    return f"Paused schedule {schedule_id}"


@log_self_call("resume_schedule")
async def resume_schedule(schedule_id: str) -> str:
    """
    Resume a paused schedule.

    Args:
        schedule_id: The ID of the schedule to resume

    Returns:
        Success message, or error message starting with "ERROR:"
    """
    result, error = await _make_request("POST", f"/api/v1/schedules/{schedule_id}/resume")
    if error:
        return error

    return f"Resumed schedule {schedule_id}"


@log_self_call("delete_schedule")
async def delete_schedule(schedule_id: str) -> str:
    """
    Delete a schedule.

    Args:
        schedule_id: The ID of the schedule to delete

    Returns:
        Success message, or error message starting with "ERROR:"
    """
    result, error = await _make_request("DELETE", f"/api/v1/schedules/{schedule_id}")
    if error:
        return error

    return f"Deleted schedule {schedule_id}"


# ============================================================================
# AGENT MANAGEMENT TOOLS (read-only - no agent creation)
# ============================================================================

@log_self_call("list_agents")
async def list_agents() -> list[dict] | str:
    """
    List all agents for the current user.

    Returns:
        List of agent dictionaries with id, name, model_provider, etc., or error message
    """
    result, error = await _make_request("GET", "/api/v1/agents")
    if error:
        return error

    agents = result if isinstance(result, list) else []
    return agents


@log_self_call("get_agent_by_name")
async def get_agent_by_name(name: str) -> dict | str:
    """
    Get an agent's details by name.

    Args:
        name: The name of the agent

    Returns:
        Agent dictionary, or error message starting with "ERROR:"
    """
    agents_result = await list_agents()
    if isinstance(agents_result, str):
        return agents_result  # error message
    agents = agents_result

    for agent in agents:
        if agent.get("name") == name:
            return agent

    return f"ERROR: Agent '{name}' not found"


@log_self_call("get_agent")
async def get_agent(agent_id: str) -> dict | str:
    """
    Get an agent's details by ID.

    Args:
        agent_id: The ID of the agent

    Returns:
        Agent dictionary, or error message starting with "ERROR:"
    """
    result, error = await _make_request("GET", f"/api/v1/agents/{agent_id}")
    if error:
        return error

    return result


# ============================================================================
# MEMORY MANAGEMENT TOOLS
# ============================================================================

@log_self_call("get_memory")
async def get_memory(agent_name: str) -> dict | str:
    """
    Get all memory facts for an agent.

    Args:
        agent_name: The name of the agent

    Returns:
        Dictionary of memory facts, or error message starting with "ERROR:"
    """
    # Get agent ID first
    agents_result = await list_agents()
    if isinstance(agents_result, str):
        return agents_result  # error message
    agents = agents_result

    agent_id = None
    for agent in agents:
        if agent.get("name") == agent_name:
            agent_id = agent.get("id")
            break

    if not agent_id:
        return f"ERROR: Agent '{agent_name}' not found"

    result, error = await _make_request("GET", f"/api/v1/memory/{agent_id}")
    if error:
        return error

    return result if result else {}


@log_self_call("set_memory")
async def set_memory(agent_name: str, key: str, value: str) -> str:
    """
    Set a memory fact for an agent.

    Args:
        agent_name: The name of the agent
        key: The memory key
        value: The memory value

    Returns:
        Success message, or error message starting with "ERROR:"
    """
    # Get agent ID first
    agents_result = await list_agents()
    if isinstance(agents_result, str):
        return agents_result  # error message
    agents = agents_result

    agent_id = None
    for agent in agents:
        if agent.get("name") == agent_name:
            agent_id = agent.get("id")
            break

    if not agent_id:
        return f"ERROR: Agent '{agent_name}' not found"

    data = {"value": value}
    result, error = await _make_request("PUT", f"/api/v1/memory/{agent_id}/{key}", data=data)
    if error:
        return error

    return f"Set memory '{key}' for agent '{agent_name}'"


@log_self_call("delete_memory")
async def delete_memory(agent_name: str, key: str) -> str:
    """
    Delete a memory fact for an agent.

    Args:
        agent_name: The name of the agent
        key: The memory key to delete

    Returns:
        Success message, or error message starting with "ERROR:"
    """
    # Get agent ID first
    agents_result = await list_agents()
    if isinstance(agents_result, str):
        return agents_result  # error message
    agents = agents_result

    agent_id = None
    for agent in agents:
        if agent.get("name") == agent_name:
            agent_id = agent.get("id")
            break

    if not agent_id:
        return f"ERROR: Agent '{agent_name}' not found"

    result, error = await _make_request("DELETE", f"/api/v1/memory/{agent_id}/{key}")
    if error:
        return error

    return f"Deleted memory '{key}' for agent '{agent_name}'"


# ============================================================================
# RUN MANAGEMENT TOOLS
# ============================================================================

@log_self_call("trigger_run")
async def trigger_run(agent_name: str, input: str) -> str:
    """
    Trigger a new agent run.

    Args:
        agent_name: The name of the agent to run
        input: The input text for the agent

    Returns:
        Success message with run_id, or error message starting with "ERROR:"
    """
    # Get agent ID first
    agents_result = await list_agents()
    if isinstance(agents_result, str):
        return agents_result  # error message
    agents = agents_result

    agent_id = None
    for agent in agents:
        if agent.get("name") == agent_name:
            agent_id = agent.get("id")
            break

    if not agent_id:
        return f"ERROR: Agent '{agent_name}' not found"

    data = {"agent_id": agent_id, "input": input}
    result, error = await _make_request("POST", "/api/v1/runs/trigger", data=data)
    if error:
        return error

    run_id = result.get("run_id", "unknown")
    return f"Triggered run with ID: {run_id}"


@log_self_call("get_run_status")
async def get_run_status(run_id: str) -> dict | str:
    """
    Get the status of a run.

    Args:
        run_id: The ID of the run

    Returns:
        Run status dictionary, or error message starting with "ERROR:"
    """
    result, error = await _make_request("GET", f"/api/v1/runs/{run_id}")
    if error:
        return error

    return result


@log_self_call("list_runs")
async def list_runs(limit: int = 10, agent_name: str | None = None) -> list[dict] | str:
    """
    List recent runs.

    Args:
        limit: Maximum number of runs to return (default: 10)
        agent_name: Optional filter by agent name

    Returns:
        List of run dictionaries, or error message starting with "ERROR:"
    """
    params = {"limit": limit}
    if agent_name:
        # Get agent ID for filtering
        agents_result = await list_agents()
        if isinstance(agents_result, str):
            return agents_result  # error message
        agents = agents_result
        for agent in agents:
            if agent.get("name") == agent_name:
                params["agent_id"] = agent.get("id")
                break

    result, error = await _make_request("GET", "/api/v1/runs", params=params)
    if error:
        return error

    runs = result if isinstance(result, list) else []
    return runs[:limit]


# ============================================================================
# THREAD MANAGEMENT TOOLS
# ============================================================================

@log_self_call("list_threads")
async def list_threads(limit: int = 20) -> list[dict] | str:
    """
    List all chat threads.

    Args:
        limit: Maximum number of threads to return (default: 20)

    Returns:
        List of thread dictionaries, or error message starting with "ERROR:"
    """
    params = {"limit": limit}
    result, error = await _make_request("GET", "/api/v1/chat/threads", params=params)
    if error:
        return error

    threads = result.get("threads", [])
    return threads[:limit]


@log_self_call("get_thread_messages")
async def get_thread_messages(thread_id: str, limit: int = 50) -> list[dict] | str:
    """
    Get messages from a thread.

    Args:
        thread_id: The ID of the thread
        limit: Maximum number of messages to return (default: 50)

    Returns:
        List of message dictionaries, or error message starting with "ERROR:"
    """
    params = {"limit": limit}
    result, error = await _make_request("GET", f"/api/v1/chat/threads/{thread_id}/messages", params=params)
    if error:
        return error

    messages = result.get("messages", [])
    return messages[:limit]


# ============================================================================
# APPROVAL MANAGEMENT TOOLS
# ============================================================================

@log_self_call("request_approval")
async def request_approval(
    kind: str = "execute_action",
    title: str = "Agent action requires approval",
    description: str = "No description provided",
    payload: dict | None = None,
) -> str:
    """
    Request user approval for an action.

    Use this tool when you need to perform an action that requires user consent,
    such as:
    - Sending messages to users
    - Making purchases or financial transactions
    - Deleting or modifying important data
    - Any action with potential negative consequences

    Args:
        kind: Type of approval needed (e.g., "execute_action", "send_message", "delete_data")
        title: Short title for the approval request
        description: Detailed description of what will be done
        payload: Optional additional context data

    Returns:
        This tool raises ApprovalRequestedError to pause execution and request user approval

    Raises:
        ApprovalRequestedError: Always raised to pause agent execution and wait for approval
    """
    logger.info({
        "event": "approval_requested_via_tool",
        "kind": kind,
        "title": title,
        "description": description[:200],  # Truncate for logging
    })

    # Raise exception to stop agent execution and trigger approval workflow
    raise ApprovalRequestedError(kind, title, description, payload)


# ============================================================================
# TOOL LIST FOR AGENT
# ============================================================================

def get_self_tools() -> list[Callable]:
    """
    Return all self-call tools for inclusion in an agent's tool list.

    Returns:
        List of async functions that can be used as PydanticAI tools
    """
    return [
        create_schedule,
        list_schedules,
        get_schedule,
        pause_schedule,
        resume_schedule,
        delete_schedule,
        list_agents,
        get_agent_by_name,
        get_agent,
        get_memory,
        set_memory,
        delete_memory,
        trigger_run,
        get_run_status,
        list_runs,
        list_threads,
        get_thread_messages,
        resolve_integration,
        request_approval,
    ]
