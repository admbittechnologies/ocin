import logging
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.core.dependencies import CurrentUser
from app.models.agent import Agent
from app.models.run import Run
from app.models.schedule import Schedule
from app.models.tool import Tool

logger = logging.getLogger("ocin")

router = APIRouter()


class DashboardStats(BaseModel):
    active_agents: int
    runs_today: int
    schedules_active: int
    tools_connected: int


class RecentRun(BaseModel):
    id: str
    agent: str  # Agent name (renamed from agent_name)
    agent_id: str  # Agent ID
    status: str
    started: Optional[datetime]  # Started timestamp (can be None for pending runs)
    duration: str  # Duration string (calculated)
    schedule_id: Optional[str]  # Schedule ID if triggered by schedule, else null
    schedule_name: Optional[str]  # Schedule name if available, else null


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard statistics for the current user."""
    user_id = str(current_user.id)

    # Count active agents
    result = await db.execute(
        select(func.count(Agent.id)).where(
            Agent.user_id == user_id,
            Agent.is_active == True,
        )
    )
    active_agents = result.scalar() or 0

    # Count runs today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Run.id)).where(
            Run.user_id == user_id,
            Run.started_at >= today_start,
        )
    )
    runs_today = result.scalar() or 0

    # Count active schedules
    result = await db.execute(
        select(func.count(Schedule.id)).where(
            Schedule.user_id == user_id,
            Schedule.is_active == True,
        )
    )
    schedules_active = result.scalar() or 0

    # Count connected external tools (excluding builtin tools)
    # Only count Composio, Apify, Maton tools that are active/configured
    # Built-in tools (File, HTTP, DateTime, Wait) are excluded
    result = await db.execute(
        select(func.count(Tool.id)).where(
            Tool.user_id == user_id,
            Tool.source != "builtin",      # Exclude built-in tools
            Tool.is_active == True,          # Only count active/configured tools
        )
    )
    tools_connected = result.scalar() or 0

    return DashboardStats(
        active_agents=active_agents,
        runs_today=runs_today,
        schedules_active=schedules_active,
        tools_connected=tools_connected,
    )


@router.get("/recent-runs", response_model=list[RecentRun])
async def get_recent_runs(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
):
    """Get recent runs for the current user."""
    user_id = str(current_user.id)

    # Get recent runs with agent names and schedule information
    result = await db.execute(
        select(Run, Agent.name, Schedule.id, Schedule.label)
        .outerjoin(Agent, Run.agent_id == Agent.id)
        .outerjoin(Schedule, Run.schedule_id == Schedule.id)
        .where(Run.user_id == user_id)
        .order_by(Run.started_at.desc())
        .limit(limit)
    )

    runs = []
    for run, agent_name, schedule_id, schedule_name in result.all():
        # Calculate duration string
        duration = ""
        if run.started_at and run.finished_at:
            diff = run.finished_at - run.started_at
            total_seconds = int(diff.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            duration = f"{minutes}m {seconds}s"
        elif run.started_at:
            duration = "Running..."

        runs.append(RecentRun(
            id=str(run.id),
            agent=agent_name or "Unknown Agent",
            agent_id=str(run.agent_id) if run.agent_id else "",
            status=run.status,
            started=run.started_at,
            duration=duration,
            schedule_id=str(schedule_id) if schedule_id else None,
            schedule_name=schedule_name,
        ))

    return runs
