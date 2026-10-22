from dataclasses import fields

import pytest

from app.config import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_LOG_LEVEL,
    AppConfigurationError,
    AppSettings,
    load_app_settings,
)


def test_defaults_do_not_require_gemini_configuration(tmp_path):
    settings = load_app_settings(
        env_file=tmp_path / "missing.env",
        environ={},
    )
    assert settings.environment == DEFAULT_ENVIRONMENT
    assert settings.log_level == DEFAULT_LOG_LEVEL


def test_values_are_normalized(tmp_path):
    settings = load_app_settings(
        env_file=tmp_path / "missing.env",
        environ={"APP_ENV": " Test ", "LOG_LEVEL": " debug "},
    )
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"


def test_dotenv_values_are_loaded(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=production\nLOG_LEVEL=ERROR\n",
        encoding="utf-8",
    )
    settings = load_app_settings(env_file=env_file, environ={})
    assert settings.environment == "production"
    assert settings.log_level == "ERROR"


def test_process_environment_overrides_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=production\nLOG_LEVEL=ERROR\n",
        encoding="utf-8",
    )
    settings = load_app_settings(
        env_file=env_file,
        environ={"APP_ENV": "test"},
    )
    assert settings.environment == "test"
    assert settings.log_level == "ERROR"


@pytest.mark.parametrize("value", ["staging", "prod", "unknown"])
def test_invalid_app_env_is_rejected(tmp_path, value):
    with pytest.raises(AppConfigurationError, match="APP_ENV"):
        load_app_settings(
            env_file=tmp_path / "missing.env",
            environ={"APP_ENV": value},
        )


@pytest.mark.parametrize("value", ["VERBOSE", "TRACE", "10"])
def test_invalid_log_level_is_rejected(tmp_path, value):
    with pytest.raises(AppConfigurationError, match="LOG_LEVEL"):
        load_app_settings(
            env_file=tmp_path / "missing.env",
            environ={"LOG_LEVEL": value},
        )


def test_app_settings_do_not_contain_credentials():
    field_names = {item.name for item in fields(AppSettings)}
    assert field_names == {"environment", "log_level"}
