import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.memory import AgentMemory
from app.models.agent import Agent as AgentModel
from app.core.system_model import run_system_task
from pydantic import BaseModel, Field

logger = logging.getLogger("ocin")

# Memory retention period
MEMORY_RETENTION_DAYS = 30
MEMORY_RETENTION_DAYS = 30


class _MemoryFact(BaseModel):
    """A single fact worth remembering."""
    key: str
    value: str


class _MemoryFacts(BaseModel):
    """Structured output from memory extraction LLM."""
    facts: list[_MemoryFact] = Field(
        default_factory=list,
        description="0 to 3 important facts worth remembering",
    )


async def extract_facts_from_conversation(
    db: AsyncSession,
    user_id: str,
    user_input: str,
    assistant_output: str,
) -> list[dict]:
    """
    Extract 1-3 important facts from a conversation using user's coordinator model.

    Returns a list of {key, value} pairs, or empty list if nothing important.
    """
    system_prompt = (
        "You are a memory extraction assistant. Given a short conversation between a user "
        "and an AI assistant, extract 0 to 3 facts worth remembering about the user or their "
        "situation for future conversations. Only extract things that are stable and useful "
        "across conversations (names, preferences, ongoing projects, recurring schedules). "
        "Do NOT extract small talk, jokes, or one-off information. Return an empty list if "
        "nothing is worth remembering.\n\n"
        "IMPORTANT: Extract fact keys and values in the SAME LANGUAGE as the user's input. "
        "Do NOT translate facts to English."
    )

    user_message = (
        f"User said: {user_input}\n\n"
        f"Assistant said: {assistant_output}\n\n"
        "Extract 0 to 3 facts worth remembering."
    )

    result = await run_system_task(
        db=db,
        user_id=user_id,
        system_prompt=system_prompt,
        user_message=user_message,
        result_type=_MemoryFacts,
        max_tokens=512,
        temperature=0.0,
    )

    if result is None:
        return []
    return [{"key": f.key, "value": f.value} for f in result.facts[:3]]


async def extract_and_save_memory(
    db: AsyncSession,
    agent_id: str,
    user_input: str,
    assistant_output: str,
) -> None:
    """
    Extract facts from conversation and save to agent_memory with 30-day expiry.
    """
    # Look up user_id from agent
    result = await db.execute(
        select(AgentModel).where(AgentModel.id == agent_id).limit(1)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        logger.debug({"event": "memory_extraction_no_agent", "agent_id": agent_id})
        return
    user_id = str(agent.user_id)

    # Extract facts
    facts = await extract_facts_from_conversation(
        db=db,
        user_id=user_id,
        user_input=user_input,
        assistant_output=assistant_output,
    )

    if not facts:
        logger.debug({"event": "memory_extraction", "result": "no_facts", "agent_id": agent_id})
        return

    # Calculate expiry date (30 days from now)
    expires_at = datetime.utcnow() + timedelta(days=MEMORY_RETENTION_DAYS)

    # Upsert facts into agent_memory table
    for fact in facts:
        if not isinstance(fact, dict) or "key" not in fact or "value" not in fact:
            continue

        key = str(fact["key"])[:255]  # Limit key length
        value = str(fact["value"])

        # PostgreSQL upsert (ON CONFLICT DO UPDATE)
        stmt = pg_insert(AgentMemory).values(
            agent_id=agent_id,
            key=key,
            value=value,
            source="agent",  # AI-extracted facts have source="agent"
            updated_at=datetime.utcnow(),
            expires_at=expires_at,
        ).on_conflict_do_update(
            index_elements=["agent_id", "key"],
            set_=dict(
                value=value,
                source="agent",  # Maintain source="agent" on update
                updated_at=datetime.utcnow(),
                expires_at=expires_at,
            )
        )

        await db.execute(stmt)

    await db.commit()
    logger.info({
        "event": "memory_saved",
        "agent_id": agent_id,
        "facts_count": len(facts),
        "expires_at": expires_at.isoformat(),
    })


async def get_agent_memory(
    db: AsyncSession,
    agent_id: str,
) -> list[dict]:
    """
    Retrieve active (non-expired) memory facts for an agent.

    Returns a list of {key, value} pairs.
    """
    result = await db.execute(
        select(AgentMemory.key, AgentMemory.value)
        .where(
            AgentMemory.agent_id == agent_id,
            (AgentMemory.expires_at.is_(None)) | (AgentMemory.expires_at > datetime.utcnow())
        )
        .order_by(AgentMemory.updated_at.desc())
    )

    memories = [
        {"key": row.key, "value": row.value}
        for row in result.all()
    ]

    logger.debug({"event": "get_memory", "agent_id": agent_id, "memories_count": len(memories)})
    return memories


async def format_memory_context(
    db: AsyncSession,
    agent_id: str,
) -> str:
    """
    Format agent memory as a context string for system prompt injection.

    Returns a string like: "Things I remember: key1: value1, key2: value2"
    Or empty string if no memories.
    """
    memories = await get_agent_memory(db, agent_id)

    if not memories:
        return ""

    memory_parts = [f"{m['key']}: {m['value']}" for m in memories]
    return f"Things I remember: {', '.join(memory_parts)}"
