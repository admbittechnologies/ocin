"""Pydantic schemas for approval operations."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ApprovalBase(BaseModel):
    """Base approval fields."""
    kind: str = Field(..., description="Type of approval requested (e.g. send_email, post_social)")
    title: str = Field(..., description="Short user-facing summary")
    description: Optional[str] = Field(None, description="Longer explanation")
    payload: dict = Field(default_factory=dict, description="Full payload the agent wants to execute")


class ApprovalCreate(ApprovalBase):
    """Schema for creating an approval."""
    agent_id: str
    run_id: str
    schedule_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class ApprovalResolve(BaseModel):
    """Schema for approving/rejecting an approval."""
    note: Optional[str] = Field(None, description="Optional note from user when approving/rejecting")


class ApprovalOut(BaseModel):
    """Full approval schema including resolved relationships."""
    id: str
    user_id: str
    agent_id: Optional[str]
    agent_name: Optional[str] = Field(None, description="Agent name resolved via join")
    agent_avatar: str = Field(default="avatar-01", description="Agent avatar slug")
    run_id: Optional[str]
    schedule_id: Optional[str]
    kind: str
    title: str
    description: Optional[str]
    payload: dict
    status: str  # pending | approved | rejected | expired
    resolved_at: Optional[datetime]
    resolution_note: Optional[str]
    expires_at: Optional[datetime]
    created_at: datetime
    continuation_run_id: Optional[str] = Field(None, description="Run ID created after approval (for approved approvals)")

    class Config:
        from_attributes = True


class ApprovalCount(BaseModel):
    """Count of pending approvals."""
    count: int


class ApprovalListResponse(BaseModel):
    """Response for approval list endpoint."""
    approvals: List[ApprovalOut]
