import logging
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
import json

from fastapi import APIRouter, Depends, status, Request, Query, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis

from app.database import get_db
from app.core.dependencies import CurrentUser
from app.core.security import decode_token, decrypt_value
from app.services.run_service import create_run
from app.services.agent_runner import run_agent
from app.config import settings
from app.core.exceptions import NotFoundException
from app.services.agent_service import get_agent
from app.schemas.agent import normalize_provider
from app.models.tool import Tool
from app.schemas.thread import ThreadOut, ThreadListItem, ThreadListResponse
from app.schemas.message import MessageOut, MessageListResponse, ChatAttachment
from app.core.attachments import build_multimodal_input
from app.services.thread_service import (
    create_thread,
    get_user_threads,
    get_thread,
    delete_thread,
    get_thread_messages,
)
from app.models.message import Message

logger = logging.getLogger("ocin")
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


async def get_redis() -> Redis:
    """Get Redis client."""
    return Redis.from_url(settings.REDIS_URL, decode_responses=False)


async def get_api_keys_for_provider(
    db: AsyncSession,
    user_id: str,
    provider_normalized: str,
) -> dict[str, str]:
    """
    Retrieve API keys for a given provider from tools table.

    API keys are stored in tools table with source='api_key' and
    provider name as source_key (lowercase).
    """
    result = await db.execute(
        select(Tool).where(
            Tool.user_id == user_id,
            Tool.source == "api_key",
            Tool.source_key == provider_normalized,
            Tool.is_active == True,
        )
    )
    tools = result.scalars().all()

    api_keys = {}
    for tool in tools:
        try:
            encrypted_key = tool.config.get("api_key")
            if encrypted_key:
                decrypted_key = decrypt_value(encrypted_key)
                api_keys[provider_normalized] = decrypted_key
        except Exception as e:
            logger.warning({
                "event": "get_api_keys_for_provider",
                "user_id": user_id,
                "provider": provider_normalized,
                "error": str(e),
            })

    return api_keys


class ChatSendRequest(BaseModel):
    """Request schema for sending a chat message."""
    agent_id: str
    message: str = Field(..., min_length=1, max_length=10000)
    thread_id: Optional[str] = None
    attachments: Optional[list[ChatAttachment]] = None


class ChatSendResponse(BaseModel):
    """Response schema for chat send."""
    message_id: str
    thread_id: Optional[str] = None
    type: Optional[str] = None
    message: Optional[str] = None


@router.post("/send", response_model=ChatSendResponse)
@limiter.limit("30/minute")
async def send_chat_message(
    request: Request,
    data: ChatSendRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a chat message to an agent.

    If thread_id is provided, continues conversation in that thread.
    If no thread_id, creates a new thread and returns thread_id.

    Supports commands:
    - /clear — Clear conversation history and start fresh
    - /help — Show available commands

    Supports image attachments for vision-capable models.
    """
    from app.services.run_service import RunCreate as RunCreateModel

    # Log chat request with attachment info
    has_attachments = data.attachments is not None and len(data.attachments) > 0
    attachment_count = len(data.attachments) if has_attachments else 0

    logger.info({
        "event": "chat_request_received",
        "has_attachments": has_attachments,
        "attachment_count": attachment_count,
        "input_len": len(data.message),
    })

    # TRACE: Router entry - after Pydantic parsing
    first_attachment_type = data.attachments[0].type if data.attachments and len(data.attachments) > 0 else None
    first_attachment_data_len = len(data.attachments[0].data_base64) if data.attachments and len(data.attachments) > 0 else None
    logger.info({
        "event": "attachment_trace",
        "checkpoint": "router_entry",
        "count": len(data.attachments) if data.attachments else 0,
        "first_type": first_attachment_type,
        "first_data_len": first_attachment_data_len,
    })

    # Validate attachment count (max 5 per message)
    if attachment_count > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Too many attachments. Maximum 5 attachments per message.",
                "code": "TOO_MANY_ATTACHMENTS"
            }
        )

    # Validate attachment types (only images supported in v1)
    if has_attachments:
        from app.core.attachments import ACCEPTED_IMAGE_TYPES
        for attachment in data.attachments:
            if not attachment.type.startswith("image/"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": f"Unsupported attachment type: {attachment.type}. Only image attachments are supported.",
                        "code": "UNSUPPORTED_ATTACHMENT_TYPE"
                    }
                )
            if attachment.type not in ACCEPTED_IMAGE_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": f"Unsupported image type: {attachment.type}. Accepted types: {', '.join(ACCEPTED_IMAGE_TYPES)}.",
                        "code": "UNSUPPORTED_IMAGE_TYPE"
                    }
                )

    # Log attachment details if present
    if has_attachments:
        total_bytes = 0
        mime_types = []
        for attachment in data.attachments:
            try:
                from app.core.attachments import normalize_base64
                image_bytes = normalize_base64(attachment.data_base64)
                total_bytes += len(image_bytes)
                mime_types.append(attachment.type)
            except Exception as e:
                logger.warning({
                    "event": "attachment_validation_failed",
                    "error": str(e),
                })
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "Invalid attachment data. Please ensure files are properly encoded.",
                        "code": "INVALID_ATTACHMENT_DATA"
                    }
                )

        # Enforce 15MB total limit per message
        MAX_TOTAL_SIZE = 15 * 1024 * 1024  # 15MB
        if total_bytes > MAX_TOTAL_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": f"Total attachment size exceeds 15MB limit. Current size: {total_bytes / (1024 * 1024):.1f}MB",
                    "code": "ATTACHMENT_TOO_LARGE"
                }
            )

        logger.info({
            "event": "attachment_received",
            "count": attachment_count,
            "total_bytes": total_bytes,
            "mime_types": mime_types,
        })

    # Extract user from Authorization header
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_token(token)
        if payload and "sub" in payload:
            user_id = payload.get("sub")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Invalid authentication credentials", "code": "UNAUTHORIZED"}
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Missing authentication", "code": "UNAUTHORIZED"}
        )

    # Handle /help command
    if data.message.strip().lower() == "/help":
        help_text = """Available commands:
/clear — Clear conversation history and start fresh
/help  — Show this help message

Tips:
• I remember our conversation context automatically
• I can create Google Sheets, send Slack messages, manage HubSpot
• Ask me to remember things and I will store them in memory
• You can switch agents by typing @ followed by agent name"""
        return ChatSendResponse(
            message_id="help",
            type="help",
            message=help_text,
        )

    # Handle /clear command
    if data.message.strip().lower() == "/clear":
        # If thread_id is provided, delete all messages in that thread
        if data.thread_id:
            # Verify thread belongs to user
            thread = await get_thread(db, data.thread_id, user_id)
            if not thread:
                raise NotFoundException("Thread not found")

            # Delete all messages in this thread
            await db.execute(
                delete(Message).where(Message.thread_id == data.thread_id)
            )
            await db.commit()
            logger.info({
                "event": "thread_cleared",
                "thread_id": data.thread_id,
                "user_id": user_id,
            })

            # Publish cleared message to Redis so open SSE connections get it
            redis = await get_redis()
            await redis.publish(
                f"ocin:thread:{data.thread_id}:system",
                json.dumps({
                    "type": "cleared",
                    "message": "🧹 Conversation cleared. Starting fresh!",
                })
            )
            await redis.close()
        else:
            # No thread to clear
            return ChatSendResponse(
                message_id="cleared",
                type="cleared",
                message="No active conversation to clear.",
            )

        return ChatSendResponse(
            message_id="cleared",
            type="cleared",
            message="🧹 Conversation cleared. Starting fresh!",
        )

    # Verify agent belongs to user
    agent = await get_agent(db, data.agent_id, user_id)
    if not agent:
        raise NotFoundException("Agent not found")

    # Get or create thread
    thread_id = data.thread_id
    if thread_id:
        # Verify thread belongs to user
        thread = await get_thread(db, thread_id, user_id)
        if not thread:
            raise NotFoundException("Thread not found")
    else:
        # Create new thread with title from message (truncated to 50 chars)
        title = data.message[:50] + "..." if len(data.message) > 50 else data.message
        thread = await create_thread(db, user_id, data.agent_id, title=title)
        thread_id = str(thread.id)

    # Get API keys for agent's provider
    provider_normalized = normalize_provider(agent.model_provider)
    model_api_keys = await get_api_keys_for_provider(db, user_id, provider_normalized)

    # Create run record
    run = await create_run(
        db,
        RunCreateModel(
            user_id=user_id,
            agent_id=data.agent_id,
            input=data.message,
        ),
    )

    # Launch agent run in background
    redis = await get_redis()

    # TRACE: Router dispatch - before calling agent executor
    logger.info({
        "event": "attachment_trace",
        "checkpoint": "router_dispatch",
        "count": len(data.attachments) if data.attachments else 0,
        "target_function": "run_agent",
    })

    # TRACE: Post router conversion - detect exact serialization behavior
    # Log state BEFORE any serialization/conversion happens
    if has_attachments:
        first_type = type(data.attachments[0]).__name__ if data.attachments and len(data.attachments) > 0 else "None"
        first_keys = list(data.attachments[0].model_fields.keys()) if data.attachments and len(data.attachments) > 0 else []
        logger.info({
            "event": "attachment_trace",
            "checkpoint": "post_router_conversion",
            "count": attachment_count,
            "first_element_type": first_type,
            "first_element_keys": first_keys,
        })

    # Store attachments to DB first (persistence must happen before agent execution)
    if has_attachments:
        # Prepare attachment metadata for storage (with inline base64 data)
        from app.core.attachments import normalize_base64, ACCEPTED_IMAGE_TYPES
        attachment_metadata_list = []
        for attachment in data.attachments:
            try:
                attachment_type = attachment.type
                if not attachment_type.startswith("image/"):
                    continue
                if attachment_type not in ACCEPTED_IMAGE_TYPES:
                    continue
                image_bytes = normalize_base64(attachment.data_base64)
                # Convert back to raw base64 (no data URL prefix)
                import base64
                raw_base64 = base64.b64encode(image_bytes).decode('utf-8')
                attachment_metadata_list.append({
                    "name": attachment.name,
                    "media_type": attachment_type,
                    "size_bytes": len(image_bytes),
                    "data_base64": raw_base64,
                })
            except Exception as e:
                logger.warning({
                    "event": "attachment_processing_failed",
                    "error": str(e),
                })

    background_tasks.add_task(
        run_agent,
        run_id=str(run.id),
        agent_id=data.agent_id,
        user_id=user_id,
        input_text=data.message,
        db=db,
        redis=redis,
        model_api_keys=model_api_keys,
        thread_id=thread_id,
        jwt_token=token,
        api_base="http://api:8000",
        attachments=data.attachments,  # Pass original attachment objects directly
    )

    logger.info({
        "event": "chat_send",
        "run_id": str(run.id),
        "thread_id": thread_id,
        "agent_id": data.agent_id,
        "user_id": user_id,
    })
    return ChatSendResponse(message_id=str(run.id), thread_id=thread_id)

async def chat_event_generator(run_id: str, token: str):
    """Generate SSE events for chat stream.

    Uses Redis list (RPUSH + LRANGE) instead of pub/sub to avoid race conditions.
    Late SSE subscribers can read from offset 0 and never miss anything.
    """
    redis = None
    stream_key = f"ocin:run:{run_id}:stream"
    cache_key = f"ocin:run:{run_id}:output"

    logger.info({"event": "sse_generator_subscribe", "run_id": run_id, "stream_key": stream_key})

    try:
        redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)

        # ALWAYS yield connected event first to ensure proper SSE framing
        yield f"event: connected\ndata: {json.dumps({'type': 'connected'})}\n\n"

        # Check initial buffer state
        initial_buffer = await redis.lrange(stream_key, 0, -1)
        initial_buffer_state = "empty" if not initial_buffer else f"non-empty: {len(initial_buffer)} items, first: {initial_buffer[0][:50] if initial_buffer else 'N/A'}"
        logger.info({"event": "sse_stream_started", "run_id": run_id, "initial_buffer_state": initial_buffer_state})

        # Fast path: if run is already fully complete, replay from cache
        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            output = data.get("output", "")
            logger.info({"event": "sse_stream_cache_hit", "run_id": run_id, "output_length": len(output)})
            yield f"event: token\ndata: {json.dumps({'type': 'token', 'token': output})}\n\n"
            yield f"event: done\ndata: {json.dumps({'type': 'done', 'run_id': run_id, 'status': 'success'})}\n\n"
            logger.info({"event": "sse_stream_done", "run_id": run_id, "total_tokens": 1, "final_text_length": len(output), "final_text_preview": output[:100]})
            logger.info({
                "event": "sse_generator_exit",
                "run_id": run_id,
                "reason": "cache_hit",
                "total_iters": 0,
                "total_yielded": 1,
            })
            return

        cursor = 0
        idle_loops = 0
        MAX_IDLE_LOOPS = 300  # ~5 min hard timeout
        token_count = 0
        accumulated_text = ""
        total_iters = 0

        while True:
            total_iters += 1
            # Log every 10th iteration
            if total_iters % 10 == 0:
                logger.info({
                    "event": "sse_generator_loop_iter",
                    "run_id": run_id,
                    "iter_n": total_iters,
                    "items_in_list": len(batch) if 'batch' in locals() else 0,
                    "waited_ms_so_far": total_iters * 1000,
                    "cursor": cursor,
                })
            # Drain anything currently buffered in the list
            batch = await redis.lrange(stream_key, cursor, cursor + 99)
            if batch:
                cursor += len(batch)
                idle_loops = 0
                for i, raw in enumerate(batch):
                    try:
                        msg_data = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(msg_data, dict):
                        continue
                    msg_type = msg_data.get("type", "token")

                    # Log every 10th token for diagnostics
                    if msg_type == "token":
                        token_count += 1
                        if token_count % 10 == 0:
                            token_preview = msg_data.get("token", "")[:30]
                            logger.info({"event": "sse_token_received", "run_id": run_id, "token_index": token_count, "token_preview": token_preview})

                        # Accumulate text for final summary
                        accumulated_text += msg_data.get("token", "")

                    # Handle error messages specially — yield as error event and close stream
                    if msg_type == "error":
                        logger.error({"event": "sse_stream_error", "run_id": run_id, "error": msg_data.get("error")})
                        yield f"event: error\ndata: {json.dumps(msg_data)}\n\n"
                        logger.info({
                            "event": "sse_generator_exit",
                            "run_id": run_id,
                            "reason": "error_received",
                            "total_iters": total_iters,
                            "total_yielded": token_count,
                        })
                        return

                    yield f"event: {msg_type}\ndata: {json.dumps(msg_data)}\n\n"

                    if msg_type in ("done",):
                        logger.info({"event": "sse_stream_done", "run_id": run_id, "total_tokens": token_count, "final_text_length": len(accumulated_text), "final_text_preview": accumulated_text[:100]})
                        logger.info({
                            "event": "sse_generator_exit",
                            "run_id": run_id,
                            "reason": "done_received",
                            "total_iters": total_iters,
                            "total_yielded": token_count,
                        })
                        return
                continue

            # List is empty — check if run finished while we were sleeping.
            # The publisher may have RPUSHed the full output, written to cache,
            # and deleted the list all within one of our polling intervals.
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                output = data.get("output", "")
                logger.info({"event": "sse_stream_cache_recovered", "run_id": run_id, "output_length": len(output)})
                yield f"event: token\ndata: {json.dumps({'type': 'token', 'token': output})}\n\n"
                yield f"event: done\ndata: {json.dumps({'type': 'done', 'run_id': run_id, 'status': 'success'})}\n\n"
                logger.info({"event": "sse_stream_done", "run_id": run_id, "total_tokens": 1, "final_text_length": len(output), "final_text_preview": output[:100]})
                logger.info({
                    "event": "sse_generator_exit",
                    "run_id": run_id,
                    "reason": "cache_recovered",
                    "total_iters": total_iters,
                    "total_yielded": 1,
                })
                return

            # Nothing buffered and run not yet complete — sleep + heartbeat
            await asyncio.sleep(1)
            idle_loops += 1
            yield ": keepalive\n\n"
            if idle_loops >= MAX_IDLE_LOOPS:
                logger.error({"event": "sse_stream_timeout", "run_id": run_id, "idle_loops": idle_loops})
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': 'stream timeout'})}\n\n"
                logger.info({
                    "event": "sse_generator_exit",
                    "run_id": run_id,
                    "reason": "timeout",
                    "total_iters": total_iters,
                    "total_yielded": token_count,
                })
                return
    except Exception as e:
        logger.error({
            "event": "sse_generator_exception",
            "run_id": run_id,
            "error": str(e),
            "error_type": type(e).__name__,
        })
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': 'stream error'})}\n\n"
        logger.info({
            "event": "sse_generator_exit",
            "run_id": run_id,
            "reason": "exception",
            "total_iters": total_iters if 'total_iters' in locals() else 0,
            "total_yielded": token_count if 'token_count' in locals() else 0,
        })
    finally:
        if redis:
            await redis.close()


@router.get("/stream")
async def stream_chat(
    message_id: str = Query(...),
    token: str = Query(...),
):
    """Stream chat output via SSE."""
    # Verify token
    payload = decode_token(token)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid authentication credentials", "code": "UNAUTHORIZED"}
        )

    user_id = payload.get("sub")

    return StreamingResponse(
        chat_event_generator(message_id, token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# Thread management endpoints

@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    agent_id: Optional[str] = None,
):
    """List all chat threads for current user."""
    threads, total = await get_user_threads(db, str(current_user.id), agent_id, skip, limit)

    thread_items = []
    for thread in threads:
        thread_items.append(ThreadListItem(
            id=str(thread.id),
            agent_id=str(thread.agent_id),
            title=thread.title,
            created_at=thread.created_at,
            last_message_at=thread.last_message_at,
            message_count=getattr(thread, "message_count", 0),
            last_message_preview=getattr(thread, "last_message_preview", None),
        ))

    return ThreadListResponse(threads=thread_items, total=total)


@router.get("/threads/{thread_id}", response_model=ThreadOut)
async def get_single_thread(
    thread_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a single thread by ID."""
    thread = await get_thread(db, thread_id, str(current_user.id))
    if not thread:
        raise NotFoundException("Thread not found")

    return ThreadOut(
        id=str(thread.id),
        user_id=str(thread.user_id),
        agent_id=str(thread.agent_id),
        title=thread.title,
        created_at=thread.created_at,
        last_message_at=thread.last_message_at,
    )


@router.get("/threads/{thread_id}/messages", response_model=MessageListResponse)
async def list_thread_messages(
    thread_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """Get all messages for a thread."""
    messages = await get_thread_messages(db, thread_id, str(current_user.id), limit=limit + skip)

    # Apply pagination
    paginated_messages = messages[skip:skip + limit]

    message_responses = [
        MessageOut(
            id=str(msg.id),
            thread_id=str(msg.thread_id),
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
        )
        for msg in paginated_messages
    ]

    return MessageListResponse(messages=message_responses, total=len(messages))


@router.delete("/threads/{thread_id}")
async def delete_thread_endpoint(
    thread_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Delete a thread and all its messages."""
    success = await delete_thread(db, thread_id, str(current_user.id))
    if not success:
        raise NotFoundException("Thread not found")

    return {"success": True}
