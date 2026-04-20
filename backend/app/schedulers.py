"""Scheduler functions for APScheduler."""
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis

from app.models.schedule import Schedule
from app.models.approval import Approval
from app.services.run_service import create_run, update_run, RunCreate as RunCreateModel
from app.services.agent_runner import run_agent
from app.database import AsyncSessionLocal
from app.config import settings
from app.core.security import create_access_token

logger = logging.getLogger("ocin")


async def trigger_scheduled_run(schedule_id: str) -> None:
    """
    Trigger a scheduled run.
    Called by APScheduler when a schedule fires.
    """
    db = AsyncSessionLocal()
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    try:
        # Load schedule
        result = await db.execute(
            select(Schedule).where(Schedule.id == schedule_id, Schedule.is_active == True)
        )
        schedule = result.scalar_one_or_none()

        if not schedule:
            logger.warning({
                "event": "trigger_scheduled_run",
                "error": "Schedule not found or inactive",
                "schedule_id": schedule_id,
            })
            return

        # Guard: Check if this schedule has unresolved approvals from prior runs
        # This prevents noisy schedules from creating pending approval requests
        # every 5 minutes when prior ones are still waiting for user action
        pending_approval_result = await db.execute(
            select(Approval).where(
                Approval.schedule_id == schedule_id,
                Approval.status == "awaiting_approval"
            )
        )
        pending_approvals = list(pending_approval_result.scalars().all())

        if pending_approvals:
            logger.info({
                "event": "schedule_fire_skipped",
                "reason": "prior_approval_unresolved",
                "schedule_id": schedule_id,
                "pending_approval_count": len(pending_approvals),
            })
            # Update schedule last_run_at / next_run_at to prevent stuck schedule
            from croniter import croniter
            cron = croniter(schedule.cron_expression, datetime.utcnow())
            schedule.last_run_at = datetime.utcnow()
            schedule.next_run_at = cron.get_next(datetime)
            await db.commit()
            return

        # Extract input text from payload
        input_text = (schedule.payload or {}).get("input", "Scheduled run")

        # Create run record using the RunCreate Pydantic model
        # (create_run expects a RunCreate instance, not a raw dict)
        run = await create_run(
            db,
            RunCreateModel(
                user_id=str(schedule.user_id),
                agent_id=str(schedule.agent_id),
                schedule_id=str(schedule.id),
                input=input_text,
                status="pending",
            ),
        )

        # Update schedule last_run_at / next_run_at
        from croniter import croniter
        cron = croniter(schedule.cron_expression, datetime.utcnow())
        schedule.last_run_at = datetime.utcnow()
        schedule.next_run_at = cron.get_next(datetime)
        await db.commit()

        # Fetch user API keys for the agent's provider so scheduled runs
        # can actually make LLM calls (same path as chat.py uses)
        model_api_keys = {}
        try:
            from app.models.agent import Agent as AgentModel
            from app.models.tool import Tool
            from app.core.security import decrypt_value
            from app.schemas.agent import normalize_provider

            agent_result = await db.execute(
                select(AgentModel).where(AgentModel.id == schedule.agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if agent:
                provider_normalized = normalize_provider(agent.model_provider)
                tools_result = await db.execute(
                    select(Tool).where(
                        Tool.user_id == schedule.user_id,
                        Tool.source == "api_key",
                        Tool.source_key == provider_normalized,
                        Tool.is_active == True,
                    )
                )
                for tool in tools_result.scalars().all():
                    encrypted_key = (tool.config or {}).get("api_key")
                    if encrypted_key:
                        try:
                            model_api_keys[provider_normalized] = decrypt_value(encrypted_key)
                        except Exception as e:
                            logger.warning({
                                "event": "trigger_scheduled_run_decrypt",
                                "schedule_id": schedule_id,
                                "error": str(e),
                            })
        except Exception as e:
            logger.warning({
                "event": "trigger_scheduled_run_keys",
                "schedule_id": schedule_id,
                "error": str(e),
            })

        # Generate JWT token for self-call tools (needed for approval system)
        # This token has a long expiry since scheduled runs might take a while
        jwt_token = create_access_token(
            data={"sub": str(schedule.user_id)},
            expires_delta=timedelta(hours=1)  # 1 hour expiry for scheduled runs
        )

        # Launch agent run with JWT token
        await run_agent(
            run_id=str(run.id),
            agent_id=str(schedule.agent_id),
            user_id=str(schedule.user_id),
            input_text=input_text,
            db=db,
            redis=redis,
            model_api_keys=model_api_keys,
            jwt_token=jwt_token,  # Add JWT token for self-tools
            api_base="http://api:8000",
        )

        logger.info({
            "event": "trigger_scheduled_run",
            "run_id": str(run.id),
            "schedule_id": schedule_id,
        })
    except Exception as e:
        logger.error({
            "event": "trigger_scheduled_run",
            "schedule_id": schedule_id,
            "error": str(e),
        })
    finally:
        await db.close()
        await redis.close()


async def reload_schedules(scheduler) -> None:
    """
    Reload all active schedules from DB into APScheduler.
    Call this on startup or when schedules change.
    """
    db = AsyncSessionLocal()
    try:
        from app.services.schedule_service import get_all_active_schedules
        schedules = await get_all_active_schedules(db)

        from apscheduler.triggers.cron import CronTrigger

        for schedule in schedules:
            job_id = f"schedule_{schedule.id}"
            scheduler.add_job(
                trigger_scheduled_run,
                trigger=CronTrigger.from_crontab(schedule.cron_expression),
                args=[str(schedule.id)],
                id=job_id,
                replace_existing=True,
            )

        logger.info({"event": "reload_schedules", "count": len(schedules)})
    except Exception as e:
        logger.error({"event": "reload_schedules", "error": str(e)})
    finally:
        await db.close()
