from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.middleware import RequestIdMiddleware
from app.core.observability import configure_logging, init_error_tracking


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings, service="api")
    init_error_tracking(settings)
    app = FastAPI(title=settings.app_name)
    app.state.request_id_header = settings.request_id_header
    app.dependency_overrides[get_settings] = lambda: settings
    app.add_middleware(RequestIdMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    @app.get("/health", tags=["Health"], summary="Application liveness check")
    async def root_health() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "environment": settings.environment,
            "status": "ok",
        }

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
