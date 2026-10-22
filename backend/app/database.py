import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    pass


class Database:
    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def is_configured(self) -> bool:
        return self._session_factory is not None

    def start(self) -> None:
        if self.is_configured:
            return

        if not self._settings.url:
            logger.warning(
                "DATABASE_URL is not set; transcript persistence is disabled."
            )
            return

        self._engine = create_engine(self._settings.url, pool_pre_ping=True)
        self._session_factory = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )
        logger.info("Database engine configured.")

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session_factory = self._session_factory
        if session_factory is None:
            raise DatabaseUnavailableError(
                "Transcript persistence is not configured."
            )

        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine = None
        self._session_factory = None
