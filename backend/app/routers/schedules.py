import logging
import hashlib
import hmac

from fastapi import APIRouter, Depends, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.triggers.cron import CronTrigger

from app.database import get_db
from app.core.dependencies import CurrentUser, check_plan_limits
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleOut
from app.services.schedule_service import (
    create_schedule,
    list_schedules,
    get_schedule,
    update_schedule,
    delete_schedule,
    pause_schedule,
    resume_schedule,
)
from app.core.exceptions import NotFoundException, ScheduleParseException
from pydantic import BaseModel

logger = logging.getLogger("ocin")

router = APIRouter()


class ScheduleToggle(BaseModel):
    active: bool


@router.get("", response_model=list[ScheduleOut])
async def list_user_schedules(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
):
    """List schedules for the current user."""
    schedules = await list_schedules(db, str(current_user.id), skip, limit, active_only)

    return [
        ScheduleOut(
            id=str(s.id),
            user_id=str(s.user_id),
            agent_id=str(s.agent_id),
            label=s.label,
            cron_expression=s.cron_expression,
            trigger_type=s.trigger_type,
            payload=s.payload,
            is_active=s.is_active,
            last_run_at=s.last_run_at,
            next_run_at=s.next_run_at,
        )
        for s in schedules
    ]


@router.get("/{schedule_id}", response_model=ScheduleOut)
async def get_single_schedule(
    schedule_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single schedule by ID."""
    s = await get_schedule(db, schedule_id, str(current_user.id))
    if not s:
        raise NotFoundException("Schedule not found")

    return ScheduleOut(
        id=str(s.id),
        user_id=str(s.user_id),
        agent_id=str(s.agent_id),
        label=s.label,
        cron_expression=s.cron_expression,
        trigger_type=s.trigger_type,
        payload=s.payload,
        is_active=s.is_active,
        last_run_at=s.last_run_at,
        next_run_at=s.next_run_at,
    )


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_user_schedule(
    schedule_data: ScheduleCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Create a new schedule."""
    # Enforce plan limits
    await check_plan_limits(current_user, db, "schedules", 1)

    schedule = await create_schedule(db, str(current_user.id), schedule_data)

    # Register with APScheduler
    from app.main import scheduler
    from app.schedulers import trigger_scheduled_run

    scheduler.add_job(
        trigger_scheduled_run,
        trigger=CronTrigger.from_crontab(schedule.cron_expression),
        args=[str(schedule.id)],
        id=f"schedule_{schedule.id}",
        replace_existing=True,
    )

    return ScheduleOut(
        id=str(schedule.id),
        user_id=str(schedule.user_id),
        agent_id=str(schedule.agent_id),
        label=schedule.label,
        cron_expression=schedule.cron_expression,
        trigger_type=schedule.trigger_type,
        payload=schedule.payload,
        is_active=schedule.is_active,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
    )


@router.put("/{schedule_id}", response_model=ScheduleOut)
async def update_user_schedule(
    schedule_id: str,
    schedule_data: ScheduleUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Update a schedule."""
    schedule = await update_schedule(db, schedule_id, str(current_user.id), schedule_data)

    # Update APScheduler job
    from app.main import scheduler

    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        if schedule.is_active:
            scheduler.reschedule_job(
                job_id,
                trigger=CronTrigger.from_crontab(schedule.cron_expression),
            )
        else:
            scheduler.remove_job(job_id)

    return ScheduleOut(
        id=str(schedule.id),
        user_id=str(schedule.user_id),
        agent_id=str(schedule.agent_id),
        label=schedule.label,
        cron_expression=schedule.cron_expression,
        trigger_type=schedule.trigger_type,
        payload=schedule.payload,
        is_active=schedule.is_active,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
    )


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_schedule(
    schedule_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Delete a schedule."""
    await delete_schedule(db, schedule_id, str(current_user.id))

    # Remove from APScheduler
    from app.main import scheduler

    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


@router.post("/{schedule_id}/pause", response_model=ScheduleOut)
async def pause_user_schedule(
    schedule_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Pause a schedule."""
    schedule = await pause_schedule(db, schedule_id, str(current_user.id))

    # Remove from APScheduler
    from app.main import scheduler

    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    return ScheduleOut(
        id=str(schedule.id),
        user_id=str(schedule.user_id),
        agent_id=str(schedule.agent_id),
        label=schedule.label,
        cron_expression=schedule.cron_expression,
        trigger_type=schedule.trigger_type,
        payload=schedule.payload,
        is_active=schedule.is_active,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
    )


@router.post("/{schedule_id}/resume", response_model=ScheduleOut)
async def resume_user_schedule(
    schedule_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Resume a schedule."""
    schedule = await resume_schedule(db, schedule_id, str(current_user.id))

    # Re-add to APScheduler
    from app.main import scheduler
    from app.schedulers import trigger_scheduled_run

    scheduler.add_job(
        trigger_scheduled_run,
        trigger=CronTrigger.from_crontab(schedule.cron_expression),
        args=[str(schedule.id)],
        id=f"schedule_{schedule.id}",
        replace_existing=True,
    )

    return ScheduleOut(
        id=str(schedule.id),
        user_id=str(schedule.user_id),
        agent_id=str(schedule.agent_id),
        label=schedule.label,
        cron_expression=schedule.cron_expression,
        trigger_type=schedule.trigger_type,
        payload=schedule.payload,
        is_active=schedule.is_active,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
    )


@router.put("/{schedule_id}/toggle", response_model=ScheduleOut)
async def toggle_user_schedule(
    schedule_id: str,
    toggle_data: ScheduleToggle,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Toggle a schedule's active status."""
    if toggle_data.active:
        schedule = await resume_schedule(db, schedule_id, str(current_user.id))
        # Re-add to APScheduler
        from app.main import scheduler
        from app.schedulers import trigger_scheduled_run
        scheduler.add_job(
            trigger_scheduled_run,
            trigger=CronTrigger.from_crontab(schedule.cron_expression),
            args=[str(schedule.id)],
            id=f"schedule_{schedule.id}",
            replace_existing=True,
        )
    else:
        schedule = await pause_schedule(db, schedule_id, str(current_user.id))
        # Remove from APScheduler
        from app.main import scheduler
        job_id = f"schedule_{schedule_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    return ScheduleOut(
        id=str(schedule.id),
        user_id=str(schedule.user_id),
        agent_id=str(schedule.agent_id),
        label=schedule.label,
        cron_expression=schedule.cron_expression,
        trigger_type=schedule.trigger_type,
        payload=schedule.payload,
        is_active=schedule.is_active,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
    )
