import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import (
    AppSettings,
    DatabaseSettings,
    load_app_settings,
    load_database_settings,
)
from app.database import Database
from app.errors import register_exception_handlers
from app.logging_config import configure_logging
from app.live import LiveRunner, LiveTranscriptionRunner
from app.routes.health import router as health_router
from app.routes.transcription import router as transcription_router
from app.services import TranscriptService

APP_TITLE = "Real-time Speech-to-Text API"
APP_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database: Database = app.state.database
    database.start()
    try:
        yield
    finally:
        database.dispose()


def create_app(
    settings: AppSettings | None = None,
    database_settings: DatabaseSettings | None = None,
    live_runner: LiveRunner | None = None,
) -> FastAPI:
    resolved_settings = settings if settings is not None else load_app_settings()
    resolved_database_settings = (
        database_settings
        if database_settings is not None
        else load_database_settings()
    )
    configure_logging(resolved_settings.log_level)

    database = Database(resolved_database_settings)
    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.transcript_service = TranscriptService(database)

    if live_runner is None:
        live_runner = LiveTranscriptionRunner(
            transcript_service=app.state.transcript_service,
            database=database,
        )
    app.state.live_runner = live_runner

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(transcription_router)

    logger.info(
        "Starting %s in %s environment",
        APP_TITLE,
        resolved_settings.environment,
    )
    return app


app = create_app()
