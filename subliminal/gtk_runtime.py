from __future__ import annotations

import ctypes

# gtk4-layer-shell must be loaded before libwayland-client (which GTK may pull in).
# Upstream's Python example explicitly preloads the library for this reason.
try:
    ctypes.CDLL("libgtk4-layer-shell.so.0", mode=ctypes.RTLD_GLOBAL)
except OSError:
    ctypes.CDLL("libgtk4-layer-shell.so", mode=ctypes.RTLD_GLOBAL)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, Gtk4LayerShell, Pango
import cairo

LayerShell = Gtk4LayerShell

__all__ = [
    "Gdk",
    "GdkPixbuf",
    "Gio",
    "GLib",
    "GObject",
    "Gtk",
    "LayerShell",
    "Pango",
    "cairo",
]
