import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from app.models.run import Run
from app.models.agent import Agent
from app.schemas.run import RunCreate
from app.models.approval import Approval

logger = logging.getLogger("ocin")


async def create_run(
    db: AsyncSession,
    run_data: RunCreate,
) -> Run:
    """Create a new run record."""
    run = Run(
        user_id=run_data.user_id,
        agent_id=run_data.agent_id,
        schedule_id=run_data.schedule_id,
        input=run_data.input,
        status=run_data.status,
        parent_run_id=run_data.parent_run_id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info({"event": "create_run", "run_id": str(run.id), "agent_id": run.agent_id})
    return run


async def update_run(
    db: AsyncSession,
    run_id: str,
    status: Optional[str] = None,
    output: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tokens_used: Optional[int] = None,
    cost_usd: Optional[float] = None,
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    parent_run_id: Optional[str] = None,  # New child run for continuation
) -> Optional[Run]:
    """Update a run record.

    Args:
        db: Database session
        run_id: The run ID
        status: Optional new status (pending | running | success | failed | awaiting_approval)
        output: Optional new output
        tool_calls: Optional new tool call list
        tokens_used: Optional new token count
        cost_usd: Optional new cost
        error: Optional new error message
        started_at: Optional new start time
        finished_at: Optional new finish time
        parent_run_id: Optional parent run ID for continuation

    Returns:
        Updated Run object or None if not found

    Status Change Support:
        When setting status="awaiting_approval", run is paused but not blocked.
        When setting status="running", run continues from awaiting_approval state.
        When setting status="success", run completes normally.
        When setting status="failed" or "awaiting_approval", run is blocked and doesn't auto-continue.
    """
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()

    if not run:
        return None

    # Apply status update if provided
    if status is not None:
        run.status = status
    if output is not None:
        run.output = output
    if tool_calls is not None:
            run.tool_calls = tool_calls
    if tokens_used is not None:
            run.tokens_used = tokens_used
    if cost_usd is not None:
            run.cost_usd = cost_usd
    if error is not None:
            run.error = error
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at

    await db.commit()
    await db.refresh(run)

    logger.info({"event": "update_run", "run_id": str(run.id), "status": run.status})

    return run
    """Update a run record."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()

    if not run:
        return None

    if status is not None:
        run.status = status
    if output is not None:
        run.output = output
    if tool_calls is not None:
        run.tool_calls = tool_calls
    if tokens_used is not None:
        run.tokens_used = tokens_used
    if cost_usd is not None:
        run.cost_usd = cost_usd
    if error is not None:
        run.error = error
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at

    await db.commit()
    await db.refresh(run)

    logger.info({"event": "update_run", "run_id": str(run.id), "status": run.status})
    return run


async def list_runs(
    db: AsyncSession,
    user_id: str,
    skip: int = 0,
    limit: int = 50,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Run]:
    """List runs for a user."""
    query = select(Run).where(Run.user_id == user_id)
    if agent_id:
        query = query.where(Run.agent_id == agent_id)
    if status:
        query = query.where(Run.status == status)
    query = query.order_by(Run.started_at.desc().nullslast()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_run(db: AsyncSession, run_id: str, user_id: str) -> Optional[Run]:
    """Get a run by ID (user-scoped)."""
    result = await db.execute(
        select(Run).where(Run.id == run_id, Run.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def purge_old_runs() -> None:
    """Daily retention job. Tier 2 blanks heavy fields; Tier 3 deletes rows.

    Retention tiers:
    - Tier 1 (0-30 days): full row, no changes
    - Tier 2 (30-90 days): purge heavy fields (output, tool_calls, input), keep metadata
    - Tier 3 (>90 days): delete row entirely
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            cutoff_30 = datetime.now(timezone.utc) - timedelta(days=30)
            cutoff_90 = datetime.now(timezone.utc) - timedelta(days=90)

            # Tier 2: 30-90 days, blank heavy fields (only on rows that still have output)
            tier2 = await session.execute(
                update(Run)
                .where(
                    Run.finished_at < cutoff_30,
                    Run.finished_at >= cutoff_90,
                    Run.output.isnot(None),
                )
                .values(output=None, tool_calls=[], input=None)
            )

            # Tier 3: >90 days, delete
            tier3 = await session.execute(
                delete(Run).where(Run.finished_at < cutoff_90)
            )

            await session.commit()
            logger.info({
                "event": "runs_retention_purge",
                "tier2_purged_count": tier2.rowcount,
                "tier3_deleted_count": tier3.rowcount,
                "cutoff_30": cutoff_30.isoformat(),
                "cutoff_90": cutoff_90.isoformat(),
            })
        except Exception as e:
            await session.rollback()
            logger.error({"event": "runs_retention_purge_failed", "error": str(e)})


async def reconcile_orphaned_awaiting_runs() -> dict:
    """One-time cleanup for orphaned runs stuck in awaiting_approval.

    Finds runs where:
    - status = "awaiting_approval"
    - There's an approval with the same run_id whose status is now "approved" or "rejected"

    For each orphaned run:
    - If approval approved: set run status="success", finished_at=approval.resolved_at
    - If approval rejected: set run status="failed", finished_at=approval.resolved_at

    Returns:
        Dict with counts of fixed runs
    """
    from app.database import AsyncSessionLocal
    from datetime import timezone

    async with AsyncSessionLocal() as session:
        try:
            # Find orphaned runs: awaiting_approval with resolved approvals
            result = await session.execute(
                select(Run, Approval)
                .join(Approval, Run.id == Approval.run_id)
                .where(
                    Run.status == "awaiting_approval",
                    Approval.status.in_(["approved", "rejected"])
                )
            )

            fixed_success = 0
            fixed_failed = 0

            for run, approval in result:
                if approval.status == "approved":
                    run.status = "success"
                    run.output = f"Approved by user — continuation may not have executed (orphaned run fix). Original approval: {approval.id}"
                else:  # rejected
                    run.status = "failed"
                    run.output = f"Rejected by user (orphaned run fix). Original approval: {approval.id}"

                run.finished_at = approval.resolved_at
                fixed_success += 1 if approval.status == "approved" else 0
                fixed_failed += 1 if approval.status == "rejected" else 0

            await session.commit()

            logger.info({
                "event": "orphaned_awaiting_runs_reconciled",
                "fixed_success_count": fixed_success,
                "fixed_failed_count": fixed_failed,
                "total_fixed": fixed_success + fixed_failed,
            })

            return {
                "fixed_success": fixed_success,
                "fixed_failed": fixed_failed,
                "total_fixed": fixed_success + fixed_failed,
            }

        except Exception as e:
            await session.rollback()
            logger.error({"event": "reconcile_orphaned_runs_failed", "error": str(e)})
            return {"error": str(e)}
