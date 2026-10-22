from pathlib import Path

import app


def test_app_package_does_not_shadow_stdlib_logging():
    package_dir = Path(app.__file__).resolve().parent

    assert not (package_dir / "logging.py").exists()
    assert (package_dir / "logging_config.py").is_file()
