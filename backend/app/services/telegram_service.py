"""Telegram bot service for OCIN.

Uses python-telegram-bot (async v20+) with long-polling.
Users can list/switch agents via /agent, and all other messages
route to the currently selected agent via the agent runner.
"""
import asyncio
import base64
import logging
import re
from typing import Optional

import httpx
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.telegram import TelegramUser, TelegramThread
from app.models.agent import Agent
from app.services.run_service import create_run, update_run
from app.services.thread_service import create_thread
from app.schemas.run import RunCreate
from app.schemas.message import ChatAttachment

logger = logging.getLogger("ocin")

# MarkdownV2 special chars that must be escaped
_MD2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def escape_md2(text: str) -> str:
    """Escape text for Telegram MarkdownV2 format."""
    result = []
    for ch in text:
        if ch in _MD2_SPECIAL:
            result.append("\\")
        result.append(ch)
    return "".join(result)


def _truncate(text: str, max_len: int = 4096) -> str:
    """Truncate text to Telegram message limit."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n\n…[truncated]"


class TelegramService:
    """Encapsulates the Telegram bot lifecycle."""

    def __init__(self, token: str):
        self.token = token
        self.app: Optional[Application] = None
        self._batch_timers: dict[int, asyncio.Task] = {}
        self._batch_messages: dict[int, list] = {}  # tg_user_id -> [Update]

    async def start(self):
        """Build and start the bot with long-polling."""
        self.app = (
            Application.builder()
            .token(self.token)
            .build()
        )
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("agent", self._cmd_agent))
        # Photo, document, or text — everything else falls through
        self.app.add_handler(
            MessageHandler(
                filters.PHOTO | filters.Document.ALL | filters.TEXT & ~filters.COMMAND,
                self._handle_message,
            )
        )
        logger.info({"event": "telegram_start", "message": "Telegram bot starting (long-polling)"})
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

    async def stop(self):
        """Gracefully stop the bot."""
        if self.app:
            logger.info({"event": "telegram_stop", "message": "Telegram bot stopping"})
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    # ── Commands ──────────────────────────────────────────────

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        tg_user = update.effective_user
        if not tg_user:
            return
        async with AsyncSessionLocal() as db:
            ocin_user_id = await self._get_or_create_ocin_user(db, tg_user.id, tg_user.username)
            # Select first active agent as default
            await self._ensure_default_agent(db, tg_user.id, ocin_user_id)
            user_rec = await self._get_user_record(db, tg_user.id)
            agent_name = None
            if user_rec and user_rec.selected_agent_id:
                agent = await db.get(Agent, user_rec.selected_agent_id)
                agent_name = agent.name if agent else None

        welcome = (
            "👋 Welcome to OCIN Bot\!\n\n"
            f"Your active agent: *{escape_md2(agent_name or 'None')}*\n\n"
            "Use /agent to switch agents, then just type a message\."
        )
        await update.message.reply_text(welcome, parse_mode="MarkdownV2")

    async def _cmd_agent(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        tg_user = update.effective_user
        if not tg_user:
            return
        async with AsyncSessionLocal() as db:
            user_rec = await self._get_user_record(db, tg_user.id)
            if not user_rec:
                await update.message.reply_text("Please use /start first\.", parse_mode="MarkdownV2")
                return
            agents = await self._list_agents(db, user_rec.ocin_user_id)
            if not agents:
                await update.message.reply_text("No agents found\. Create one in the OCIN dashboard\.", parse_mode="MarkdownV2")
                return

            buttons = []
            for agent in agents:
                is_selected = user_rec.selected_agent_id == agent.id
                prefix = "✅ " if is_selected else ""
                buttons.append(
                    InlineKeyboardButton(
                        text=f"{prefix}{agent.name}",
                        callback_data=f"agent:{agent.id}",
                    )
                )
            markup = InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)])

        await update.message.reply_text("Select an agent:", reply_markup=markup)

    async def _on_agent_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callback for agent selection."""
        query = update.callback_query
        await query.answer()
        data = query.data
        if not data.startswith("agent:"):
            return

        agent_id = data.split(":", 1)[1]
        tg_user = query.from_user

        async with AsyncSessionLocal() as db:
            user_rec = await self._get_user_record(db, tg_user.id)
            if not user_rec:
                await query.edit_message_text("Please use /start first\.")
                return
            agent = await db.get(Agent, agent_id)
            if not agent or str(agent.user_id) != str(user_rec.ocin_user_id):
                await query.edit_message_text("Agent not found\.")
                return
            user_rec.selected_agent_id = agent.id
            await db.commit()

        await query.edit_message_text(
            f"✅ Switched to *{escape_md2(agent.name)}*\n\nSend a message to start chatting\.",
            parse_mode="MarkdownV2",
        )

    # ── Message handling with batching ────────────────────────

    async def _handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        tg_user = update.effective_user
        if not tg_user:
            return

        uid = tg_user.id
        self._batch_messages.setdefault(uid, []).append(update)

        # Cancel existing timer
        if uid in self._batch_timers:
            self._batch_timers[uid].cancel()

        # Set new 2-second batch timer
        self._batch_timers[uid] = asyncio.create_task(
            self._flush_batch(uid)
        )

    async def _flush_batch(self, tg_user_id: int):
        """Wait 2 seconds, then dispatch all batched messages."""
        await asyncio.sleep(2)
        updates = self._batch_messages.pop(tg_user_id, [])
        self._batch_timers.pop(tg_user_id, None)
        if not updates:
            return
        try:
            await self._dispatch_updates(tg_user_id, updates)
        except Exception as e:
            logger.error({"event": "telegram_dispatch_error", "error": str(e)})
            # Try to notify the user
            try:
                await updates[-1].message.reply_text(
                    f"❌ Error: {escape_md2(str(e)[:200])}",
                    parse_mode="MarkdownV2",
                )
            except Exception:
                pass

    async def _dispatch_updates(self, tg_user_id: int, updates: list):
        """Collect text + attachments from batched updates, then run agent."""
        async with AsyncSessionLocal() as db:
            user_rec = await self._get_user_record(db, tg_user_id)
            if not user_rec:
                msg = updates[0].message
                await msg.reply_text("Please use /start first\.", parse_mode="MarkdownV2")
                return

            if not user_rec.selected_agent_id:
                msg = updates[0].message
                await msg.reply_text("No agent selected\. Use /agent to pick one\.", parse_mode="MarkdownV2")
                return

            agent_id = str(user_rec.selected_agent_id)
            ocin_user_id = str(user_rec.ocin_user_id)

            # Get or create thread for this tg user + agent
            thread_id = await self._get_or_create_thread(db, tg_user_id, agent_id)

        # Collect text parts and attachments from all updates
        text_parts = []
        attachments: list[ChatAttachment] = []
        reply_to_msg = updates[0].message  # for sending the response

        for upd in updates:
            msg = upd.message
            if msg.photo:
                # Get highest resolution photo
                photo = msg.photo[-1]
                file = await upd.get_bot().get_file(photo.file_id)
                data = await file.download_as_bytearray()
                b64 = base64.b64encode(data).decode()
                caption = msg.caption or ""
                if caption:
                    text_parts.append(caption)
                attachments.append(
                    ChatAttachment(
                        name=f"photo_{photo.file_unique_id[:8]}.jpg",
                        type="image/jpeg",
                        data_base64=b64,
                    )
                )
            elif msg.document:
                file = await upd.get_bot().get_file(msg.document.file_id)
                data = await file.download_as_bytearray()
                b64 = base64.b64encode(data).decode()
                caption = msg.caption or ""
                if caption:
                    text_parts.append(caption)
                attachments.append(
                    ChatAttachment(
                        name=msg.document.file_name or f"doc_{msg.document.file_unique_id[:8]}",
                        type=msg.document.mime_type or "application/octet-stream",
                        data_base64=b64,
                    )
                )
            elif msg.text:
                text_parts.append(msg.text)

        input_text = "\n".join(text_parts) if text_parts else "(media)"
        input_text = _truncate(input_text, 10000)

        # Send typing indicator
        await reply_to_msg.chat.send_action("typing")

        # Create run and execute
        import redis as sync_redis
        redis_client = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
        from redis.asyncio import Redis as AsyncRedis
        async_redis = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)

        from app.schemas.run import RunCreate
        run_data = RunCreate(
            user_id=ocin_user_id,
            agent_id=agent_id,
            input=input_text,
            status="pending",
        )

        async with AsyncSessionLocal() as db:
            run = await create_run(db, run_data)
            run_id = str(run.id)

        try:
            from app.services.agent_runner import run_agent
            output = await run_agent(
                run_id=run_id,
                agent_id=agent_id,
                user_id=ocin_user_id,
                input_text=input_text,
                db=db,
                redis=async_redis,
                thread_id=str(thread_id),
                attachments=attachments if attachments else None,
            )
        except Exception as e:
            logger.error({"event": "telegram_agent_error", "error": str(e)})
            await reply_to_msg.reply_text(
                f"❌ Agent error: {escape_md2(str(e)[:300])}",
                parse_mode="MarkdownV2",
            )
            return

        if output:
            # Split long messages at 4096 chars (Telegram limit)
            chunks = _split_message(output, 4096)
            for chunk in chunks:
                try:
                    await reply_to_msg.reply_text(chunk, parse_mode="MarkdownV2")
                except Exception:
                    # Fallback: send without formatting
                    await reply_to_msg.reply_text(chunk)

    # ── Helpers ───────────────────────────────────────────────

    async def _get_or_create_ocin_user(self, db, tg_user_id: int, username: Optional[str]) -> str:
        """Get existing OCIN user for this Telegram user, or create one."""
        from app.models.user import User
        from sqlalchemy import select

        # Check if already linked
        result = await db.execute(
            select(TelegramUser).where(TelegramUser.telegram_user_id == str(tg_user_id))
        )
        rec = result.scalar_one_or_none()
        if rec:
            return str(rec.ocin_user_id)

        # Find or create OCIN user by email (telegram_{tg_id}@ocin.site)
        email = f"telegram_{tg_user_id}@ocin.site"
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            from passlib.hash import bcrypt
            user = User(
                email=email,
                hashed_password=bcrypt.hash("unused_telegram_user"),
                is_active=True,
            )
            db.add(user)
            await db.flush()

        # Create telegram user link
        rec = TelegramUser(
            telegram_user_id=str(tg_user_id),
            ocin_user_id=user.id,
        )
        db.add(rec)
        await db.commit()
        return str(user.id)

    async def _get_user_record(self, db, tg_user_id: int) -> Optional[TelegramUser]:
        from sqlalchemy import select
        result = await db.execute(
            select(TelegramUser).where(TelegramUser.telegram_user_id == str(tg_user_id))
        )
        return result.scalar_one_or_none()

    async def _ensure_default_agent(self, db, tg_user_id: int, ocin_user_id: str):
        """Set the first active agent as default if none selected."""
        rec = await self._get_user_record(db, tg_user_id)
        if rec and rec.selected_agent_id:
            return
        agents = await self._list_agents(db, ocin_user_id)
        if agents:
            if not rec:
                rec = TelegramUser(
                    telegram_user_id=str(tg_user_id),
                    ocin_user_id=agents[0].user_id,
                )
                db.add(rec)
            rec.selected_agent_id = agents[0].id
            await db.commit()

    async def _list_agents(self, db, ocin_user_id: str) -> list[Agent]:
        from sqlalchemy import select
        result = await db.execute(
            select(Agent).where(
                Agent.user_id == ocin_user_id,
                Agent.is_active == True,
            ).order_by(Agent.created_at)
        )
        return list(result.scalars().all())

    async def _get_or_create_thread(self, db, tg_user_id: int, agent_id: str) -> str:
        from sqlalchemy import select
        result = await db.execute(
            select(TelegramThread).where(
                TelegramThread.telegram_user_id == str(tg_user_id),
                TelegramThread.agent_id == agent_id,
            )
        )
        rec = result.scalar_one_or_none()
        if rec:
            return str(rec.thread_id)

        # Get ocin_user_id
        user_rec = await self._get_user_record(db, tg_user_id)
        if not user_rec:
            raise ValueError("Telegram user not registered")

        thread = await create_thread(db, str(user_rec.ocin_user_id), agent_id, title="Telegram Chat")
        rec = TelegramThread(
            telegram_user_id=str(tg_user_id),
            agent_id=agent_id,
            thread_id=thread.id,
        )
        db.add(rec)
        await db.commit()
        return str(thread.id)


def _split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split a message into chunks that fit within Telegram limits."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ── Singleton lifecycle ─────────────────────────────────────

_service: Optional[TelegramService] = None


async def start_telegram_service():
    """Called from FastAPI lifespan startup."""
    global _service
    token = settings.TELEGRAM_BOT_TOKEN if hasattr(settings, "TELEGRAM_BOT_TOKEN") else ""
    if not token:
        logger.warning({"event": "telegram_skip", "message": "TELEGRAM_BOT_TOKEN not set, skipping"})
        return
    _service = TelegramService(token)
    # Register callback handler after init
    _service.app.add_handler(
        # CallbackQueryHandler needs to be imported
        # We'll add it in start() instead — register here
    )
    await _service.start()

    _service.app.add_handler(CallbackQueryHandler(_service._on_agent_callback))
    logger.info({"event": "telegram_started", "message": "Telegram bot is running"})


async def stop_telegram_service():
    """Called from FastAPI lifespan shutdown."""
    global _service
    if _service:
        await _service.stop()
        _service = None
