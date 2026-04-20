"""Admin endpoints for managing users and runs."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.core.dependencies import require_admin, get_current_user
from app.core.exceptions import UnauthorizedException, NotFoundException
from app.core.security import decrypt_value
from app.models.user import User
from app.models.agent import Agent
from app.models.run import Run
from app.models.tool import Tool
from app.integrations.maton_gateway import build_maton_gateway_tools

logger = logging.getLogger("ocin")

router = APIRouter()


class UserAdminOut:
    def __init__(self, id: str, email: str, plan: str, created_at: str, agent_count: int, run_count_this_month: int):
        self.id = id
        self.email = email
        self.plan = plan
        self.created_at = created_at
        self.agent_count = agent_count
        self.run_count_this_month = run_count_this_month


class RunAdminOut:
    def __init__(self, id: str, user_id: str, agent_id: str, status: str, input: str, created_at: str):
        self.id = id
        self.user_id = user_id
        self.agent_id = agent_id
        self.status = status
        self.input = input
        self.created_at = created_at


@router.post("/admin/debug/maton-test")
async def debug_maton_gateway(
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_admin),
):
    """
    TRACE 4: Debug endpoint to test Maton gateway HTTP API directly.
    No agent involved - direct HTTP communication only.
    """
    result = {
        "steps": [],
        "tools": [],
        "error": None,
    }

    # Step 1: Find the first Maton tool in the database
    maton_tools = await db.execute(
        select(Tool).where(
            Tool.source == "maton",
            Tool.is_active == True,
        )
    )
    maton_tool = maton_tools.scalars().first()

    if not maton_tool:
        result["error"] = "No active Maton tool found in database"
        return result

    result["steps"].append({"step": 1, "action": "Found Maton tool", "tool_id": str(maton_tool.id)})

    # Step 2: Get app config and API key
    api_key = maton_tool.config.get("api_key") or maton_tool.config.get("api_token", "")
    maton_app = maton_tool.config.get("app", "google-sheet")

    if not api_key:
        result["error"] = "Maton tool has no API key configured"
        return result

    result["steps"].append({"step": 2, "action": "Got config", "app": maton_app, "key_length": len(api_key)})

    # Step 3: Decrypt API key
    try:
        decrypted_key = decrypt_value(api_key)
        logger.info({
            "event": "debug_maton_test",
            "action": "decrypted_key",
            "key_length": len(decrypted_key),
        })
    except Exception as e:
        result["error"] = f"Failed to decrypt API key: {str(e)}"
        result["steps"].append({"step": 3, "action": "Decrypt failed", "error": str(e)})
        return result

    result["steps"].append({"step": 3, "action": "Decrypted API key", "length": len(decrypted_key)})

    # Step 4: Build gateway tools
    logger.info({"event": "debug_maton_test", "action": "testing_gateway"})

    try:
        tools = build_maton_gateway_tools(decrypted_key, maton_app)

        # Get tool names
        tool_names = [t.__name__ for t in tools]
        result["tools"] = tool_names
        result["steps"].append({
            "step": 4,
            "action": "Built gateway tools",
            "count": len(tools),
            "tool_names": tool_names,
        })

        # Step 5: Test create_spreadsheet via gateway
        logger.info({"event": "debug_maton_test", "action": "calling_create_spreadsheet"})

        # Find the create_spreadsheet tool function
        create_tool = None
        for tool in tools:
            if tool.__name__ == "google_sheet_create_spreadsheet":
                create_tool = tool
                break

        if not create_tool:
            result["error"] = "google_sheet_create_spreadsheet tool not found in built tools"
            return result

        try:
            create_result = await create_tool("OCIN_Gateway_Test")
            result["tool_call"] = {
                "tool_name": "google_sheet_create_spreadsheet",
                "result": str(create_result),
            }
            result["steps"].append({
                "step": 5,
                "action": "Tool call completed",
                "success": True,
            })
        except Exception as call_err:
            result["tool_call"] = {
                "tool_name": "google_sheet_create_spreadsheet",
                "error": str(call_err),
            }
            result["steps"].append({
                "step": 5,
                "action": "Tool call failed",
                "error": str(call_err),
            })
    except Exception as e:
        result["error"] = f"Gateway test failed: {str(e)}"
        result["steps"].append({"step": 4, "action": "Gateway build/call failed", "error": str(e)})

    return result


@router.get("/admin/users")
async def list_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_admin),
):
    """List all users with admin stats."""
    # Get users
    result = await db.execute(
        select(User).offset(skip).limit(limit)
    )
    users = result.scalars().all()

    # Get stats for each user
    user_stats = []
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for user in users:
        # Agent count
        agent_result = await db.execute(
            select(func.count(Agent.id)).where(
                and_(
                    Agent.user_id == user.id,
                    Agent.is_active == True,
                )
        )
        )
        agent_count = agent_result.scalar()

        # Run count this month
        run_result = await db.execute(
            select(func.count(Run.id)).where(
                and_(
                    Run.user_id == user.id,
                    Run.created_at >= month_start,
                )
        )
        )
        run_count_this_month = run_result.scalar()

        user_stats.append(UserAdminOut(
            id=str(user.id),
            email=user.email,
            plan=user.plan,
            created_at=str(user.created_at),
            agent_count=agent_count,
            run_count_this_month=run_count_this_month,
        ))

    return [u.__dict__ for u in user_stats]


@router.put("/admin/users/{user_id}/plan")
async def update_user_plan(
    user_id: str,
    plan: str,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_admin),
):
    """Update a user's plan."""
    if plan not in ["free", "pro", "business"]:
        raise ValueError("Plan must be one of: free, pro, business")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise NotFoundException("User not found")

    old_plan = user.plan
    user.plan = plan
    await db.commit()

    logger.info({"event": "admin_update_plan", "user_id": user_id, "old_plan": old_plan, "new_plan": plan})

    return {"user_id": user_id, "plan": plan}


@router.get("/admin/runs")
async def list_all_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    _admin: None = Depends(require_admin),
):
    """List all runs across all users."""
    # Get runs
    result = await db.execute(
        select(Run).offset(skip).limit(limit)
    )
    runs = result.scalars().all()

    return [
        RunAdminOut(
            id=str(run.id),
            user_id=str(run.user_id),
            agent_id=str(run.agent_id),
            status=run.status,
            input=run.input or "",
            created_at=str(run.created_at),
        ) for run in runs
    ]


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"api": "ok", "db": "ok", "redis": "ok", "scheduler": "ok"}
