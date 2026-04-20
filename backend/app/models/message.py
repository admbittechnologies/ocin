from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Message(Base):
    """Individual message in a chat thread."""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    attachments = Column(JSONB, nullable=True)  # Stores attachment metadata: [{name, media_type, size_bytes, path}]
    kind = Column(String(20), nullable=False, server_default="normal", index=True)  # 'normal' | 'error' | 'system'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    thread = relationship("Thread", back_populates="messages")
