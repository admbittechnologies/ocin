import logging
from pydantic import BaseModel

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.dependencies import CurrentUser, check_plan_limits
from app.schemas.agent import AgentCreate, AgentUpdate, AgentOut
from app.services.agent_service import (
    create_agent,
    get_agent,
    list_agents,
    update_agent,
    delete_agent,
    get_agent_with_tools,
)
from app.core.exceptions import NotFoundException, ForbiddenException

logger = logging.getLogger("ocin")

router = APIRouter()


@router.get("", response_model=list[AgentOut])
async def list_user_agents(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    active_only: bool = False,
):
    """List all agents for the current user."""
    agents = await list_agents(db, str(current_user.id), skip, limit, active_only)
    # Resolve tool names for each agent
    result = []
    for agent in agents:
        agent_dict = await get_agent_with_tools(db, str(agent.id), str(current_user.id))
        if agent_dict:
            result.append(AgentOut(**agent_dict))
    return result


@router.get("/{agent_id}", response_model=AgentOut)
async def get_single_agent(
    agent_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single agent by ID."""
    agent_dict = await get_agent_with_tools(db, agent_id, str(current_user.id))
    if not agent_dict:
        raise NotFoundException("Agent not found")
    return AgentOut(**agent_dict)


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_user_agent(
    agent_data: AgentCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent."""
    # Enforce plan limits
    await check_plan_limits(current_user, db, "agents", 1)

    agent = await create_agent(db, str(current_user.id), agent_data)
    agent_dict = await get_agent_with_tools(db, str(agent.id), str(current_user.id))
    return AgentOut(**agent_dict)


@router.put("/{agent_id}", response_model=AgentOut)
async def update_user_agent(
    agent_id: str,
    agent_data: AgentUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent."""
    agent = await update_agent(db, agent_id, str(current_user.id), agent_data)
    agent_dict = await get_agent_with_tools(db, str(agent.id), str(current_user.id))
    return AgentOut(**agent_dict)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_agent(
    agent_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent."""
    await delete_agent(db, agent_id, str(current_user.id))


class AgentToggle(BaseModel):
    active: bool


@router.put("/{agent_id}/toggle", response_model=AgentOut)
async def toggle_user_agent(
    agent_id: str,
    toggle_data: AgentToggle,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Toggle an agent's active status."""
    agent = await update_agent(db, agent_id, str(current_user.id), AgentUpdate(is_active=toggle_data.active))
    agent_dict = await get_agent_with_tools(db, str(agent.id), str(current_user.id))
    return AgentOut(**agent_dict)
