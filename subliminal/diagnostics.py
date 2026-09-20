from __future__ import annotations

import os
import platform
import sys

from . import __version__


def run_diagnostics() -> int:
    print("Subliminal diagnostics")
    print(f"Version: {__version__}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"System: {platform.platform()}")
    print(f"XDG_SESSION_TYPE: {os.environ.get('XDG_SESSION_TYPE', '<unset>')}")
    print(f"WAYLAND_DISPLAY: {os.environ.get('WAYLAND_DISPLAY', '<unset>')}")
    print(f"XDG_CURRENT_DESKTOP: {os.environ.get('XDG_CURRENT_DESKTOP', '<unset>')}")

    try:
        from .gtk_runtime import Gdk, Gtk, LayerShell
    except Exception as exc:
        print(f"GTK runtime: FAIL ({exc})")
        return 2

    try:
        Gtk.init()
        display = Gdk.Display.get_default()
        if display is None:
            print("GDK display: FAIL (no display)")
            return 3
        print(f"GDK display: OK ({type(display).__name__})")
        supported = bool(LayerShell.is_supported())
        print(f"Layer shell: {'OK' if supported else 'UNAVAILABLE'}")
        monitors = display.get_monitors()
        print(f"Monitors: {monitors.get_n_items()}")
        for index in range(monitors.get_n_items()):
            monitor = monitors.get_item(index)
            geo = monitor.get_geometry()
            connector = monitor.get_connector() or f"monitor-{index + 1}"
            refresh = monitor.get_refresh_rate() / 1000.0
            print(
                f"  {connector}: {geo.width}x{geo.height}, "
                f"scale={monitor.get_scale_factor()}, refresh={refresh:.2f} Hz"
            )
        return 0 if supported else 4
    except Exception as exc:
        print(f"Runtime probe: FAIL ({exc})")
        return 5
