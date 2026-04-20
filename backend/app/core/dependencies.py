import logging
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.services.user_service import get_user_by_id
from app.core.exceptions import ForbiddenException, UnauthorizedException, RateLimitExceededException

logger = logging.getLogger("ocin")

# HTTP Bearer for JWT
security = HTTPBearer()

# Plan limits configuration
PLAN_LIMITS = {
    "free": {
        "max_agents": 2,
        "max_active_schedules": 2,
        "runs_per_month": 100,
        "max_tool_integrations": 2,
        "allowed_providers": ["openai", "anthropic"],
        "ollama": False,
    },
    "pro": {
        "max_agents": 10,
        "max_active_schedules": 20,
        "runs_per_month": 2000,
        "max_tool_integrations": 10,
        "allowed_providers": "all",
        "ollama": True,
    },
    "business": {
        "max_agents": -1,  # unlimited
        "max_active_schedules": -1,  # unlimited
        "runs_per_month": -1,  # unlimited
        "max_tool_integrations": -1,  # unlimited
        "allowed_providers": "all",
        "ollama": True,
    },
}


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get the current authenticated user from JWT token."""
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None or "sub" not in payload:
        logger.warning({"event": "get_current_user", "error": "Invalid token"})
        raise UnauthorizedException("Invalid authentication credentials")

    user_id = payload.get("sub")
    user = await get_user_by_id(db, user_id)

    if user is None:
        logger.warning({"event": "get_current_user", "user_id": user_id, "error": "User not found"})
        raise UnauthorizedException("User not found")

    return user


async def require_admin(x_admin_secret: Annotated[str | None, Header()] = None) -> None:
    """Require admin secret header."""
    from app.config import settings

    if x_admin_secret != settings.ADMIN_SECRET:
        logger.warning({"event": "require_admin", "error": "Invalid admin secret"})
        raise UnauthorizedException("Invalid admin credentials")


async def check_plan_limits(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    resource: str,
    count: int = 1,
) -> User:
    """Check if user's plan allows the requested resource usage."""
    limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])

    # Check provider restrictions
    if resource in ["openai", "anthropic", "google", "ollama", "openrouter", "mistral", "xai", "qwen", "deepseek", "zai"]:
        allowed = limits.get("allowed_providers", "all")
        if allowed != "all" and resource not in allowed:
            raise ForbiddenException(f"Provider '{resource}' not available in {user.plan} plan")

    # Check Ollama restriction
    if resource == "ollama" and not limits.get("ollama", False):
        raise ForbiddenException("Ollama not available in free plan")

    # Check agent count
    if resource == "agents":
        from app.models.agent import Agent
        from sqlalchemy import select, func

        result = await db.execute(
            select(func.count(Agent.id)).where(Agent.user_id == user.id, Agent.is_active == True)
        )
        current_count = result.scalar()
        max_agents = limits.get("max_agents", -1)
        if max_agents != -1 and current_count + count > max_agents:
            raise ForbiddenException(f"Plan limit reached: maximum {max_agents} agents")

    # Check schedule count
    if resource == "schedules":
        from app.models.schedule import Schedule
        from sqlalchemy import select, func

        result = await db.execute(
            select(func.count(Schedule.id)).where(Schedule.user_id == user.id, Schedule.is_active == True)
        )
        current_count = result.scalar()
        max_schedules = limits.get("max_active_schedules", -1)
        if max_schedules != -1 and current_count + count > max_schedules:
            raise ForbiddenException(f"Plan limit reached: maximum {max_schedules} active schedules")

    # Check tool integrations
    if resource == "tools":
        from app.models.tool import Tool
        from sqlalchemy import select, func

        # Only count actual tool integrations (composio, apify, maton), NOT LLM provider API keys
        result = await db.execute(
            select(func.count(Tool.id)).where(
                Tool.user_id == user.id,
                Tool.is_active == True,
                Tool.source != "builtin",
                Tool.source != "api_key"  # Exclude LLM provider API keys from tool integration count
            )
        )
        current_count = result.scalar()
        max_tools = limits.get("max_tool_integrations", -1)
        if max_tools != -1 and current_count + count > max_tools:
            raise ForbiddenException(f"Plan limit reached: maximum {max_tools} tool integrations")

    # Check runs per month (TODO: implement counter with Redis)
    if resource == "runs":
        max_runs = limits.get("runs_per_month", -1)
        if max_runs != -1:
            # Placeholder: implement with Redis counter
            pass

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
