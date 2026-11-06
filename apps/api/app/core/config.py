"""Application settings, validated at startup from environment variables."""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AI_PROVIDERS = frozenset({"openai", "anthropic", "fake"})


class AIModelPrice(BaseModel):
    """List price in USD per million tokens. Decimal strings, never floats."""

    model_config = ConfigDict(frozen=True)

    input_usd_per_mtok: Decimal = Field(ge=0, max_digits=12, decimal_places=6)
    output_usd_per_mtok: Decimal = Field(ge=0, max_digits=12, decimal_places=6)


class Settings(BaseSettings):
    """Runtime configuration. Secrets never have defaults."""

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
    database_url: SecretStr | None = Field(
        default=None,
        description="SQLAlchemy URL for the application role (postgresql+psycopg://...).",
    )
    supabase_url: str | None = Field(
        default=None,
        description="Supabase project URL (https://<ref>.supabase.co); issues the login tokens.",
    )
    jwt_audience: str = "authenticated"
    migration_database_url: SecretStr | None = Field(
        default=None,
        description="SQLAlchemy URL for the schema-owner role used only by Alembic and seeding.",
    )
    # --- AI gateway (server only; nothing here is ever sent to a browser) ---------------------
    openai_api_key: SecretStr | None = Field(default=None, description="OpenAI API key.")
    anthropic_api_key: SecretStr | None = Field(default=None, description="Anthropic API key.")
    ai_default_model: str | None = Field(
        default=None,
        description="'<provider>:<model>' used when a workload has no override. Unset locally "
        "means the fake model; unset in a deployed environment means AI is unavailable.",
    )
    ai_workload_models: dict[str, str] = Field(
        default_factory=dict,
        description='Per-workload model overrides as JSON, e.g. {"diagnostic": "openai:..."}.',
    )
    ai_model_prices: dict[str, AIModelPrice] = Field(
        default_factory=dict,
        description="USD price per million tokens for each allowed model, as JSON. A model "
        "without a price is refused, so spend can always be computed.",
    )
    ai_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    ai_max_attempts: int = Field(default=3, ge=1, le=5)
    ai_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    ai_max_output_tokens: int = Field(default=1024, ge=16, le=32_000)

    # Email connector (Resend). All four set = email channels connected; otherwise they refuse.
    resend_api_key: SecretStr | None = Field(default=None, description="Resend API key.")
    resend_webhook_secret: SecretStr | None = Field(
        default=None, description="Signing secret (whsec_...) of the Resend webhook."
    )
    email_inbound_domain: str | None = Field(
        default=None, description="Receiving domain for channel addresses, e.g. in.onyx.mt."
    )
    email_from_domain: str | None = Field(
        default=None, description="Verified sending domain, e.g. reply.onyx.mt."
    )
    email_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    email_provider: Literal["resend", "fake"] = Field(
        default="resend",
        description="'fake' records sends in memory for local and e2e runs; never deployed.",
    )

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "resend_api_key",
        "resend_webhook_secret",
        mode="before",
    )
    @classmethod
    def _blank_key_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("email_inbound_domain", "email_from_domain", mode="before")
    @classmethod
    def _email_domain(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().lower() or None
            if value is not None and (
                "@" in value or "/" in value or "." not in value or value.startswith(".")
            ):
                raise ValueError("Use a bare domain name, e.g. in.onyx.mt.")
        return value

    @property
    def email_configured(self) -> bool:
        return None not in (
            self.resend_api_key,
            self.resend_webhook_secret,
            self.email_inbound_domain,
            self.email_from_domain,
        )

    @field_validator("ai_default_model", mode="before")
    @classmethod
    def _blank_model_is_unset(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("supabase_url", mode="before")
    @classmethod
    def _normalise_supabase_url(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().rstrip("/")
            return value or None
        return value

    @field_validator("supabase_url")
    @classmethod
    def _supabase_url_is_origin(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = urlsplit(value)
        local = (parts.hostname or "") in LOCAL_HOSTS
        if parts.scheme not in ("https", "http") or (parts.scheme == "http" and not local):
            raise ValueError("ONYX_API_SUPABASE_URL must be https (http only for localhost).")
        if parts.path or parts.query or parts.fragment:
            raise ValueError("ONYX_API_SUPABASE_URL is scheme://host[:port] only.")
        return value

    @property
    def jwt_issuer(self) -> str | None:
        return f"{self.supabase_url}/auth/v1" if self.supabase_url else None

    @property
    def jwks_url(self) -> str | None:
        return f"{self.jwt_issuer}/.well-known/jwks.json" if self.jwt_issuer else None

    @field_validator("database_url", "migration_database_url", mode="before")
    @classmethod
    def _blank_url_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
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

    def require_database_url(self) -> str:
        """The application database URL, or a clear error when it is not configured."""
        if self.database_url is None:
            raise MissingDatabaseUrlError("ONYX_API_DATABASE_URL is not set.")
        return self.database_url.get_secret_value()

    def require_migration_database_url(self) -> str:
        """The schema-owner URL. Locally it falls back to the application URL."""
        if self.migration_database_url is not None:
            return self.migration_database_url.get_secret_value()
        if self.is_deployed:
            raise MissingDatabaseUrlError(
                "ONYX_API_MIGRATION_DATABASE_URL must be set explicitly in a deployed environment."
            )
        return self.require_database_url()

    @model_validator(mode="after")
    def _validate_ai_models(self) -> Self:
        refs = [self.ai_default_model, *self.ai_workload_models.values()]
        for ref in filter(None, refs):
            provider, _, name = ref.partition(":")
            if provider not in AI_PROVIDERS or not name:
                raise ValueError(f"AI model must be '<openai|anthropic|fake>:<model>': {ref!r}")
            if provider == "fake" and self.is_deployed:
                raise ValueError("The fake AI model is not allowed in a deployed environment.")
        return self

    @model_validator(mode="after")
    def _validate_email_provider(self) -> Self:
        if self.email_provider == "fake" and self.is_deployed:
            raise ValueError("The fake email provider is not allowed in a deployed environment.")
        return self

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


class MissingDatabaseUrlError(RuntimeError):
    """Raised when database access is attempted without a configured URL."""


DEPLOYED_ENVIRONMENTS = frozenset({"preview", "production"})
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # noqa: S104


@lru_cache
def get_settings() -> Settings:
    return Settings()
