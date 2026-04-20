from typing import Optional
from pydantic import BaseModel, Field, field_validator

# Supported model providers from CLAUDE.md
# Note: These are stored/retrieved in the format sent by the frontend (capitalized)
# Normalized to lowercase internally for consistency
SUPPORTED_PROVIDERS = [
    "OpenAI",
    "Anthropic",
    "Google",
    "Ollama",
    "OpenRouter",
    "Mistral",
    "Grok",  # xai is displayed as Grok in the frontend
    "Qwen",
    "DeepSeek",
    "ZAI",
]


def normalize_provider(provider: str) -> str:
    """Normalize provider name to lowercase for internal storage/comparison."""
    return provider.lower()


def get_provider_key(provider: str) -> str:
    """Get the normalized lowercase key for a provider name."""
    return normalize_provider(provider)

SUPPORTED_ROLES = ["coordinator", "worker", "standalone"]


class ToolReference(BaseModel):
    id: str
    name: str


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    avatar: str = Field(default="avatar-01", min_length=1, max_length=64)
    role: str = Field(default="worker")
    model_provider: str
    model_id: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    system_prompt: Optional[str] = None
    tool_ids: list[str] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in SUPPORTED_ROLES:
            raise ValueError(f"role must be one of {SUPPORTED_ROLES}")
        return v

    @field_validator("model_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        normalized = normalize_provider(v)
        if not any(normalize_provider(p) == normalized for p in SUPPORTED_PROVIDERS):
            raise ValueError(f"model_provider must be one of {SUPPORTED_PROVIDERS}")
        # Store in the format provided by frontend (preserves casing)
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    avatar: Optional[str] = Field(None, min_length=1, max_length=64)
    role: Optional[str] = None
    model_provider: Optional[str] = None
    model_id: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    system_prompt: Optional[str] = None
    tool_ids: Optional[list[str]] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SUPPORTED_ROLES:
            raise ValueError(f"role must be one of {SUPPORTED_ROLES}")
        return v

    @field_validator("model_provider")
    @classmethod
    def validate_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            normalized = normalize_provider(v)
            if not any(normalize_provider(p) == normalized for p in SUPPORTED_PROVIDERS):
                raise ValueError(f"model_provider must be one of {SUPPORTED_PROVIDERS}")
        return v


class AgentOut(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str]
    avatar: str
    role: str
    model_provider: str
    model_id: str
    temperature: float
    system_prompt: Optional[str]
    tool_ids: list[str]
    tools: Optional[list[ToolReference]] = None  # Resolved tool names
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True
