import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    """Runtime configuration. Cookiecutter defaults can be overridden with MCP_* env vars."""

    model_config = SettingsConfigDict(env_prefix="MCP_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = Field(default=1, ge=1)
    log_level: str = "INFO"
    log_format: LogFormat = "json"
    log_health: bool = False
    auth_required: bool = False
    auth_scope: str = "{{cookiecutter.auth_scope}}"
    product_name: str = "{{cookiecutter.product_name}}"
    product_slug: str = "{{cookiecutter.product_slug}}"
    domain_team: str = "{{cookiecutter.domain_team}}"
    owner_email: str = "{{cookiecutter.owner_email}}"
    tools_prefix: str = "{{cookiecutter.tools_prefix}}"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Accept a standard logging level in any case."""
        candidate = value.upper()
        if candidate not in logging.getLevelNamesMapping():
            raise ValueError("MCP_LOG_LEVEL must be a standard logging level")
        return candidate

    @field_validator("log_format", mode="before")
    @classmethod
    def normalize_log_format(cls, value: str) -> str:
        """Accept json or console in any case."""
        return value.lower()


@lru_cache
def get_settings() -> Settings:
    """Return process settings, loaded once from the environment."""
    return Settings()
