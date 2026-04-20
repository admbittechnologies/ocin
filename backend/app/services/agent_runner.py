import logging
import time
import os
import re
import functools
from datetime import datetime
from typing import Any
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis
from pydantic_ai import Agent as PydanticAgent
from pydantic import BaseModel as PydanticBaseModel
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart

from app.models.run import Run
from app.models.agent import Agent as AgentModel
from app.models.tool import Tool
from app.services.tool_loader import build_tools_for_agent
from app.services.run_service import update_run, create_run
from app.services.thread_service import save_messages, get_thread_messages_for_context
from app.services.memory_extraction import extract_and_save_memory, format_memory_context
from app.services.approval_service import create_approval
from app.services.agent_service import is_vision_capable
from app.core.exceptions import ToolUnavailableException
from app.config import settings
from app.core.attachments import build_multimodal_input
from app.schemas.message import ChatAttachment
from app.core.errors import parse_llm_provider_error
from app.integrations.self_tools import (
    set_self_call_context, clear_self_call_context, get_self_tools,
    ApprovalRequestedError
)

logger = logging.getLogger("ocin")
BaseModel = PydanticBaseModel


def estimate_tokens(messages: list) -> int:
    """Rough token estimate: ~4 chars per token."""
    total_chars = sum(len(str(m)) for m in messages)
    return total_chars // 4


def convert_to_pydantic_messages(raw_messages: list) -> list[ModelRequest | ModelResponse]:
    """Convert plain dict messages to PydanticAI ModelMessage objects.

    PydanticAI's message_history parameter expects a sequence of ModelRequest
    and ModelResponse objects, not plain dicts. This function handles the conversion.

    Args:
        raw_messages: List of dicts with 'role' and 'content' keys

    Returns:
        List of ModelRequest (for user messages) or ModelResponse (for assistant messages)
    """
    result = []
    for msg in raw_messages:
        # Handle both dict and object types
        if isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
        else:
            role = getattr(msg, "role", None)
            content = getattr(msg, "content", None)

        if not content or not isinstance(content, str):
            continue

        if role == "user":
            result.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            result.append(ModelResponse(parts=[TextPart(content=content)]))

    return result


def extract_tool_results(all_messages: list) -> str:
    """
    Extract tool call results from PydanticAI message history.
    Returns a compact summary to append to the assistant message
    so future context includes what tools actually returned.
    """
    tool_summaries = []
    try:
        for msg in all_messages:
            parts = getattr(msg, 'parts', [])
            for part in parts:
                part_type = type(part).__name__
                # ToolReturnPart contains what the tool returned
                if 'ToolReturn' in part_type or 'tool_return' in part_type.lower():
                    content = getattr(part, 'content', '')
                    tool_name = getattr(part, 'tool_name', '')
                    if content and len(str(content)) < 300:
                        tool_summaries.append(f"[{tool_name}: {content}]")
    except Exception as e:
        logger.debug({"event": "extract_tool_results_failed", "error": str(e)})
    return ' '.join(tool_summaries)


def wrap_tool_with_progress(tool_fn, redis_client, stream_key):
    """Wrap a tool function to emit progress updates via Redis."""
    @functools.wraps(tool_fn)
    async def wrapped(*args, **kwargs):
        tool_name = getattr(tool_fn, "__name__", str(tool_fn))

        # Progress messages for different tools
        progress_messages = {
            "google_sheet_create_spreadsheet": "📊 Creating Google Sheet...",
            "google_sheet_append_rows": "✍️ Adding rows to spreadsheet...",
            "google_sheet_get_values": "📖 Reading spreadsheet data...",
            "google_sheet_update_values": "✏️ Updating spreadsheet...",
            "google_sheet_get_spreadsheet": "🔍 Fetching spreadsheet info...",
            "slack_send_message": "💬 Sending Slack message...",
            "slack_list_channels": "📋 Fetching Slack channels...",
            "hubspot_create_contact": "👤 Creating HubSpot contact...",
            "hubspot_create_company": "🏢 Creating HubSpot company...",
            "hubspot_search_contacts": "🔍 Searching HubSpot contacts...",
            "hubspot_create_deal": "💼 Creating HubSpot deal...",
            "gmail_send_email": "📧 Sending email...",
            "gmail_list_emails": "📬 Fetching emails...",
        }
        start_msg = progress_messages.get(tool_name, f"⚙️ Running {tool_name}...")

        # Emit "working on it" message
        await redis_client.publish(stream_key, json.dumps({
            "type": "progress",
            "message": start_msg,
        }))

        # Execute the actual tool
        result = await tool_fn(*args, **kwargs)

        # Emit completion message with result preview
        completion_msg = None
        if isinstance(result, str):
            if "docs.google.com/spreadsheets" in result:
                # Extract URL from result
                urls = re.findall(r'https://docs\.google\.com/spreadsheets/d/[^\s"]+', result)
                if urls:
                    completion_msg = f"✅ Spreadsheet ready: {urls[0]}"
            elif "Updated" in result or "Appended" in result:
                completion_msg = f"✅ {result}"
            elif "Sent" in result or "sent" in result:
                completion_msg = f"✅ {result}"
            elif "Created" in result or "created" in result:
                completion_msg = f"✅ {result}"
            elif "Found" in result or "fetched" in result.lower():
                completion_msg = f"✅ {result}"

        if completion_msg:
            await redis_client.publish(stream_key, json.dumps({
                "type": "progress",
                "message": completion_msg,
            }))

        return result

    return wrapped


# Global prefix for all agents' system prompts
GLOBAL_PREFIX = """You are a proactive AI assistant. Follow these rules strictly:

1. ALWAYS use your tools immediately when asked — never ask for confirmation
   unless a critical piece of information is genuinely missing
2. NEVER ask what the user wants — they already told you, just do it
3. When a tool call fails, try a different approach before giving up
4. Remember everything in this conversation — do not ask for information
   already provided earlier in the chat
5. When using Maton tools, just call them directly with reasonable parameters
6. Confirm what you did after completing an action, briefly and clearly
   Respond in the SAME LANGUAGE as the user's input whenever possible.
7. Each request is independent — always execute fresh and report actual results
8. After EVERY tool action that creates or retrieves a resource, your response
   MUST include the complete details on a new line:
   - Spreadsheets: full URL and spreadsheet ID
   - Contacts/companies: record ID and name
   - Any resource: its ID and direct access link
   Format: "✅ Done. Access it here: [URL]" (or equivalent emoji/phrase in user's language)
   Never omit the URL or ID — users need them to access what you created.
9. After creating any resource via tools, immediately call set_memory to save
   key details so you can reference them later:
   - Spreadsheet: set_memory(key="{title}_url", value="{spreadsheetUrl}")
                 set_memory(key="{title}_id", value="{spreadsheetId}")
   - Contact: set_memory(key="contact_{email}", value="{contactId}")
   - Any resource: set_memory(key="{descriptive_name}", value="{id_or_url}")
10. BEFORE executing any action that could have significant consequences,
    you MUST call request_approval with:
    - kind: Type of action (e.g., "send_message", "delete_data", "modify_data")
    - title: Short description of what you want to do
    - description: Detailed explanation of why and what will happen
    - payload: Relevant details (optional)

    Actions requiring approval:
    - Sending messages to users (email, Slack, etc.)
    - Deleting or modifying important data
    - Making purchases or financial transactions
    - Any action with irreversible consequences

    Actions NOT requiring approval (just do them):
    - Creating spreadsheets, documents, contacts
    - Reading/retrieving data
    - Standard data operations
    - Scheduling tasks
    - Setting memory

## Memory guidelines
- Save a memory when user states a lasting fact about themselves, their preferences, or their work.
- Do NOT save transient chat content, greetings, or single-use questions.
- Use dotted key notation: "preferences.timezone", "work.company", "personal.name".
- Before saving, check if key already exists (call memory_get first). Update rather than create duplicates.
- You can reference saved memories naturally in conversation without mentioning the memory system explicitly.
"""

# Result type for agent runs (PydanticAI expects a typed result)
class AgentResult(BaseModel):
    """Typed result for agent execution."""
    output: str
    tool_calls: list[dict] = []


async def run_agent(
    run_id: str,
    agent_id: str,
    user_id: str,
    input_text: str,
    db: AsyncSession,
    redis: Redis,
    model_api_keys: dict[str, str] | None = None,
    thread_id: str | None = None,
    jwt_token: str | None = None,
    api_base: str = "http://localhost:8000",
    parent_run_id: str | None = None,
    attachments: list[ChatAttachment] | None = None,
) -> str | None:
    """
    Execute an agent run and stream output to Redis.

    Args:
        run_id: The run ID
        agent_id: The agent ID
        user_id: The user ID
        input_text: The user input to process
        db: Database session
        redis: Redis client for streaming
        model_api_keys: Optional dict of model-specific API keys
        thread_id: Optional thread ID for chat history and message saving
        jwt_token: Optional JWT token for self-call tools
        api_base: Base URL for self-call API requests
        attachments: Optional list of ChatAttachment objects for image support

    Returns:
        The output text if successful, None otherwise
    """
    # TRACE: Executor entry - first line inside function
    logger.info({
        "event": "attachment_trace",
        "checkpoint": "executor_entry",
        "count": len(attachments) if attachments and isinstance(attachments, list) else 0,
        "param_name": "attachments",
        "attachments_type": type(attachments).__name__ if attachments else "None",
    })

    start_time = time.time()
    stream_key = f"ocin:run:{run_id}:stream"
    tools_data = {"clients": []}  # Initialize before try block for finally block access
    output_text = None

    # Set self-call context if JWT token is provided
    if jwt_token:
        set_self_call_context(jwt_token, user_id, api_base)
        logger.debug({"event": "set_self_call_context", "user_id": user_id})

    async def stream_progress(message: str):
        """Stream a progress update to the user in real time."""
        await redis.rpush(stream_key, json.dumps({
            "type": "progress",
            "message": message,
        }))
        await redis.expire(stream_key, 600)

    async def stream_token(token: str):
        """Stream a single token to Redis."""
        await redis.rpush(stream_key, json.dumps({"type": "token", "token": token}))
        await redis.expire(stream_key, 600)
        logger.info({"event": "sse_publish_token", "run_id": run_id, "token_preview": token[:50], "token_length": len(token)})

    async def stream_message(message: dict):
        """Stream a JSON message to Redis."""
        await redis.rpush(stream_key, json.dumps(message))
        await redis.expire(stream_key, 600)
        logger.info({"event": "sse_publish_message", "run_id": run_id, "message_type": message.get("type"), "message": message})

    saved_env_vars = {}  # Track which env vars we modified
    try:
        # Load agent from DB
        result = await db.execute(
            select(AgentModel).where(AgentModel.id == agent_id, AgentModel.user_id == user_id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Check vision capability if attachments are present
        has_attachments = attachments is not None and len(attachments) > 0
        if has_attachments:
            vision_capable = is_vision_capable(agent.model_provider, agent.model_id)
            if not vision_capable:
                # Finish run with error for non-vision models
                error_msg = "This agent's model does not support images. Switch to a vision-capable model (Claude Sonnet, GPT-4o, or Gemini) to use image attachments."

                # Update run status to failed with the error
                await update_run(
                    db,
                    run_id,
                    status="failed",
                    error=error_msg,
                    finished_at=datetime.utcnow(),
                )

                # Stream the error message as if it came from the assistant
                stream_key = f"ocin:run:{run_id}:stream"
                await redis.rpush(stream_key, json.dumps({
                    "type": "token",
                    "token": error_msg,
                }))
                await redis.expire(stream_key, 600)

                await redis.rpush(stream_key, json.dumps({
                    "type": "done",
                    "run_id": run_id,
                    "status": "failed",
                }))
                await redis.expire(stream_key, 600)

                # Cache the error as output
                await redis.setex(
                    f"ocin:run:{run_id}:output",
                    300,
                    json.dumps({"type": "done", "output": error_msg, "run_id": run_id})
                )

                logger.info({
                    "event": "vision_capability_check_failed",
                    "run_id": run_id,
                    "model_provider": agent.model_provider,
                    "model_id": agent.model_id,
                    "error": "Model does not support vision",
                })

                return None

        # Mark run as running and set started_at
        await update_run(
            db,
            run_id,
            status="running",
            started_at=datetime.utcnow(),
        )

        # Fetch user's API keys from database for this agent's provider
        provider_normalized = agent.model_provider.lower()
        result_keys = await db.execute(
            select(Tool).where(
                Tool.user_id == user_id,
                Tool.source == "api_key",
                Tool.source_key == provider_normalized,
                Tool.is_active == True,
            )
        )
        api_keys_from_db = {tool.source_key: tool.config.get("api_key") for tool in result_keys.scalars().all()}

        # Build tool list
        logger.info({"event": "run_agent", "run_id": run_id, "agent_id": agent_id, "status": "building_tools"})
        tools_data = await build_tools_for_agent(agent, db)
        tools = list(tools_data["tools"])  # Regular function tools
        mcp_servers = list(tools_data.get("mcp_servers", []))  # MCP server instances

        # Wrap Maton tools with progress streaming
        wrapped_tools = []
        for tool in tools:
            tool_name = getattr(tool, "__name__", "")
            if tool_name.startswith("google_sheet_") or \
               tool_name.startswith("slack_") or \
               tool_name.startswith("hubspot_") or \
               tool_name.startswith("gmail_"):
                wrapped_tools.append(wrap_tool_with_progress(tool, redis, stream_key))
            else:
                wrapped_tools.append(tool)
        tools = wrapped_tools

        # Add self-call tools if JWT token is provided
        if jwt_token:
            self_tools = get_self_tools()
            tools.extend(self_tools)
            logger.info({"event": "self_tools_added", "count": len(self_tools)})

        # Load message history if thread_id is provided
        message_history = []
        filtered_history: list[dict] = []  # Initialize for all code paths (resumed runs may skip the thread_id block)
        if thread_id:
            raw_history = await get_thread_messages_for_context(
                db, thread_id, user_id, limit=20
            )

            # Separate conversational messages from tool result messages
            conversational = []
            for msg in raw_history:
                content = str(msg).lower()
                # Keep messages that are conversational context
                # Skip messages that are just tool execution reports
                is_tool_noise = any(phrase in content for phrase in [
                    "spreadsheetid",
                    "docs.google.com/spreadsheets",
                    "maton_gateway",
                    "tool call",
                ])
                if not is_tool_noise:
                    conversational.append(msg)

            # Detect if current turn is multimodal (has attachments)
            is_multimodal_turn = attachments and isinstance(attachments, list) and len(attachments) > 0

            # If history is long, handle based on turn type
            if len(conversational) > 10:
                if is_multimodal_turn:
                    # For multimodal turns, skip summarization and stub prior attachment turns
                    # Keep last 4 messages but stub any that had attachments
                    recent = conversational[-4:]

                    # Stub prior attachment turns to prevent model confusion
                    stubbed_history = []
                    prior_attachment_turns = 0

                    i = 0
                    while i < len(recent):
                        msg = recent[i]

                        # Check if this message (prior turn) had attachments
                        if isinstance(msg, dict) and msg.get("attachments"):
                            prior_attachment_turns += 1
                            # Stub user message (prior turn had image)
                            stubbed_history.append({
                                "role": "user",
                                "content": "[Past turn: user sent an image (image/png). Image bytes are no longer in context.]"
                            })

                            # Stub the immediately-following assistant message too (if it exists)
                            if i + 1 < len(recent):
                                next_msg = recent[i + 1]
                                if isinstance(next_msg, dict) and next_msg.get("role") == "assistant":
                                    stubbed_history.append({
                                        "role": "assistant",
                                        "content": "[Past turn: assistant described an image which is no longer visible. The current turn's image is unrelated.]"
                                    })
                                    i += 1  # Skip the assistant message we just stubbed
                        else:
                            # No attachments - keep as-is
                            stubbed_history.append(msg)

                        i += 1

                    message_history = stubbed_history

                    logger.info({
                        "event": "history_strategy_chosen",
                        "run_id": run_id,
                        "multimodal_turn": True,
                        "strategy": "raw_recent",
                        "raw_count": len(raw_history),
                        "used_count": len(message_history),
                    })

                    # Log stubbed turns
                    if prior_attachment_turns > 0:
                        logger.info({
                            "event": "history_turn_stubbed",
                            "run_id": run_id,
                            "prior_attachment_turns": prior_attachment_turns,
                        })
                else:
                    # For text-only turns, summarize older messages (existing behavior)
                    recent = conversational[-6:]
                    older_count = len(conversational) - 6
                    # Build a summary placeholder
                    summary = {
                        "role": "user",
                        "content": f"[Context summary: This conversation has {older_count} earlier messages. The user has been working with this agent on various tasks.]"
                    }
                    message_history = [summary] + recent
                    logger.info({
                        "event": "history_strategy_chosen",
                        "run_id": run_id,
                        "multimodal_turn": False,
                        "strategy": "summarized",
                        "raw_count": len(raw_history),
                        "used_count": len(message_history),
                    })
            else:
                message_history = conversational
                if len(raw_history) > 0:
                    logger.info({
                        "event": "history_strategy_chosen",
                        "run_id": run_id,
                        "multimodal_turn": is_multimodal_turn,
                        "strategy": "raw_all",
                        "raw_count": len(raw_history),
                        "used_count": len(message_history),
                    })

            # Add multimodal isolation guard to current user prompt if there are prior multimodal turns (with images)
            # Only apply guard when previous turns had text content AND image attachments (indicates prior multimodal turns)
            # Filter out guard instruction messages from history to prevent them from being processed as context
            prior_multimodal_turns = [
                msg for msg in message_history[:-1]
                if isinstance(msg, dict) and
                   msg.get("role") == "user" and
                   msg.get("attachments") and
                   msg.get("content", "").strip() and
                   not msg.get("content", "").startswith("[The image attached")
            ]

            if is_multimodal_turn and prior_multimodal_turns:
                # Modify input_text to include guard instruction
                guard_instruction = "\n\n[The image attached to this message is the ONLY image you can currently see. Any images from earlier in this conversation are no longer available. Describe ONLY what is in the current attached image.]\n\n"
                input_text = guard_instruction + input_text

                logger.info({
                    "event": "multimodal_isolation_guard_applied",
                    "run_id": run_id,
                    "prior_attachment_turns": sum(
                        1 for msg in message_history[:-1]
                        if isinstance(msg, dict) and msg.get("attachments")
                    ),
                })

            # Token budget calculation: reserve space for current turn first
            # For multimodal turns, images consume significant tokens (~1500 per image)
            # We MUST calculate budget BEFORE truncation to avoid dropping current turn
            CONTEXT_WINDOW_TOKENS = 200000  # 200K token budget (Claude Sonnet 4.6)
            MAX_HISTORY_TOKENS = 8000  # Reserve 8K for history

            # Calculate current turn's token cost
            current_turn_text_tokens = estimate_tokens([input_text])
            current_turn_image_tokens = 0
            if is_multimodal_turn and attachments:
                # Estimate image tokens (conservative: ~1500 per image for Anthropic)
                current_turn_image_tokens = sum(1500 for _ in attachments)

            # Guard text tokens
            guard_text_tokens = estimate_tokens(["\n\n[The image attached to this message is the ONLY image you can currently see. Any images from earlier in this conversation are no longer available. Describe ONLY what is in the current attached image.]\n\n"])

            # System prompt tokens (estimate 4K)
            system_prompt_tokens = 4000

            # Total reserved for current turn
            total_current_turn_tokens = current_turn_text_tokens + current_turn_image_tokens + guard_text_tokens + system_prompt_tokens

            # Remaining budget for history
            history_budget = CONTEXT_WINDOW_TOKENS - total_current_turn_tokens

            # Truncate history to fit budget ONLY (never touch current turn's input)
            original_history_count = len(message_history)
            dropped_messages = []

            if estimate_tokens(message_history) > history_budget:
                # Truncate from oldest first until it fits
                temp_history = list(message_history)  # Make mutable copy
                while temp_history and estimate_tokens(temp_history) > history_budget:
                    # Drop the oldest message
                    dropped_msg = temp_history.pop(0)
                    dropped_messages.append(dropped_msg)

                message_history = temp_history

                # Log dropped messages
                if dropped_messages:
                    for i, dropped_msg in enumerate(dropped_messages):
                        msg_id = getattr(dropped_msg, 'id', 'unknown')
                        estimated_tokens = estimate_tokens([dropped_msg.get('content', '')])
                        logger.info({
                            "event": "history_turn_dropped",
                            "run_id": run_id,
                            "message_id": msg_id,
                            "reason": "token_budget",
                            "estimated_tokens": estimated_tokens,
                        })

            # Log token budget calculation
            logger.info({
                "event": "token_budget_calculation",
                "run_id": run_id,
                "model_id": f"{agent.model_provider}:{agent.model_id}",
                "context_window_tokens": CONTEXT_WINDOW_TOKENS,
                "current_turn_text_tokens": current_turn_text_tokens,
                "current_turn_image_tokens": current_turn_image_tokens,
                "guard_text_tokens": guard_text_tokens,
                "system_prompt_tokens": system_prompt_tokens,
                "total_current_turn_tokens": total_current_turn_tokens,
                "history_budget_remaining": history_budget,
                "history_actual_tokens": estimate_tokens(message_history),
                "history_count_before_truncation": original_history_count,
                "history_count_after_truncation": len(message_history),
                "messages_dropped": len(dropped_messages),
            })

            # Log current turn kept intact
            if is_multimodal_turn and attachments:
                logger.info({
                    "event": "current_turn_kept_intact",
                    "run_id": run_id,
                    "attachment_count": len(attachments),
                    "total_attachment_tokens": current_turn_image_tokens,
                })

            logger.info({
                "event": "history_loaded",
                "run_id": run_id,
                "thread_id": thread_id,
                "raw_count": len(raw_history),
                "used_count": len(message_history),
            })

            # Defensive filtering: Remove poisoned assistant messages from history
            # Filter out any assistant messages containing vision-denial phrases
            VISION_DENIAL_PHRASES = [
                "i don't see any picture", "i cannot see", "i can't see",
                "no picture attached", "no image attached", "unable to view images",
                "i'm unable to view", "i don't have access to", "i can only see",
            ]
            filtered_history = []
            dropped_poisoned_count = 0

            for msg in message_history:
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    content_lower = msg.get("content", "").lower()
                    if any(phrase in content_lower for phrase in VISION_DENIAL_PHRASES):
                        logger.info({
                            "event": "poisoned_history_message_dropped",
                            "run_id": run_id,
                            "matched_phrase": next(p for p in VISION_DENIAL_PHRASES if p in content_lower),
                        })
                        dropped_poisoned_count += 1
                    else:
                        filtered_history.append(msg)
                else:
                    filtered_history.append(msg)

            if dropped_poisoned_count > 0:
                logger.info({
                    "event": "poisoned_history_summary",
                    "run_id": run_id,
                    "messages_dropped": dropped_poisoned_count,
                })

            message_history = filtered_history

            # Ensure history starts with user message (not ModelResponse)
            # If history is empty, create a placeholder user message to avoid ModelResponse first
            if not message_history:
                message_history = [{"role": "user", "content": "Starting a new conversation."}]
                logger.info({
                    "event": "history_leading_assistant_trimmed",
                    "run_id": run_id,
                    "reason": "empty_history_after_filtering",
                })

            # Get memory context and inject into system prompt
        memory_context = await format_memory_context(db, agent_id)

        # Build agent identity block — tells LLM who it is, what it does,
        # and what role it plays. This goes BEFORE global prefix so that
        # identity is the strongest signal in the context.
        identity_lines = [f"You are {agent.name}, an AI agent."]
        if agent.description and agent.description.strip():
            identity_lines.append(f"Your purpose: {agent.description.strip()}")
        role_descriptions = {
            "standalone": "You operate independently and handle user requests end-to-end.",
            "coordinator": "You are a coordinator agent. You delegate work to worker agents when appropriate, using list_agents and trigger_run tools.",
            "worker": "You are a worker agent. You handle specific tasks delegated to you and report results clearly.",
        }
        if agent.role in role_descriptions:
            identity_lines.append(role_descriptions[agent.role])

        identity_block = "## Your identity\n" + "\n".join(identity_lines)

        # User-defined system prompt (the "instructions" field user typed in
        # Edit Agent dialog)
        user_instructions = agent.system_prompt or ""
        if user_instructions.strip():
            user_instructions_block = f"## Your instructions\n{user_instructions.strip()}"
        else:
            user_instructions_block = ""

        # Assemble: identity → user instructions → global rules
        system_prompt_parts = [identity_block]
        if user_instructions_block:
            system_prompt_parts.append(user_instructions_block)
        system_prompt_parts.append(GLOBAL_PREFIX)
        system_prompt = "\n\n".join(system_prompt_parts)

        # Append memory context (agent-scoped only)
        if memory_context:
            system_prompt = f"{system_prompt}\n\n{memory_context}"
            logger.debug({"event": "run_agent", "agent_id": agent_id, "has_agent_memory": True})

        from app.services.approval_service import get_approval, list_approvals
        pending_approvals = []
        if parent_run_id:
            # Check if this run has any unapproved approvals
            result = await list_approvals(
                db=db,
                user_id=user_id,
                status="pending",
                limit=100,
            )
            for approval in result:
                if approval.run_id == parent_run_id:
                    pending_approvals.append(approval)
                    logger.info({
                        "event": "pending_approval_found",
                        "approval_id": str(approval.id),
                        "parent_run_id": parent_run_id,
                    })
        elif run_id:
            # Check for approvals requested by this run
            result = await list_approvals(
                db=db,
                user_id=user_id,
                status="pending",
                limit=100,
            )
            for approval in result:
                if approval.run_id == run_id:
                    pending_approvals.append(approval)
                    logger.info({
                        "event": "run_pending_approval_found",
                        "approval_id": str(approval.id),
                        "run_id": run_id,
                    })
                    break  # No need to check more if we found one

        # If there are pending approvals, pause execution
        if pending_approvals:
            await update_run(
                db=db,
                run_id=run_id,
                status="awaiting_approval",
            )
            logger.info({
                "event": "run_paused_for_approval",
                "run_id": run_id,
                "approval_count": len(pending_approvals),
            })

        # Load user's configured external tools for context
        external_tools_result = await db.execute(
            select(Tool).where(
                Tool.user_id == user_id,
                Tool.source.in_(['composio', 'apify', 'maton']),
                Tool.is_active == True,
            )
        )
        external_tools = external_tools_result.scalars().all()

        if external_tools:
            tool_context = "\n\n## Your configured external tools:\n"
            for tool in external_tools:
                if tool.source == 'maton':
                    app_name = tool.config.get("app", "google-sheet")
                    # Maton gateway tools use underscore format (e.g., google_sheet_create_spreadsheet)
                    # These are async Python functions that call Maton's gateway HTTP API directly
                    # No check_connection workflow needed - gateway tools can be called immediately
                    if app_name in ("google-sheet", "google-sheets"):
                        tool_context += (
                            "- Google Sheets (Maton): "
                            "google_sheet_create_spreadsheet(title), "
                            "google_sheet_append_rows(spreadsheet_id, values, range), "
                            "google_sheet_get_values(spreadsheet_id, range), "
                            "google_sheet_update_values(spreadsheet_id, range, values), "
                            "google_sheet_get_spreadsheet(spreadsheet_id).\n"
                            "  WORKFLOW: After create_spreadsheet succeeds:\n"
                            "  1. Call set_memory(key='{title}_url', value=spreadsheetUrl)\n"
                            "  2. Call set_memory(key='{title}_id', value=spreadsheetId)\n"
                            "  3. Include the URL in your response text\n"
                            "  Default sheet name is 'Hoja 1' (Spanish locale).\n"
                        )
                    else:
                        tool_context += (
                            f"- Google Sheets (Maton): google_sheet_create_spreadsheet(title), "
                            f"google_sheet_append_rows(spreadsheet_id, range, values), "
                            f"google_sheet_get_values(spreadsheet_id, range), "
                            f"google_sheet_update_values(spreadsheet_id, range, values), "
                            f"google_sheet_get_spreadsheet(spreadsheet_id).\n"
                            f"NOTE: Default range for appending is 'Hoja 1!A1' (Spanish locale), not 'Sheet1!A1'. "
                            f"Workflow: 1) create_spreadsheet, 2) append_rows with range='Hoja 1!A1'.\n"
                        )
                elif tool.source == 'composio':
                    toolkits = tool.config.get("toolkits", [])
                    if toolkits:
                        toolkit_names = ", ".join(toolkits[:3])
                        if len(toolkits) > 3:
                            toolkit_names += f", and {len(toolkits) - 3} more"
                        tool_context += f"- Composio: Access {toolkit_names} tools. Use the appropriate tools for each service.\n"
                    else:
                        tool_context += f"- Composio: Access your connected business tools. Search and use the available tools dynamically.\n"
                elif tool.source == 'apify':
                    tools_config = tool.config.get("tools", "")
                    tool_context += f"- Apify: Web scraping and data extraction. Use apify_* tools like search-actors, call-actor, and apify-slash-rag-web-browser for web browsing.\n"
            system_prompt += tool_context
            logger.debug({"event": "external_tools_context", "count": len(external_tools)})

        # List the agent's actually-granted tools by name so LLM knows
        # what's in its toolbox without having to discover them.
        if tools:
            granted_tool_names = []
            for t in tools:
                name = getattr(t, "__name__", None) or getattr(t, "name", None) or str(t)
                if name and name not in granted_tool_names:
                    granted_tool_names.append(name)
            if granted_tool_names:
                system_prompt += "\n\n## Your available tools\n"
                system_prompt += "You have access to these tools — use them when relevant:\n"
                for name in granted_tool_names:
                    system_prompt += f"- {name}\n"

        # Add self-call capabilities context
        system_prompt += """

## IMPORTANT — How to behave:
- When a user asks you to DO something (send a message, trigger a workflow,
  create a schedule, save a memory), USE THE TOOL IMMEDIATELY. Do not ask
  for confirmation unless critical information is missing.
- When a user mentions "maton", "maton.ai", "workflow", or any variation,
  call trigger_maton_workflow directly.
- When a user asks you to remember something, call set_memory immediately.
- When a user asks to schedule something, call create_schedule immediately.
- Integration setup: ALWAYS call resolve_integration before creating or configuring
  any Maton/Composio/Apify integration. Show the confirmation_message
  to the user and wait for their confirmation before proceeding. If confidence is "low",
  show the clarification_message instead and wait for the user to clarify.
- You have the following platform capabilities — use them proactively:
  - Schedules: create_schedule, list_schedules, pause_schedule, resume_schedule, delete_schedule
  - Memory: get_memory, set_memory, delete_memory
  - Runs: trigger_run, get_run_status, list_runs
  - Threads: list_threads, get_thread_messages
  - Agents: list_agents, get_agent_by_name, get_agent
  - Integration Setup: resolve_integration
"""
        logger.debug({"event": "self_call_context_added"})

        # Emit "thinking" indicator
        await stream_progress("🤔 Thinking...")

        # Set API keys as environment variables for PydanticAI
        # PydanticAI automatically uses OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, etc.
        if model_api_keys:
            for provider, key in model_api_keys.items():
                # Google provider uses GEMINI_API_KEY (not GOOGLE_API_KEY)
                env_var_name = "GEMINI_API_KEY" if provider == "google" else f"{provider.upper()}_API_KEY"
                original_value = os.environ.get(env_var_name, "")
                saved_env_vars[env_var_name] = original_value
                os.environ[env_var_name] = key

        # Create PydanticAI agent
        logger.info({"event": "run_agent", "run_id": run_id, "agent_id": agent_id, "status": "creating_agent"})

        # PydanticAI expects model as string like "openai:gpt-4o" or Model object
        # For Google GLA (provider='google'), we need to create a GeminiModel object
        if agent.model_provider == "google":
            # Create GeminiModel with google-gla provider
            # GEMINI_API_KEY environment variable is set above (line 99)
            model_obj = GeminiModel(agent.model_id, provider='google-gla')
        elif agent.model_provider == "openai":
            model_obj = f"openai:{agent.model_id}"
        elif agent.model_provider == "anthropic":
            model_obj = f"anthropic:{agent.model_id}"
        elif agent.model_provider == "ollama":
            model_obj = f"ollama:{agent.model_id}"
        elif agent.model_provider == "openrouter":
            model_obj = f"openrouter:{agent.model_id}"
        elif agent.model_provider == "mistral":
            model_obj = f"mistral:{agent.model_id}"
        elif agent.model_provider == "xai":
            model_obj = f"xai:{agent.model_id}"
        elif agent.model_provider == "qwen":
            model_obj = f"qwen:{agent.model_id}"
        elif agent.model_provider == "deepseek":
            model_obj = f"deepseek:{agent.model_id}"
        elif agent.model_provider == "zai":
            model_obj = f"zai:{agent.model_id}"
        else:
            model_obj = agent.model_id

        # Create agent with PydanticAI
        # PydanticAI automatically picks up API keys from env vars (OPENAI_API_KEY, GEMINI_API_KEY, etc.)
        pydantic_agent = PydanticAgent(
            model_obj,
            tools=tools,
            toolsets=mcp_servers,  # MCP servers go here
            system_prompt=system_prompt,
        )

        # Run the agent with streaming
        logger.info({"event": "run_agent", "run_id": run_id, "agent_id": agent_id, "status": "executing"})

        # Emit "using tools" indicator
        await stream_progress("🔧 Using tools...")

        # Prepare run kwargs with message history if available
        run_kwargs = {"deps": None}
        if agent.temperature is not None:
            run_kwargs["model_settings"] = {"temperature": float(agent.temperature)}
        # Initialize pydantic_message_history so it's always available for logging
        pydantic_message_history = []

        if filtered_history:
            # CRITICAL: Convert plain dicts to PydanticAI ModelMessage objects
            # PydanticAI's message_history expects Sequence[ModelRequest | ModelResponse]
            # NOT plain dicts with role/content keys
            pydantic_message_history = convert_to_pydantic_messages(filtered_history)

            # Log what is actually being passed to PydanticAI
            logger.info({
                "event": "history_passed_to_agent",
                "run_id": run_id,
                "message_count": len(pydantic_message_history),
                "first_message_type": type(pydantic_message_history[0]).__name__ if pydantic_message_history else None,
                "sample": str(pydantic_message_history[0])[:100] if pydantic_message_history else None,
            })

            run_kwargs["message_history"] = pydantic_message_history

        # Auto-reattach last image for text-only past-image references (Bug B fix)
        # When user references "the last image" in a text-only turn, re-attach the most recent image
        PAST_IMAGE_REFERENCE_TRIGGERS = [
            "the last image", "the last picture", "the last photo",
            "what i sent", "what i just sent", "what i showed you",
            "that image", "that picture", "that photo",
            "the previous image", "the previous picture", "the previous photo",
            "the image above", "the picture above", "the photo above",
            "the image before", "the picture before", "the photo before",
            "what was the last image", "what was the last picture",
        ]

        # Check if this is a text-only turn that references a past image
        is_past_image_reference = (
            not has_attachments and
            any(phrase in input_text.lower() for phrase in PAST_IMAGE_REFERENCE_TRIGGERS)
        )

        # Check if there are prior multimodal turns in history
        has_prior_multimodal_turns = any(
            isinstance(msg, dict) and msg.get("attachments")
            for msg in message_history
        )

        # Auto-reattach if both conditions are met
        # Wrapped in try/except to prevent transaction poisoning (Bug B fix #2)
        if is_past_image_reference and has_prior_multimodal_turns and thread_id:
            try:
                logger.info({
                    "event": "past_image_reference_detected",
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "input_text": input_text[:100],
                })

                # Use a separate database session to prevent transaction poisoning
                from app.database import AsyncSessionLocal

                async with AsyncSessionLocal() as lookup_session:
                    # Query for the most recent message with attachments in this thread
                    from app.models.message import Message as MessageModel

                    # Simple SQL query - do detailed filtering in Python to avoid JSONB operator issues
                    result = await lookup_session.execute(
                        select(MessageModel)
                        .where(
                            MessageModel.thread_id == thread_id,
                            MessageModel.attachments.isnot(None),
                            MessageModel.role == 'user'
                        )
                        .order_by(MessageModel.created_at.desc())
                        .limit(1)
                    )
                    last_attachment_message = result.scalar_one_or_none()

                    # Log why no attachment was found (for debugging)
                    if not last_attachment_message:
                        logger.info({
                            "event": "no_attachment_to_reattach",
                            "run_id": run_id,
                            "thread_id": thread_id,
                            "reason": "no_user_messages_with_attachments"
                        })
                    elif not last_attachment_message.attachments:
                        logger.info({
                            "event": "no_attachment_to_reattach",
                            "run_id": run_id,
                            "thread_id": thread_id,
                            "reason": "last_message_has_empty_attachments"
                        })
                    else:
                        # Get the first attachment (most recent)
                        attachment_list = last_attachment_message.attachments if isinstance(last_attachment_message.attachments, list) else [last_attachment_message.attachments]
                        last_attachment = attachment_list[0] if attachment_list else None

                        # Check for non-purged attachment with data_base64
                        if not last_attachment:
                            logger.info({
                                "event": "no_attachment_to_reattach",
                                "run_id": run_id,
                                "thread_id": thread_id,
                                "reason": "last_message_has_empty_attachments"
                            })
                        elif ('data_base64' not in last_attachment or
                              not last_attachment.get('data_base64') or
                              last_attachment.get('purged')):
                            logger.info({
                                "event": "no_attachment_to_reattach",
                                "run_id": run_id,
                                "thread_id": thread_id,
                                "reason": "data_base64_missing_or_purged"
                            })
                        else:
                            # Create ChatAttachment from the stored attachment
                            from app.schemas.message import ChatAttachment
                            reattached_attachment = ChatAttachment(
                                name=last_attachment.get('name', 'reattached_image'),
                                type=last_attachment.get('media_type', 'image/png'),
                                data_base64=last_attachment['data_base64']
                            )

                            # Update attachments and has_attachments flag
                            attachments = [reattached_attachment]
                            has_attachments = True

                            logger.info({
                                "event": "auto_reattach_last_image",
                                "run_id": run_id,
                                "source_message_id": str(last_attachment_message.id),
                                "media_type": last_attachment.get('media_type'),
                                "size_bytes": last_attachment.get('size_bytes'),
                            })

            except Exception as e:
                # Log failure and proceed without re-attach (graceful degradation)
                logger.warning({
                    "event": "auto_reattach_query_failed",
                    "error": str(e),
                    "thread_id": thread_id,
                    "run_id": run_id,
                })
                # Continue execution without re-attach - don't poison the transaction

        # Build multimodal input (text + images) if attachments present
        # Build once and cache to avoid duplicate calls
        multimodal_input = None
        if has_attachments:
            multimodal_input = build_multimodal_input(input_text, attachments)

            # Log if we're using multimodal input (only log once)
            logger.info({
                "event": "multimodal_input_prepared",
                "run_id": run_id,
                "input_type": "multimodal" if isinstance(multimodal_input, list) else "text_only",
                "attachment_count": len(attachments) if has_attachments else 0,
            })

        # FINAL ASSERTION: Verify current turn's BinaryContent made it through
        # This should be the LAST check before agent.run() to catch any truncation bugs
        logger.info({
            "event": "final_agent_call_shape",
            "run_id": run_id,
            "user_prompt_type": "list" if isinstance(multimodal_input, list) else "str",
            "user_prompt_elements": [
                {
                    "type": type(elem).__name__,
                    "size_or_len": len(elem.data) if hasattr(elem, 'data') else len(str(elem)),
                } for elem in (multimodal_input if isinstance(multimodal_input, list) else [multimodal_input])
            ],
            "message_history_count": len(pydantic_message_history),
            "message_history_total_estimated_tokens": estimate_tokens(message_history),
            "last_history_role": message_history[-1].get("role") if message_history else None,  # Should be 'user'
        })

        # Build multimodal input (text + images) if attachments present
        # TRACE: Executor pre-helper - log what we received before calling helper
        if attachments and isinstance(attachments, list) and len(attachments) > 0:
            first_element = attachments[0] if len(attachments) > 0 else None
            first_type = type(first_element).__name__ if first_element else "None"
            first_keys = list(first_element.model_fields.keys()) if first_element else []
            has_data = hasattr(first_element, "data_base64") if first_element else False
            has_type = hasattr(first_element, "type") if first_element else False

            logger.info({
                "event": "attachment_trace",
                "checkpoint": "executor_pre_helper",
                "first_type": first_type,
                "first_keys": first_keys,
                "has_data": has_data,
                "has_type": has_type,
            })

        # TRACE: Before calling build_multimodal_input
        logger.info({
            "event": "attachment_trace",
            "checkpoint": "pre_build_multimodal",
            "count": len(attachments) if attachments and isinstance(attachments, list) else 0,
            "input_text": input_text[:50],
        })

        multimodal_input = build_multimodal_input(input_text, attachments)

        # Log if we're using multimodal input
        if has_attachments:
            logger.info({
                "event": "multimodal_input_prepared",
                "run_id": run_id,
                "input_type": "multimodal" if isinstance(multimodal_input, list) else "text_only",
                "attachment_count": len(attachments) if has_attachments else 0,
            })

        # DEBUG: Log exactly what's being passed to PydanticAI agent
        logger.info({
            "event": "agent_input_debug",
            "run_id": run_id,
            "multimodal_input_type": type(multimodal_input).__name__,
            "is_list": isinstance(multimodal_input, list),
            "element_count": len(multimodal_input) if isinstance(multimodal_input, list) else 1,
            "elements": [
                {
                    "type": type(elem).__name__,
                    "class": str(type(elem)),
                    "value_preview": str(elem)[:100],
                    "has_data_attr": hasattr(elem, 'data') if hasattr(elem, '__class__') else False,
                    "has_media_type_attr": hasattr(elem, 'media_type') if hasattr(elem, '__class__') else False,
                    # For BinaryContent, show data details
                    "binary_data_length": len(elem.data) if hasattr(elem, 'data') else None,
                    "binary_media_type": elem.media_type if hasattr(elem, 'media_type') else None,
                }
                for elem in (multimodal_input if isinstance(multimodal_input, list) else [multimodal_input])
            ]
        })

        # Use async context manager to properly start/stop MCP servers
        try:
            async with pydantic_agent.run_mcp_servers():
                result = await pydantic_agent.run(multimodal_input, **run_kwargs)
        except ApprovalRequestedError as e:
            # Agent requested approval - pause execution and wait for user
            logger.info({
                "event": "approval_requested_exception",
                "kind": e.kind,
                "title": e.title,
                "run_id": run_id,
            })

            # Create approval record
            approval = await create_approval(
                db=db,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                schedule_id=None,
                kind=e.kind,
                title=e.title,
                description=e.description,
                payload=e.payload,
            )

            # Update run status to awaiting_approval
            await update_run(
                db=db,
                run_id=run_id,
                status="awaiting_approval",
            )

            # Stream approval requested message
            await stream_progress(f"🔔 Approval requested: {e.title}")

            # Stream completion message with approval details
            await stream_message({
                "type": "approval_requested",
                "approval_id": str(approval.id),
                "kind": e.kind,
                "title": e.title,
                "description": e.description,
                "payload": e.payload,
            })

            logger.info({
                "event": "approval_created_from_exception",
                "approval_id": str(approval.id),
                "run_id": run_id,
                "kind": e.kind,
            })

            # Stop execution - return None to indicate waiting for approval
            return None

        # TRACE 5: Log full message history including all tool calls and responses
        logger.info({"event": "agent_trace_start_history", "run_id": run_id})
        try:
            for msg in result.all_messages():
                for part in getattr(msg, "parts", []):
                    kind = getattr(part, "part_kind", type(part).__name__)
                    if kind == "tool-call":
                        tool_name = getattr(part, "tool_name", None)
                        logger.info({
                            "event": "agent_tool_call",
                            "run_id": run_id,
                            "tool_name": tool_name,
                            "args": part.args_as_dict() if hasattr(part, "args_as_dict") else str(getattr(part, "args", "")),
                        })

                        # Check for approval request
                        if tool_name == "request_approval":
                            # Extract approval data from tool arguments
                            args_dict = part.args_as_dict() if hasattr(part, "args_as_dict") else {}
                            kind = args_dict.get("kind", "execute_action")
                            title = args_dict.get("title", "Agent action requires approval")
                            description = args_dict.get("description", "No description provided")
                            payload = args_dict.get("payload", {})

                            # Create approval record
                            approval = await create_approval(
                                db=db,
                                user_id=user_id,
                                agent_id=agent_id,
                                run_id=run_id,
                                schedule_id=None,
                                kind=kind,
                                title=title,
                                description=description,
                                payload=payload,
                            )

                            # Update run status to awaiting_approval
                            await update_run(
                                db=db,
                                run_id=run_id,
                                status="awaiting_approval",
                            )

                            # Stream approval requested message
                            await stream_progress(f"🔔 Approval requested: {title}")

                            # Stream completion message with approval details
                            await stream_message({
                                "type": "approval_requested",
                                "approval_id": str(approval.id),
                                "kind": kind,
                                "title": title,
                                "description": description,
                            })

                            logger.info({
                                "event": "approval_created",
                                "approval_id": str(approval.id),
                                "run_id": run_id,
                                "kind": kind,
                            })

                            # Stop execution - output will be set to awaiting_approval
                            return None
                    elif kind == "tool-return":
                        content_str = str(getattr(part, "content", ""))[:500]
                        logger.info({
                            "event": "agent_tool_return",
                            "run_id": run_id,
                            "tool_name": getattr(part, "tool_name", None),
                            "content": content_str,
                        })
                    elif kind in ("user-prompt", "text", "system-prompt"):
                        logger.debug({
                            "event": "agent_message_part",
                            "run_id": run_id,
                            "kind": kind,
                            "content_preview": str(getattr(part, "content", ""))[:200],
                        })
        except Exception as history_err:
            logger.warning({
                "event": "agent_history_log_failed",
                "error": str(history_err),
            })

        # Stream the output
        output_text = result.output
        await stream_token(output_text)

        # Enrich saved message with tool results for future context
        tool_results = extract_tool_results(result.all_messages())

        # Only append if tool results contain something not already in output
        # (avoids duplication if agent already mentioned the URL)
        saved_output = output_text
        if tool_results:
            # Check if key info (spreadsheet IDs, URLs) is already in output
            has_url = "docs.google.com" in output_text or "spreadsheetId" in output_text
            if not has_url:
                saved_output = output_text + "\n" + tool_results
            logger.debug({
                "event": "tool_results_extracted",
                "run_id": run_id,
                "has_url_in_output": has_url,
                "tool_results_preview": tool_results[:100] if len(tool_results) > 100 else tool_results,
            })

        # Cache full output in Redis FIRST so late SSE consumers can always replay.
        # Must happen before done event so consumer's empty-list fallback always finds something.
        try:
            await redis.setex(
                f"ocin:run:{run_id}:output",
                300,
                json.dumps({"type": "done", "output": saved_output, "run_id": run_id})
            )
            logger.debug({"event": "output_cached", "run_id": run_id})
        except Exception as e:
            logger.warning({"event": "cache_output_failed", "run_id": run_id, "error": str(e)})

        # Now publish done event. Any consumer reading the list will see this;
        # any consumer that arrives later will hit the cache fallback.
        await stream_message({
            "type": "done",
            "run_id": run_id,
            "status": "success",
        })

        # Calculate metrics
        duration_ms = int((time.time() - start_time) * 1000)
        usage = result.usage() if hasattr(result, "usage") else None
        tokens_used = usage.total_tokens if usage and hasattr(usage, "total_tokens") else 0

        # Update run record
        await update_run(
            db,
            run_id,
            status="success",
            output=saved_output,  # ← use saved_output not output_text
            tool_calls=[],  # Tool calls are embedded in output
            tokens_used=tokens_used,
            cost_usd=0.0,  # TODO: calculate based on model pricing
            finished_at=datetime.utcnow(),
        )

        logger.info({
            "event": "run_agent_complete",
            "run_id": run_id,
            "agent_id": agent_id,
            "status": "success",
            "tokens_used": tokens_used,
            "duration_ms": duration_ms,
        })

        # Extract and save memory if output is long enough (runs in background)
        # Use saved_output so memory includes tool results (URLs, IDs, etc.)
        if len(saved_output.strip()) >= 100:
            try:
                await extract_and_save_memory(db, agent_id, input_text, saved_output)
            except Exception as e:
                logger.warning({"event": "memory_extraction_failed", "error": str(e)})

        # Save messages to thread if thread_id is provided
        if thread_id:
            try:
                await save_messages(db, thread_id, input_text, saved_output, attachments)
                logger.info({"event": "messages_saved", "thread_id": thread_id})
            except Exception as e:
                logger.warning({"event": "save_messages_failed", "error": str(e)})

        return output_text

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)

        # Parse structured error details and surface to user
        error_details = parse_llm_provider_error(e)

        # Determine error kind for user-facing message
        error_kind = error_details.get("kind", "provider_error") if isinstance(error_details, dict) else "provider_error"
        user_message = error_details.get("message", str(e)) if isinstance(error_details, dict) else str(e)

        # Update run status to failed
        await update_run(
            db=db,
            run_id=run_id,
            status="failed",
            error=json.dumps(error_details),
        )

        # Create assistant error message for thread (only if thread_id exists)
        # Approval continuation runs have no thread_id, so skip message saving
        if thread_id is not None:
            await save_messages(
                db=db,
                thread_id=thread_id,
                user_input=input_text,
                assistant_output=user_message,
                attachments=None,
                kind="error",
            )
        else:
            logger.info({
                "event": "save_messages_skipped",
                "run_id": run_id,
                "reason": "no_thread_id_continuation_run",
            })

        # Publish final SSE event so frontend updates immediately
        stream_key = f"ocin:run:{run_id}:stream"
        final_error_event = {
            "type": "error",
            "error": user_message,
            "error_details": error_details,
        }
        await redis.publish(stream_key, json.dumps(final_error_event))

        logger.info({
            "event": "run_finalized_with_error",
            "run_id": run_id,
            "error_kind": error_kind,
            "user_message": user_message[:200],
        })

        return None

    finally:
        # Clear self-call context
        if jwt_token:
            clear_self_call_context()
            logger.debug({"event": "cleared_self_call_context"})

        # Close MCP servers - guard against empty list
        if mcp_servers:
            for server in mcp_servers:
                try:
                    if hasattr(server, 'close'):
                        await server.close()
                except Exception as e:
                    logger.warning({"event": "cleanup_mcp_server", "error": str(e)})

        # Clean up legacy clients (now empty) - guard against empty list
        clients = tools_data.get("clients", [])
        if clients:
            for client in clients:
                try:
                    await client.close()
                except Exception as e:
                    logger.warning({"event": "cleanup_client", "error": str(e)})

        # Restore original environment variables (only those we modified)
        for env_var_name, original_value in saved_env_vars.items():
            os.environ[env_var_name] = original_value
