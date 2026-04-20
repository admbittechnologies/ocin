import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status, Query, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from redis.asyncio import Redis
import json

from app.database import get_db
from app.core.dependencies import CurrentUser
from app.core.security import decode_token
from app.schemas.run import RunCreate, RunOut
from app.services.run_service import create_run, list_runs, get_run
from app.services.agent_runner import run_agent
from app.config import settings
from app.core.exceptions import NotFoundException

logger = logging.getLogger("ocin")
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


async def get_redis() -> Redis:
    """Get Redis client."""
    return Redis.from_url(settings.REDIS_URL, decode_responses=False)


@router.get("", response_model=list[RunOut])
async def list_user_runs(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    agent_id: str | None = None,
    status: str | None = None,
):
    """List runs for the current user. Excludes heavy fields (output, tool_calls)."""
    from app.models.run import Run

    # Build query with eager loading for agent and schedule
    query = (
        select(Run)
        .options(
            selectinload(Run.agent),
            selectinload(Run.schedule),
        )
        .where(Run.user_id == str(current_user.id))
    )
    if agent_id:
        query = query.where(Run.agent_id == agent_id)
    if status:
        query = query.where(Run.status == status)
    query = query.order_by(Run.started_at.desc().nullslast()).offset(skip).limit(limit)

    result = await db.execute(query)
    runs = list(result.scalars().all())

    # Convert to response format
    cutoff_30 = datetime.now(timezone.utc) - timedelta(days=30)
    response_runs = []
    for run in runs:
        # Compute is_archived: finished_at < now-30d AND output is None
        is_archived = (
            run.finished_at is not None
            and run.finished_at < cutoff_30
            and run.output is None
        )

        response_runs.append(RunOut(
            id=str(run.id),
            user_id=str(run.user_id),
            agent_id=str(run.agent_id) if run.agent_id else None,
            agent_name=run.agent.name if run.agent else None,
            schedule_id=str(run.schedule_id) if run.schedule_id else None,
            schedule_label=run.schedule.label if run.schedule else None,
            status=run.status,
            input="",  # Exclude input from list
            output=None,  # Exclude output from list
            tool_calls=[],  # Exclude tool_calls from list
            tokens_used=run.tokens_used,
            cost_usd=run.cost_usd,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error=run.error,
            is_archived=is_archived,
        ))
    return response_runs


@router.get("/{run_id}", response_model=RunOut)
async def get_single_run(
    run_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single run by ID with all details including output and tool_calls."""
    from app.models.run import Run

    # Load run with agent and schedule relationships
    result = await db.execute(
        select(Run)
        .options(
            selectinload(Run.agent),
            selectinload(Run.schedule),
        )
        .where(Run.id == run_id, Run.user_id == str(current_user.id))
    )
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundException("Run not found")

    # Compute is_archived: finished_at < now-30d AND output is None
    cutoff_30 = datetime.now(timezone.utc) - timedelta(days=30)
    is_archived = (
        run.finished_at is not None
        and run.finished_at < cutoff_30
        and run.output is None
    )

    # Convert tool_calls from JSONB to ToolCall objects
    tool_calls = []
    if run.tool_calls:
        for tc in run.tool_calls:
            tool_calls.append({
                "tool": tc.get("tool"),
                "input": tc.get("input"),
                "output": tc.get("output"),
                "duration_ms": tc.get("duration_ms"),
            })

    return RunOut(
        id=str(run.id),
        user_id=str(run.user_id),
        agent_id=str(run.agent_id) if run.agent_id else None,
        agent_name=run.agent.name if run.agent else None,
        schedule_id=str(run.schedule_id) if run.schedule_id else None,
        schedule_label=run.schedule.label if run.schedule else None,
        parent_run_id=str(run.parent_run_id) if run.parent_run_id else None,
        status=run.status,
        input=run.input or "",
        output=run.output,
        tool_calls=tool_calls,
        tokens_used=run.tokens_used,
        cost_usd=run.cost_usd,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        is_archived=is_archived,
    )


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def trigger_run(
    run_data: RunCreate,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Trigger an agent run and return run_id immediately."""
    from app.services.run_service import RunCreate as RunCreateModel

    # Verify agent belongs to user
    from app.services.agent_service import get_agent
    agent = await get_agent(db, run_data.agent_id, str(current_user.id))
    if not agent:
        raise NotFoundException("Agent not found")

    # Create run record
    run = await create_run(
        db,
        RunCreateModel(
            user_id=str(current_user.id),
            agent_id=run_data.agent_id,
            schedule_id=run_data.schedule_id,
            input=run_data.input,
        ),
    )

    # Launch agent run in background
    redis = await get_redis()
    background_tasks.add_task(
        run_agent,
        run_id=str(run.id),
        agent_id=run_data.agent_id,
        user_id=str(current_user.id),
        input_text=run_data.input,
        db=db,
        redis=redis,
    )

    logger.info({"event": "trigger_run", "run_id": str(run.id), "agent_id": run_data.agent_id})
    return {"run_id": str(run.id)}


@router.websocket("/{run_id}/stream")
async def stream_run(
    run_id: str,
    token: str,
    websocket: WebSocket,
):
    """Stream run output via WebSocket."""
    # Verify token
    payload = decode_token(token)
    if payload is None or "sub" not in payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload.get("sub")

    # Verify run belongs to user
    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        run = await get_run(db, run_id, user_id)
        if not run:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Subscribe to Redis channel
        redis = await get_redis()
        stream_key = f"ocin:run:{run_id}:stream"
        pubsub = redis.pubsub()
        await pubsub.subscribe(stream_key)

        await websocket.accept()

        # Stream messages
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]

                # Try to parse as JSON for control messages
                try:
                    msg = json.loads(data)
                    # Forward all control messages including progress
                    if msg.get("type") in ["done", "error", "progress"]:
                        await websocket.send_json(msg)
                        if msg.get("type") in ["done", "error"]:
                            break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Raw token
                    await websocket.send_text(data.decode() if isinstance(data, bytes) else data)

        await pubsub.unsubscribe(stream_key)
        await pubsub.close()
        await redis.close()

    except WebSocketDisconnect:
        logger.info({"event": "websocket_disconnect", "run_id": run_id})
    except Exception as e:
        logger.error({"event": "websocket_error", "run_id": run_id, "error": str(e)})
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        await db_gen.aclose()
