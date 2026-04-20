from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChatAttachment(BaseModel):
    """Schema for chat attachments."""
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=100)  # MIME type
    data_base64: str = Field(..., min_length=1)  # Data URL or raw base64


class MessageCreate(BaseModel):
    """Schema for creating a message."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class MessageOut(BaseModel):
    """Schema for message response."""
    id: str
    thread_id: str
    role: str
    content: str
    created_at: datetime
    kind: str = "normal"  # "normal" | "error" | "system"

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Schema for message list response."""
    messages: list[MessageOut]
    total: int
