import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, status, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import Query
from redis.asyncio import Redis

from app.core.dependencies import CurrentUser, get_db
from app.core.exceptions import (
    NotFoundException,
    ApprovalRequestedException,
)
from app.schemas.approval import (
    ApprovalOut,
    ApprovalListResponse,
    ApprovalCreate,
    ApprovalResolve,
)
from app.services.approval_service import (
    create_approval,
    list_approvals,
    get_approval,
    resolve_approval,
    get_pending_approvals_count,
)
from app.services.run_service import create_run, update_run
from app.services.agent_runner import run_agent
from app.models.approval import Approval
from app.models.run import Run
from app.models.agent import Agent as AgentModel
from app.config import settings
from app.schemas.agent import normalize_provider
from app.models.tool import Tool
from sqlalchemy import select

logger = logging.getLogger("ocin")
router = APIRouter()


async def get_api_keys_for_provider(
    db: AsyncSession,
    user_id: str,
    provider_normalized: str,
) -> dict[str, str]:
    """
    Retrieve API keys for a given provider from tools table.

    This is the SAME mechanism used by chat path when invoking run_agent.
    API keys are stored in tools table with source='api_key' and
    provider name as source_key (lowercase).

    Args:
        db: Database session
        user_id: User ID
        provider_normalized: Normalized provider name (lowercase)

    Returns:
        Dict mapping provider names to decrypted API keys
    """
    from sqlalchemy import select
    from app.core.security import decrypt_value

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

# Status mapping: API-facing status values to DB internal values
STATUS_API_TO_DB = {
    "pending": "awaiting_approval",
    "approved": "approved",
    "rejected": "rejected",
    "expired": "expired",
}

def map_status_filter(api_value: str | None) -> str | None:
    """Map API status query param to DB status value."""
    if api_value is None:
        return None
    mapped = STATUS_API_TO_DB.get(api_value)
    if mapped is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"Unknown status filter: {api_value}", "code": "INVALID_STATUS_FILTER"},
        )
    return mapped

def to_api_status(db_status: str) -> str:
    """Map DB status value to API-facing status."""
    # Reverse mapping for API responses
    db_to_api = {v: k for k, v in STATUS_API_TO_DB.items()}
    return db_to_api.get(db_status, db_status)


async def get_approval_for_response(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
) -> Approval | None:
    """Get approval with all relationships loaded for response serialization.

    Uses consistent query shape with eager loading to prevent N+1 queries
    and ensure ORM objects are returned (not dicts).
    """
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.agent), selectinload(Approval.run))
        .where(Approval.id == approval_id, Approval.user_id == user_id)
    )
    return result.scalar_one_or_none()


def assert_can_resolve(approval: Approval) -> None:
    """Assert that an approval can still be resolved.

    Raises 409 Conflict if approval is already resolved (not awaiting_approval).
    """
    if approval.status != "awaiting_approval":
        logger.warning({
            "event": "resolve_approval_invalid_status",
            "approval_id": str(approval.id),
            "current_status": approval.status,
            "expected_status": "awaiting_approval",
        })
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "approval_already_resolved",
                "current_status": approval.status,
            },
        )


@router.get("", response_model=ApprovalListResponse)
async def list_approvals_endpoint(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    status_filter: str = Query("pending", alias="status"),
    limit: int = 50,
    offset: int = 0,
):
    """List approvals for current user, newest first."""
    try:
        # Map API status to DB status
        db_status = map_status_filter(status_filter)

        # Add required logging for Problem B diagnosis
        logger.info({
            "event": "approvals_list",
            "requested_status": status_filter,
            "normalized_db_status": db_status,
        })

        approvals = await list_approvals(
            db=db,
            user_id=str(current_user.id),
            status=db_status,
            limit=limit,
            skip=offset,
        )

        # Calculate status distribution
        status_distribution = {}
        for approval in approvals:
            status = approval.status
            status_distribution[status] = status_distribution.get(status, 0) + 1

        logger.info({
            "event": "approvals_list",
            "requested_status": status_filter,
            "normalized_db_status": db_status,
            "result_count": len(approvals),
            "row_status_distribution": status_distribution,
        })

        approval_list = [
            ApprovalOut(
                id=str(approval.id),
                user_id=str(approval.user_id),
                agent_id=str(approval.agent_id) if approval.agent_id else None,
                agent_name=approval.agent.name if approval.agent else None,
                agent_avatar=approval.agent.avatar if approval.agent else "avatar-01",
                run_id=str(approval.run_id) if approval.run_id else None,
                schedule_id=str(approval.schedule_id) if approval.schedule_id else None,
                kind=approval.kind,
                title=approval.title,
                description=approval.description,
                payload=approval.payload,
                status=to_api_status(approval.status),  # ← translate DB status to API status
                resolved_at=approval.resolved_at,
                resolution_note=approval.resolution_note,
                expires_at=approval.expires_at,
                created_at=approval.created_at,
            )
            for approval in approvals
        ]

        return ApprovalListResponse(approvals=approval_list)

    except HTTPException:
        # Re-raise HTTP exceptions (like invalid status filter)
        raise
    except Exception as e:
        logger.error({"event": "list_approvals_error", "error": str(e)})
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "code": "INTERNAL_ERROR"},
        )


@router.get("/pending/count")
async def pending_approvals_count_endpoint(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Return count of pending approvals for current user."""
    # Use same mapping as list endpoint: "pending" → "awaiting_approval"
    from app.services.approval_service import count_pending
    count = await count_pending(db, str(current_user.id))
    return {"count": count}


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval_endpoint(
    approval_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Get full details of a specific approval.

    Path params:
        approval_id: UUID of approval to fetch

    Raises:
        NotFoundException if approval not found or doesn't belong to user
    """
    try:
        approval = await get_approval_for_response(db, approval_id, str(current_user.id))

        if not approval:
            raise NotFoundException(f"Approval {approval_id} not found")

        # Defensive type check - ensure we have ORM object before accessing attributes
        if not isinstance(approval, Approval):
            logger.error({
                "event": "get_approval_type_error",
                "approval_id": approval_id,
                "approval_type": type(approval).__name__,
                "error": f"Expected Approval ORM object, got {type(approval).__name__}",
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "Internal type error - approval is not an ORM object", "code": "TYPE_ERROR"},
            )

        return ApprovalOut(
            id=str(approval.id),
            user_id=str(approval.user_id),
            agent_id=str(approval.agent_id) if approval.agent_id else None,
            agent_name=approval.agent.name if approval.agent else None,
            agent_avatar=approval.agent.avatar if approval.agent else "avatar-01",
            run_id=str(approval.run_id) if approval.run_id else None,
            schedule_id=str(approval.schedule_id) if approval.schedule_id else None,
            kind=approval.kind,
            title=approval.title,
            description=approval.description,
            payload=approval.payload,
            status=to_api_status(approval.status),  # ← translate DB status to API status
            resolved_at=approval.resolved_at,
            resolution_note=approval.resolution_note,
            expires_at=approval.expires_at,
            created_at=approval.created_at,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (including 404 and 500)
        raise
    except Exception as e:
        logger.error({"event": "get_approval_error", "approval_id": approval_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e), "code": "INTERNAL_ERROR"},
        )


@router.post("/{approval_id}/approve", status_code=status.HTTP_200_OK)
async def approve_approval(
    current_user: CurrentUser,
    approval_id: str,
    body: ApprovalResolve,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Approve an approval request.

    Path params:
        approval_id: UUID of approval to approve

    Request body:
        note: Optional note from user

    Action:
        - Mark approval as approved
        - Set resolved_at timestamp
        - Trigger continuation of paused run

    The original run that requested approval will get a new child run
    created on approval with approved payload.
    """
    try:
        # Get approval with proper eager loading
        approval = await get_approval_for_response(db, approval_id, str(current_user.id))

        if not approval:
            raise NotFoundException(f"Approval {approval_id} not found")

        # Enforce state transition guard BEFORE any side effects
        assert_can_resolve(approval)

        # Resolve the approval
        approval = await resolve_approval(
            db=db,
            approval_id=approval_id,
            user_id=str(current_user.id),
            approved=True,
            note=body.note,
        )

        logger.info({
            "event": "approve_handler_step",
            "step_label": "after_resolve_approval",
            "approval_type": type(approval).__name__,
            "is_dict": isinstance(approval, dict),
        })

        # Side-effects block - wrapped in try/except so failures don't cause 500
        try:
            # Trigger continuation of paused run by creating a child run
            if approval.run_id:
                logger.info({
                    "event": "approve_handler_step",
                    "step_label": "has_run_id_check",
                    "run_id": str(approval.run_id),
                    "run_id_type": type(approval.run_id).__name__,
                })

                # Get the original run to extract details for continuation
                result = await db.execute(
                    select(Run).where(Run.id == approval.run_id)
                )
                original_run = result.scalar_one_or_none()

                logger.info({
                    "event": "approve_handler_step",
                    "step_label": "after_get_original_run",
                    "original_run_type": type(original_run).__name__,
                    "is_dict": isinstance(original_run, dict) if original_run else None,
                    "original_run_id": str(original_run.id) if original_run else None,
                })

                if original_run:
                    # Verify original_run has expected attributes
                    logger.info({
                        "event": "approve_handler_step",
                        "step_label": "before_accessing_run_attrs",
                        "has_user_id": hasattr(original_run, 'user_id'),
                        "has_agent_id": hasattr(original_run, 'agent_id'),
                        "has_schedule_id": hasattr(original_run, 'schedule_id'),
                        "has_id": hasattr(original_run, 'id'),
                    })

                    # Import the schema for type safety
                    from app.schemas.run import RunCreate

                    # Create child run with approved payload
                    # The child run continues from where the parent paused
                    continuation_input = f"Continuing from approved approval: {approval.title}"

                    logger.info({
                        "event": "approve_handler_step",
                        "step_label": "before_create_run",
                        "continuation_input": continuation_input,
                    })

                    child_run = await create_run(
                        db=db,
                        run_data=RunCreate(
                            user_id=str(original_run.user_id),
                            agent_id=str(original_run.agent_id),
                            schedule_id=str(original_run.schedule_id) if original_run.schedule_id else None,
                            input=continuation_input,
                            status="pending",
                            parent_run_id=str(original_run.id),
                        )
                    )

                    logger.info({
                        "event": "approve_handler_step",
                        "step_label": "after_create_run",
                        "child_run_type": type(child_run).__name__,
                        "child_run_id": str(child_run.id),
                    })

                    logger.info({
                        "event": "approval_continuation_created",
                        "approval_id": approval_id,
                        "parent_run_id": str(original_run.id),
                        "child_run_id": str(child_run.id),
                    })

                    # Get API keys for the agent (same mechanism as chat path uses)
                    # Load agent to get model_provider and model_id
                    agent_result = await db.execute(
                        select(AgentModel).where(AgentModel.id == original_run.agent_id)
                    )
                    agent = agent_result.scalar_one_or_none()
                    if not agent:
                        raise RuntimeError(f"Agent {original_run.agent_id} not found")

                    provider_normalized = normalize_provider(agent.model_provider)
                    model_api_keys = await get_api_keys_for_provider(
                        db=db,
                        user_id=str(original_run.user_id),
                        provider_normalized=provider_normalized,
                    )

                    logger.info({
                        "event": "child_run_credentials_prepared",
                        "child_run_id": str(child_run.id),
                        "api_key_providers_loaded": list(model_api_keys.keys()),  # don't log values, just provider names
                    })

                    # Schedule the child run for execution as a background task
                    from redis.asyncio import Redis
                    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
                    background_tasks.add_task(
                        run_agent,
                        run_id=str(child_run.id),
                        user_id=str(original_run.user_id),
                        agent_id=str(original_run.agent_id),
                        input_text=continuation_input,
                        db=db,
                        redis=redis_client,
                        model_api_keys=model_api_keys,  # Pass API keys
                        parent_run_id=str(original_run.id),
                    )

                    logger.info({
                        "event": "child_run_scheduled_for_execution",
                        "child_run_id": str(child_run.id),
                        "parent_run_id": str(original_run.id),
                    })

                    # Mark the parent run as resolved with success
                    await update_run(
                        db=db,
                        run_id=str(original_run.id),
                        status="success",
                        output=f"Approved by user. Continued in run {child_run.id}",
                        finished_at=datetime.now(timezone.utc),
                    )

                    logger.info({
                        "event": "run_resolved_after_approval",
                        "approval_id": approval_id,
                        "parent_run_id": str(original_run.id),
                        "child_run_id": str(child_run.id),
                    })
                else:
                    logger.info({
                        "event": "approval_approved_no_continuation",
                        "approval_id": approval_id,
                        "reason": "No associated run_id or run not found",
                    })
            else:
                logger.info({
                    "event": "approval_approved_no_continuation",
                    "approval_id": approval_id,
                    "reason": "Approval has no run_id",
                })

        except Exception as side_effect_error:
            # Side-effects failed, but the approval was committed successfully
            # Log the failure but don't crash the API response
            logger.error({
                "event": "approval_side_effect_failed",
                "approval_id": approval_id,
                "error": str(side_effect_error),
                "error_type": type(side_effect_error).__name__,
                "detail": "Approval was committed successfully, but run continuation failed",
            })
            # Do NOT raise - the approval succeeded, this is just a side-effect failure

        return {"success": True}

    except HTTPException:
        # Re-raise HTTP exceptions (including 409 from assert_can_resolve)
        raise
    except Exception as e:
        logger.error({"event": "approve_approval_error", "approval_id": approval_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e), "code": "INTERNAL_ERROR"},
        )


@router.post("/{approval_id}/reject", status_code=status.HTTP_200_OK)
async def reject_approval(
    current_user: CurrentUser,
    approval_id: str,
    body: ApprovalResolve,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Reject an approval request.

    Path params:
        approval_id: UUID of approval to reject

    Request body:
        note: Optional note from user

    Action:
        - Mark approval as rejected
        - Set resolved_at timestamp
        - The paused run gets status="failed" with error="User rejected approval"

    The original run is NOT continued - no child run is created.
    """
    try:
        # Get approval with proper eager loading
        approval = await get_approval_for_response(db, approval_id, str(current_user.id))

        if not approval:
            raise NotFoundException(f"Approval {approval_id} not found")

        # Enforce state transition guard BEFORE any side effects
        assert_can_resolve(approval)

        # Resolve the approval
        approval = await resolve_approval(
            db=db,
            approval_id=approval_id,
            user_id=str(current_user.id),
            approved=False,
            note=body.note,
        )

        # Side-effects block - wrapped in try/except so failures don't cause 500
        try:
            # Mark the original run as failed with user rejection reason
            if approval.run_id:
                await update_run(
                    db=db,
                    run_id=str(approval.run_id),
                    status="failed",
                    output=f"Rejected by user: {body.note if body.note else 'No reason provided'}",
                    finished_at=datetime.now(timezone.utc),
                )

                logger.info({
                    "event": "run_failed_after_rejection",
                    "approval_id": approval_id,
                    "run_id": str(approval.run_id),
                })

        except Exception as side_effect_error:
            # Side-effects failed, but the approval was committed successfully
            # Log the failure but don't crash the API response
            logger.error({
                "event": "approval_side_effect_failed",
                "approval_id": approval_id,
                "error": str(side_effect_error),
                "error_type": type(side_effect_error).__name__,
                "detail": "Approval was committed successfully, but run update failed",
            })
            # Do NOT raise - the approval succeeded, this is just a side-effect failure

        logger.info({
            "event": "approval_rejected",
            "approval_id": approval_id,
            "user_id": str(current_user.id),
        })

        return {"success": True}

    except HTTPException:
        # Re-raise HTTP exceptions (including 409 from assert_can_resolve)
        raise
    except Exception as e:
        logger.error({"event": "reject_approval_error", "approval_id": approval_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e), "code": "INTERNAL_ERROR"},
        )
