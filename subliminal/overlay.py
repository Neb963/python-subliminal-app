from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

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
    """One permanently mapped, click-through layer-shell surface per monitor."""

    def __init__(self, application: Gtk.Application, monitor_info: MonitorInfo, media: MediaCache) -> None:
        self.monitor_info = monitor_info
        self.media = media
        self.window = Gtk.Window(application=application)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_focusable(False)
        self.window.set_default_size(monitor_info.width, monitor_info.height)
        self.window.add_css_class("subliminal-overlay")

        self._views: dict[str, SceneView] = {}
        self._active: SceneView | None = None
        self._tick_id: int | None = None
        self._watchdog_id: int | None = None
        self._target_frames = 1
        self._completed_frames = 0
        self._first_tick_seen = False
        self._done: Callable[[], None] | None = None
        self._pending_flash: tuple[str, int, Callable[[], None]] | None = None

        LayerShell.init_for_window(self.window)
        LayerShell.set_namespace(self.window, "subliminal-overlay")
        LayerShell.set_monitor(self.window, monitor_info.monitor)
        LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.NONE)
        LayerShell.set_exclusive_zone(self.window, 0)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(self.window, edge, True)

        self.window.connect("realize", self._make_click_through)
        self.window.connect("map", self._on_mapped)
        self.rebuild([])
        self.window.present()

    def rebuild(self, scenes: list[Scene]) -> None:
        # Rebuilding invalidates presentation widgets, so cancel without completing it.
        self.cancel_flash()
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
        self.window.queue_draw()
        GLib.idle_add(self._make_click_through)

    def flash_scene(self, scene_id: str, frames: int, done: Callable[[], None]) -> None:
        self.cancel_flash()
        if not self.window.get_mapped():
            self._pending_flash = (scene_id, max(1, int(frames)), done)
            self.window.present()
            return

        view = self._views.get(scene_id)
        if view is None:
            LOG.warning("Scene %s is not built on monitor %s", scene_id, self.monitor_info.connector)
            GLib.idle_add(self._invoke_once, done)
            return

        self.stack.set_visible_child_name(scene_id)
        self._active = view
        view.start_animations()
        self._target_frames = max(1, int(frames))
        self._completed_frames = 0
        self._first_tick_seen = False
        self._done = done

        # Changing the visible stack child requests drawing, and the tick callback
        # keeps the frame clock running. We intentionally do not count the first
        # tick: tick callbacks run in GTK's Update phase before Paint. The first
        # tick therefore prepares the first actually visible frame.
        view.queue_draw()
        self.stack.queue_draw()
        self.window.queue_draw()
        self._tick_id = self.window.add_tick_callback(self._on_tick)

        refresh = self.monitor_info.refresh_hz or 60.0
        expected_ms = (self._target_frames / refresh) * 1000.0
        watchdog_ms = max(1000, round(expected_ms * 10 + 500))
        self._watchdog_id = GLib.timeout_add(watchdog_ms, self._on_watchdog)

        LOG.debug(
            "Flash %s on %s for %d frames (%.2f Hz)",
            scene_id,
            self.monitor_info.connector,
            self._target_frames,
            refresh,
        )

    def cancel_flash(self) -> None:
        self._pending_flash = None
        self._remove_tick()
        self._remove_watchdog()
        self._done = None
        self._set_blank()

    def destroy(self) -> None:
        self.cancel_flash()
        self.window.destroy()

    def _on_tick(self, _widget, _frame_clock) -> bool:
        if self._done is None:
            self._tick_id = None
            return GLib.SOURCE_REMOVE

        if not self._first_tick_seen:
            self._first_tick_seen = True
            self.window.queue_draw()
            return GLib.SOURCE_CONTINUE

        self._completed_frames += 1
        if self._completed_frames < self._target_frames:
            self.window.queue_draw()
            return GLib.SOURCE_CONTINUE

        self._tick_id = None
        self._remove_watchdog()
        done = self._done
        self._done = None
        self._set_blank()
        # Let GTK finish this frame-clock callback before the scheduler mutates state.
        GLib.idle_add(self._invoke_once, done)
        return GLib.SOURCE_REMOVE

    def _on_watchdog(self) -> bool:
        self._watchdog_id = None
        if self._done is None:
            return GLib.SOURCE_REMOVE
        LOG.warning(
            "Frame-clock watchdog fired on %s after %d/%d frames",
            self.monitor_info.connector,
            self._completed_frames,
            self._target_frames,
        )
        self._remove_tick()
        done = self._done
        self._done = None
        self._set_blank()
        GLib.idle_add(self._invoke_once, done)
        return GLib.SOURCE_REMOVE

    def _set_blank(self) -> None:
        if self._active is not None:
            self._active.stop_animations()
        self._active = None
        if hasattr(self, "stack"):
            self.stack.set_visible_child_name("__blank__")
        self.window.queue_draw()
        self._make_click_through()

    def _remove_tick(self) -> None:
        if self._tick_id is not None:
            try:
                self.window.remove_tick_callback(self._tick_id)
            except Exception:
                LOG.debug("Tick callback was already removed", exc_info=True)
            self._tick_id = None

    def _remove_watchdog(self) -> None:
        if self._watchdog_id is not None:
            try:
                GLib.source_remove(self._watchdog_id)
            except Exception:
                LOG.debug("Watchdog source was already removed", exc_info=True)
            self._watchdog_id = None

    def _on_mapped(self, *_args) -> None:
        self._make_click_through()
        self.window.queue_draw()
        if self._pending_flash is not None:
            pending = self._pending_flash
            self._pending_flash = None
            GLib.idle_add(self._start_pending_flash, pending)

    def _make_click_through(self, *_args) -> bool:
        surface = self.window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())
        return GLib.SOURCE_REMOVE

    def _start_pending_flash(self, pending: tuple[str, int, Callable[[], None]]) -> bool:
        scene_id, frames, done = pending
        self.flash_scene(scene_id, frames, done)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _invoke_once(callback: Callable[[], None]) -> bool:
        callback()
        return GLib.SOURCE_REMOVE


class OverlayManager:
    def __init__(self, application: Gtk.Application, get_config) -> None:
        self.application = application
        self.get_config = get_config
        self.media = MediaCache()
        self.windows: dict[str, OverlayWindow] = {}
        self._monitor_model: Gio.ListModel | None = None
        self._monitors_handler: int | None = None
        self._presentation_generation = 0
        self._pending_windows: set[str] = set()
        self._presentation_done: Callable[[], None] | None = None

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
        self.cancel_flash()
        for window in list(self.windows.values()):
            window.destroy()
        self.windows.clear()
        if self._monitor_model is not None and self._monitors_handler is not None:
            self._monitor_model.disconnect(self._monitors_handler)
        self._monitor_model = None
        self._monitors_handler = None

    def sync_monitors(self) -> None:
        # A hot-plug/display-target change can invalidate frame clocks. Finish the
        # current presentation cleanly so the scheduler can enter its next break.
        self._abort_presentation(notify=True)
        config: AppConfig = self.get_config()
        infos = enumerate_monitors()
        wanted = {
            info.key: info
            for info in infos
            if config.display.mode == "all" or info.connector in config.display.connectors
        }
        for key in list(self.windows):
            if key not in wanted:
                self._mark_window_finished(key)
                self.windows.pop(key).destroy()
        for key, info in wanted.items():
            if key not in self.windows:
                self.windows[key] = OverlayWindow(self.application, info, self.media)
        self.rebuild_scenes()

    def rebuild_scenes(self) -> None:
        # Structural widget replacement invalidates frame callbacks.
        self._abort_presentation(notify=True)
        scenes = self.get_config().scenes
        for window in self.windows.values():
            window.rebuild(scenes)

    def flash_scene(self, scene: Scene, frames: int, done: Callable[[], None]) -> None:
        self.cancel_flash()
        if not self.windows:
            self.start()
        if not self.windows:
            LOG.warning("No target monitor available for flash")
            GLib.idle_add(self._invoke_once, done)
            return

        self._presentation_generation += 1
        generation = self._presentation_generation
        self._pending_windows = set(self.windows)
        self._presentation_done = done

        for key, window in self.windows.items():
            window.flash_scene(
                scene.id,
                frames,
                lambda key=key, generation=generation: self._window_finished(generation, key),
            )

    def cancel_flash(self) -> None:
        self._abort_presentation(notify=False)

    def _abort_presentation(self, *, notify: bool) -> None:
        done = self._presentation_done
        self._presentation_generation += 1
        self._pending_windows.clear()
        self._presentation_done = None
        for window in self.windows.values():
            window.cancel_flash()
        if notify and done is not None:
            GLib.idle_add(self._invoke_once, done)

    def clear(self) -> None:
        self.cancel_flash()

    def monitors(self) -> list[MonitorInfo]:
        return enumerate_monitors()

    def _window_finished(self, generation: int, key: str) -> None:
        if generation != self._presentation_generation:
            return
        self._mark_window_finished(key)

    def _mark_window_finished(self, key: str) -> None:
        self._pending_windows.discard(key)
        if self._pending_windows or self._presentation_done is None:
            return
        done = self._presentation_done
        self._presentation_done = None
        GLib.idle_add(self._invoke_once, done)

    def _on_monitors_changed(self, *_args) -> None:
        GLib.idle_add(self._sync_after_change)

    def _sync_after_change(self) -> bool:
        self.sync_monitors()
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _invoke_once(callback: Callable[[], None]) -> bool:
        callback()
        return GLib.SOURCE_REMOVE
