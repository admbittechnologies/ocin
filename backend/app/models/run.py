from sqlalchemy import Column, String, DateTime, Integer, Float, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)  # null if manual
    parent_run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True)  # Parent run that requested approval
    status = Column(String(50), nullable=False, default="pending")  # pending | running | success | failed | awaiting_approval
    input = Column(Text, nullable=True)
    output = Column(Text, nullable=True)
    tool_calls = Column(JSONB, nullable=False, default=list)
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="runs")
    agent = relationship("Agent", back_populates="runs")
    schedule = relationship("Schedule", back_populates="runs")
    parent_run = relationship("Run", remote_side="Run.id", back_populates="child_runs", foreign_keys=[parent_run_id])
    child_runs = relationship("Run", back_populates="parent_run", foreign_keys=[parent_run_id])
    approvals = relationship("Approval", back_populates="run", foreign_keys="Approval.run_id", cascade="all, delete-orphan")
