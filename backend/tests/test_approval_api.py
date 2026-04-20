"""API endpoint tests for approval operations."""
import pytest
from datetime import datetime, timedelta

from app.models.approval import Approval


@pytest.mark.integration
class TestListApprovalsEndpoint:
    """Test GET /api/v1/approvals endpoint."""

    async def test_list_approvals_authenticated(self, authenticated_client, test_approval):
        """Test listing approvals with authentication."""
        response = await authenticated_client.get("/api/v1/approvals/")

        assert response.status_code == 200
        data = response.json()
        assert "approvals" in data
        assert len(data["approvals"]) >= 1

    async def test_list_approvals_unauthenticated(self, client):
        """Test listing approvals without authentication fails."""
        response = await client.get("/api/v1/approvals/")

        assert response.status_code == 401

    async def test_list_approvals_with_status_filter(self, authenticated_client, test_user, test_agent, test_run):
        """Test filtering approvals by status."""
        # Create approved approval
        approved_approval = Approval(
            user_id=test_user.id,
            agent_id=test_agent.id,
            run_id=test_run.id,
            kind="approved_test",
            title="Approved test",
            status="approved",
            resolved_at=datetime.now()
        )
        import asyncio
        from app.database import get_db
        async with get_db() as db:
            db.add(approved_approval)
            await db.commit()

        # Test pending filter
        pending_response = await authenticated_client.get("/api/v1/approvals/?status=pending")
        assert pending_response.status_code == 200
        pending_data = pending_response.json()
        assert all(app["status"] == "pending" for app in pending_data["approvals"])

        # Test approved filter
        approved_response = await authenticated_client.get("/api/v1/approvals/?status=approved")
        assert approved_response.status_code == 200
        approved_data = approved_response.json()
        assert all(app["status"] == "approved" for app in approved_data["approvals"])

    async def test_list_approvals_with_pagination(self, authenticated_client, test_user, test_agent, test_run):
        """Test pagination of approvals."""
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
            import asyncio
            from app.database import get_db
            async with get_db() as db:
                db.add(approval)
                await db.commit()

        # Test first page
        response = await authenticated_client.get("/api/v1/approvals/?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["approvals"]) == 5

    async def test_list_approvals_response_structure(self, authenticated_client, test_approval):
        """Test that response has correct structure."""
        response = await authenticated_client.get("/api/v1/approvals/")

        assert response.status_code == 200
        data = response.json()

        # Check overall structure
        assert "approvals" in data
        assert isinstance(data["approvals"], list)

        if len(data["approvals"]) > 0:
            approval = data["approvals"][0]
            # Check approval fields
            required_fields = [
                "id", "user_id", "agent_id", "run_id",
                "kind", "title", "description", "payload",
                "status", "created_at"
            ]
            for field in required_fields:
                assert field in approval


@pytest.mark.integration
class TestPendingCountEndpoint:
    """Test GET /api/v1/approvals/pending/count endpoint."""

    async def test_pending_count_authenticated(self, authenticated_client, test_user, test_agent, test_run):
        """Test getting pending approval count."""
        # Create pending approvals
        for i in range(5):
            approval = Approval(
                user_id=test_user.id,
                agent_id=test_agent.id,
                run_id=test_run.id,
                kind=f"test_{i}",
                title=f"Test {i}",
                payload={}
            )
            import asyncio
            from app.database import get_db
            async with get_db() as db:
                db.add(approval)
                await db.commit()

        response = await authenticated_client.get("/api/v1/approvals/pending/count")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] >= 5

    async def test_pending_count_unauthenticated(self, client):
        """Test pending count without authentication fails."""
        response = await client.get("/api/v1/approvals/pending/count")

        assert response.status_code == 401

    async def test_pending_count_zero(self, authenticated_client):
        """Test pending count when no pending approvals."""
        response = await authenticated_client.get("/api/v1/approvals/pending/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0


@pytest.mark.integration
class TestGetApprovalEndpoint:
    """Test GET /api/v1/approvals/{approval_id} endpoint."""

    async def test_get_approval_authenticated(self, authenticated_client, test_approval):
        """Test getting specific approval."""
        response = await authenticated_client.get(f"/api/v1/approvals/{test_approval.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_approval.id)
        assert data["kind"] == test_approval.kind
        assert data["title"] == test_approval.title

    async def test_get_approval_unauthenticated(self, client, test_approval):
        """Test getting approval without authentication fails."""
        response = await client.get(f"/api/v1/approvals/{test_approval.id}")

        assert response.status_code == 401

    async def test_get_approval_not_found(self, authenticated_client):
        """Test getting non-existent approval returns 404."""
        import uuid
        fake_id = uuid.uuid4()

        response = await authenticated_client.get(f"/api/v1/approvals/{fake_id}")

        assert response.status_code == 404

    async def test_get_approval_different_user(self, client, auth_token, test_approval):
        """Test users can't access other users' approvals."""
        # Create another user and get their token
        from app.core.security import hash_password, create_access_token
        from app.models.user import User
        import asyncio
        from app.database import get_db

        async with get_db() as db:
            other_user = User(
                email="other@example.com",
                hashed_password=get_password_hash("password"),
                plan="free"
            )
            db.add(other_user)
            await db.commit()
            await db.refresh(other_user)

        other_token = create_access_token(data={"sub": str(other_user.id)})
        other_client = client
        other_client.headers.update({"Authorization": f"Bearer {other_token}"})

        response = await other_client.get(f"/api/v1/approvals/{test_approval.id}")

        assert response.status_code == 404


@pytest.mark.integration
class TestApproveApprovalEndpoint:
    """Test POST /api/v1/approvals/{approval_id}/approve endpoint."""

    async def test_approve_approval_authenticated(self, authenticated_client, test_approval):
        """Test approving an approval."""
        response = await authenticated_client.post(
            f"/api/v1/approvals/{test_approval.id}/approve",
            json={"note": "Approved for testing"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_approve_approval_unauthenticated(self, client, test_approval):
        """Test approving without authentication fails."""
        response = await client.post(
            f"/api/v1/approvals/{test_approval.id}/approve",
            json={}
        )

        assert response.status_code == 401

    async def test_approve_approval_with_note(self, authenticated_client, test_approval):
        """Test approving with a note."""
        response = await authenticated_client.post(
            f"/api/v1/approvals/{test_approval.id}/approve",
            json={"note": "Great choice!"}
        )

        assert response.status_code == 200

    async def test_approve_approval_without_note(self, authenticated_client, test_approval):
        """Test approving without providing a note."""
        response = await authenticated_client.post(
            f"/api/v1/approvals/{test_approval.id}/approve",
            json={}
        )

        assert response.status_code == 200

    async def test_approve_approval_not_found(self, authenticated_client):
        """Test approving non-existent approval."""
        import uuid
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"/api/v1/approvals/{fake_id}/approve",
            json={}
        )

        assert response.status_code == 500

    async def test_approve_different_user(self, client, auth_token, test_approval):
        """Test users can't approve other users' approvals."""
        # Create another user
        from app.core.security import hash_password, create_access_token
        from app.models.user import User
        import asyncio
        from app.database import get_db

        async with get_db() as db:
            other_user = User(
                email="other@example.com",
                hashed_password=get_password_hash("password"),
                plan="free"
            )
            db.add(other_user)
            await db.commit()
            await db.refresh(other_user)

        other_token = create_access_token(data={"sub": str(other_user.id)})
        other_client = client
        other_client.headers.update({"Authorization": f"Bearer {other_token}"})

        response = await other_client.post(
            f"/api/v1/approvals/{test_approval.id}/approve",
            json={}
        )

        assert response.status_code == 500


@pytest.mark.integration
class TestRejectApprovalEndpoint:
    """Test POST /api/v1/approvals/{approval_id}/reject endpoint."""

    async def test_reject_approval_authenticated(self, authenticated_client, test_approval):
        """Test rejecting an approval."""
        response = await authenticated_client.post(
            f"/api/v1/approvals/{test_approval.id}/reject",
            json={"note": "Not ready yet"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_reject_approval_unauthenticated(self, client, test_approval):
        """Test rejecting without authentication fails."""
        response = await client.post(
            f"/api/v1/approvals/{test_approval.id}/reject",
            json={}
        )

        assert response.status_code == 401

    async def test_reject_approval_with_note(self, authenticated_client, test_approval):
        """Test rejecting with a note."""
        response = await authenticated_client.post(
            f"/api/v1/approvals/{test_approval.id}/reject",
            json={"note": "Insufficient information"}
        )

        assert response.status_code == 200

    async def test_reject_approval_without_note(self, authenticated_client, test_approval):
        """Test rejecting without providing a note."""
        response = await authenticated_client.post(
            f"/api/v1/approvals/{test_approval.id}/reject",
            json={}
        )

        assert response.status_code == 200

    async def test_reject_approval_not_found(self, authenticated_client):
        """Test rejecting non-existent approval."""
        import uuid
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"/api/v1/approvals/{fake_id}/reject",
            json={}
        )

        assert response.status_code == 500


@pytest.mark.integration
class TestApprovalWorkflowIntegration:
    """Integration tests for complete approval workflow."""

    async def test_complete_approval_workflow(self, authenticated_client, test_user, test_agent, test_run):
        """Test complete workflow: create -> list -> approve -> verify."""
        # Step 1: Create approval
        from app.services.approval_service import create_approval
        import asyncio
        from app.database import get_db

        async with get_db() as db:
            approval = await create_approval(
                db=db,
                user_id=str(test_user.id),
                agent_id=str(test_agent.id),
                run_id=str(test_run.id),
                kind="send_email",
                title="Send test email",
                description="This is a test email",
                payload={"to": "test@example.com"}
            )

        # Step 2: List approvals and find our approval
        list_response = await authenticated_client.get("/api/v1/approvals/")
        assert list_response.status_code == 200
        approvals_data = list_response.json()

        our_approval = None
        for app in approvals_data["approvals"]:
            if app["title"] == "Send test email":
                our_approval = app
                break

        assert our_approval is not None
        assert our_approval["status"] == "pending"

        # Step 3: Get specific approval details
        get_response = await authenticated_client.get(f"/api/v1/approvals/{our_approval['id']}")
        assert get_response.status_code == 200
        approval_detail = get_response.json()
        assert approval_detail["title"] == "Send test email"
        assert approval_detail["payload"] == {"to": "test@example.com"}

        # Step 4: Approve the approval
        approve_response = await authenticated_client.post(
            f"/api/v1/approvals/{our_approval['id']}/approve",
            json={"note": "Approved!"}
        )
        assert approve_response.status_code == 200

        # Step 5: Verify approval is now approved
        final_response = await authenticated_client.get("/api/v1/approvals/?status=approved")
        assert final_response.status_code == 200
        approved_approvals = final_response.json()["approvals"]

        approved_ours = None
        for app in approved_approvals:
            if app["id"] == our_approval["id"]:
                approved_ours = app
                break

        assert approved_ours is not None
        assert approved_ours["status"] == "approved"

    async def test_rejection_workflow(self, authenticated_client, test_user, test_agent, test_run):
        """Test complete rejection workflow."""
        # Create approval
        from app.services.approval_service import create_approval
        import asyncio
        from app.database import get_db

        async with get_db() as db:
            approval = await create_approval(
                db=db,
                user_id=str(test_user.id),
                agent_id=str(test_agent.id),
                run_id=str(test_run.id),
                kind="test",
                title="Test rejection",
                description="This should be rejected",
                payload={}
            )

        # Reject the approval
        reject_response = await authenticated_client.post(
            f"/api/v1/approvals/{approval.id}/reject",
            json={"note": "Not acceptable"}
        )
        assert reject_response.status_code == 200

        # Verify rejection
        final_response = await authenticated_client.get("/api/v1/approvals/?status=rejected")
        assert final_response.status_code == 200
        rejected_approvals = final_response.json()["approvals"]

        rejected_ours = None
        for app in rejected_approvals:
            if app["id"] == str(approval.id):
                rejected_ours = app
                break

        assert rejected_ours is not None
        assert rejected_ours["status"] == "rejected"
        assert rejected_ours["resolution_note"] == "Not acceptable"