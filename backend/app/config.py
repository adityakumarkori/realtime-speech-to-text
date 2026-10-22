import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

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
    cors_origins: tuple[str, ...] = ()


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


def _parse_cors_origins(value: str) -> tuple[str, ...]:
    origins: list[str] = []
    for raw_origin in value.split(","):
        candidate = raw_origin.strip().rstrip("/")
        if not candidate:
            continue

        try:
            parts = urlsplit(candidate)
            port = parts.port
        except ValueError:
            parts = None
            port = None
        if (
            parts is None
            or parts.scheme not in ("http", "https")
            or not parts.netloc
            or parts.username
            or parts.password
            or parts.path
            or parts.query
            or parts.fragment
        ):
            raise AppConfigurationError(
                "CORS_ORIGINS entries must be absolute http:// or https:// "
                "origins without paths, credentials, queries, or fragments."
            )

        hostname = parts.hostname or ""
        host = f"[{hostname}]" if ":" in hostname else hostname
        default_port = 443 if parts.scheme == "https" else 80
        if port is not None and port != default_port:
            host = f"{host}:{port}"

        origin = f"{parts.scheme}://{host}"
        if origin not in origins:
            origins.append(origin)

    return tuple(origins)


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

    cors_origins = _parse_cors_origins(values.get("CORS_ORIGINS") or "")

    return AppSettings(
        environment=environment,
        log_level=log_level,
        cors_origins=cors_origins,
    )


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
