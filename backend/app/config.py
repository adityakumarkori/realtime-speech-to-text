import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_ENVIRONMENT = "development"
DEFAULT_LOG_LEVEL = "INFO"
VALID_ENVIRONMENTS = ("development", "test", "production")
VALID_LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
DATABASE_PLACEHOLDER_MARKERS = (
    "replace_with",
    "your_password",
    "your-password",
)


class AppConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class AppSettings:
    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL


@dataclass(frozen=True)
class DatabaseSettings:
    url: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        value = "<redacted>" if self.url else None
        return f"DatabaseSettings(url={value!r})"


def default_env_file() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def _load_values(
    env_file: Path | None,
    environ: Mapping[str, str] | None,
) -> dict[str, str]:
    path = env_file if env_file is not None else default_env_file()
    values = dict(os.environ if environ is None else environ)

    if path.is_file():
        for key, value in dotenv_values(path).items():
            if value is not None and key not in values:
                values[key] = value
    return values


def load_app_settings(
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppSettings:
    values = _load_values(env_file, environ)
    environment = (values.get("APP_ENV") or DEFAULT_ENVIRONMENT).strip().lower()
    if environment not in VALID_ENVIRONMENTS:
        allowed = ", ".join(VALID_ENVIRONMENTS)
        raise AppConfigurationError(
            f"APP_ENV must be one of: {allowed}."
        )

    log_level = (values.get("LOG_LEVEL") or DEFAULT_LOG_LEVEL).strip().upper()
    if log_level not in VALID_LOG_LEVELS:
        allowed = ", ".join(VALID_LOG_LEVELS)
        raise AppConfigurationError(
            f"LOG_LEVEL must be one of: {allowed}."
        )

    return AppSettings(environment=environment, log_level=log_level)


def load_database_settings(
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DatabaseSettings:
    values = _load_values(env_file, environ)
    url = (values.get("DATABASE_URL") or "").strip()
    if not url:
        return DatabaseSettings()

    lowered_url = url.lower()
    if any(marker in lowered_url for marker in DATABASE_PLACEHOLDER_MARKERS):
        raise AppConfigurationError(
            "DATABASE_URL is still a placeholder. Set a real database URL "
            "in backend/.env or the environment."
        )

    try:
        make_url(url)
    except ArgumentError:
        raise AppConfigurationError("DATABASE_URL is not a valid URL.") from None

    return DatabaseSettings(url=url)
