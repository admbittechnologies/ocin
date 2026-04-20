from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    """Schema for creating a new thread."""
    agent_id: str
    title: Optional[str] = Field(None, max_length=500)


class ThreadUpdate(BaseModel):
    """Schema for updating a thread."""
    title: Optional[str] = Field(None, max_length=500)


class ThreadOut(BaseModel):
    """Schema for thread response."""
    id: str
    user_id: str
    agent_id: str
    title: str
    created_at: datetime
    last_message_at: datetime

    class Config:
        from_attributes = True


class ThreadListItem(BaseModel):
    """Schema for thread in list view with minimal info."""
    id: str
    agent_id: str
    title: str
    created_at: datetime
    last_message_at: datetime
    message_count: int
    last_message_preview: Optional[str] = None

    class Config:
        from_attributes = True


class ThreadListResponse(BaseModel):
    """Schema for paginated thread list response."""
    threads: list[ThreadListItem]
    total: int
