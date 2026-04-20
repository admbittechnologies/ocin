from typing import Optional
from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

SUPPORTED_SOURCES = ["builtin", "composio", "apify", "maton"]


class ToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source: str
    source_key: Optional[str] = None
    # API keys and sensitive config are passed here and will be encrypted
    config: dict = Field(default_factory=dict)

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in SUPPORTED_SOURCES:
            raise ValueError(f"source must be one of {SUPPORTED_SOURCES}")
        return v


class ToolOut(BaseModel):
    id: str
    user_id: str
    name: str
    source: str
    source_key: Optional[str]
    is_active: bool

    # Never expose raw config or keys
    configured: bool = Field(default=False)

    class Config:
        from_attributes = True
