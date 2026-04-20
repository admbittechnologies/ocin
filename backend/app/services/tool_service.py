import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.tool import Tool
from app.core.security import encrypt_value
from app.core.exceptions import NotFoundException, ForbiddenException
from app.schemas.tool import ToolCreate

logger = logging.getLogger("ocin")


async def create_tool(
    db: AsyncSession,
    user_id: str,
    tool_data: ToolCreate,
) -> Tool:
    """Create a new tool, encrypting any sensitive config."""
    # Encrypt API keys in config before storing
    encrypted_config = {}
    for key, value in tool_data.config.items():
        if isinstance(value, str):
            # Heuristic: encrypt keys that look like secrets
            if any(secret_word in key.lower() for secret_word in ["key", "token", "secret", "password", "api"]):
                encrypted_config[key] = encrypt_value(value)
            else:
                encrypted_config[key] = value
        else:
            encrypted_config[key] = value

    # Builtin tools shouldn't have user-specific config
    if tool_data.source == "builtin":
        raise ForbiddenException("Builtin tools are automatically available")

    tool = Tool(
        user_id=user_id,
        name=tool_data.name,
        source=tool_data.source,
        source_key=tool_data.source_key,
        config=encrypted_config,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    logger.info({"event": "create_tool", "tool_id": str(tool.id), "user_id": user_id, "source": tool.source})
    return tool


async def list_tools(
    db: AsyncSession,
    user_id: str,
    skip: int = 0,
    limit: int = 100,
    source: Optional[str] = None,
    active_only: bool = False,
) -> list[Tool]:
    """List tools for a user."""
    query = select(Tool).where(Tool.user_id == user_id)
    if source:
        query = query.where(Tool.source == source)
    if active_only:
        query = query.where(Tool.is_active == True)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_tool(db: AsyncSession, tool_id: str, user_id: str) -> Optional[Tool]:
    """Get a tool by ID (user-scoped)."""
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id, Tool.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_tool(db: AsyncSession, tool_id: str, user_id: str) -> bool:
    """Delete a tool."""
    tool = await get_tool(db, tool_id, user_id)
    if not tool:
        raise NotFoundException("Tool not found")

    await db.delete(tool)
    await db.commit()

    logger.info({"event": "delete_tool", "tool_id": str(tool.id), "user_id": user_id})
    return True


async def get_tool_config(db: AsyncSession, tool_id: str) -> Optional[dict]:
    """Get decrypted tool config (internal use only)."""
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        return None

    return tool.config
