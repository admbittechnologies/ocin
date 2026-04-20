import logging
from typing import Optional, List

import httpx
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.core.dependencies import CurrentUser
from app.core.security import decrypt_value
from app.models.tool import Tool
from app.schemas.agent import SUPPORTED_PROVIDERS, normalize_provider

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger("ocin")

router = APIRouter()


# Provider name mapping: normalized (lowercase) -> display (capitalized)
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


class ProviderModels(BaseModel):
    provider: str
    models: List[str]


async def get_user_provider_api_key(
    db: AsyncSession,
    user_id: str,
    provider: str,
) -> Optional[str]:
    """Get and decrypt the user's API key for a given provider."""
    provider_normalized = normalize_provider(provider)

    result = await db.execute(
        select(Tool).where(
            Tool.user_id == user_id,
            Tool.source == "api_key",
            Tool.source_key == provider_normalized,
            Tool.is_active == True,
        )
    )
    tool = result.scalar_one_or_none()

    if not tool or not tool.config:
        return None

    try:
        encrypted_key = tool.config.get("api_key")
        if encrypted_key:
            return decrypt_value(encrypted_key)
    except Exception as e:
        logger.error(
            {
                "event": "decrypt_api_key_failed",
                "user_id": user_id,
                "provider": provider,
                "error": str(e),
            }
        )

    return None


async def fetch_openai_models(api_key: Optional[str]) -> List[str]:
    """
    Fetch available models from OpenAI API.
    Fallback: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    """
    fallback = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    if not api_key:
        return fallback

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                # Filter model IDs that contain "gpt"
                models = [m["id"] for m in data.get("data", []) if "gpt" in m["id"].lower()]
                return models if models else fallback
    except Exception as e:
        logger.error({"event": "fetch_openai_models_failed", "error": str(e)})

    return fallback


async def fetch_anthropic_models(api_key: Optional[str] = None) -> List[str]:
    """
    Anthropic has no public list-models endpoint.
    Always return hardcoded: ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-3-5", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
    """
    return [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-3-5",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    ]


async def fetch_google_models(api_key: Optional[str]) -> List[str]:
    """
    Fetch available models from Google Generative AI API.
    Fallback: ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"]
    """
    fallback = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"]

    if not api_key:
        return fallback

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            )
            if response.status_code == 200:
                data = response.json()
                models = []
                for model in data.get("models", []):
                    name = model.get("name", "")
                    # Strip "models/" prefix
                    if name.startswith("models/"):
                        model_id = name[7:]  # Remove "models/" prefix
                        models.append(model_id)
                return models if models else fallback
    except Exception as e:
        logger.error({"event": "fetch_google_models_failed", "error": str(e)})

    return fallback


async def fetch_mistral_models(api_key: Optional[str]) -> List[str]:
    """
    Fetch available models from Mistral API.
    Fallback: ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"]
    """
    fallback = ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"]

    if not api_key:
        return fallback

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                models = [m["id"] for m in data.get("data", [])]
                return models if models else fallback
    except Exception as e:
        logger.error({"event": "fetch_mistral_models_failed", "error": str(e)})

    return fallback


async def fetch_openrouter_models(api_key: Optional[str]) -> List[str]:
    """
    Fetch available models from OpenRouter API.
    Fallback: ["openai/gpt-4o", "anthropic/claude-3-5-sonnet"]
    """
    fallback = ["openai/gpt-4o", "anthropic/claude-3-5-sonnet"]

    if not api_key:
        return fallback

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                models = [m["id"] for m in data.get("data", [])]
                return models if models else fallback
    except Exception as e:
        logger.error({"event": "fetch_openrouter_models_failed", "error": str(e)})

    return fallback


async def fetch_grok_models(api_key: Optional[str] = None) -> List[str]:
    """
    Grok (xAI) has no public models endpoint.
    Always return hardcoded: ["grok-2", "grok-2-mini", "grok-beta"]
    """
    return [
        "grok-2",
        "grok-2-mini",
        "grok-beta",
    ]


async def fetch_deepseek_models(api_key: Optional[str] = None) -> List[str]:
    """
    DeepSeek has no public models endpoint.
    Always return hardcoded: ["deepseek-chat", "deepseek-reasoner"]
    """
    return [
        "deepseek-chat",
        "deepseek-reasoner",
    ]


async def fetch_qwen_models(api_key: Optional[str] = None) -> List[str]:
    """
    Qwen has no public models endpoint.
    Always return hardcoded: ["qwen-max", "qwen-plus", "qwen-turbo"]
    """
    return [
        "qwen-max",
        "qwen-plus",
        "qwen-turbo",
    ]


async def fetch_ollama_models(api_key: Optional[str] = None) -> List[str]:
    """
    Fetch available models from local Ollama instance.
    Fallback: ["llama3.2", "mistral", "codellama"]
    """
    fallback = ["llama3.2", "mistral", "codellama"]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                return models if models else fallback
    except Exception as e:
        logger.error({"event": "fetch_ollama_models_failed", "error": str(e)})

    return fallback


async def fetch_zai_models(api_key: Optional[str] = None) -> List[str]:
    """
    ZAI has no public models endpoint.
    Always return hardcoded: ["zai-large", "zai-medium", "zai-small"]
    """
    return [
        "zai-large",
        "zai-medium",
        "zai-small",
    ]


@router.get("/{name}/models", response_model=ProviderModels)
async def get_provider_models(
    name: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Get available models for a provider.

    Uses the user's saved API key to call the provider's models API.
    If the call fails or no key is saved, returns a hardcoded fallback list with 200 status.
    """
    # Validate provider name (accept both normalized and display names)
    normalized_name = normalize_provider(name)
    display_name = PROVIDER_NAME_MAP.get(normalized_name, name)

    # Debug logging
    logger.info({
        "event": "get_provider_models",
        "input_name": name,
        "normalized_name": normalized_name,
        "display_name": display_name,
        "supported_providers": SUPPORTED_PROVIDERS,
    })

    # Simplified check: just check if normalized name is in normalized supported list
    supported_normalized = [normalize_provider(p) for p in SUPPORTED_PROVIDERS]
    if normalized_name not in supported_normalized:
        logger.error({
            "event": "provider_not_found",
            "input": name,
            "normalized_name": normalized_name,
            "supported_normalized": supported_normalized,
        })
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Provider '{name}' not found", "code": "PROVIDER_NOT_FOUND"}
        )

    # Get user's API key for this provider
    user_id = str(current_user.id)
    api_key = await get_user_provider_api_key(db, user_id, display_name)

    # Fetch models from provider API (or return fallback)
    fetcher_map = {
        "openai": fetch_openai_models,
        "anthropic": fetch_anthropic_models,
        "google": fetch_google_models,
        "mistral": fetch_mistral_models,
        "openrouter": fetch_openrouter_models,
        "xai": fetch_grok_models,
        "qwen": fetch_qwen_models,
        "deepseek": fetch_deepseek_models,
        "zai": fetch_zai_models,
        "ollama": fetch_ollama_models,
    }

    fetcher = fetcher_map.get(normalized_name)
    if fetcher:
        models = await fetcher(api_key)
    else:
        models = []

    return ProviderModels(
        provider=display_name,
        models=models,
    )


@router.get("/", response_model=dict)
async def list_providers():
    """List all supported providers."""
    return {"providers": list(PROVIDER_NAME_MAP.values())}
