from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Thread(Base):
    """Chat thread for grouping related agent conversations."""
    __tablename__ = "threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(Text, nullable=False, default="New Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_message_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="threads")
    agent = relationship("Agent", back_populates="threads")
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at")
