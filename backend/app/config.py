from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ocin:ocinpass@localhost:5432/ocin"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ADMIN_SECRET: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Encryption (Fernet key for API keys)
    ENCRYPTION_KEY: str = "change-me-in-production-32-bytes-min"

    # LLM Provider API Keys (optional)
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENROUTER_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    XAI_API_KEY: str = ""
    QWEN_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    ZAI_API_KEY: str = ""


    # Schedule Parsing (LLM model for plain-language to cron conversion)
    SCHEDULE_PARSE_MODEL: str = "gpt-4o-mini"

    # Email (Mailjet)
    MAILJET_API_KEY: str = ""
    MAILJET_API_SECRET: str = ""
    MAILJET_SENDER: str = "noreply@ocin.site"
    OCIN_PUBLIC_URL: str = "http://localhost:8080"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
