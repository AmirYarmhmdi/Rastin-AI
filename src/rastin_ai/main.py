"""File guide.

- Use: Creates the FastAPI application and wires startup, logging, routers, and
  errors.
- Usage: Import create_app, create_lifespan, and main from rastin_ai.main.
- Duties: Defines create_app, create_lifespan, and main and related helper logic.
- Depends on: Project modules: rastin_ai.api.router, rastin_ai.core.config,
  rastin_ai.core.exceptions, and rastin_ai.core.logging.
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rastin_ai.api.dependencies import close_storage_providers
from rastin_ai.api.router import router as api_router
from rastin_ai.core.config import (
    Settings,
    cors_allowed_origins,
    get_settings,
    safe_configuration_summary,
    validate_startup_configuration,
)
from rastin_ai.core.exceptions import register_exception_handlers
from rastin_ai.core.logging import configure_logging
from rastin_ai.database.engine import dispose_engine
from rastin_ai.observability import shutdown_observability, startup_observability

logger = logging.getLogger(__name__)


# This creates the startup and shutdown behavior for the FastAPI app.
def create_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Log basic startup information without exposing secrets.
        logger.info(
            "Starting %s version %s in %s environment",
            settings.APP_NAME,
            settings.APP_VERSION,
            settings.ENVIRONMENT,
        )
        startup_observability(settings)
        try:
            yield
        finally:
            shutdown_observability(settings)
            await close_storage_providers()
            await dispose_engine()
            logger.info("Stopping %s", settings.APP_NAME)

    return lifespan


# This builds and configures the FastAPI application.
def create_app() -> FastAPI:
    # Load settings once and use them to configure the app.
    settings = get_settings()
    validate_startup_configuration(settings)
    configure_logging(settings.LOG_LEVEL)

    # Create the FastAPI app with project name, version, debug mode, and lifespan.
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=create_lifespan(settings),
    )

    origins = cors_allowed_origins(settings)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Store settings on the app and connect routers and exception handlers.
    app.state.settings = settings
    app.include_router(api_router)
    register_exception_handlers(app)

    # This is a minimal root endpoint for a quick running check.
    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
        }

    logger.info(
        "Application initialized: name=%s version=%s environment=%s",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )
    logger.info("Configuration summary: %s", safe_configuration_summary(settings))

    return app


# This is the app object used by Uvicorn.
app = create_app()


# This is a small command-line helper if this file is run directly.
def main() -> None:
    settings = get_settings()
    print(
        f"{settings.APP_NAME} backend is ready. "
        f"Run: uvicorn rastin_ai.main:app --reload"
    )


if __name__ == "__main__":
    main()
