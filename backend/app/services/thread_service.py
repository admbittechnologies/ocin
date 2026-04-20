import logging
from datetime import datetime, timedelta
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from sqlalchemy.dialects.postgresql import insert

from app.models.thread import Thread
from app.models.message import Message
from app.models.agent import Agent
from app.models.user import User

logger = logging.getLogger("ocin")


def clean_assistant_message(text: str) -> str:
    """Remove raw tool output noise from assistant messages before saving."""
    # If message is just a tool result dump, replace with summary
    if len(text) > 500 and ('"spreadsheetId"' in text or text.strip().startswith("{")):
        return "[Tool execution result — see run details]"
    return text


async def create_thread(
    db: AsyncSession,
    user_id: str,
    agent_id: str,
    title: Optional[str] = None,
) -> Thread:
    """Create a new chat thread."""
    # Generate title from first message if not provided
    if title is None:
        title = "New Chat"

    thread = Thread(
        user_id=user_id,
        agent_id=agent_id,
        title=title,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)

    logger.info({"event": "create_thread", "thread_id": str(thread.id), "user_id": user_id, "agent_id": agent_id})
    return thread


async def get_user_threads(
    db: AsyncSession,
    user_id: str,
    agent_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Thread], int]:
    """List threads for a user with pagination and optional agent filter."""
    # Get total count
    count_query = select(func.count(Thread.id)).where(Thread.user_id == user_id)
    if agent_id:
        count_query = count_query.where(Thread.agent_id == agent_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get threads with message count and last message preview
    # Use explicit correlate() to avoid auto-correlation issues
    last_message_subquery = (
        select(Message.content)
        .where(Message.thread_id == Thread.id)
        .where(Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(1)
        .correlate(Thread)
        .scalar_subquery()
    )

    query = (
        select(
            Thread,
            func.count(Message.id).label("message_count"),
            func.coalesce(last_message_subquery, None).label("last_message_preview")
        )
        .outerjoin(Message, Message.thread_id == Thread.id)
        .where(Thread.user_id == user_id)
        .group_by(Thread.id)
    )

    if agent_id:
        query = query.where(Thread.agent_id == agent_id)

    query = query.order_by(Thread.last_message_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)

    threads = []
    for row in result.all():
        thread, message_count, last_message_preview = row
        thread.message_count = message_count or 0
        thread.last_message_preview = last_message_preview[:100] if last_message_preview else None
        threads.append(thread)

    return threads, total


async def get_thread(
    db: AsyncSession,
    thread_id: str,
    user_id: str,
) -> Optional[Thread]:
    """Get a thread by ID (user-scoped)."""
    result = await db.execute(
        select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_thread(
    db: AsyncSession,
    thread_id: str,
    user_id: str,
) -> bool:
    """Delete a thread and all its messages (user-scoped)."""
    result = await db.execute(
        delete(Thread).where(Thread.id == thread_id, Thread.user_id == user_id).returning(Thread.id)
    )
    await db.commit()

    if result.scalar_one_or_none():
        logger.info({"event": "delete_thread", "thread_id": thread_id, "user_id": user_id})
        return True
    return False


async def save_messages(
    db: AsyncSession,
    thread_id: str,
    user_input: str,
    assistant_output: str,
    attachments: Any | None = None,
    kind: str = "normal",  # "normal" | "error" | "system"
) -> tuple[Message, Message]:
    """Save user message and assistant response to a thread."""
    # Update thread's last_message_at
    await db.execute(
        update(Thread)
        .where(Thread.id == thread_id)
        .values(last_message_at=datetime.utcnow())
    )

    # Process attachments if present - store inline in JSONB
    attachment_metadata = None
    if attachments:
        try:
            from app.core.attachments import normalize_base64, ACCEPTED_IMAGE_TYPES

            attachment_metadata = []
            total_size = 0

            for attachment in attachments:
                # Get attachment fields
                attachment_type = getattr(attachment, "type", None)
                attachment_data = getattr(attachment, "data_base64", None)
                attachment_name = getattr(attachment, "name", None)

                if not all([attachment_type, attachment_data, attachment_name]):
                    continue

                # Skip non-images
                if not attachment_type.startswith("image/"):
                    continue

                # Skip unsupported types
                if attachment_type not in ACCEPTED_IMAGE_TYPES:
                    continue

                try:
                    # Decode base64 data
                    image_bytes = normalize_base64(attachment_data)

                    # Check size limit (15MB total per message)
                    total_size += len(image_bytes)
                    MAX_TOTAL_SIZE = 15 * 1024 * 1024  # 15MB
                    # Note: Size validation is done in router, but we log here for debugging
                    if total_size > MAX_TOTAL_SIZE:
                        logger.warning({
                            "event": "attachment_size_exceeded_after_validation",
                            "total_bytes": total_size,
                        })

                    # Convert back to raw base64 (without data URL prefix)
                    import base64
                    raw_base64 = base64.b64encode(image_bytes).decode('utf-8')

                    # Store metadata with inline base64 data
                    attachment_metadata.append({
                        "name": attachment_name,
                        "media_type": attachment_type,
                        "size_bytes": len(image_bytes),
                        "data_base64": raw_base64,
                    })

                except ValueError as size_error:
                    logger.warning({
                        "event": "attachment_processing_error",
                        "error": str(size_error),
                    })
                except Exception as process_error:
                    logger.warning({
                        "event": "attachment_processing_failed",
                        "error": str(process_error),
                    })
                    continue

            if attachment_metadata:
                logger.info({
                    "event": "attachments_processed",
                    "count": len(attachment_metadata),
                    "total_bytes": total_size,
                })
        except Exception as e:
            logger.error({
                "event": "attachments_save_error",
                "error": str(e),
            })
            # Continue without attachments — don't fail the whole message save

    # Create user message
    user_message = Message(
        thread_id=thread_id,
        role="user",
        content=user_input,
        attachments=attachment_metadata if attachment_metadata else None,
        kind=kind,
    )
    db.add(user_message)
    await db.flush()  # Get the message ID

    # Log inline storage success
    if attachment_metadata:
        logger.info({
            "event": "attachment_stored_inline",
            "message_id": str(user_message.id),
            "attachment_count": len(attachment_metadata),
        })

    # Clean assistant message before saving (remove tool result noise)
    cleaned_output = clean_assistant_message(assistant_output)

    # Instrumentation: Log before saving assistant message
    logger.info({
        "event": "save_messages_pre",
        "thread_id": thread_id,
        "assistant_content_length": len(cleaned_output),
        "assistant_content_preview": cleaned_output[:100],
    })

    # Create assistant message
    assistant_message = Message(
        thread_id=thread_id,
        role="assistant",
        content=cleaned_output,
        kind=kind,
    )
    db.add(assistant_message)

    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)

    # Instrumentation: Log after saving assistant message
    logger.info({
        "event": "save_messages_post",
        "thread_id": thread_id,
        "assistant_message_id": str(assistant_message.id),
        "db_returned_content_length": len(assistant_message.content),
    })

    logger.info({
        "event": "save_messages",
        "thread_id": thread_id,
        "user_message_id": str(user_message.id),
        "assistant_message_id": str(assistant_message.id),
        "has_attachments": user_message.attachments is not None,
    })
    return user_message, assistant_message


async def get_thread_messages(
    db: AsyncSession,
    thread_id: str,
    user_id: str,
    limit: int = 100,
) -> list[Message]:
    """Get all messages for a thread (user-scoped)."""
    # First verify user owns the thread
    thread = await get_thread(db, thread_id, user_id)
    if not thread:
        return []

    result = await db.execute(
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_thread_messages_for_context(
    db: AsyncSession,
    thread_id: str,
    user_id: str,
    limit: int = 10,
) -> list[dict]:
    """Get recent messages for PydanticAI message history (user-scoped).

    Limits to:
    - Max 10 most recent messages (reduced from 20 to prevent confusion)
    - Only messages from the last 24 hours
    - If thread has >30 messages total, only load last 5
    """
    from datetime import datetime, timedelta

    # First verify user owns the thread
    thread = await get_thread(db, thread_id, user_id)
    if not thread:
        return []

    # Check total message count in thread
    count_result = await db.execute(
        select(func.count(Message.id)).where(Message.thread_id == thread_id)
    )
    total_count = count_result.scalar() or 0

    # If thread is long, only load last 5 messages
    if total_count > 30:
        limit = 5

    # Get messages with date filter (last 24 hours)
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)

    result = await db.execute(
        select(Message)
        .where(
            Message.thread_id == thread_id,
            Message.created_at >= twenty_four_hours_ago,
        )
        .order_by(Message.created_at.asc())
        .limit(limit * 2)  # Load extra to account for user/assistant pairs
    )
    messages = list(result.scalars().all())

    # Get only the last N messages
    recent_messages = messages[-limit:] if len(messages) > limit else messages

    # Filter out messages that are themselves guard instructions (start with "[The image attached")
    # This prevents old guard instructions from being processed as if they were current context
    filtered_messages = [
        msg for msg in recent_messages
        if not msg.content.startswith("[The image attached")
    ]

    # Return as plain dicts - PydanticAI accepts this format
    # Includes attachments field to detect prior multimodal turns for history stubbing
    # Use filtered_messages (without guard instructions) to prevent old guard instructions from being processed
    return [
        {"role": msg.role, "content": msg.content, "attachments": msg.attachments}
        for msg in filtered_messages
    ]


async def update_thread_title(
    db: AsyncSession,
    thread_id: str,
    user_id: str,
    title: str,
) -> Optional[Thread]:
    """Update thread title (user-scoped)."""
    result = await db.execute(
        update(Thread)
        .where(Thread.id == thread_id, Thread.user_id == user_id)
        .values(title=title)
        .returning(Thread)
    )
    await db.commit()

    thread = result.scalar_one_or_none()
    if thread:
        logger.info({"event": "update_thread_title", "thread_id": thread_id, "title": title})
    return thread
