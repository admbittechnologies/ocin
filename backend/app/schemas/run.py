from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ToolCall(BaseModel):
    tool: str
    input: dict
    output: Optional[dict] = None
    duration_ms: Optional[int] = None


class RunCreate(BaseModel):
    user_id: str
    agent_id: str
    input: str
    schedule_id: Optional[str] = None
    status: str = "pending"
    parent_run_id: Optional[str] = None


class RunOut(BaseModel):
    id: str
    user_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = Field(default=None, description="Resolved from agent table")
    schedule_id: Optional[str] = None
    schedule_label: Optional[str] = Field(default=None, description="Human-readable schedule label")
    parent_run_id: Optional[str] = None  # Parent run that requested approval
    status: str
    input: str
    output: Optional[str] = None
    tool_calls: list[ToolCall] = []
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    is_archived: bool = Field(default=False, description="True if output was purged by retention")

    class Config:
        from_attributes = True
