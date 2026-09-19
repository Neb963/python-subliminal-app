from __future__ import annotations

import logging
from dataclasses import dataclass

from .gtk_runtime import Gdk, Gio, GLib, Gtk, LayerShell, cairo
from .media import MediaCache
from .model import AppConfig, Scene
from .render import SceneView

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class MonitorInfo:
    key: str
    connector: str
    description: str
    width: int
    height: int
    scale_factor: int
    refresh_hz: float | None
    monitor: object


def enumerate_monitors() -> list[MonitorInfo]:
    display = Gdk.Display.get_default()
    if display is None:
        return []
    model = display.get_monitors()
    result: list[MonitorInfo] = []
    for index in range(model.get_n_items()):
        monitor = model.get_item(index)
        connector = monitor.get_connector() or f"monitor-{index + 1}"
        manufacturer = monitor.get_manufacturer() or ""
        model_name = monitor.get_model() or ""
        description = " ".join(part for part in (manufacturer, model_name) if part).strip() or connector
        geometry = monitor.get_geometry()
        refresh_mhz = monitor.get_refresh_rate()
        result.append(
            MonitorInfo(
                key=connector,
                connector=connector,
                description=description,
                width=geometry.width,
                height=geometry.height,
                scale_factor=monitor.get_scale_factor(),
                refresh_hz=(refresh_mhz / 1000.0) if refresh_mhz > 0 else None,
                monitor=monitor,
            )
        )
    return result


class OverlayWindow:
    def __init__(self, application: Gtk.Application, monitor_info: MonitorInfo, media: MediaCache) -> None:
        self.monitor_info = monitor_info
        self.media = media
        self.window = Gtk.Window(application=application)
        self.window.set_decorated(False)
        self.window.set_resizable(True)
        self.window.add_css_class("subliminal-overlay")
        self._views: dict[str, SceneView] = {}
        self._active: SceneView | None = None

        LayerShell.init_for_window(self.window)
        LayerShell.set_namespace(self.window, "subliminal-overlay")
        LayerShell.set_monitor(self.window, monitor_info.monitor)
        LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.NONE)
        LayerShell.set_exclusive_zone(self.window, 0)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(self.window, edge, True)

        self.window.connect("realize", self._make_click_through)
        self.window.connect("map", self._make_click_through)
        self.rebuild([])
        self.window.present()

    def rebuild(self, scenes: list[Scene]) -> None:
        if self._active is not None:
            self._active.stop_animations()
        stack = Gtk.Stack()
        stack.set_hexpand(True)
        stack.set_vexpand(True)
        blank = Gtk.Box()
        blank.add_css_class("subliminal-blank")
        stack.add_named(blank, "__blank__")
        self._views = {}
        for scene in scenes:
            view = SceneView(scene, self.media)
            self._views[scene.id] = view
            stack.add_named(view, scene.id)
        stack.set_visible_child_name("__blank__")
        self.window.set_child(stack)
        self.stack = stack
        self._active = None
        GLib.idle_add(self._make_click_through)

    def show_scene(self, scene_id: str) -> None:
        view = self._views.get(scene_id)
        if view is None:
            return
        if self._active is not None and self._active is not view:
            self._active.stop_animations()
        self.stack.set_visible_child_name(scene_id)
        self._active = view
        view.start_animations()
        self._make_click_through()

    def clear(self) -> None:
        if self._active is not None:
            self._active.stop_animations()
        self._active = None
        self.stack.set_visible_child_name("__blank__")
        self._make_click_through()

    def destroy(self) -> None:
        if self._active is not None:
            self._active.stop_animations()
        self.window.destroy()

    def _make_click_through(self, *_args) -> bool:
        surface = self.window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())
        return GLib.SOURCE_REMOVE


class OverlayManager:
    def __init__(self, application: Gtk.Application, get_config) -> None:
        self.application = application
        self.get_config = get_config
        self.media = MediaCache()
        self.windows: dict[str, OverlayWindow] = {}
        self._monitor_model: Gio.ListModel | None = None
        self._monitors_handler: int | None = None

    @staticmethod
    def supported() -> bool:
        try:
            return bool(LayerShell.is_supported())
        except Exception:
            return False

    def start(self) -> None:
        self.sync_monitors()
        display = Gdk.Display.get_default()
        if display is not None and self._monitor_model is None:
            self._monitor_model = display.get_monitors()
            self._monitors_handler = self._monitor_model.connect("items-changed", self._on_monitors_changed)

    def stop(self) -> None:
        for window in list(self.windows.values()):
            window.destroy()
        self.windows.clear()
        if self._monitor_model is not None and self._monitors_handler is not None:
            self._monitor_model.disconnect(self._monitors_handler)
        self._monitor_model = None
        self._monitors_handler = None

    def sync_monitors(self) -> None:
        config: AppConfig = self.get_config()
        infos = enumerate_monitors()
        wanted = {
            info.key: info
            for info in infos
            if config.display.mode == "all" or info.connector in config.display.connectors
        }
        for key in list(self.windows):
            if key not in wanted:
                self.windows.pop(key).destroy()
        for key, info in wanted.items():
            if key not in self.windows:
                self.windows[key] = OverlayWindow(self.application, info, self.media)
        self.rebuild_scenes()

    def rebuild_scenes(self) -> None:
        scenes = self.get_config().scenes
        for window in self.windows.values():
            window.rebuild(scenes)

    def show_scene(self, scene: Scene) -> None:
        if not self.windows:
            self.start()
        for window in self.windows.values():
            window.show_scene(scene.id)

    def clear(self) -> None:
        for window in self.windows.values():
            window.clear()

    def monitors(self) -> list[MonitorInfo]:
        return enumerate_monitors()

    def _on_monitors_changed(self, *_args) -> None:
        GLib.idle_add(self._sync_after_change)

    def _sync_after_change(self) -> bool:
        self.sync_monitors()
        return GLib.SOURCE_REMOVE
