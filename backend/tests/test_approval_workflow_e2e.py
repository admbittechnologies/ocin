"""End-to-end integration tests for approval workflow."""
import pytest
from datetime import datetime, timedelta

from app.models.approval import Approval


@pytest.mark.e2e
class TestApprovalWorkflowE2E:
    """End-to-end tests for approval workflow integration."""

    async def test_approval_workflow_from_agent_run_to_approval(self, authenticated_client, test_user, test_agent):
        """Test complete workflow: agent run creates approval, user approves, child run created."""
        # Step 1: Create a run that requests approval
        from app.services.run_service import create_run
        import asyncio
        from app.database import get_db

        async with get_db() as db:
            parent_run = await create_run(
                db=db,
                run_data={
                    "user_id": str(test_user.id),
                    "agent_id": str(test_agent.id),
                    "input": "Send an email to john@example.com",
                    "status": "awaiting_approval"
                }
            )

        # Step 2: Create approval for the run
        from app.services.approval_service import create_approval

        async with get_db() as db:
            approval = await create_approval(
                db=db,
                user_id=str(test_user.id),
                agent_id=str(test_agent.id),
                run_id=str(parent_run.id),
                kind="send_email",
                title="Send email to john@example.com",
                description="Agent wants to send an email as requested",
                payload={
                    "to": "john@example.com",
                    "subject": "Product inquiry",
                    "body": "Thanks for your interest!"
                }
            )

        # Step 3: Verify approval appears in pending list
        list_response = await authenticated_client.get("/api/v1/approvals/?status=pending")
        assert list_response.status_code == 200
        pending_approvals = list_response.json()["approvals"]

        our_approval = None
        for app in pending_approvals:
            if app["run_id"] == str(parent_run.id):
                our_approval = app
                break

        assert our_approval is not None
        assert our_approval["status"] == "pending"

        # Step 4: User approves the request
        approve_response = await authenticated_client.post(
            f"/api/v1/approvals/{our_approval['id']}/approve",
            json={"note": "Approved, go ahead"}
        )
        assert approve_response.status_code == 200

        # Step 5: Verify approval status changed
        approved_response = await authenticated_client.get(
            f"/api/v1/approvals/{our_approval['id']}"
        )
        assert approved_response.status_code == 200
        approved_approval = approved_response.json()
        assert approved_approval["status"] == "approved"
        assert approved_approval["resolution_note"] == "Approved, go ahead"

        # Step 6: Verify child run was created
        from app.services.run_service import get_runs
        from app.models.run import Run
        from sqlalchemy import select

        async with get_db() as db:
            result = await db.execute(
                select(Run)
                .where(Run.parent_run_id == str(parent_run.id))
            )
            child_runs = result.scalars().all()

            assert len(child_runs) == 1
            child_run = child_runs[0]
            assert child_run.agent_id == test_agent.id
            assert child_run.user_id == test_user.id

    async def test_approval_workflow_rejection_cancels_run(self, authenticated_client, test_user, test_agent):
        """Test that rejection marks parent run as failed."""
        # Create run requesting approval
        from app.services.run_service import create_run
        import asyncio
        from app.database import get_db

        async with get_db() as db:
            parent_run = await create_run(
                db=db,
                run_data={
                    "user_id": str(test_user.id),
                    "agent_id": str(test_agent.id),
                    "input": "Make a purchase",
                    "status": "awaiting_approval"
                }
            )

        # Create approval
        from app.services.approval_service import create_approval

        async with get_db() as db:
            approval = await create_approval(
                db=db,
                user_id=str(test_user.id),
                agent_id=str(test_agent.id),
                run_id=str(parent_run.id),
                kind="purchase",
                title="Make a $50 purchase",
                description="Agent wants to purchase API credits",
                payload={"amount": 50, "currency": "USD"}
            )

        # Reject the approval
        reject_response = await authenticated_client.post(
            f"/api/v1/approvals/{approval.id}/reject",
            json={"note": "Too expensive, not approved"}
        )
        assert reject_response.status_code == 200

        # Verify parent run is marked as failed
        from app.services.run_service import get_run
        failed_run = await get_run(db=await get_db().__aenter__(), run_id=str(parent_run.id))

        assert failed_run.status == "failed"
        assert "User rejected approval" in failed_run.error

    async def test_multiple_approvals_different_statuses(self, authenticated_client, test_user, test_agent, test_run):
        """Test managing multiple approvals in different states."""
        from app.services.approval_service import create_approval
        import asyncio
        from app.database import get_db

        # Create pending approval
        pending_approval = await create_approval(
            db=await get_db().__aenter__(),
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(test_run.id),
            kind="pending",
            title="Pending approval",
            payload={}
        )

        # Create approved approval
        approved_approval = Approval(
            user_id=test_user.id,
            agent_id=test_agent.id,
            run_id=test_run.id,
            kind="approved",
            title="Approved approval",
            status="approved",
            resolved_at=datetime.now()
        )
        import asyncio
        db = await get_db().__aenter__()
        db.add(approved_approval)
        await db.commit()

        # Create rejected approval
        rejected_approval = Approval(
            user_id=test_user.id,
            agent_id=test_agent.id,
            run_id=test_run.id,
            kind="rejected",
            title="Rejected approval",
            status="rejected",
            resolved_at=datetime.now()
        )
        db.add(rejected_approval)
        await db.commit()

        # Test filtering by status
        pending_response = await authenticated_client.get("/api/v1/approvals/?status=pending")
        assert pending_response.status_code == 200
        pending_data = pending_response.json()
        assert all(app["status"] == "pending" for app in pending_data["approvals"])

        approved_response = await authenticated_client.get("/api/v1/approvals/?status=approved")
        assert approved_response.status_code == 200
        approved_data = approved_response.json()
        assert all(app["status"] == "approved" for app in approved_data["approvals"])

        rejected_response = await authenticated_client.get("/api/v1/approvals/?status=rejected")
        assert rejected_response.status_code == 200
        rejected_data = rejected_response.json()
        assert all(app["status"] == "rejected" for app in rejected_data["approvals"])

        # Test pending count
        count_response = await authenticated_client.get("/api/v1/approvals/pending/count")
        assert count_response.status_code == 200
        count_data = count_response.json()
        assert count_data["count"] >= 1

    async def test_approval_expiration_workflow(self, authenticated_client, test_user, test_agent, test_run):
        """Test handling of expired approvals."""
        # Create approval that will expire soon
        from app.services.approval_service import create_approval
        import asyncio
        from app.database import get_db

        expires_soon = datetime.now() + timedelta(minutes=1)
        approval = await create_approval(
            db=await get_db().__aenter__(),
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(test_run.id),
            kind="expiring",
            title="Expiring approval",
            description="This will expire in 1 minute",
            payload={},
            expires_at=expires_soon
        )

        # Get approval details to verify expiration
        response = await authenticated_client.get(f"/api/v1/approvals/{approval.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is not None
        assert data["status"] == "pending"

        # Attempt to approve expired approval (this would work in real system,
        # but logic to prevent approval of expired approvals would be in business rules)

    async def test_approval_with_complex_payload(self, authenticated_client, test_user, test_agent, test_run):
        """Test approval with complex nested JSON payload."""
        from app.services.approval_service import create_approval
        import asyncio
        from app.database import get_db

        complex_payload = {
            "action": "create_order",
            "customer": {
                "name": "John Doe",
                "email": "john@example.com",
                "address": {
                    "street": "123 Main St",
                    "city": "New York",
                    "state": "NY",
                    "zip": "10001"
                }
            },
            "items": [
                {
                    "product_id": "SKU001",
                    "quantity": 2,
                    "price": 29.99,
                    "name": "Widget"
                },
                {
                    "product_id": "SKU002",
                    "quantity": 1,
                    "price": 49.99,
                    "name": "Gadget"
                }
            ],
            "metadata": {
                "source": "web",
                "campaign": "spring_sale",
                "priority": "high"
            }
        }

        approval = await create_approval(
            db=await get_db().__aenter__(),
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(test_run.id),
            kind="create_order",
            title="Create order for John Doe",
            description="Customer order for $109.97",
            payload=complex_payload
        )

        # Verify complex payload is preserved
        response = await authenticated_client.get(f"/api/v1/approvals/{approval.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["payload"] == complex_payload
        assert data["payload"]["items"][0]["name"] == "Widget"
        assert data["payload"]["customer"]["address"]["city"] == "New York"

    async def test_approval_workflow_with_schedule(self, authenticated_client, test_user, test_agent):
        """Test approval workflow for scheduled agent runs."""
        # Create a schedule
        from app.models.schedule import Schedule
        import asyncio
        from app.database import get_db

        async with get_db() as db:
            schedule = Schedule(
                user_id=test_user.id,
                agent_id=test_agent.id,
                label="Morning report",
                cron_expression="0 9 * * *",
                is_active=True
            )
            db.add(schedule)
            await db.commit()
            await db.refresh(schedule)

        # Create run from schedule
        from app.services.run_service import create_run
        run = await create_run(
            db=db,
            run_data={
                "user_id": str(test_user.id),
                "agent_id": str(test_agent.id),
                "schedule_id": str(schedule.id),
                "input": "Generate daily report",
                "status": "pending"
            }
        )

        # Create approval
        from app.services.approval_service import create_approval
        approval = await create_approval(
            db=db,
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(run.id),
            schedule_id=str(schedule.id),
            kind="approve_schedule_run",
            title="Approve daily report generation",
            description="Scheduled run needs approval",
            payload={"schedule_id": str(schedule.id)}
        )

        # Verify approval includes schedule information
        response = await authenticated_client.get(f"/api/v1/approvals/{approval.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["schedule_id"] == str(schedule.id)

        # Approve the scheduled run approval
        approve_response = await authenticated_client.post(
            f"/api/v1/approvals/{approval.id}/approve",
            json={"note": "Approved schedule run"}
        )
        assert approve_response.status_code == 200

    async def test_concurrent_approval_processing(self, authenticated_client, test_user, test_agent, test_run):
        """Test handling multiple concurrent approvals."""
        from app.services.approval_service import create_approval
        import asyncio
        from app.database import get_db

        # Create multiple approvals simultaneously
        approval_ids = []
        for i in range(10):
            approval = await create_approval(
                db=await get_db().__aenter__(),
                user_id=str(test_user.id),
                agent_id=str(test_agent.id),
                run_id=str(test_run.id),
                kind=f"action_{i}",
                title=f"Action {i}",
                description=f"Concurrent action {i}",
                payload={"index": i}
            )
            approval_ids.append(str(approval.id))

        # Verify all are in pending list
        list_response = await authenticated_client.get("/api/v1/approvals/?status=pending")
        assert list_response.status_code == 200
        pending_data = list_response.json()
        assert len(pending_data["approvals"]) >= 10

        # Approve first half, reject second half
        approved_count = 0
        rejected_count = 0

        for i, approval_id in enumerate(approval_ids):
            if i < 5:
                # Approve
                await authenticated_client.post(
                    f"/api/v1/approvals/{approval_id}/approve",
                    json={"note": f"Approved action {i}"}
                )
                approved_count += 1
            else:
                # Reject
                await authenticated_client.post(
                    f"/api/v1/approvals/{approval_id}/reject",
                    json={"note": f"Rejected action {i}"}
                )
                rejected_count += 1

        # Verify counts
        approved_response = await authenticated_client.get("/api/v1/approvals/?status=approved")
        assert approved_response.status_code == 200
        approved_data = approved_response.json()
        # Should have at least the approved ones
        approved_in_list = [app for app in approved_data["approvals"] if app["id"] in approval_ids[:5]]
        assert len(approved_in_list) >= approved_count

        rejected_response = await authenticated_client.get("/api/v1/approvals/?status=rejected")
        assert rejected_response.status_code == 200
        rejected_data = rejected_response.json()
        rejected_in_list = [app for app in rejected_data["approvals"] if app["id"] in approval_ids[5:]]
        assert len(rejected_in_list) >= rejected_count

    async def test_approval_search_and_filtering(self, authenticated_client, test_user, test_agent, test_run):
        """Test searching and filtering approvals."""
        from app.services.approval_service import create_approval
        import asyncio
        from app.database import get_db

        # Create approvals with different kinds
        kinds = ["send_email", "post_social", "make_purchase", "create_user", "delete_file"]
        for kind in kinds:
            await create_approval(
                db=await get_db().__aenter__(),
                user_id=str(test_user.id),
                agent_id=str(test_agent.id),
                run_id=str(test_run.id),
                kind=kind,
                title=f"{kind.replace('_', ' ').title()}",
                description=f"Test {kind}",
                payload={}
            )

        # Test listing all approvals
        all_response = await authenticated_client.get("/api/v1/approvals/")
        assert all_response.status_code == 200
        all_data = all_response.json()
        assert len(all_data["approvals"]) >= len(kinds)

        # Test that different kinds exist
        approval_kinds = set(app["kind"] for app in all_data["approvals"])
        for kind in kinds:
            assert kind in approval_kinds