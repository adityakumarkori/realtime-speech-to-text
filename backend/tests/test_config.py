import pytest

from poc.config import (
    DEFAULT_MODEL,
    ConfigurationError,
    Settings,
    load_settings,
    parse_language_codes,
)


def test_missing_api_key_raises(tmp_path):
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        load_settings(env_file=tmp_path / "missing.env", environ={})


@pytest.mark.parametrize("value", ["   ", "replace_with_your_key", "your_api_key"])
def test_blank_or_placeholder_key_raises(tmp_path, value):
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        load_settings(
            env_file=tmp_path / "missing.env",
            environ={"GEMINI_API_KEY": value},
        )


def test_api_key_and_default_model(tmp_path):
    settings = load_settings(
        env_file=tmp_path / "missing.env",
        environ={"GEMINI_API_KEY": " test-key "},
    )
    assert settings.api_key == "test-key"
    assert settings.model == DEFAULT_MODEL


def test_custom_model_from_environment(tmp_path):
    settings = load_settings(
        env_file=tmp_path / "missing.env",
        environ={
            "GEMINI_API_KEY": "test-key",
            "GEMINI_LIVE_MODEL": "custom-model",
        },
    )
    assert settings.model == "custom-model"


def test_environment_key_overrides_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=file-key\nGEMINI_LIVE_MODEL=file-model\n",
        encoding="utf-8",
    )
    settings = load_settings(
        env_file=env_file,
        environ={"GEMINI_API_KEY": "process-key"},
    )
    assert settings.api_key == "process-key"
    assert settings.model == "file-model"


def test_dotenv_file_is_loaded_when_environment_is_empty(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=file-key\n", encoding="utf-8")
    settings = load_settings(env_file=env_file, environ={})
    assert settings.api_key == "file-key"


def test_settings_repr_redacts_key():
    text = repr(Settings(api_key="secret-key", model="test-model"))
    assert "secret-key" not in text
    assert "<redacted>" in text


def test_parse_language_codes_auto_variants():
    assert parse_language_codes("auto") == []
    assert parse_language_codes("") == []
    assert parse_language_codes("AUTO") == []


def test_parse_language_codes_list():
    assert parse_language_codes("hi-IN, en-IN") == ["hi-IN", "en-IN"]


def test_parse_language_codes_rejects_whitespace_inside_code():
    with pytest.raises(ConfigurationError, match="Invalid language code"):
        parse_language_codes("hi IN,en-IN")


def test_parse_language_codes_rejects_only_commas():
    with pytest.raises(ConfigurationError, match="No language codes"):
        parse_language_codes(" , ")
