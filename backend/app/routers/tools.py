import logging
import uuid

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.dependencies import CurrentUser, check_plan_limits
from app.schemas.tool import ToolCreate, ToolOut
from app.services.tool_service import create_tool, list_tools, get_tool, delete_tool
from app.core.exceptions import NotFoundException, ForbiddenException, BadRequestException
from app.core.security import encrypt_value
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("ocin")

router = APIRouter()


def validate_tool_id(tool_id: str) -> uuid.UUID:
    """Validate that tool_id is a valid UUID. Returns UUID or raises BadRequestException."""
    try:
        return uuid.UUID(tool_id)
    except (ValueError, AttributeError):
        raise BadRequestException(
            f"Invalid tool_id '{tool_id}'. Expected a UUID format, "
            f"got a source key or other identifier. Use the tool's UUID ID, not its source value."
        )


class ToolConnectRequest(BaseModel):
    """Request to connect a tool with credentials."""
    api_token: Optional[str] = None
    connection_id: Optional[str] = None
    actor_id: Optional[str] = None
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None


@router.get("", response_model=list[ToolOut])
async def list_user_tools(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    source: str | None = None,
    active_only: bool = False,
):
    """List all tools for the current user."""
    tools = await list_tools(db, str(current_user.id), skip, limit, source, active_only)

    # Never expose raw config - use 'configured' flag
    result = []
    for tool in tools:
        is_configured = bool(tool.config) if tool.source != "builtin" else True
        result.append(ToolOut(
            id=str(tool.id),
            user_id=str(tool.user_id),
            name=tool.name,
            source=tool.source,
            source_key=tool.source_key,
            is_active=tool.is_active,
            configured=is_configured,
        ))
    return result


@router.get("/{tool_id}", response_model=ToolOut)
async def get_single_tool(
    tool_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single tool by ID."""
    # Validate tool_id is a valid UUID
    validate_tool_id(tool_id)
    tool = await get_tool(db, tool_id, str(current_user.id))
    if not tool:
        raise NotFoundException("Tool not found")

    is_configured = bool(tool.config) if tool.source != "builtin" else True
    return ToolOut(
        id=str(tool.id),
        user_id=str(tool.user_id),
        name=tool.name,
        source=tool.source,
        source_key=tool.source_key,
        is_active=tool.is_active,
        configured=is_configured,
    )


@router.post("", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
async def create_user_tool(
    tool_data: ToolCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Create a new tool."""
    if tool_data.source == "builtin":
        raise ForbiddenException("Builtin tools are automatically available")

    # Enforce plan limits
    await check_plan_limits(current_user, db, "tools", 1)

    tool = await create_tool(db, str(current_user.id), tool_data)

    is_configured = bool(tool.config)
    return ToolOut(
        id=str(tool.id),
        user_id=str(tool.user_id),
        name=tool.name,
        source=tool.source,
        source_key=tool.source_key,
        is_active=tool.is_active,
        configured=is_configured,
    )


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_tool(
    tool_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Delete a tool."""
    # Validate tool_id is a valid UUID
    validate_tool_id(tool_id)
    await delete_tool(db, tool_id, str(current_user.id))


@router.post("/{tool_id}/connect", response_model=ToolOut)
async def connect_tool(
    tool_id: str,
    connect_data: ToolConnectRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Connect a tool with credentials."""
    from app.models.tool import Tool
    from sqlalchemy import select

    # Validate tool_id is a valid UUID
    tool_uuid = validate_tool_id(tool_id)

    # Get the tool
    result = await db.execute(
        select(Tool).where(Tool.id == tool_uuid, Tool.user_id == str(current_user.id))
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("Tool not found")

    # Build config with encrypted credentials
    # Preserve existing config to avoid losing fields like "app" for Maton
    config = dict(tool.config) if tool.config else {}

    if connect_data.api_token:
        config["api_token"] = encrypt_value(connect_data.api_token)
    if connect_data.connection_id:
        config["connection_id"] = connect_data.connection_id
    if connect_data.actor_id:
        config["actor_id"] = connect_data.actor_id
    if connect_data.webhook_url:
        config["webhook_url"] = connect_data.webhook_url
    if connect_data.webhook_secret:
        config["webhook_secret"] = encrypt_value(connect_data.webhook_secret)

    tool.config = config
    tool.is_active = True

    await db.commit()

    logger.info({"event": "connect_tool", "tool_id": tool_id, "user_id": str(current_user.id)})

    is_configured = bool(tool.config) if tool.source != "builtin" else True
    return ToolOut(
        id=str(tool.id),
        user_id=str(tool.user_id),
        name=tool.name,
        source=tool.source,
        source_key=tool.source_key,
        is_active=tool.is_active,
        configured=is_configured,
    )


@router.post("/{tool_id}/disconnect", response_model=ToolOut)
async def disconnect_tool(
    tool_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a tool by clearing credentials."""
    from app.models.tool import Tool
    from sqlalchemy import select

    # Validate tool_id is a valid UUID
    tool_uuid = validate_tool_id(tool_id)

    # Get the tool
    result = await db.execute(
        select(Tool).where(Tool.id == tool_uuid, Tool.user_id == str(current_user.id))
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("Tool not found")

    # Clear config and deactivate
    tool.config = {}
    tool.is_active = False

    await db.commit()

    logger.info({"event": "disconnect_tool", "tool_id": tool_id, "user_id": str(current_user.id)})

    is_configured = bool(tool.config) if tool.source != "builtin" else True
    return ToolOut(
        id=str(tool.id),
        user_id=str(tool.user_id),
        name=tool.name,
        source=tool.source,
        source_key=tool.source_key,
        is_active=tool.is_active,
        configured=is_configured,
    )
