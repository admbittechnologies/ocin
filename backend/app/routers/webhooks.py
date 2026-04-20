"""Webhook endpoints for external triggers."""
import logging
import hashlib
import hmac
from fastapi import APIRouter, Request, HTTPException, status, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.database import get_db
from app.services.run_service import create_run
from app.services.agent_runner import run_agent
from app.models.schedule import Schedule
from app.config import settings
from sqlalchemy import select

logger = logging.getLogger("ocin")
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


@router.post("/webhooks/{schedule_id}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
async def webhook_trigger(
    schedule_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Public webhook endpoint for triggering scheduled runs.
    Validates HMAC signature from scheduler.
    """
    # Get HMAC signature from headers
    signature = request.headers.get("X-Webhook-Signature")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature header",
        )

    # Verify schedule exists and is webhook type
    result = await db.execute(
        select(Schedule).where(
            Schedule.id == schedule_id,
            Schedule.is_active == True,
            Schedule.trigger_type == "webhook",
        )
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    # Verify HMAC signature
    # For simplicity, we use schedule_id as secret (in production, use proper secret)
    expected_signature = hmac.new(
        settings.SECRET_KEY.encode(),
        str(schedule_id).encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        logger.warning({"event": "webhook_invalid_signature", "schedule_id": schedule_id})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    # Get request body
    body = await request.json()

    # Create run record
    run = await create_run(
        db,
        {
            "user_id": str(schedule.user_id),
            "agent_id": str(schedule.agent_id),
            "schedule_id": str(schedule.id),
            "input": body.get("input", "Webhook trigger"),
            "status": "pending",
        },
    )

    # Launch agent run in background
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    import asyncio
    asyncio.create_task(
        run_agent(
            run_id=str(run.id),
            agent_id=str(schedule.agent_id),
            user_id=str(schedule.user_id),
            input_text=body.get("input", "Webhook trigger"),
            db=db,
            redis=redis,
        )
    )

    logger.info({"event": "webhook_trigger", "run_id": str(run.id), "schedule_id": schedule_id})
    return {"run_id": str(run.id)}
