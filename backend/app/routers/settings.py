import logging
from typing import Optional, Dict
from pydantic import BaseModel

from fastapi import APIRouter, Depends, status, Header

from app.database import get_db
from app.core.dependencies import CurrentUser
from app.core.security import verify_password, hash_password, encrypt_value, decrypt_value
from app.models.user import User
from app.models.tool import Tool
from app.schemas.agent import SUPPORTED_PROVIDERS, normalize_provider
from app.core.exceptions import NotFoundException

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger("ocin")

router = APIRouter()


# Provider name mapping: normalized (lowercase) -> display (capitalized)
# Frontend expects: OpenAI, Anthropic, Google, Mistral, OpenRouter, Grok, Qwen, DeepSeek, Ollama
PROVIDER_NAME_MAP = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "ollama": "Ollama",
    "openrouter": "OpenRouter",
    "mistral": "Mistral",
    "xai": "Grok",  # xai is displayed as Grok in the frontend
    "qwen": "Qwen",
    "deepseek": "DeepSeek",
    "zai": "ZAI",
}

# Search/API key providers for non-LLM services
SEARCH_PROVIDERS = {
    "tavily": "Tavily",
}


class ApiKeysOut(BaseModel):
    """Masked API keys by provider (lowercase for internal compatibility)."""
    OpenAI: Optional[str] = None
    Anthropic: Optional[str] = None
    Google: Optional[str] = None
    Ollama: Optional[str] = None
    OpenRouter: Optional[str] = None
    Mistral: Optional[str] = None
    Grok: Optional[str] = None
    Qwen: Optional[str] = None
    DeepSeek: Optional[str] = None
    ZAI: Optional[str] = None
    Tavily: Optional[str] = None  # For web search tool


class ApiKeyUpdate(BaseModel):
    provider: str
    api_key: str


class PlanUpdate(BaseModel):
    plan: str  # free | pro | business


class SuccessResponse(BaseModel):
    success: bool


def mask_api_key(key: str) -> str:
    """Mask API key for display."""
    if not key or len(key) < 8:
        return "••••"
    return f"{key[:4]}...••••"


async def get_or_create_provider_tool(
    db: AsyncSession,
    user_id: str,
    provider: str,
) -> Optional[Tool]:
    """Get or create a tool for storing provider API key."""
    result = await db.execute(
        select(Tool).where(
            Tool.user_id == user_id,
            Tool.source == "api_key",
            Tool.source_key == provider,
        )
    )
    tool = result.scalar_one_or_none()
    return tool


@router.get("/api-keys")
async def get_api_keys(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get masked API keys for the current user.

    Returns provider names capitalized to match frontend expectations:
    OpenAI, Anthropic, Google, Ollama, OpenRouter, Mistral, Grok, Qwen, DeepSeek, ZAI
    """
    user_id = str(current_user.id)
    masked_keys: Dict[str, Optional[str]] = {
        **{display: None for display in PROVIDER_NAME_MAP.values()},
        **{display: None for display in SEARCH_PROVIDERS.values()},
    }

    # Get all tools that store API keys
    result = await db.execute(
        select(Tool).where(
            Tool.user_id == user_id,
            Tool.source == "api_key",
            Tool.is_active == True,
        )
    )
    tools = result.scalars().all()

    for tool in tools:
        tool_normalized = normalize_provider(tool.source_key)
        if (tool_normalized in PROVIDER_NAME_MAP or tool_normalized in SEARCH_PROVIDERS) and tool.config:
            try:
                # Try to decrypt the API key from config
                encrypted_key = tool.config.get("api_key")
                if encrypted_key:
                    key = decrypt_value(encrypted_key)
                    masked_value = mask_api_key(key)
                    # Get display name from appropriate map
                    if tool_normalized in PROVIDER_NAME_MAP:
                        display_name = PROVIDER_NAME_MAP[tool_normalized]
                    else:
                        display_name = SEARCH_PROVIDERS[tool_normalized]
                    masked_keys[display_name] = masked_value
            except Exception:
                pass

    return masked_keys


@router.put("/api-keys")
async def update_api_key(
    key_data: ApiKeyUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Store or update an API key for a provider."""
    user_id = str(current_user.id)
    provider = key_data.provider

    # Case-insensitive provider validation
    provider_normalized = normalize_provider(provider)
    # Check both LLM providers and search providers
    valid_providers = list(SUPPORTED_PROVIDERS) + list(SEARCH_PROVIDERS.keys())
    if not any(normalize_provider(p) == provider_normalized for p in valid_providers):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"Invalid provider: {provider}", "code": "INVALID_PROVIDER"}
        )

    # Check if API key is empty (deletion request)
    api_key = key_data.api_key.strip() if key_data.api_key else ""
    is_deletion = len(api_key) == 0

    # Get or create tool (use normalized provider name for storage)
    tool = await get_or_create_provider_tool(db, user_id, provider_normalized)

    if is_deletion:
        # Delete the API key
        if tool:
            await db.delete(tool)
            await db.commit()
            logger.info({
                "event": "delete_api_key",
                "user_id": user_id,
                "provider": provider,
            })
            return {"success": True}
        else:
            # No key to delete, but that is fine
            logger.info({
                "event": "delete_api_key_not_found",
                "user_id": user_id,
                "provider": provider,
            })
            return {"success": True}
    else:
        # Encrypt API key
        encrypted_key = encrypt_value(api_key)

        if tool:
            # Update existing tool - preserve existing config fields
            existing_config = dict(tool.config) if tool.config else {}
            existing_config["api_key"] = encrypted_key
            existing_config["api_token"] = encrypted_key  # store under both keys for compatibility
            tool.config = existing_config
            tool.is_active = True
        else:
            # Create new tool (store provider as lowercase)
            tool = Tool(
                user_id=user_id,
                name=f"{provider} API Key",
                source="api_key",
                source_key=provider_normalized,
                config={"api_key": encrypted_key},
                is_active=True,
            )
            db.add(tool)

    await db.commit()
    logger.info({"event": "update_api_key", "user_id": user_id, "provider": provider})
    return {"success": True}



    # Get or create tool (use normalized provider name for storage)
    tool = await get_or_create_provider_tool(db, user_id, provider_normalized)

    if is_deletion:
        # Delete the API key
        if tool:
            await db.delete(tool)
            await db.commit()
            logger.info({
                "event": "delete_api_key",
                "user_id": user_id,
                "provider": provider,
            })
            return {"success": True}
        else:
            # No key to delete, but that is fine
            logger.info({
                "event": "delete_api_key_not_found",
                "user_id": user_id,
                "provider": provider,
            })
            return {"success": True}
    else:
        # Encrypt API key
        encrypted_key = encrypt_value(api_key)

        if tool:
            # Update existing tool - preserve existing config fields
            existing_config = dict(tool.config) if tool.config else {}
            existing_config["api_key"] = encrypted_key
            existing_config["api_token"] = encrypted_key  # store under both keys for compatibility
            tool.config = existing_config
            tool.is_active = True
        else:
            # Create new tool (store provider as lowercase)
            tool = Tool(
                user_id=user_id,
                name=f"{provider} API Key",
                source="api_key",
                source_key=provider_normalized,
                config={"api_key": encrypted_key},
                is_active=True,
            )
            db.add(tool)

    await db.commit()
    logger.info({"event": "update_api_key", "user_id": user_id, "provider": provider})
    return {"success": True}



