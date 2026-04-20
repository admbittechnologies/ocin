from sqlalchemy import Column, String, DateTime, Float, Boolean, Text, ARRAY, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    avatar = Column(String(64), nullable=False, default="avatar-01")
    role = Column(String(50), nullable=False, default="worker")  # coordinator | worker | standalone
    model_provider = Column(String(50), nullable=False)
    model_id = Column(String(100), nullable=False)
    temperature = Column(Float, nullable=False, default=0.7)
    system_prompt = Column(Text, nullable=True)
    tool_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="agents")
    schedules = relationship("Schedule", back_populates="agent", cascade="all, delete-orphan")
    runs = relationship("Run", back_populates="agent")
    memories = relationship("AgentMemory", back_populates="agent", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="agent", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="agent", cascade="all, delete-orphan")
