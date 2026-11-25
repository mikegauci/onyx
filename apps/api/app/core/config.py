"""Application settings, validated at startup from environment variables."""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
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

    # WhatsApp connector (Meta Cloud API). All three secrets set = WhatsApp channels connected.
    whatsapp_app_secret: SecretStr | None = Field(
        default=None, description="Meta app secret; signs webhook requests (X-Hub-Signature-256)."
    )
    whatsapp_verify_token: SecretStr | None = Field(
        default=None, description="Token Meta echoes when the webhook subscription is set up."
    )
    whatsapp_access_token: SecretStr | None = Field(
        default=None, description="System user access token for the WhatsApp Cloud API."
    )
    whatsapp_graph_version: str = Field(default="v23.0", pattern=r"^v\d{1,2}\.\d$")
    whatsapp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    whatsapp_provider: Literal["meta", "fake"] = Field(
        default="meta",
        description="'fake' records sends in memory for local and e2e runs; never deployed.",
    )

    # Telephony (VA-004 missed-call text-back). Twilio needs the account SID, auth token and
    # the public webhook URL it calls (it signs that exact URL).
    telephony_provider: Literal["twilio", "fake"] = Field(
        default="twilio",
        description="'fake' accepts locally signed test webhooks; never deployed.",
    )
    telephony_webhook_url: str | None = Field(
        default=None,
        pattern=r"^https?://[^\s]+/v1/webhooks/telephony$",
        description="The public URL of POST /v1/webhooks/telephony, as the provider calls it.",
    )
    twilio_account_sid: str | None = Field(default=None, pattern=r"^AC[0-9a-f]{32}$")
    twilio_auth_token: SecretStr | None = Field(default=None, description="Twilio auth token")
    telephony_fake_secret: SecretStr | None = Field(
        default=None, description="Signs fake telephony webhooks (local and e2e only)."
    )
    telephony_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # Tenant files (VA-007 deal documents). "supabase" needs the URL above and the service key;
    # "local" keeps files under storage_local_dir (development); "memory" is for tests.
    storage_backend: Literal["supabase", "local", "memory"] | None = Field(
        default=None,
        description="Unset: supabase when deployed and configured, local otherwise.",
    )
    supabase_service_key: SecretStr | None = Field(
        default=None, description="Supabase secret (service) key; server only, never logged."
    )
    storage_bucket: str = Field(default="tenant-files", pattern=r"^[a-z0-9][a-z0-9-]{2,62}$")
    storage_local_dir: str = ".storage"

    # Scheduler (VA-007 part 3): a free GitHub Actions schedule calls POST
    # /v1/internal/scheduler/run with this secret every 30 minutes. Unset = the endpoint is off.
    scheduler_secret: SecretStr | None = Field(
        default=None, description="Bearer secret for the scheduler endpoint (32+ characters)."
    )

    # Billing (PR-026). Off until the owner creates the Stripe account and plans; test-mode
    # keys first. Price ids map Onyx plans to Stripe prices.
    stripe_api_key: SecretStr | None = Field(default=None, description="Stripe secret key")
    stripe_webhook_secret: SecretStr | None = Field(default=None, description="whsec_…")
    stripe_price_starter: str | None = Field(default=None, pattern=r"^price_[A-Za-z0-9]+$")
    stripe_price_growth: str | None = Field(default=None, pattern=r"^price_[A-Za-z0-9]+$")
    stripe_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    automotive_site: Literal["live", "fake"] = Field(
        default="live",
        description="'fake' imports from a built-in demo site (local and e2e; never deployed).",
    )
    billing_provider: Literal["stripe", "fake"] = Field(
        default="stripe",
        description="'fake' creates fake checkout links for local and e2e runs; never deployed.",
    )

    # Error tracking (PR-027): off unless a DSN is set. Creating the Sentry projects needs the
    # owner's approval. ``release`` is the deployed commit (Render sets RENDER_GIT_COMMIT).
    sentry_dsn: SecretStr | None = Field(default=None, description="Sentry DSN (server only)")
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    release: str | None = Field(
        default=None, validation_alias=AliasChoices("ONYX_API_RELEASE", "RENDER_GIT_COMMIT")
    )

    # Temporal (PR-020). Only the worker process connects; the API never does. Temporal Cloud
    # (mTLS or an API key) needs the owner's approval and is not configured yet.
    temporal_address: str = Field(default="localhost:7233", description="host:port")
    temporal_namespace: str = Field(default="default", min_length=1, max_length=200)
    temporal_task_queue: str = Field(default="onyx", min_length=1, max_length=200)
    outbox_batch_size: int = Field(default=20, ge=1, le=100)
    outbox_poll_seconds: float = Field(default=2.0, gt=0, le=60)
    outbox_lease_seconds: int = Field(default=60, ge=5, le=3600)
    outbox_max_attempts: int = Field(default=10, ge=1, le=100)

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "resend_api_key",
        "resend_webhook_secret",
        "whatsapp_app_secret",
        "whatsapp_verify_token",
        "whatsapp_access_token",
        "twilio_auth_token",
        "telephony_fake_secret",
        "supabase_service_key",
        "scheduler_secret",
        "telephony_webhook_url",
        "twilio_account_sid",
        "sentry_dsn",
        "stripe_api_key",
        "stripe_webhook_secret",
        "stripe_price_starter",
        "stripe_price_growth",
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

    @property
    def billing_configured(self) -> bool:
        return None not in (self.stripe_api_key, self.stripe_webhook_secret)

    @property
    def whatsapp_configured(self) -> bool:
        return None not in (
            self.whatsapp_app_secret,
            self.whatsapp_verify_token,
            self.whatsapp_access_token,
        )

    @property
    def telephony_configured(self) -> bool:
        if self.telephony_webhook_url is None:
            return False
        if self.telephony_provider == "fake":
            return self.telephony_fake_secret is not None
        return None not in (self.twilio_account_sid, self.twilio_auth_token)

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

    @property
    def resolved_storage_backend(self) -> str | None:
        """Where tenant files go, or None when deployed without Supabase Storage (fail closed)."""
        if self.storage_backend is not None:
            return self.storage_backend
        if self.supabase_url is not None and self.supabase_service_key is not None:
            return "supabase"
        return None if self.is_deployed else "local"

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
        if self.whatsapp_provider == "fake" and self.is_deployed:
            raise ValueError("The fake WhatsApp provider is not allowed in a deployed environment.")
        if self.automotive_site == "fake" and self.is_deployed:
            raise ValueError("The fake vehicle site is not allowed in a deployed environment.")
        if self.telephony_provider == "fake" and self.is_deployed:
            raise ValueError(
                "The fake telephony provider is not allowed in a deployed environment."
            )
        if self.billing_provider == "fake" and self.is_deployed:
            raise ValueError("The fake billing provider is not allowed in a deployed environment.")
        if self.storage_backend in ("local", "memory") and self.is_deployed:
            raise ValueError("Local or in-memory file storage is not allowed when deployed.")
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
