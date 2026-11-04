"""Application settings, validated at startup from environment variables."""

from functools import lru_cache
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets never have defaults; none are needed in PR-001."""

    model_config = SettingsConfigDict(
        env_prefix="ONYX_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "onyx-api"
    version: str = "0.1.0"
    environment: Literal["local", "test", "preview", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3001"],
        description="Explicit browser origins allowed to call the API (comma-separated in env).",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("Wildcard CORS origins are not allowed; list origins explicitly.")
        return value

    @property
    def is_deployed(self) -> bool:
        """True for hosted environments (preview, production), which get strict validation."""
        return self.environment in DEPLOYED_ENVIRONMENTS

    @model_validator(mode="after")
    def _validate_deployed_origins(self) -> Self:
        if not self.is_deployed:
            return self
        if not self.cors_origins:
            raise ValueError("ONYX_API_CORS_ORIGINS must be set in a deployed environment.")
        for origin in self.cors_origins:
            parts = urlsplit(origin)
            host = parts.hostname or ""
            if parts.scheme != "https" or not host:
                raise ValueError(f"Deployed CORS origins must be https URLs: {origin!r}")
            if host in LOCAL_HOSTS or host.endswith(".localhost"):
                raise ValueError(f"Deployed CORS origins must not be local: {origin!r}")
            if parts.path not in ("", "/") or parts.query or parts.fragment:
                raise ValueError(f"A CORS origin is scheme://host[:port] only: {origin!r}")
        return self


DEPLOYED_ENVIRONMENTS = frozenset({"preview", "production"})
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # noqa: S104


@lru_cache
def get_settings() -> Settings:
    return Settings()
