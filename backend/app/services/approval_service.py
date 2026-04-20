"""Service layer for approval CRUD operations."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
import logging

from app.models.approval import Approval
from app.models.agent import Agent
from app.core.exceptions import NotFoundException

logger = logging.getLogger(__name__)


async def create_approval(
    db: AsyncSession,
    user_id: str,
    agent_id: str,
    run_id: str,
    kind: str,
    title: str,
    description: Optional[str],
    payload: dict,
    schedule_id: Optional[str] = None,
) -> Approval:
    """Create a new approval record."""
    approval = Approval(
        user_id=user_id,
        agent_id=agent_id,
        run_id=run_id,
        schedule_id=schedule_id,
        kind=kind,
        title=title,
        description=description,
        payload=payload,
        status="awaiting_approval",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval


async def list_approvals(
    db: AsyncSession,
    user_id: str,
    status: str = "awaiting_approval",
    skip: int = 0,
    limit: int = 100,
) -> List[Approval]:
    """List approvals for a user with filtering."""
    # Log incoming parameters for debugging
    logger.info({
        "event": "list_approvals_called",
        "user_id": user_id,
        "user_id_type": type(user_id).__name__,
        "user_id_value": str(user_id),  # Log actual value to see if it's being transformed
        "status_filter": status,
    })

    # Use explicit parameter binding to avoid any string interpolation issues
    query = (
        select(Approval)
        .where(Approval.user_id == user_id)
        .options(selectinload(Approval.agent))  # Load agent for name resolution
    )
    
    if status:
        query = query.where(Approval.status == status)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def get_approval(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
) -> Approval:
    """Get a specific approval by ID, ensuring user ownership."""
    query = (
        select(Approval)
        .where(and_(Approval.id == approval_id, Approval.user_id == user_id))
        .options(selectinload(Approval.agent))
    )
    result = await db.execute(query)
    approval = result.scalar_one_or_none()

    if not approval:
        raise NotFoundException(f"Approval {approval_id} not found")

    return approval


async def approve_approval(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
    note: Optional[str] = None,
) -> Approval:
    """Mark an approval as approved."""
    approval = await get_approval(db, approval_id, user_id)
    approval.status = "approved"
    approval.resolved_at = func.now()
    approval.resolution_note = note
    await db.commit()
    await db.refresh(approval)
    return approval


async def reject_approval(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
    note: Optional[str] = None,
) -> Approval:
    """Mark an approval as rejected."""
    approval = await get_approval(db, approval_id, user_id)
    approval.status = "rejected"
    approval.resolved_at = func.now()
    approval.resolution_note = note
    await db.commit()
    await db.refresh(approval)
    return approval


async def count_pending(
    db: AsyncSession,
    user_id: str,
) -> int:
    """Count pending approvals for a user."""
    query = (
        select(func.count())
        .where(and_(Approval.user_id == user_id, Approval.status == "awaiting_approval"))
    )
    result = await db.execute(query)
    return result.scalar() or 0


async def get_pending_approvals_count(
    db: AsyncSession,
    user_id: str,
) -> int:
    """Alias for count_pending for consistency."""
    return await count_pending(db, user_id)


async def request_approval_with_continuation(
    db: AsyncSession,
    user_id: str,
    agent_id: str,
    run_id: str,
    kind: str,
    title: str,
    payload: dict,
    schedule_id: Optional[str] = None,
    description: Optional[str] = None,
) -> Approval:
    """Request approval with continuation mechanism built in.

    Creates an approval request and sets status to 'awaiting_approval',
    then waits for user decision using the wait_for_approval polling mechanism.
    """
    approval = Approval(
        user_id=user_id,
        agent_id=agent_id,
        run_id=run_id,
        schedule_id=schedule_id,
        kind=kind,
        title=title,
        description=description,
        payload=payload,
        status="awaiting_approval",  # Set to awaiting status for wait_for_approval
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    logger.info({
        "event": "approval_created_with_continuation",
        "approval_id": str(approval.id),
        "run_id": run_id,
        "kind": kind,
        "user_id": user_id,
    })

    return approval


async def wait_for_approval(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
    timeout: int = 300,
) -> Approval:
    """Wait for an approval to be resolved (approved or rejected).

    Polls the approval status until it changes from 'pending' to 'approved' or 'rejected',
    or until timeout is reached.

    Args:
        db: Database session
        approval_id: UUID of approval to wait for
        user_id: Current user ID
        timeout: Maximum seconds to wait before timing out

    Returns:
        The approval record with final status

    Raises:
        Exception: If approval is not found or times out
    """
    import time
    import asyncio

    start_time = time.time()

    while True:
        # Refresh approval status
        approval = await get_approval(db, approval_id, user_id)

        if not approval:
            raise Exception(f"Approval {approval_id} not found")

        if approval.status in ("approved", "rejected", "expired"):
            # Approval resolved - return final status
            return approval

        # Check timeout
        if time.time() - start_time > timeout:
            # Timeout - mark as expired
            approval.status = "expired"
            approval.resolution_note = f"Approval request timed out after {timeout} seconds"
            await db.commit()
            await db.refresh(approval)
            logger.info({
                "event": "approval_timeout",
                "approval_id": approval_id,
                "user_id": user_id,
            })
            return approval

        # Still pending - wait before polling again
        await asyncio.sleep(2)


async def resolve_approval(
    db: AsyncSession,
    approval_id: str,
    user_id: str,
    approved: bool,
    note: Optional[str] = None,
) -> Approval:
    """Mark an approval as approved or rejected using continuation mechanism.

    The approval request should have been created via request_approval_with_continuation,
    which sets status to 'awaiting_approval'. This function waits for user decision
    and then resolves the approval to 'approved' or 'rejected'.
    """
    approval = await get_approval(db, approval_id, user_id)

    if not approval:
        raise Exception(f"Approval {approval_id} not found")

    # Approval should be in awaiting_approval status if we're resolving it
    if approval.status != "awaiting_approval":
        logger.warning({
            "event": "resolve_approval_invalid_status",
            "approval_id": approval_id,
            "current_status": approval.status,
            "expected_status": "awaiting_approval",
        })
        # Still proceed to update anyway, but log warning
        # This handles edge case where approval was already approved/rejected

    approval.status = "approved" if approved else "rejected"
    approval.resolved_at = func.now()
    approval.resolution_note = note
    await db.commit()
    await db.refresh(approval)

    logger.info({
        "event": "approval_resolved",
        "approval_id": str(approval.id),
        "user_id": str(approval.user_id),
        "status": approval.status,
        "note": note,
    })

    return approval
