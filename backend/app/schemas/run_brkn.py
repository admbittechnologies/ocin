from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class ToolCall(BaseModel):
    tool: str
    input: dict
    output: Optional[dict] = None


class RunCreate(BaseModel):
    agent_id: str
    input: str
    schedule_id: Optional[str] = None


class RunOut(BaseModel):
    id: str
    user_id: str
    agent_id: str
    schedule_id: Optional[str]
    parent_run_id: Optional[str]  # Parent run that requested approval
    status: str
    input: str
    output: Optional[str]
    tool_calls: list[ToolCall]
    tokens_used: Optional[int]
    cost_usd: Optional[float]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]

    class Config:
        from_attributes = True
