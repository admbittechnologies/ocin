from sqlalchemy import Column, String, DateTime, Integer, Float, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Approval(Base):
    """Human approval for agent actions.

    Stores approvals for agent-initiated actions that require user confirmation
    before proceeding. Enables multi-step workflows like:
    - Sending emails
    - Posting to social media
    - Creating resources that cost money
    - Any action the user wants to review before execution
    """
    __tablename__ = "approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True)
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(64))  # e.g. "send_email", "post_social", "execute_action"
    title = Column(String(255))  # Short user-facing summary
    description = Column(Text)  # Longer explanation
    payload = Column(JSONB, nullable=True, default=dict)  # Full payload the agent wants to execute
    status = Column(String(32), nullable=False, default="pending")  # pending | approved | rejected | expired
    resolved_at = Column(DateTime(timezone=True), nullable=True)  # When user approved or rejected
    resolution_note = Column(Text, nullable=True)  # Optional note from user when approving/rejecting
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional TTL for automatic expiry
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="approvals")
    agent = relationship("Agent", back_populates="approvals")
    run = relationship("Run", back_populates="approvals", foreign_keys=[run_id])
    schedule = relationship("Schedule", foreign_keys=[schedule_id])
