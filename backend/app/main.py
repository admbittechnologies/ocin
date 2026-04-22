from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import time
from typing import Callable

from app.config import settings as app_settings
from app.database import engine, AsyncSessionLocal
from app.core.dependencies import get_db
from app.core.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    BadRequestException,
    NotFoundException,
    ConflictException,
    RateLimitExceededException,
    ToolUnavailableException,
    ScheduleParseException,
    ApprovalRequestedException,
)
from app.models.message import Message

# Configure structured logging
from pythonjsonlogger import jsonlogger

logger = logging.getLogger("ocin")
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Central APScheduler instance
scheduler = AsyncIOScheduler()


async def cleanup_old_history():
    """Daily cleanup job to delete old threads, expired memory, and purge old attachments."""
    from sqlalchemy import delete, select, func, and_
    from app.models.thread import Thread
    from app.models.memory import AgentMemory
    from app.models.message import Message

    async with AsyncSessionLocal() as db:
        # Delete threads older than 50 days (messages cascade automatically)
        cutoff = datetime.utcnow() - timedelta(days=50)

        result = await db.execute(
            delete(Thread).where(Thread.last_message_at < cutoff)
        )
        deleted_threads = result.rowcount

        # Delete expired memory facts
        result2 = await db.execute(
            delete(AgentMemory).where(
                AgentMemory.expires_at != None,
                AgentMemory.expires_at < datetime.utcnow()
            )
        )
        deleted_memory = result2.rowcount

        # Purge old attachment base64 data (keep only last 50 messages per thread)
        # Find threads with > 50 messages
        subq = (
            select(Message.thread_id, func.count(Message.id).label("msg_count"))
            .group_by(Message.thread_id)
            .having(func.count(Message.id) > 50)
            .subquery()
        )

        result3 = await db.execute(
            select(Message.thread_id, Message.id, Message.attachments)
            .join(subq, Message.thread_id == subq.c.thread_id)
            .order_by(Message.thread_id, Message.created_at.desc())
        )

        threads_with_old_messages = result3.all()

        # For each thread, identify messages older than the most recent 50
        total_bytes_freed = 0
        total_messages_purged = 0

        current_thread_id = None
        message_count = 0

        for msg in threads_with_old_messages:
            if msg.thread_id != current_thread_id:
                current_thread_id = msg.thread_id
                message_count = 0

            message_count += 1

            # Skip the most recent 50 messages
            if message_count > 50 and msg.attachments:
                # Calculate bytes before purging
                bytes_before = 0
                try:
                    if isinstance(msg.attachments, list):
                        for attachment in msg.attachments:
                            if isinstance(attachment, dict) and "data_base64" in attachment:
                                bytes_before += len(str(attachment.get("data_base64", "")))
                except Exception:
                    pass

                # Replace attachments with metadata-only stub
                stub_attachments = []
                try:
                    if isinstance(msg.attachments, list):
                        for attachment in msg.attachments:
                            if isinstance(attachment, dict):
                                stub_attachments.append({
                                    "name": attachment.get("name"),
                                    "media_type": attachment.get("media_type"),
                                    "size_bytes": attachment.get("size_bytes"),
                                    "data_base64": None,
                                    "purged": True,
                                })
                except Exception:
                    stub_attachments = []

                if stub_attachments:
                    await db.execute(
                        Message.__table__.update()
                        .where(Message.id == msg.id)
                        .values(attachments=stub_attachments)
                    )
                    total_bytes_freed += bytes_before
                    total_messages_purged += 1

        await db.commit()

        if total_messages_purged > 0:
            logger.info({
                "event": "attachments_purged",
                "thread_id": "multiple",
                "message_count": total_messages_purged,
                "total_bytes_freed": total_bytes_freed,
            })

        logger.info({
            "event": "cleanup_old_history",
            "deleted_threads": deleted_threads,
            "deleted_memory": deleted_memory,
        })


async def purge_old_runs():
    """Daily retention job for runs. Tiered cleanup:
    - Tier 1 (0-30 days): full row, no changes
    - Tier 2 (30-90 days): purge heavy fields (output, tool_calls, input)
    - Tier 3 (>90 days): delete row entirely
    """
    from app.services.run_service import purge_old_runs as do_purge
    await do_purge()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    logger.info({"event": "startup", "message": "Starting OCIN API"})

    # Start APScheduler
    scheduler.start()
    logger.info({"event": "startup", "message": "APScheduler started"})

    # Register daily cleanup job at 3am
    scheduler.add_job(
        cleanup_old_history,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_old_history",
        replace_existing=True,
    )
    logger.info({"event": "startup", "message": "Cleanup job registered (daily at 3am)"})

    # Register daily runs retention job at 3:15am
    scheduler.add_job(
        purge_old_runs,
        trigger=CronTrigger(hour=3, minute=15),
        id="runs_retention_purge",
        replace_existing=True,
    )
    logger.info({"event": "startup", "message": "Runs retention job registered (daily at 3:15am)"})

    # Load schedules from DB and register jobs
    from app.schedulers import reload_schedules
    await reload_schedules(scheduler)
    logger.info({"event": "startup", "message": "Schedules loaded"})

    # Start Telegram bot (non-blocking, runs in background)
    from app.services.telegram_service import start_telegram_service, stop_telegram_service
    await start_telegram_service()

    yield

    # Shutdown
    logger.info({"event": "shutdown", "message": "Shutting down OCIN API"})
    await stop_telegram_service()
    scheduler.shutdown()
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="OCIN API",
    description="Lean SaaS platform for personal AI agents",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware - IMMEDIATELY after app creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://0.0.0.0:8080",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://0.0.0.0:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://0.0.0.0:5173",
        "http://89.167.104.147:8091",
        "http://89.167.104.147:8090",
        "http://89.167.104.147:5173",
        "https://ocin.site",
        "https://www.ocin.site",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
from app.routers import auth, agents, tools, runs, memory, schedules, webhooks, admin, dashboard, providers, settings, chat, approvals
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(tools.router, prefix="/api/v1/tools", tags=["tools"])
app.include_router(runs.router, prefix="/api/v1/runs", tags=["runs"])
app.include_router(memory.router, prefix="/api/v1/memory", tags=["memory"])
app.include_router(schedules.router, prefix="/api/v1/schedules", tags=["schedules"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(providers.router, prefix="/api/v1/providers", tags=["providers"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])


# Exception handler for custom exceptions
@app.exception_handler(UnauthorizedException)
async def unauthorized_handler(request: Request, exc: UnauthorizedException):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=exc.detail,
    )


@app.exception_handler(ForbiddenException)
async def forbidden_handler(request: Request, exc: ForbiddenException):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=exc.detail,
    )


@app.exception_handler(BadRequestException)
async def bad_request_handler(request: Request, exc: BadRequestException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=exc.detail,
    )


@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=exc.detail,
    )


@app.exception_handler(ConflictException)
async def conflict_handler(request: Request, exc: ConflictException):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=exc.detail,
    )


@app.exception_handler(RateLimitExceededException)
async def rate_limit_handler(request: Request, exc: RateLimitExceededException):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=exc.detail,
    )


@app.exception_handler(ApprovalRequestedException)
async def approval_requested_handler(request: Request, exc: ApprovalRequestedException):
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=exc.message,
    )


@app.exception_handler(ScheduleParseException)


@app.exception_handler(ScheduleParseException)
async def schedule_parse_handler(request: Request, exc: ScheduleParseException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=exc.detail,
    )


@app.get("/")
async def root():
    return {"name": "OCIN API", "version": "1.0.0"}


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint - tests db, redis, and scheduler connectivity."""
    health_status = {"api": "ok"}

    # Check database
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
        health_status["db"] = "ok"
    except Exception as e:
        logger.error({"event": "health_check", "component": "db", "error": str(e)})
        health_status["db"] = "error"

    # Check Redis
    try:
        import redis as sync_redis
        r = sync_redis.from_url(app_settings.REDIS_URL, decode_responses=True)
        r.ping()
        r.close()
        health_status["redis"] = "ok"
    except Exception as e:
        import traceback
        logger.error({"event": "health_check", "component": "redis", "error": str(e), "traceback": traceback.format_exc()})
        health_status["redis"] = "error"

    # Check scheduler
    try:
        health_status["scheduler"] = "ok" if scheduler.running else "error"
    except Exception as e:
        logger.error({"event": "health_check", "component": "scheduler", "error": str(e)})
        health_status["scheduler"] = "error"

    return health_status
