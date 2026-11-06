"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.gateway import AIGateway
from app.ai.providers import ModelFactory, build_model
from app.api.admin import router as admin_router
from app.api.ai import router as ai_router
from app.api.audit import router as audit_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.modules import router as modules_router
from app.api.workspaces import router as workspaces_router
from app.core.auth.tokens import TokenVerifier
from app.core.config import Settings, get_settings
from app.core.db.session import create_engine, create_session_factory
from app.core.errors import install_error_handlers
from app.core.logging import REQUEST_ID_HEADER, RequestIdMiddleware, configure_logging
from app.modules.assistant.routes import router as assistant_router
from app.modules.catalogue.routes import router as catalogue_router
from app.modules.crm.routes import router as crm_router
from app.modules.inbox.routes import router as inbox_router
from app.modules.outbound.routes import router as outbound_router
from app.modules.quotations.routes import router as quotations_router


def _default_verifier(settings: Settings) -> TokenVerifier | None:
    if settings.jwks_url is None or settings.jwt_issuer is None:
        return None
    return TokenVerifier.for_jwks_url(
        jwks_url=settings.jwks_url, issuer=settings.jwt_issuer, audience=settings.jwt_audience
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
) -> FastAPI:
    """Build the app. Auth and database are optional: without them those routes return 503."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

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
            )
            if app.state.session_factory is not None
            else None
        )
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Onyx Platform API",
        version=settings.version,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.dependency_overrides[get_settings] = lambda: settings

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
    v1.include_router(admin_router)
    v1.include_router(ai_router)
    v1.include_router(crm_router)
    v1.include_router(catalogue_router)
    v1.include_router(inbox_router)
    v1.include_router(quotations_router)
    v1.include_router(assistant_router)
    v1.include_router(outbound_router)
    app.include_router(v1)
    return app


app = create_app()
