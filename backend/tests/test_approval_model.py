"""Unit tests for Approval model."""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from app.models.approval import Approval


@pytest.mark.unit
class TestApprovalModel:
    """Test Approval model properties and constraints."""

    async def test_create_approval_with_minimal_fields(self, db_session, test_user, test_run):
        """Test creating approval with required fields only."""
        approval = Approval(
            user_id=test_user.id,
            run_id=test_run.id,
            kind="send_email",
            title="Send email",
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        assert approval.id is not None
        assert approval.user_id == test_user.id
        assert approval.run_id == test_run.id
        assert approval.kind == "send_email"
        assert approval.title == "Send email"
        assert approval.status == "pending"
        assert approval.created_at is not None

    async def test_create_approval_with_all_fields(self, db_session, test_user, test_agent, test_run):
        """Test creating approval with all optional fields."""
        expires_at = datetime.now() + timedelta(hours=24)
        approval = Approval(
            user_id=test_user.id,
            agent_id=test_agent.id,
            run_id=test_run.id,
            kind="post_social",
            title="Post to Twitter",
            description="Share promotional content",
            payload={"text": "Check out our new product!"},
            status="pending",
            expires_at=expires_at
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        assert approval.user_id == test_user.id
        assert approval.agent_id == test_agent.id
        assert approval.run_id == test_run.id
        assert approval.kind == "post_social"
        assert approval.title == "Post to Twitter"
        assert approval.description == "Share promotional content"
        assert approval.payload == {"text": "Check out our new product!"}
        assert approval.status == "pending"
        assert approval.expires_at == expires_at
        assert approval.resolved_at is None
        assert approval.resolution_note is None

    async def test_approval_status_enum(self, db_session, test_user, test_run):
        """Test that approval status accepts valid values."""
        valid_statuses = ["pending", "approved", "rejected", "expired"]

        for status_value in valid_statuses:
            approval = Approval(
                user_id=test_user.id,
                run_id=test_run.id,
                kind="test_action",
                title=f"Test {status_value}",
                status=status_value
            )
            db_session.add(approval)
            await db_session.commit()
            await db_session.refresh(approval)

            assert approval.status == status_value

    async def test_approval_timestamps(self, db_session, test_user, test_run):
        """Test that created_at is set automatically."""
        before_creation = datetime.now()

        approval = Approval(
            user_id=test_user.id,
            run_id=test_run.id,
            kind="test",
            title="Test timestamps"
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        after_creation = datetime.now()

        assert approval.created_at >= before_creation
        assert approval.created_at <= after_creation

    async def test_approval_resolved_fields(self, db_session, test_user, test_run):
        """Test resolved_at and resolution_note fields."""
        now = datetime.now()
        approval = Approval(
            user_id=test_user.id,
            run_id=test_run.id,
            kind="test",
            title="Test resolution",
            status="approved",
            resolved_at=now,
            resolution_note="Approved for testing"
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        assert approval.resolved_at == now
        assert approval.resolution_note == "Approved for testing"

    async def test_approval_payload_jsonb(self, db_session, test_user, test_run):
        """Test that payload can store complex JSON data."""
        complex_payload = {
            "recipient": "user@example.com",
            "subject": "Complex email",
            "body": {
                "greeting": "Hello",
                "message": "This is a test",
                "attachments": [
                    {"name": "file1.pdf", "size": 1024},
                    {"name": "file2.jpg", "size": 2048}
                ]
            },
            "metadata": {
                "priority": "high",
                "category": "marketing"
            }
        }

        approval = Approval(
            user_id=test_user.id,
            run_id=test_run.id,
            kind="send_email",
            title="Complex email",
            payload=complex_payload
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        assert approval.payload == complex_payload
        assert approval.payload["body"]["attachments"][0]["name"] == "file1.pdf"

    async def test_approval_expiration(self, db_session, test_user, test_run):
        """Test approval expiration handling."""
        # Approval that will expire in 1 hour
        expires_soon = datetime.now() + timedelta(hours=1)
        approval = Approval(
            user_id=test_user.id,
            run_id=test_run.id,
            kind="test",
            title="Expiring approval",
            expires_at=expires_soon
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        assert approval.expires_at == expires_soon

    async def test_approval_without_expiration(self, db_session, test_user, test_run):
        """Test approval without expiration date."""
        approval = Approval(
            user_id=test_user.id,
            run_id=test_run.id,
            kind="test",
            title="Non-expiring approval"
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        assert approval.expires_at is None

    async def test_approval_relationships(self, db_session, test_user, test_agent, test_run):
        """Test approval relationships with user, agent, and run."""
        approval = Approval(
            user_id=test_user.id,
            agent_id=test_agent.id,
            run_id=test_run.id,
            kind="test",
            title="Relationship test"
        )
        db_session.add(approval)
        await db_session.commit()
        await db_session.refresh(approval)

        # Test that relationships are loaded
        assert approval.user_id == test_user.id
        assert approval.agent_id == test_agent.id
        assert approval.run_id == test_run.id