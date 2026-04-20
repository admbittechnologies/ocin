import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.agent import Agent
from app.models.tool import Tool
from app.core.exceptions import ForbiddenException, NotFoundException
from app.schemas.agent import AgentCreate, AgentUpdate

logger = logging.getLogger("ocin")

# Vision-capable models that can process image attachments
VISION_CAPABLE_MODELS = {
    # Claude models
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-sonnet-4-4",
    "claude-sonnet-4-3",
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-opus-4-4",
    "claude-opus-4-3",
    # OpenAI models
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    # Google models
    "gemini-2.0-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
}


def is_vision_capable(model_provider: str, model_id: str) -> bool:
    """
    Check if a model supports vision capabilities.

    Args:
        model_provider: The model provider (e.g., "anthropic", "openai", "google")
        model_id: The model ID (e.g., "claude-sonnet-4-6", "gpt-4o")

    Returns:
        True if the model can process images, False otherwise
    """
    # Normalize model_id for comparison
    normalized_id = model_id.lower().strip()

    # Check against known vision-capable models
    return normalized_id in VISION_CAPABLE_MODELS


async def create_agent(
    db: AsyncSession,
    user_id: str,
    agent_data: AgentCreate,
) -> Agent:
    """Create a new agent."""
    # Auto-assign role='coordinator' to first agent per user if no coordinator exists yet
    existing_coordinator = await db.execute(
        select(Agent).where(Agent.user_id == user_id, Agent.role == "coordinator", Agent.is_active == True)
    )
    if existing_coordinator.scalar_one_or_none() is None:
        role = "coordinator"
    else:
        role = agent_data.role

    # Verify tool IDs belong to user
    if agent_data.tool_ids:
        tool_uuids = [UUID(tid) for tid in agent_data.tool_ids]
        result = await db.execute(
            select(Tool.id).where(
                Tool.id.in_(tool_uuids),
                Tool.user_id == user_id,
                Tool.is_active == True,
            )
        )
        found_ids = {str(row[0]) for row in result.all()}
        missing = set(agent_data.tool_ids) - found_ids
        if missing:
            raise NotFoundException(f"Tools not found or not accessible: {', '.join(missing)}")

    agent = Agent(
        user_id=user_id,
        name=agent_data.name,
        description=agent_data.description,
        avatar=agent_data.avatar,
        role=role,
        model_provider=agent_data.model_provider,
        model_id=agent_data.model_id,
        temperature=agent_data.temperature,
        system_prompt=agent_data.system_prompt,
        tool_ids=[UUID(tid) for tid in agent_data.tool_ids] if agent_data.tool_ids else [],
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info({"event": "create_agent", "agent_id": str(agent.id), "user_id": user_id})
    return agent


async def get_agent(db: AsyncSession, agent_id: str, user_id: str) -> Optional[Agent]:
    """Get an agent by ID (user-scoped)."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_agents(
    db: AsyncSession,
    user_id: str,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
) -> list[Agent]:
    """List all agents for a user."""
    query = select(Agent).where(Agent.user_id == user_id)
    if active_only:
        query = query.where(Agent.is_active == True)
    query = query.order_by(Agent.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_agent(
    db: AsyncSession,
    agent_id: str,
    user_id: str,
    agent_data: AgentUpdate,
) -> Agent:
    """Update an agent."""
    agent = await get_agent(db, agent_id, user_id)
    if not agent:
        raise NotFoundException("Agent not found")

    # Verify tool IDs belong to user if updating
    if agent_data.tool_ids is not None:
        if agent_data.tool_ids:
            tool_uuids = [UUID(tid) for tid in agent_data.tool_ids]
            result = await db.execute(
                select(Tool.id).where(
                    Tool.id.in_(tool_uuids),
                    Tool.user_id == user_id,
                    Tool.is_active == True,
                )
            )
            found_ids = {str(row[0]) for row in result.all()}
            missing = set(agent_data.tool_ids) - found_ids
            if missing:
                raise NotFoundException(f"Tools not found or not accessible: {', '.join(missing)}")
        agent.tool_ids = [UUID(tid) for tid in agent_data.tool_ids]

    update_data = agent_data.model_dump(exclude_unset=True, exclude={"tool_ids"})
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)

    logger.info({"event": "update_agent", "agent_id": str(agent.id), "user_id": user_id})
    return agent


async def delete_agent(db: AsyncSession, agent_id: str, user_id: str) -> bool:
    """Delete an agent."""
    agent = await get_agent(db, agent_id, user_id)
    if not agent:
        raise NotFoundException("Agent not found")

    await db.delete(agent)
    await db.commit()

    logger.info({"event": "delete_agent", "agent_id": str(agent.id), "user_id": user_id})
    return True


async def get_agent_with_tools(db: AsyncSession, agent_id: str, user_id: str) -> Optional[dict]:
    """Get agent with resolved tool names."""
    agent = await get_agent(db, agent_id, user_id)
    if not agent:
        return None

    # Resolve tool names
    tool_refs = []
    if agent.tool_ids:
        result = await db.execute(
            select(Tool.id, Tool.name).where(Tool.id.in_(agent.tool_ids))
        )
        tool_map = {str(row[0]): row[1] for row in result.all()}
        tool_refs = [
            {"id": str(tool_id), "name": tool_map.get(str(tool_id), "Unknown")}
            for tool_id in agent.tool_ids
        ]

    agent_dict = {
        "id": str(agent.id),
        "user_id": str(agent.user_id),
        "name": agent.name,
        "description": agent.description,
        "avatar": agent.avatar,
        "role": agent.role,
        "model_provider": agent.model_provider,
        "model_id": agent.model_id,
        "temperature": agent.temperature,
        "system_prompt": agent.system_prompt,
        "tool_ids": [str(t) for t in agent.tool_ids],
        "tools": tool_refs,
        "is_active": agent.is_active,
        "created_at": str(agent.created_at),
    }
    return agent_dict
