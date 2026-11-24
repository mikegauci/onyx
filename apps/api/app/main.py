"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embeddings import EmbeddingFactory, build_embedding_model
from app.ai.gateway import AIGateway
from app.ai.providers import ModelFactory, build_model
from app.api.admin import router as admin_router
from app.api.admin_organizations import router as admin_organizations_router
from app.api.ai import router as ai_router
from app.api.audit import router as audit_router
from app.api.billing import router as billing_router
from app.api.controls import router as controls_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.modules import router as modules_router
from app.api.tasks import router as tasks_router
from app.api.webhooks import router as webhooks_router
from app.api.workspaces import router as workspaces_router
from app.core.auth.tokens import TokenVerifier
from app.core.billing.service import BillingWebhooks
from app.core.config import Settings, get_settings
from app.core.db.session import create_engine, create_session_factory
from app.core.errors import install_error_handlers
from app.core.logging import REQUEST_ID_HEADER, RequestIdMiddleware, configure_logging
from app.core.observability import init_sentry
from app.integrations import email, telephony, whatsapp
from app.integrations.billing import BillingConfig, BillingProvider
from app.integrations.billing.fake import FakeBillingProvider
from app.integrations.billing.stripe import StripeProvider
from app.integrations.email import EmailConfig, EmailProvider
from app.integrations.email.fake import FakeEmailProvider
from app.integrations.email.resend import ResendProvider
from app.integrations.telephony import TelephonyConfig, TelephonyProvider
from app.integrations.telephony.fake import FakeTelephonyProvider
from app.integrations.telephony.twilio import TwilioProvider
from app.integrations.whatsapp import WhatsAppConfig, WhatsAppProvider
from app.integrations.whatsapp.fake import FakeWhatsAppProvider
from app.integrations.whatsapp.meta import MetaProvider
from app.modules.assistant.routes import router as assistant_router
from app.modules.automotive import fake_site
from app.modules.automotive.routes import router as automotive_router
from app.modules.catalogue.routes import router as catalogue_router
from app.modules.crm.routes import router as crm_router
from app.modules.inbox import whatsapp_send
from app.modules.inbox.email_connector import EmailConnector
from app.modules.inbox.missed_calls import MissedCallConnector
from app.modules.inbox.routes import router as inbox_router
from app.modules.inbox.whatsapp_connector import WhatsAppConnector
from app.modules.knowledge.routes import router as knowledge_router
from app.modules.outbound.routes import router as outbound_router
from app.modules.quotations.routes import router as quotations_router


def _default_verifier(settings: Settings) -> TokenVerifier | None:
    if settings.jwks_url is None or settings.jwt_issuer is None:
        return None
    return TokenVerifier.for_jwks_url(
        jwks_url=settings.jwks_url, issuer=settings.jwt_issuer, audience=settings.jwt_audience
    )


def _email_config(
    settings: Settings, provider: EmailProvider | None
) -> tuple[EmailConfig | None, ResendProvider | None]:
    """The email provider when fully configured; otherwise email channels stay disconnected."""
    if not settings.email_configured:
        return None, None
    assert settings.resend_api_key is not None  # noqa: S101 - email_configured
    assert settings.resend_webhook_secret is not None  # noqa: S101
    assert settings.email_inbound_domain is not None  # noqa: S101
    assert settings.email_from_domain is not None  # noqa: S101
    owned = None
    if provider is None and settings.email_provider == "fake":
        provider = FakeEmailProvider()  # local and e2e only; refused in deployed settings
    if provider is None:
        owned = ResendProvider(
            settings.resend_api_key.get_secret_value(), timeout=settings.email_timeout_seconds
        )
        provider = owned
    config = EmailConfig(
        provider=provider,
        webhook_secret=settings.resend_webhook_secret.get_secret_value(),
        inbound_domain=settings.email_inbound_domain,
        from_domain=settings.email_from_domain,
    )
    return config, owned


def _whatsapp_config(
    settings: Settings, provider: WhatsAppProvider | None
) -> tuple[WhatsAppConfig | None, MetaProvider | None]:
    """The WhatsApp provider when fully configured; otherwise WhatsApp channels stay off."""
    if not settings.whatsapp_configured:
        return None, None
    assert settings.whatsapp_app_secret is not None  # noqa: S101 - whatsapp_configured
    assert settings.whatsapp_verify_token is not None  # noqa: S101
    assert settings.whatsapp_access_token is not None  # noqa: S101
    owned = None
    if provider is None and settings.whatsapp_provider == "fake":
        provider = FakeWhatsAppProvider()  # local and e2e only; refused in deployed settings
    if provider is None:
        owned = MetaProvider(
            settings.whatsapp_access_token.get_secret_value(),
            graph_version=settings.whatsapp_graph_version,
            timeout=settings.whatsapp_timeout_seconds,
        )
        provider = owned
    config = WhatsAppConfig(
        provider=provider,
        app_secret=settings.whatsapp_app_secret.get_secret_value(),
        verify_token=settings.whatsapp_verify_token.get_secret_value(),
    )
    return config, owned


def _telephony_config(
    settings: Settings, provider: TelephonyProvider | None
) -> tuple[TelephonyConfig | None, TwilioProvider | None]:
    """The telephony provider when fully configured; otherwise missed calls are off (503)."""
    if not settings.telephony_configured:
        return None, None
    assert settings.telephony_webhook_url is not None  # noqa: S101 - telephony_configured
    owned = None
    if provider is None and settings.telephony_provider == "fake":
        assert settings.telephony_fake_secret is not None  # noqa: S101
        # Local and e2e only; refused in deployed settings.
        provider = FakeTelephonyProvider(settings.telephony_fake_secret.get_secret_value())
    if provider is None:
        assert settings.twilio_account_sid is not None  # noqa: S101
        assert settings.twilio_auth_token is not None  # noqa: S101
        owned = TwilioProvider(
            settings.twilio_account_sid,
            settings.twilio_auth_token.get_secret_value(),
            timeout=settings.telephony_timeout_seconds,
        )
        provider = owned
    return TelephonyConfig(provider=provider, webhook_url=settings.telephony_webhook_url), owned


def _billing_config(settings: Settings, provider: BillingProvider | None) -> BillingConfig | None:
    """Stripe Billing when configured; otherwise billing is unavailable (503)."""
    if not settings.billing_configured:
        return None
    assert settings.stripe_api_key is not None  # noqa: S101 - billing_configured
    assert settings.stripe_webhook_secret is not None  # noqa: S101
    if provider is None and settings.billing_provider == "fake":
        provider = FakeBillingProvider()  # local and e2e only; refused in deployed settings
    if provider is None:
        provider = StripeProvider(
            settings.stripe_api_key.get_secret_value(), timeout=settings.stripe_timeout_seconds
        )
    prices = {
        plan: price
        for plan, price in (
            ("starter", settings.stripe_price_starter),
            ("growth", settings.stripe_price_growth),
        )
        if price
    }
    return BillingConfig(
        provider=provider,
        webhook_secret=settings.stripe_webhook_secret.get_secret_value(),
        prices=prices,
    )


API_VERSION_PREFIX = "/v1"


def _operation_id(route: APIRoute) -> str:
    """Stable OpenAPI operation ids (the route function name) for the generated TS client."""
    return route.name


def create_app(
    settings: Settings | None = None,
    *,
    token_verifier: TokenVerifier | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    ai_model_factory: ModelFactory | None = None,
    ai_embedding_factory: EmbeddingFactory | None = None,
    email_provider: EmailProvider | None = None,
    whatsapp_provider: WhatsAppProvider | None = None,
    billing_provider: BillingProvider | None = None,
    telephony_provider: TelephonyProvider | None = None,
) -> FastAPI:
    """Build the app. Auth and database are optional: without them those routes return 503."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    init_sentry(settings, "api")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        app.state.token_verifier = token_verifier or _default_verifier(settings)
        app.state.session_factory = session_factory
        if session_factory is None and settings.database_url is not None:
            engine = create_engine(settings)
            app.state.session_factory = create_session_factory(engine)
        app.state.ai_gateway = (
            AIGateway(
                app.state.session_factory,
                settings,
                model_factory=ai_model_factory or build_model,
                embedding_factory=ai_embedding_factory or build_embedding_model,
            )
            if app.state.session_factory is not None
            else None
        )
        email_config, owned = _email_config(settings, email_provider)
        email.configure(email_config)
        app.state.email_connector = (
            EmailConnector(app.state.session_factory, email_config)
            if email_config is not None and app.state.session_factory is not None
            else None
        )
        whatsapp_config, owned_whatsapp = _whatsapp_config(settings, whatsapp_provider)
        whatsapp.configure(whatsapp_config)
        whatsapp_send.configure(app.state.session_factory)
        telephony_config, owned_telephony = _telephony_config(settings, telephony_provider)
        telephony.configure(telephony_config)
        app.state.missed_calls = (
            MissedCallConnector(app.state.session_factory, telephony_config)
            if telephony_config is not None and app.state.session_factory is not None
            else None
        )
        app.state.whatsapp_connector = (
            WhatsAppConnector(
                app.state.session_factory,
                whatsapp_config,
                on_status=app.state.missed_calls.on_whatsapp_status
                if app.state.missed_calls is not None
                else None,
            )
            if whatsapp_config is not None and app.state.session_factory is not None
            else None
        )
        if settings.automotive_site == "fake":  # local and e2e only; refused when deployed
            app.state.automotive_client_factory = fake_site.fake_client
            app.state.automotive_resolver = fake_site.fake_resolver
        billing_config = _billing_config(settings, billing_provider)
        app.state.billing_config = billing_config
        app.state.billing_webhooks = (
            BillingWebhooks(app.state.session_factory, billing_config)
            if billing_config is not None and app.state.session_factory is not None
            else None
        )
        try:
            yield
        finally:
            email.configure(None)
            whatsapp.configure(None)
            whatsapp_send.configure(None)
            telephony.configure(None)
            if owned_telephony is not None:
                await owned_telephony.aclose()
            if owned is not None:
                await owned.aclose()
            if owned_whatsapp is not None:
                await owned_whatsapp.aclose()
            if billing_config is not None and isinstance(billing_config.provider, StripeProvider):
                await billing_config.provider.aclose()
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Onyx Platform API",
        version=settings.version,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)

    # /health stays unversioned for load balancers; the product API is versioned.
    app.include_router(health_router)
    v1 = APIRouter(prefix=API_VERSION_PREFIX)
    v1.include_router(me_router)
    v1.include_router(workspaces_router)
    v1.include_router(audit_router)
    v1.include_router(modules_router)
    v1.include_router(tasks_router)
    v1.include_router(billing_router)
    v1.include_router(controls_router)
    v1.include_router(admin_router)
    v1.include_router(admin_organizations_router)
    v1.include_router(ai_router)
    v1.include_router(crm_router)
    v1.include_router(catalogue_router)
    v1.include_router(inbox_router)
    v1.include_router(quotations_router)
    v1.include_router(assistant_router)
    v1.include_router(automotive_router)
    v1.include_router(outbound_router)
    v1.include_router(knowledge_router)
    v1.include_router(webhooks_router)
    app.include_router(v1)
    return app


app = create_app()
