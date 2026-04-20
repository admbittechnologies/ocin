import logging
from typing import Optional

from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.dependencies import CurrentUser
from app.services.run_service import create_run
from app.models.agent import Agent as AgentModel
from app.models.tool import Tool
from app.services.agent_service import get_agent
from app.schemas.agent import normalize_provider
from app.services.approval_service import create_approval

logger = logging.getLogger("ocin")
router = APIRouter()


class ScheduleTriggerRequest(BaseModel):
    """Request schema for triggering a self-tool schedule."""
    name: str = Field(..., min_length=1, max_length=100)
    agent_name: str
    trigger_type: str = "cron"
    payload: dict = Field(default_factory=dict)
    label: Optional[str] = None


@router.post("/trigger", response_model=dict)
async def trigger_schedule(
    request: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a self-tool schedule (e.g., "every Monday at 9am").
    """
    # Extract parameters from request
    data = ScheduleTriggerRequest(**request)

    # Verify agent belongs to user
    agent = await get_agent(db, data.agent_name, str(current_user.id))
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Agent not found", "code": "AGENT_NOT_FOUND"},
        )

    # Create schedule
    label = data.label or f"Every {data.label}"
    schedule = await create_schedule(
        db=db,
        user_id=str(current_user.id),
        agent_id=data.agent_name,
        label=label,
        trigger_type=data.trigger_type,
        payload=data.payload,
        next_run_at=None,  # Will be calculated by scheduler
    )

    # Create a new approval for the first run
    await create_approval(
        db=db,
        user_id=str(current_user.id),
        agent_id=data.agent_name,
        schedule_id=str(schedule.id),
        kind="self_tool",
        title=f"Run {data.label}?",
        description=f"This is a self-scheduled run of {data.label}. Please confirm before execution.",
    )

    logger.info({
        "event": "schedule_triggered",
        "user_id": str(current_user.id),
        "agent_name": data.agent_name,
        "schedule_label": label,
        "schedule_id": str(schedule.id),
    })

    return {
        "schedule_id": str(schedule.id),
        "approval_id": str(approval.id),
    }
