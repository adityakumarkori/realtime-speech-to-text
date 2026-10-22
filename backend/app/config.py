import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

DEFAULT_ENVIRONMENT = "development"
DEFAULT_LOG_LEVEL = "INFO"
VALID_ENVIRONMENTS = ("development", "test", "production")
VALID_LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")


class AppConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class AppSettings:
    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL


def default_env_file() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def load_app_settings(
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppSettings:
    path = env_file if env_file is not None else default_env_file()
    values = dict(os.environ if environ is None else environ)

    if path.is_file():
        for key, value in dotenv_values(path).items():
            if value is not None and key not in values:
                values[key] = value

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
