"""MCP server factory for external integrations."""
import logging

# NOTE: Maton stdio integration has been REMOVED and replaced with gateway HTTP API.
# The @maton/mcp v0.0.10 package required to agent wrapper workflow which was causing
# 403 Forbidden errors because it skips the required connection workflow (check_connection -> start_connection).
# Maton's gateway API doesn't have this requirement - tools can be called directly.
# Direct HTTP calls are now made via app/integrations/maton_gateway.py instead.
# The create_maton_mcp_server() function below is NO LONGER USED - do not call it.
# See app/services/tool_loader.py for the new gateway-based implementation.
import asyncio
from typing import Any
from pydantic_ai.mcp import MCPServerStreamableHTTP, MCPServerStdio
from composio import Composio

from app.integrations.intent_resolver import MATON_VALID_APPS

logger = logging.getLogger("ocin")


class MCPServerStdioDebugWrapper:
    """Debug wrapper around MCPServerStdio to log all stdin/stdout communication."""

    def __init__(self, server: MCPServerStdio):
        self._server = server
        self._original_write_stdin = None

    async def __aenter__(self):
        """Enter context manager and wrap stdin writer."""
        await self._server.__aenter__()
        # Wrap the _write_stdin method to log outgoing messages
        if hasattr(self._server, '_write_stdin'):
            self._original_write_stdin = self._server._write_stdin
            async def _debug_write_stdin(data: bytes):
                import json
                try:
                    # Try to decode and log JSON
                    decoded = data.decode('utf-8')
                    try:
                        json_obj = json.loads(decoded)
                        logger.info({
                            "event": "mcp_stdin",
                            "message": json_obj,
                        })
                    except json.JSONDecodeError:
                        # Not valid JSON, log as string
                        logger.info({
                            "event": "mcp_stdin",
                            "message": decoded[:500],  # Log first 500 chars
                        })
                except Exception as e:
                    logger.warning({
                        "event": "mcp_stdin_log_failed",
                        "error": str(e),
                    })
                # Call original
                return await self._original_write_stdin(data)
            self._server._write_stdin = _debug_write_stdin
        return self

    async def __aexit__(self, *args):
        """Exit context manager."""
        return await self._server.__aexit__(*args)

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to wrapped server."""
        return getattr(self._server, name)


def create_maton_mcp_server(
    api_key: str,
    app: str = "google-sheet",
    actions: str = "all",
    debug: bool = True,  # Hardcoded True for tracing
) -> MCPServerStdio:
    """
    Create a Maton MCP server instance for a specific app.

    Args:
        api_key: Maton API key
        app: The Maton app to connect to (default: google-sheet) - MUST be canonical name from MATON_VALID_APPS
        actions: Comma-separated list of action names using HYPHEN format
            (e.g., "create-spreadsheet,add-multiple-rows", "all" for all actions)

    Returns:
        MCPServerStdio instance that can be added to agent toolsets

    Raises:
        ValueError: If the provided app name is not in the valid list
    """
    # Validate app name - it should be canonical (resolved by LLM intent resolver)
    if app not in MATON_VALID_APPS:
        raise ValueError(
            f"Invalid Maton app '{app}'. Must be one of: {', '.join(sorted(MATON_VALID_APPS))}"
        )

    # Build args for API Action mode (NO --agent flag)
    # This mode allows direct tool calls without the agent wrapper
    args = ["-y", "@maton/mcp", app, f"--actions={actions}", f"--api-key={api_key}"]

    logger.info({
        "event": "create_maton_mcp_server",
        "app": app,
        "actions": actions,
        "mode": "api-action",  # Direct tool calling mode
    })

    server = MCPServerStdio(
        command="npx",
        args=args,
        tool_prefix=None,  # No prefix needed - tools already include app name
        timeout=60.0,
    )

    # Wrap with debug tracer if enabled
    if debug:
        logger.info({"event": "maton_debug_wrapper_enabled"})
        server = MCPServerStdioDebugWrapper(server)

    return server


def create_apify_mcp_server(
    api_token: str,
    tools: str = "actors,docs,apify/rag-web-browser"
) -> MCPServerStreamableHTTP:
    """
    Create an Apify MCP server instance (hosted).

    Args:
        api_token: Apify API token
        tools: Comma-separated list of tools to load (default: actors,docs,apify/rag-web-browser)

    Returns:
        MCPServerStreamableHTTP instance that can be added to agent toolsets
    """
    url = f"https://mcp.apify.com?tools={tools}"
    headers = {"Authorization": f"Bearer {api_token}"}

    logger.info({
        "event": "create_apify_mcp_server",
        "url": url,
        "tools": tools,
    })

    server = MCPServerStreamableHTTP(
        url,
        headers=headers,
        tool_prefix="apify",
    )

    return server


async def create_composio_mcp_server(
    api_key: str,
    user_id: str,
    toolkits: list[str] | None = None
) -> MCPServerStreamableHTTP:
    """
    Create a Composio MCP server instance via Tool Router.

    Args:
        api_key: Composio API key
        user_id: User ID for the session
        toolkits: List of toolkits to enable (e.g., ['gmail', 'slack'])

    Returns:
        MCPServerStreamableHTTP instance that can be added to agent toolsets
    """
    composio = Composio(api_key=api_key)
    session = composio.create(user_id=user_id, toolkits=toolkits or [])
    url = session.mcp.url
    if not url:
        raise ValueError("Composio session did not return an MCP URL")

    headers = {"x-api-key": api_key}

    logger.info({
        "event": "create_composio_mcp_server",
        "user_id": user_id,
        "toolkits": toolkits,
    })

    server = MCPServerStreamableHTTP(url, headers=headers)

    return server
