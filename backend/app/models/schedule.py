from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(255), nullable=False)  # shown to user: "Every morning at 9"
    cron_expression = Column(String(100), nullable=False)  # never shown to user
    trigger_type = Column(String(50), nullable=False, default="cron")  # cron | webhook | event
    payload = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="schedules")
    agent = relationship("Agent", back_populates="schedules")
    runs = relationship("Run", back_populates="schedule", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="schedule", foreign_keys="Approval.schedule_id")
