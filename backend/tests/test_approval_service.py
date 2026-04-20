"""Service layer tests for approval operations."""
import pytest
from datetime import datetime, timedelta

from app.services.approval_service import (
    create_approval,
    list_approvals,
    get_approval,
    approve_approval,
    reject_approval,
    count_pending,
    resolve_approval,
)
from app.core.exceptions import NotFoundException


@pytest.mark.unit
class TestCreateApproval:
    """Test approval creation."""

    async def test_create_approval_minimal(self, db_session, test_user, test_agent, test_run):
        """Test creating approval with minimal required fields."""
        approval = await create_approval(
            db=db_session,
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(test_run.id),
            kind="send_email",
            title="Send test email",
            description=None,
            payload={"to": "test@example.com"}
        )

        await db_session.refresh(approval)

        assert approval.id is not None
        assert approval.user_id == test_user.id
        assert approval.agent_id == test_agent.id
        assert approval.run_id == test_run.id
        assert approval.kind == "send_email"
        assert approval.title == "Send test email"
        assert approval.description is None
        assert approval.payload == {"to": "test@example.com"}
        assert approval.status == "pending"

    async def test_create_approval_with_schedule(self, db_session, test_user, test_agent, test_run):
        """Test creating approval with schedule_id."""
        # Create a schedule for testing
        from app.models.schedule import Schedule
        schedule = Schedule(
            user_id=test_user.id,
            agent_id=test_agent.id,
            label="Test schedule",
            cron_expression="0 9 * * *",
            is_active=True
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        approval = await create_approval(
            db=db_session,
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(test_run.id),
            kind="test",
            title="Test with schedule",
            description=None,
            payload={},
            schedule_id=str(schedule.id)
        )

        await db_session.refresh(approval)

        assert approval.schedule_id == schedule.id

    async def test_create_approval_sets_pending_status(self, db_session, test_user, test_agent, test_run):
        """Test that new approvals default to pending status."""
        approval = await create_approval(
            db=db_session,
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(test_run.id),
            kind="test",
            title="Test status",
            description=None,
            payload={}
        )

        assert approval.status == "pending"


@pytest.mark.unit
class TestListApprovals:
    """Test approval listing."""

    async def test_list_pending_approvals(self, db_session, test_user, test_approval):
        """Test listing pending approvals for user."""
        approvals = await list_approvals(
            db=db_session,
            user_id=str(test_user.id),
            status="pending"
        )

        assert len(approvals) >= 1
        assert all(approval.status == "pending" for approval in approvals)

    async def test_list_approvals_empty_for_different_user(self, db_session, test_approval):
        """Test that users can't see other users' approvals."""
        # Create a different user
        from app.core.security import hash_password
        from app.models.user import User
        other_user = User(
            email="other@example.com",
            hashed_password=get_password_hash("password"),
            plan="free"
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        approvals = await list_approvals(
            db=db_session,
            user_id=str(other_user.id),
            status="pending"
        )

        assert len(approvals) == 0

    async def test_list_approvals_with_pagination(self, db_session, test_user, test_agent, test_run):
        """Test approval listing with pagination."""
        # Create multiple approvals
        for i in range(10):
            approval = Approval(
                user_id=test_user.id,
                agent_id=test_agent.id,
                run_id=test_run.id,
                kind=f"test_{i}",
                title=f"Test {i}",
                payload={}
            )
            db_session.add(approval)
        await db_session.commit()

        # Test pagination
        approvals = await list_approvals(
            db=db_session,
            user_id=str(test_user.id),
            status="pending",
            skip=0,
            limit=5
        )

        assert len(approvals) == 5

    async def test_list_approved_approvals(self, db_session, test_user, test_approval):
        """Test listing approved approvals."""
        # Create an approved approval
        approved_approval = Approval(
            user_id=test_user.id,
            agent_id=test_approval.agent_id,
            run_id=test_approval.run_id,
            kind="approved_test",
            title="Approved test",
            status="approved",
            resolved_at=datetime.now()
        )
        db_session.add(approved_approval)
        await db_session.commit()

        approvals = await list_approvals(
            db=db_session,
            user_id=str(test_user.id),
            status="approved"
        )

        assert len(approvals) == 1
        assert approvals[0].status == "approved"

    async def test_list_all_approvals_without_status_filter(self, db_session, test_user, test_approval):
        """Test listing all approvals when no status filter is provided."""
        # Create approvals with different statuses
        pending_approval = Approval(
            user_id=test_user.id,
            agent_id=test_approval.agent_id,
            run_id=test_approval.run_id,
            kind="pending_test",
            title="Pending",
            status="pending"
        )
        approved_approval = Approval(
            user_id=test_user.id,
            agent_id=test_approval.agent_id,
            run_id=test_approval.run_id,
            kind="approved_test",
            title="Approved",
            status="approved",
            resolved_at=datetime.now()
        )
        db_session.add(pending_approval)
        db_session.add(approved_approval)
        await db_session.commit()

        approvals = await list_approvals(
            db=db_session,
            user_id=str(test_user.id),
            status=None  # No filter
        )

        assert len(approvals) >= 2


@pytest.mark.unit
class TestGetApproval:
    """Test getting a specific approval."""

    async def test_get_approval_by_id(self, db_session, test_user, test_approval):
        """Test getting approval by ID."""
        approval = await get_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id)
        )

        assert approval.id == test_approval.id
        assert approval.kind == test_approval.kind
        assert approval.title == test_approval.title

    async def test_get_approval_not_found(self, db_session, test_user):
        """Test getting non-existent approval raises NotFoundException."""
        import uuid
        fake_id = uuid.uuid4()

        with pytest.raises(NotFoundException, match=f"Approval {fake_id} not found"):
            await get_approval(
                db=db_session,
                approval_id=str(fake_id),
                user_id=str(test_user.id)
            )

    async def test_get_approval_different_user_raises_exception(self, db_session, test_approval):
        """Test that users can't access other users' approvals."""
        from app.core.security import hash_password
        from app.models.user import User
        other_user = User(
            email="other@example.com",
            hashed_password=get_password_hash("password"),
            plan="free"
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        with pytest.raises(NotFoundException):
            await get_approval(
                db=db_session,
                approval_id=str(test_approval.id),
                user_id=str(other_user.id)
            )

    async def test_get_approval_loads_agent_relationship(self, db_session, test_user, test_approval):
        """Test that get_approval loads agent relationship."""
        approval = await get_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id)
        )

        # Access agent without triggering additional queries
        if approval.agent:
            assert approval.agent.name is not None


@pytest.mark.unit
class TestApproveApproval:
    """Test approval action."""

    async def test_approve_approval(self, db_session, test_user, test_approval):
        """Test approving an approval."""
        approved_approval = await approve_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id),
            note="Approved for testing"
        )

        await db_session.refresh(approved_approval)

        assert approved_approval.status == "approved"
        assert approved_approval.resolution_note == "Approved for testing"
        assert approved_approval.resolved_at is not None

    async def test_approve_without_note(self, db_session, test_user, test_approval):
        """Test approving without providing a note."""
        approved_approval = await approve_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id),
            note=None
        )

        await db_session.refresh(approved_approval)

        assert approved_approval.status == "approved"
        assert approved_approval.resolution_note is None
        assert approved_approval.resolved_at is not None

    async def test_approve_nonexistent_approval(self, db_session, test_user):
        """Test approving non-existent approval raises exception."""
        import uuid
        fake_id = uuid.uuid4()

        with pytest.raises(NotFoundException):
            await approve_approval(
                db=db_session,
                approval_id=str(fake_id),
                user_id=str(test_user.id)
            )


@pytest.mark.unit
class TestRejectApproval:
    """Test rejection action."""

    async def test_reject_approval(self, db_session, test_user, test_approval):
        """Test rejecting an approval."""
        rejected_approval = await reject_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id),
            note="Insufficient information"
        )

        await db_session.refresh(rejected_approval)

        assert rejected_approval.status == "rejected"
        assert rejected_approval.resolution_note == "Insufficient information"
        assert rejected_approval.resolved_at is not None

    async def test_reject_without_note(self, db_session, test_user, test_approval):
        """Test rejecting without providing a note."""
        rejected_approval = await reject_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id),
            note=None
        )

        await db_session.refresh(rejected_approval)

        assert rejected_approval.status == "rejected"
        assert rejected_approval.resolution_note is None
        assert rejected_approval.resolved_at is not None

    async def test_reject_nonexistent_approval(self, db_session, test_user):
        """Test rejecting non-existent approval raises exception."""
        import uuid
        fake_id = uuid.uuid4()

        with pytest.raises(NotFoundException):
            await reject_approval(
                db=db_session,
                approval_id=str(fake_id),
                user_id=str(test_user.id)
            )


@pytest.mark.unit
class TestCountPending:
    """Test counting pending approvals."""

    async def test_count_pending_approvals(self, db_session, test_user, test_agent, test_run):
        """Test counting pending approvals."""
        # Create multiple pending approvals
        for i in range(5):
            approval = Approval(
                user_id=test_user.id,
                agent_id=test_agent.id,
                run_id=test_run.id,
                kind=f"test_{i}",
                title=f"Test {i}",
                payload={}
            )
            db_session.add(approval)
        await db_session.commit()

        count = await count_pending(
            db=db_session,
            user_id=str(test_user.id)
        )

        assert count >= 5

    async def test_count_pending_zero_for_different_user(self, db_session, test_approval):
        """Test that count is zero for users with no approvals."""
        from app.core.security import hash_password
        from app.models.user import User
        other_user = User(
            email="other@example.com",
            hashed_password=get_password_hash("password"),
            plan="free"
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        count = await count_pending(
            db=db_session,
            user_id=str(other_user.id)
        )

        assert count == 0


@pytest.mark.unit
class TestResolveApproval:
    """Test resolve approval function (approve/reject)."""

    async def test_resolve_to_approve(self, db_session, test_user, test_approval):
        """Test resolving approval to approved status."""
        resolved = await resolve_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id),
            approved=True,
            note="Great choice!"
        )

        await db_session.refresh(resolved)

        assert resolved.status == "approved"
        assert resolved.resolution_note == "Great choice!"

    async def test_resolve_to_reject(self, db_session, test_user, test_approval):
        """Test resolving approval to rejected status."""
        resolved = await resolve_approval(
            db=db_session,
            approval_id=str(test_approval.id),
            user_id=str(test_user.id),
            approved=False,
            note="Not ready yet"
        )

        await db_session.refresh(resolved)

        assert resolved.status == "rejected"
        assert resolved.resolution_note == "Not ready yet"

    async def test_resolve_nonexistent_approval(self, db_session, test_user):
        """Test resolving non-existent approval raises exception."""
        import uuid
        fake_id = uuid.uuid4()

        with pytest.raises(NotFoundException):
            await resolve_approval(
                db=db_session,
                approval_id=str(fake_id),
                user_id=str(test_user.id),
                approved=True
            )


@pytest.mark.unit
class TestGetPendingApprovalsCount:
    """Test get_pending_approvals_count alias function."""

    async def test_get_pending_approvals_count(self, db_session, test_user, test_agent, test_run):
        """Test get_pending_approvals_count works as alias."""
        # Create some pending approvals
        for i in range(3):
            approval = Approval(
                user_id=test_user.id,
                agent_id=test_agent.id,
                run_id=test_run.id,
                kind=f"test_{i}",
                title=f"Test {i}",
                payload={}
            )
            db_session.add(approval)
        await db_session.commit()

        count = await get_pending_approvals_count(
            db=db_session,
            user_id=str(test_user.id)
        )

        assert count >= 3