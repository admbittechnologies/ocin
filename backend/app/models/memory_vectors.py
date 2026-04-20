from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY, FLOAT
from sqlalchemy.sql import func
import uuid

from app.database import Base


class AgentMemoryVector(Base):
    """
    Vector embeddings for semantic memory.

    DORMANT IN V1 — schema only, no writes.
    Embedding pipeline deferred to v2.
    """
    __tablename__ = "agent_memory_vectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(ARRAY(FLOAT, dimensions=1536), nullable=False)  # OpenAI embeddings dimension
    source = Column(String(50), nullable=True)  # e.g., 'run', 'memory'
    source_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
