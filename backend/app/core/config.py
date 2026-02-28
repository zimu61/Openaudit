from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://openaudit:openaudit@localhost:5432/openaudit"
    DATABASE_URL_SYNC: str = "postgresql://openaudit:openaudit@localhost:5432/openaudit"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI Providers
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""  # Custom endpoint for OpenAI-compatible APIs (DeepSeek, Qwen, Ollama, vLLM, etc.)
    ANTHROPIC_API_KEY: str = ""
    AI_PROVIDER: str = "openai"  # "openai", "claude", or "openai_compatible"
    AI_MODEL: str = ""  # If empty, uses default per provider
    AI_MAX_CONCURRENT: int = 5

    # Joern
    JOERN_CLI_PATH: str = "joern"
    JOERN_PARSE_PATH: str = "joern-parse"
    JOERN_IMPORT_TIMEOUT: int = 300
    JOERN_QUERY_TIMEOUT: int = 120

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    WORKSPACE_DIR: str = "./workspaces"
    MAX_UPLOAD_SIZE_MB: int = 100

    # App
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_ai_model(self) -> str:
        if self.AI_MODEL:
            return self.AI_MODEL
        if self.AI_PROVIDER == "claude":
            return "claude-sonnet-4-20250514"
        if self.AI_PROVIDER == "openai_compatible":
            return ""  # Must be set explicitly for compatible APIs
        return "gpt-4o"


settings = Settings()

# Ensure directories exist
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.WORKSPACE_DIR).mkdir(parents=True, exist_ok=True)
