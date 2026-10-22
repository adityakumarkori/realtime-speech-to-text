import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

DEFAULT_MODEL = "gemini-3.5-transcribe-live"
_PLACEHOLDER_MARKERS = ("replace_with", "your_api_key", "your-api-key")


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL

    def __repr__(self) -> str:
        return f"Settings(api_key=<redacted>, model={self.model!r})"


def default_env_file() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def load_settings(
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    path = env_file if env_file is not None else default_env_file()
    values = dict(os.environ if environ is None else environ)

    if path.is_file():
        for key, value in dotenv_values(path).items():
            if value is not None and key not in values:
                values[key] = value

    api_key = (values.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise ConfigurationError(
            "GEMINI_API_KEY is not set. Copy backend/.env.example to "
            "backend/.env and add a key from Google AI Studio."
        )

    lowered_key = api_key.lower()
    if any(marker in lowered_key for marker in _PLACEHOLDER_MARKERS):
        raise ConfigurationError(
            "GEMINI_API_KEY is still a placeholder. Set a real key in "
            "backend/.env or the environment."
        )

    model = (values.get("GEMINI_LIVE_MODEL") or DEFAULT_MODEL).strip()
    if not model:
        raise ConfigurationError("GEMINI_LIVE_MODEL must not be empty.")

    return Settings(api_key=api_key, model=model)


def parse_language_codes(value: str) -> list[str]:
    text = value.strip()
    if not text or text.lower() == "auto":
        return []

    codes: list[str] = []
    for part in text.split(","):
        code = part.strip()
        if not code:
            continue
        if any(character.isspace() for character in code):
            raise ConfigurationError(
                f"Invalid language code {code!r}. Use comma-separated "
                "BCP-47 codes such as hi-IN,en-IN."
            )
        codes.append(code)

    if not codes:
        raise ConfigurationError(
            "No language codes were provided. Use auto or BCP-47 codes."
        )
    return codes
