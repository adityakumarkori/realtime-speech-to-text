import subprocess
import sys
from pathlib import Path

import app


def test_app_package_does_not_shadow_stdlib_logging():
    package_dir = Path(app.__file__).resolve().parent

    assert not (package_dir / "logging.py").exists()
    assert (package_dir / "logging_config.py").is_file()


def test_main_entrypoint_imports_from_app_directory():
    app_dir = Path(app.__file__).resolve().parent

    result = subprocess.run(
        [sys.executable, "-c", "import main; print(main.APP_TITLE)"],
        cwd=app_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Real-time Speech-to-Text API" in result.stdout
