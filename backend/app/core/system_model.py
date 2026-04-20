"""
System model resolver.

OCIN is provider-agnostic. Internal backend tasks (schedule parsing, memory extraction,
intent resolution) must NOT hardcode specific providers or model IDs. Instead, they
reuse the user's coordinator agent's model — same provider, same model_id, same API key.

This helper returns a ready-to-use PydanticAI Agent configured with the user's
coordinator model, or None if the user has no coordinator agent yet.
"""
import logging
import os
from typing import Optional, Type, TypeVar
from contextlib import contextmanager

from pydantic import BaseModel
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models.gemini import GeminiModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent as AgentModel
from app.models.tool import Tool
from app.core.security import decrypt_value

logger = logging.getLogger("ocin")

T = TypeVar("T", bound=BaseModel)


def _build_model_string(provider: str, model_id: str):
    """Convert a (provider, model_id) pair to the form PydanticAI expects.

    Mirrors the logic in agent_runner.py so that any model working for user agents
    also works for internal system tasks.
    """
    if provider == "google":
        return GeminiModel(model_id, provider="google-gla")
    if provider in (
        "openai",
        "anthropic",
        "ollama",
        "openrouter",
        "mistral",
        "xai",
        "qwen",
        "deepseek",
        "zai",
    ):
        return f"{provider}:{model_id}"
    return model_id  # best-effort fallback


async def _get_coordinator(db: AsyncSession, user_id: str) -> Optional[AgentModel]:
    """Fetch the user's coordinator agent. Returns None if none exists."""
    result = await db.execute(
        select(AgentModel).where(
            AgentModel.user_id == user_id,
            AgentModel.role == "coordinator",
            AgentModel.is_active == True,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_api_key_for_provider(db: AsyncSession, user_id: str, provider: str) -> Optional[str]:
    """Fetch the user's stored API key for a provider from the tools table.

    OCIN stores per-user provider API keys encrypted in the tools table with
    source='api_key'. This mirrors how agent_runner.py injects keys at runtime.
    """
    result = await db.execute(
        select(Tool).where(
            Tool.user_id == user_id,
            Tool.source == "api_key",
            Tool.source_key == provider,
            Tool.is_active == True,
        ).limit(1)
    )
    tool = result.scalar_one_or_none()
    if not tool or not tool.config:
        return None
    encrypted = tool.config.get("api_key")
    if not encrypted:
        return None
    try:
        return decrypt_value(encrypted)
    except Exception as e:
        logger.error({
            "event": "system_model_decrypt_failed",
            "user_id": user_id,
            "provider": provider,
            "error": str(e),
        })
        return None


@contextmanager
def _temporary_env(env_var: str, value: str):
    """Temporarily set an env var, restore it on exit.

    PydanticAI reads provider API keys from env vars. For a short-lived internal
    call we set the env var, run the call, and restore whatever was there.
    """
    original = os.environ.get(env_var)
    os.environ[env_var] = value
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = original


async def run_system_task(
    db: AsyncSession,
    user_id: str,
    system_prompt: str,
    user_message: str,
    result_type: Type[T],
    *,
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> Optional[T]:
    """Run a one-shot internal LLM task using the user's coordinator model.

    Returns the parsed Pydantic result, or None if no coordinator exists or the call failed.
    The caller is responsible for handling the None case with a safe fallback.

    This is the ONLY way the backend should make internal LLM calls. Do NOT import
    anthropic, openai, or any other provider SDK directly.
    """
    coordinator = await _get_coordinator(db, user_id)
    if not coordinator:
        logger.info({
            "event": "system_task_no_coordinator",
            "user_id": user_id,
        })
        return None

    provider = coordinator.model_provider
    model_id = coordinator.model_id
    api_key = await _get_api_key_for_provider(db, user_id, provider)
    if not api_key:
        logger.warning({
            "event": "system_task_no_api_key",
            "user_id": user_id,
            "provider": provider,
        })
        return None

    env_var = "GEMINI_API_KEY" if provider == "google" else f"{provider.upper()}_API_KEY"
    model_obj = _build_model_string(provider, model_id)

    try:
        with _temporary_env(env_var, api_key):
            agent = PydanticAgent(
                model_obj,
                result_type=result_type,
                system_prompt=system_prompt,
            )
            run_result = await agent.run(
                user_message,
                model_settings={"temperature": temperature, "max_tokens": max_tokens},
            )
            return run_result.data
    except Exception as e:
        logger.error({
            "event": "system_task_failed",
            "user_id": user_id,
            "provider": provider,
            "model_id": model_id,
            "error": str(e),
            "error_type": type(e).__name__,
        })
        return None
