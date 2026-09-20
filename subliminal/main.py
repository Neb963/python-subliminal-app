from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import __version__
from .config import state_dir


def configure_logging() -> None:
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / "subliminal.log",
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def main() -> int:
    diagnose = "--diagnose" in sys.argv[1:]
    show_version = "--version" in sys.argv[1:] or "-V" in sys.argv[1:]
    background = "--background" in sys.argv[1:]
    argv = [
        arg for arg in sys.argv
        if arg not in {"--background", "--diagnose", "--version", "-V"}
    ]
    configure_logging()
    if show_version:
        print(f"Subliminal {__version__}")
        return 0
    if diagnose:
        from .diagnostics import run_diagnostics
        return run_diagnostics()
    try:
        from .app import SubliminalApplication
    except (ImportError, OSError, ValueError) as exc:
        print(
            "Subliminal could not load its GTK/Wayland dependencies.\n"
            "On Fedora install: python3-gobject gtk4 gtk4-layer-shell python3-cairo python3-pillow librsvg2\n"
            f"Details: {exc}",
            file=sys.stderr,
        )
        return 2
    app = SubliminalApplication(background=background)
    return app.run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
