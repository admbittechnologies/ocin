import logging

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.core.dependencies import CurrentUser
from app.models.memory import AgentMemory
from app.models.agent import Agent
from app.core.exceptions import NotFoundException, ForbiddenException

logger = logging.getLogger("ocin")

router = APIRouter()


class MemoryValue(BaseModel):
    key: str
    value: str


class MemoryResponse(BaseModel):
    key: str
    value: str
    source: str
    updated_at: str


async def _verify_agent_access(db: AsyncSession, agent_id: str, user_id: str) -> Agent:
    """Verify agent exists and belongs to user."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise NotFoundException("Agent not found")
    return agent


@router.get("/{agent_id}", response_model=list[MemoryResponse])
async def get_agent_memory(
    agent_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get all memory values for an agent."""
    await _verify_agent_access(db, agent_id, str(current_user.id))

    result = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_id == agent_id)
    )
    memories = result.scalars().all()

    return [
        MemoryResponse(
            key=m.key,
            value=m.value,
            source=m.source,
            updated_at=str(m.updated_at),
        )
        for m in memories
    ]


@router.put("/{agent_id}/{key}", response_model=MemoryResponse)
async def set_memory_value(
    agent_id: str,
    key: str,
    value: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Set a memory value for an agent."""
    await _verify_agent_access(db, agent_id, str(current_user.id))

    # Check if key already exists
    result = await db.execute(
        select(AgentMemory).where(
            AgentMemory.agent_id == agent_id,
            AgentMemory.key == key,
        )
    )
    memory = result.scalar_one_or_none()

    if memory:
        memory.value = value
        memory.source = "user"  # Human-edited via API
    else:
        memory = AgentMemory(agent_id=agent_id, key=key, value=value, source="user")
        db.add(memory)

    await db.commit()
    await db.refresh(memory)

    return MemoryResponse(
        key=memory.key,
        value=memory.value,
        source=memory.source,
        updated_at=str(memory.updated_at),
    )


@router.delete("/{agent_id}/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_value(
    agent_id: str,
    key: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Delete a memory value for an agent."""
    await _verify_agent_access(db, agent_id, str(current_user.id))

    result = await db.execute(
        select(AgentMemory).where(
            AgentMemory.agent_id == agent_id,
            AgentMemory.key == key,
        )
    )
    memory = result.scalar_one_or_none()

    if not memory:
        raise NotFoundException("Memory key not found")

    await db.delete(memory)
    await db.commit()
