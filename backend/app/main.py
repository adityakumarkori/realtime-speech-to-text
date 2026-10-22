import logging

from fastapi import FastAPI

from app.config import AppSettings, load_app_settings
from app.errors import register_exception_handlers
from app.logging import configure_logging
from app.routes.health import router as health_router

APP_TITLE = "Real-time Speech-to-Text API"
APP_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings if settings is not None else load_app_settings()
    configure_logging(resolved_settings.log_level)

    app = FastAPI(title=APP_TITLE, version=APP_VERSION)
    app.state.settings = resolved_settings

    register_exception_handlers(app)
    app.include_router(health_router)

    logger.info(
        "Starting %s in %s environment",
        APP_TITLE,
        resolved_settings.environment,
    )
    return app


app = create_app()
