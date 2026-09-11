"""Application settings loaded from environment variables.

Never commit a real `.env`. Copy `.env.example` and fill values locally or
in the deployment platform's secret store.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> project root is three levels up
PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. All secrets come from the environment."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Document Intelligence Platform"
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "sqlite:///./data/app.db"

    max_pages: int = 3
    max_upload_bytes: int = 15 * 1024 * 1024
    validation_tolerance: float = Field(
        default=1.00,
        description="Absolute numeric tolerance for financial checks (same unit as document values).",
    )

    tesseract_cmd: str = ""
    ocr_language: str = "eng"

    llm_provider: Literal["openai", "gemini", "anthropic"] = "gemini"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def data_dir(self) -> Path:
        path = PROJECT_ROOT / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def upload_dir(self) -> Path:
        path = PROJECT_ROOT / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_dir(self) -> Path:
        path = PROJECT_ROOT / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def frontend_dir(self) -> Path:
        return PROJECT_ROOT / "frontend"

    @property
    def templates_dir(self) -> Path:
        return self.frontend_dir / "templates"

    @property
    def static_dir(self) -> Path:
        return self.frontend_dir / "static"

    def sqlite_path(self) -> Path:
        """Resolved SQLite file path when DATABASE_URL is a relative sqlite URL."""
        url = self.database_url
        if url.startswith("sqlite:///"):
            raw = url.replace("sqlite:///", "", 1)
            path = Path(raw)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        return self.data_dir / "app.db"

    def active_llm_api_key(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_api_key
        if self.llm_provider == "gemini":
            return self.gemini_api_key
        return self.anthropic_api_key

    def active_llm_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_model
        if self.llm_provider == "gemini":
            return self.gemini_model
        return self.anthropic_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
