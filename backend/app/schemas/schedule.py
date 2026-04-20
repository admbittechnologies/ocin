from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ScheduleCreate(BaseModel):
    agent_id: str
    label: str = Field(..., min_length=1, max_length=255)
    trigger_type: str = Field(default="cron")
    payload: dict = Field(default_factory=dict)


class ScheduleUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=255)
    trigger_type: Optional[str] = None
    payload: Optional[dict] = None
    is_active: Optional[bool] = None


class ScheduleOut(BaseModel):
    id: str
    user_id: str
    agent_id: str
    label: str
    cron_expression: str
    trigger_type: str
    payload: dict
    is_active: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]

    class Config:
        from_attributes = True
