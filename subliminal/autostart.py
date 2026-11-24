from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .config import _xdg_dir

APP_ID = "io.github.neb963.Subliminal"
DESKTOP_FILE = "io.github.neb963.Subliminal.desktop"

_DESKTOP_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')


def autostart_path() -> Path:
    config_home = _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")
    return config_home / "autostart" / DESKTOP_FILE


def _quote_desktop_arg(arg: str) -> str:
    """Quote an Exec argument according to the FreeDesktop Desktop Entry spec."""
    # Escape % as %% so field-code expansion does not corrupt literal paths.
    escaped = arg.replace("%", "%%")
    if not escaped or any(ch in _DESKTOP_RESERVED for ch in escaped):
        escaped = (
            escaped.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("`", "\\`")
            .replace("$", "\\$")
        )
        return f'"{escaped}"'
    return escaped


def _launcher_argv() -> list[str]:
    """Return a stable launcher argv for the desktop autostart entry."""
    explicit = os.environ.get("SUBLIMINAL_EXECUTABLE")
    if explicit:
        return [str(Path(explicit).expanduser().resolve())]
    installed = shutil.which("subliminal")
    if installed:
        return [installed]
    # Development fallback. This is mainly useful when the package is installed
    # into the current interpreter's site-packages.
    return [sys.executable, "-m", "subliminal"]


def _launcher_command() -> str:
    """Return a properly quoted Exec launcher string for the autostart entry."""
    return " ".join(_quote_desktop_arg(part) for part in _launcher_argv())


def set_autostart(enabled: bool) -> None:
    path = autostart_path()
    if not enabled:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    command = _launcher_command()
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Subliminal\n"
        "Comment=Text and image overlay scheduler\n"
        f"Exec={command} --background\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
