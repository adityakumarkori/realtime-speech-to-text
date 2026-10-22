import logging
from typing import Final

APP_CONSOLE_HANDLER: Final = "app-console"
APP_LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str) -> None:
    numeric_level = logging.getLevelName(level.strip().upper())
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level!r}.")

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    if any(
        handler.get_name() == APP_CONSOLE_HANDLER
        for handler in root_logger.handlers
    ):
        return

    handler = logging.StreamHandler()
    handler.set_name(APP_CONSOLE_HANDLER)
    handler.setFormatter(logging.Formatter(APP_LOG_FORMAT))
    root_logger.addHandler(handler)
