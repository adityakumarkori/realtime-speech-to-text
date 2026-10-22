from dataclasses import fields

import pytest

from app.config import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_LOG_LEVEL,
    AppConfigurationError,
    AppSettings,
    DatabaseSettings,
    load_app_settings,
    load_database_settings,
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
    assert field_names == {"environment", "log_level", "cors_origins"}


def test_cors_origins_are_parsed_and_normalized(tmp_path):
    settings = load_app_settings(
        env_file=tmp_path / "missing.env",
        environ={
            "CORS_ORIGINS": (
                " HTTPS://APP.EXAMPLE.TEST:443/ , "
                "http://127.0.0.1:5173,https://app.example.test "
            )
        },
    )

    assert settings.cors_origins == (
        "https://app.example.test",
        "http://127.0.0.1:5173",
    )


def test_blank_cors_origins_are_empty(tmp_path):
    settings = load_app_settings(
        env_file=tmp_path / "missing.env",
        environ={"CORS_ORIGINS": "  ,  "},
    )

    assert settings.cors_origins == ()


@pytest.mark.parametrize(
    "value",
    [
        "app.example.test",
        "ftp://app.example.test",
        "https://app.example.test/api",
        "https://user:secret@app.example.test",
        "https://app.example.test?debug=1",
        "https://app.example.test#section",
        "https://app.example.test:notaport",
        "http://[::1",
    ],
)
def test_invalid_cors_origins_are_rejected(tmp_path, value):
    with pytest.raises(AppConfigurationError, match="CORS_ORIGINS"):
        load_app_settings(
            env_file=tmp_path / "missing.env",
            environ={"CORS_ORIGINS": value},
        )


def test_database_url_defaults_to_unconfigured(tmp_path):
    settings = load_database_settings(
        env_file=tmp_path / "missing.env",
        environ={},
    )
    assert settings.url is None


def test_blank_database_url_is_unconfigured(tmp_path):
    settings = load_database_settings(
        env_file=tmp_path / "missing.env",
        environ={"DATABASE_URL": "   "},
    )
    assert settings.url is None


def test_database_url_is_loaded_from_dotenv(tmp_path):
    url = "postgresql+psycopg://user:password@localhost:5432/test_db"
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={url}\n", encoding="utf-8")

    settings = load_database_settings(env_file=env_file, environ={})

    assert settings.url == url


def test_process_environment_database_url_overrides_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=sqlite+pysqlite:///file.db\n",
        encoding="utf-8",
    )

    settings = load_database_settings(
        env_file=env_file,
        environ={"DATABASE_URL": "sqlite+pysqlite:///process.db"},
    )

    assert settings.url == "sqlite+pysqlite:///process.db"


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+psycopg://replace_with_user:secret@localhost/test_db",
        "postgresql+psycopg://user:your_password@localhost/test_db",
    ],
)
def test_database_placeholder_is_rejected(tmp_path, value):
    with pytest.raises(AppConfigurationError, match="placeholder"):
        load_database_settings(
            env_file=tmp_path / "missing.env",
            environ={"DATABASE_URL": value},
        )


def test_invalid_database_url_is_rejected_without_echoing_value(tmp_path):
    value = "not-a-valid-url"
    with pytest.raises(AppConfigurationError) as exc_info:
        load_database_settings(
            env_file=tmp_path / "missing.env",
            environ={"DATABASE_URL": value},
        )

    assert "DATABASE_URL" in str(exc_info.value)
    assert value not in str(exc_info.value)


def test_database_settings_repr_redacts_url():
    settings = DatabaseSettings(
        url="postgresql+psycopg://user:secret@localhost/test_db"
    )

    text = repr(settings)

    assert "secret" not in text
    assert "<redacted>" in text
