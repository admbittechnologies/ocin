from sqlalchemy import Column, String, DateTime, Text, UniqueConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class AgentMemory(Base):
    """Long-term memory for agents with rolling 30-day retention."""
    __tablename__ = "agent_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    source = Column(String(10), nullable=False, server_default="agent")  # 'agent' | 'user'
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    agent = relationship("Agent", back_populates="memories")

    # Unique constraint on agent_id + key
    __table_args__ = (
        UniqueConstraint("agent_id", "key", name="uq_agent_memory_key"),
        Index("idx_agent_memory_expires", "expires_at"),
    )
