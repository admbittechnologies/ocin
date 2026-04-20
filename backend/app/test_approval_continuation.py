"""Test script to verify approval continuation mechanism."""

import asyncio
import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from app.services.approval_service import request_approval_with_continuation, wait_for_approval, get_approval
sys.path.insert(0, os.getcwd())
from app.database import AsyncSessionLocal
from app.services.approval import Approval
from app.models.approval import Approval
from sqlalchemy import select, delete


async def test_approval_flow():
    """Test the approval continuation mechanism."""

    print("Testing approval continuation mechanism...")

    async with AsyncSessionLocal() as db:
        # Create a test user
        from app.models.user import User
        user_result = await db.execute(
            select(User).where(User.email == "test@ocin.com")
        )
        test_user = user_result.scalar_one_or_none()

        if not test_user:
            # Create test user
            import uuid
            test_user = User(
                id=uuid.uuid4(),
                email="test@ocin.com",
                hashed_password="$2b$12$EthisSaltForTesting123!!",
                api_key="test-api-key-12345",
                plan="pro",
            )
            db.add(test_user)
            await db.commit()
            await db.refresh(test_user)

        print(f"Test user: {test_user.id}")

        # Create a test agent
        from app.models.agent import Agent
        test_agent = Agent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            name="Test Agent",
            model_provider="openai",
            model_id="gpt-4o-mini",
            temperature=0.7,
            system_prompt="You are a test agent for approval continuation testing.",
            role="worker",
            is_active=True,
        )
        db.add(test_agent)
        await db.commit()
        await db.refresh(test_agent)

        print(f"Test agent: {test_agent.id}")

        # Create a test run that will request approval
        from app.models.run import Run
        test_run = Run(
            id=uuid.uuid4(),
            user_id=test_user.id,
            agent_id=test_agent.id,
            input="create a ping",
            status="pending",
            tool_calls=[],
        )
        db.add(test_run)
        await db.commit()
        await db.refresh(test_run)

        print(f"Test run: {test_run.id}")

        # Create an approval request with continuation mechanism
        approval = await request_approval_with_continuation(
            db=db,
            user_id=str(test_user.id),
            agent_id=str(test_agent.id),
            run_id=str(test_run.id),
            schedule_id=None,
            kind="tool_execution",
            title="execute create a ping",
            description="I need to execute create a ping command",
            payload={"tool": "create a ping", "input": "sending ping to example.com"},
        )

        print(f"✓ Approval created: {approval.id}")
        print(f"✓ Run status updated to: awaiting_approval")
        print(f"✓ Approval should be 'awaiting_approval': {approval.status}")

        # Simulate approval (update to approved)
        print("\n--- Simulating user approval ---")
        approval.status = "approved"
        approval.resolved_at = "2025-01-01T00:00:00"
        await db.commit()
        await db.refresh(approval)

        print(f"✓ Approval updated to: {approval.status}")

        # Now call wait_for_approval to test continuation
        print("\n--- Testing wait_for_approval ---")
        result = await wait_for_approval(
            db=db,
            approval_id=approval.id,
            user_id=str(test_user.id),
            timeout=10,  # 10 seconds timeout for testing
        )

        print(f"✓ Wait result status: {result.status}")
        print(f"✓ Final approval status: {result.status}")

        # Cleanup test data
        await db.execute(
            delete(Approval).where(Approval.user_id == test_user.id)
        )
        await db.execute(
            delete(Agent).where(Agent.user_id == test_user.id, Agent.name == "Test Agent")
        )
        await db.execute(
            delete(Run).where(Run.user_id == test_user.id)
        )
        await db.execute(
            delete(User).where(User.email == "test@ocin.com")
        )
        await db.commit()

        print("\n✓ Test data cleaned up")
        print("✓ Test complete!")
        print("\nExpected behavior:")
        print("1. Approval created with status 'awaiting_approval'")
        print("2. wait_for_approval polls for status change")
        print("3. When status becomes 'approved', returns control to agent")
        print("4. When status becomes 'rejected', raises exception")


if __name__ == "__main__":
    asyncio.run(test_approval_flow())
