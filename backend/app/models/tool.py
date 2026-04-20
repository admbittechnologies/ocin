from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Tool(Base):
    __tablename__ = "tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)  # builtin | composio | apify | maton
    source_key = Column(String(255), nullable=True)
    config = Column(JSONB, nullable=False, default=dict)  # encrypted API keys + connection IDs
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    user = relationship("User", back_populates="tools")
