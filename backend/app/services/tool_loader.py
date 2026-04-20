import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import Agent as AgentModel
from app.models.tool import Tool
from app.core.security import decrypt_value
from app.integrations.builtin import (
    http_fetch,
    get_datetime,
    web_fetch,
    web_search,
)
from app.integrations.maton_gateway import build_maton_gateway_tools

logger = logging.getLogger("ocin")

# Re-export memory functions for tool access
from app.services.memory_extraction import get_agent_memory, format_memory_context


async def build_tools_for_agent(
    agent: AgentModel,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Build PydanticAI tool list for an agent.

    Always includes builtin tools. Loads MCP servers for external integrations.
    Single tool load failure: log and skip, do not abort.

    Args:
        agent: The Agent model
        db: Database session

    Returns:
        Dict with "tools" list (regular functions), "mcp_servers" list (MCP server instances),
        and "clients" list (legacy, now empty).
    """
    regular_tools = []
    mcp_servers = []

    # Always include builtin tools
    regular_tools.append(http_fetch)
    regular_tools.append(get_datetime)
    regular_tools.append(web_fetch)

    # Check if user has Tavily API key for web_search
    result = await db.execute(
        select(Tool).where(
            Tool.user_id == agent.user_id,
            Tool.source == "api_key",
            Tool.source_key == "tavily",
            Tool.is_active == True,
        )
    )
    tavily_tool = result.scalar_one_or_none()

    if tavily_tool and tavily_tool.config:
        try:
            tavily_api_key = decrypt_value(tavily_tool.config.get("api_key", ""))
            if tavily_api_key:
                # Clean wrapper with only (query, max_results) visible to PydanticAI.
                # api_key is captured via closure — never exposed as a parameter.
                async def tavily_search(query: str, max_results: int = 5) -> dict:
                    """Search the web for current information. Use when you need recent news, facts, or up-to-date data."""
                    return await web_search(query, max_results, tavily_api_key)

                tavily_search.__name__ = "web_search"
                regular_tools.append(tavily_search)
                logger.info({
                    "event": "web_search_enabled",
                    "user_id": str(agent.user_id),
                    "agent_id": str(agent.id),
                })
            else:
                logger.info({
                    "event": "web_search_disabled_no_key",
                    "user_id": str(agent.user_id),
                    "agent_id": str(agent.id),
                })
        except Exception as e:
            logger.warning({
                "event": "web_search_key_decrypt_failed",
                "user_id": str(agent.user_id),
                "error": str(e),
            })
    else:
        logger.info({
            "event": "web_search_disabled_no_key",
            "user_id": str(agent.user_id),
            "agent_id": str(agent.id),
        })

    # Add user memory tools with closures capturing user_id and db
    user_id = str(agent.user_id)

    async def wrapped_memory_get(key: str):
        """Get a stored memory value by key."""
        result = await memory_get(key, user_id=user_id, db=db)
        return result.model_dump()

    wrapped_memory_get.__name__ = "memory_get"
    regular_tools.append(wrapped_memory_get)

    async def wrapped_memory_set(key: str, value: str):
        """Set or update a memory value."""
        result = await memory_set(key, value, user_id=user_id, db=db)
        return result.model_dump()

    wrapped_memory_set.__name__ = "memory_set"
    regular_tools.append(wrapped_memory_set)

    async def wrapped_memory_list(prefix: str = ""):
        """List all memories for the user, optionally filtered by prefix."""
        result = await memory_list(prefix, user_id=user_id, db=db)
        return result.model_dump()

    wrapped_memory_list.__name__ = "memory_list"
    regular_tools.append(wrapped_memory_list)

    async def wrapped_memory_delete(key: str):
        """Delete a memory value by key."""
        result = await memory_delete(key, user_id=user_id, db=db)
        return result.model_dump()

    wrapped_memory_delete.__name__ = "memory_delete"
    regular_tools.append(wrapped_memory_delete)

    logger.info({
        "event": "user_memory_tools_added",
        "user_id": user_id,
        "agent_id": str(agent.id),
        "tools_count": 4,
    })

    # Load ALL active tools for this user (not just ones assigned to this agent)
    result = await db.execute(
        select(Tool).where(
            Tool.user_id == agent.user_id,
            Tool.is_active == True,
            Tool.source.in_(["composio", "apify", "maton"]),
        )
    )
    tools_db = result.scalars().all()

    for tool_db in tools_db:
        try:
            if tool_db.source == "composio":
                # Composio: Use Tool Router MCP
                # TODO: Implement Composio integration
                logger.info({
                    "event": "build_tools",
                    "tool_id": str(tool_db.id),
                    "source": "composio",
                    "action": "skipped_not_implemented",
                })
                continue

            elif tool_db.source == "maton":
                # Maton: Use gateway HTTP API (direct, no MCP stdio)
                api_key = tool_db.config.get("api_key") or tool_db.config.get("api_token", "")
                maton_app = tool_db.config.get("app", "google-sheet")

                if not api_key:
                    logger.warning({
                        "event": "build_tools",
                        "tool_id": str(tool_db.id),
                        "error": "Missing Maton API key"
                    })
                    continue

                try:
                    decrypted_key = decrypt_value(api_key)
                    logger.info({
                        "event": "maton_decrypted",
                        "tool_id": str(tool_db.id),
                    "key_length": len(decrypted_key),
                        "starts_with": decrypted_key[:6] if decrypted_key else None,
                    })
                except Exception as e:
                    logger.error({"event": "maton_decrypt_failed", "error": str(e)})
                    decrypted_key = api_key

                # Build gateway tools for this app
                maton_tools = build_maton_gateway_tools(decrypted_key, maton_app)
                regular_tools.extend(maton_tools)
                logger.info({
                    "event": "maton_gateway_tools_added",
                    "tool_id": str(tool_db.id),
                    "app": maton_app,
                    "count": len(maton_tools),
                })


            elif tool_db.source == "builtin":
                # Builtin tools are already included
                pass

        except Exception as e:
            logger.error({
                "event": "build_tools",
                "tool_id": str(tool_db.id),
                "source": tool_db.source,
                "error": str(e),
            })
            # Continue loading other tools

    return {
        "tools": regular_tools,
        "mcp_servers": mcp_servers,
        "clients": [],  # No longer needed with MCP, kept for compatibility
    }