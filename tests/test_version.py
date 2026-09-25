from pathlib import Path
import tomllib

import subliminal


def test_package_version_matches_pyproject() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert subliminal.__version__ == project["project"]["version"]
