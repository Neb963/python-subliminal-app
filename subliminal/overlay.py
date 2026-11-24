from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from .gtk_runtime import Gdk, Gio, GLib, Gtk, LayerShell, cairo
from .media import MediaCache
from .model import AppConfig, Scene
from .render import SceneView

LOG = logging.getLogger(__name__)

PRE_MAP_WATCHDOG_MS = 2000
MONITOR_SYNC_DEBOUNCE_MS = 150


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
    seen_keys: set[str] = set()
    for index in range(model.get_n_items()):
        monitor = model.get_item(index)
        connector = monitor.get_connector() or f"monitor-{index + 1}"
        key = connector if connector not in seen_keys else f"{connector}#{index + 1}"
        seen_keys.add(key)
        manufacturer = monitor.get_manufacturer() or ""
        model_name = monitor.get_model() or ""
        description = " ".join(part for part in (manufacturer, model_name) if part).strip() or connector
        geometry = monitor.get_geometry()
        refresh_mhz = monitor.get_refresh_rate()
        result.append(
            MonitorInfo(
                key=key,
                connector=connector,
                description=description,
                width=geometry.width,
                height=geometry.height,
                scale_factor=max(1, int(monitor.get_scale_factor() or 1)),
                refresh_hz=(refresh_mhz / 1000.0) if refresh_mhz > 0 else None,
                monitor=monitor,
            )
        )
    return result


class OverlayWindow:
    """One click-through layer-shell surface per monitor, mapped only while flashing."""

    def __init__(self, application: Gtk.Application, monitor_info: MonitorInfo, media: MediaCache) -> None:
        self.monitor_info = monitor_info
        self.media = media
        self.window = Gtk.Window(application=application)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_focusable(False)
        self.window.set_default_size(monitor_info.width, monitor_info.height)
        self.window.set_opacity(0.0)
        self.window.add_css_class("subliminal-overlay")

        self._views: dict[str, SceneView] = {}
        self._active: SceneView | None = None
        self._tick_id: int | None = None
        self._watchdog_id: int | None = None
        self._begin_idle_id: int | None = None
        self._flash_generation = 0
        self._target_frames = 1
        self._completed_frames = 0
        self._first_tick_seen = False
        self._done: Callable[[], None] | None = None
        self._pending_flash: tuple[int, int, Callable[[], None]] | None = None

        LayerShell.init_for_window(self.window)
        LayerShell.set_namespace(self.window, "subliminal-overlay")
        LayerShell.set_monitor(self.window, monitor_info.monitor)
        LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.NONE)
        LayerShell.set_exclusive_zone(self.window, 0)
        for edge in (
            LayerShell.Edge.TOP,
            LayerShell.Edge.BOTTOM,
            LayerShell.Edge.LEFT,
            LayerShell.Edge.RIGHT,
        ):
            LayerShell.set_anchor(self.window, edge, True)

        self.window.connect("close-request", self._on_close_request)
        self.window.connect("realize", self._make_click_through)
        self.window.connect("map", self._on_mapped)
        self.window.connect("unmap", self._on_unmapped)
        self.rebuild([])

    def update_monitor_info(self, info: MonitorInfo) -> None:
        self.monitor_info = info
        self.window.set_default_size(info.width, info.height)
        LayerShell.set_monitor(self.window, info.monitor)

    def rebuild(self, scenes: list[Scene]) -> None:
        self.cancel_flash()
        for old_view in self._views.values():
            old_view.stop_animations()

        stack = Gtk.Stack()
        stack.set_hhomogeneous(False)
        stack.set_vhomogeneous(False)
        stack.set_overflow(Gtk.Overflow.HIDDEN)
        stack.set_hexpand(True)
        stack.set_vexpand(True)

        blank = Gtk.Box()
        blank.add_css_class("subliminal-blank")
        stack.add_named(blank, "__blank__")

        self._views = {}
        device_scale = max(1, int(self.monitor_info.scale_factor or 1))
        for scene in scenes:
            view = SceneView(
                scene,
                self.media,
                device_scale=device_scale,
                render_limit=(
                    self.monitor_info.width,
                    self.monitor_info.height,
                ),
            )
            self._views[scene.id] = view
            stack.add_named(view, scene.id)

        stack.set_visible_child_name("__blank__")
        self.window.set_child(stack)
        self.stack = stack
        self._active = None
        self.window.set_opacity(0.0)
        self.window.set_visible(False)

    def sync_scene(self, scene: Scene | None, scene_id: str) -> None:
        self.cancel_flash()
        old = self._views.pop(scene_id, None)
        if old is not None:
            old.stop_animations()
            self.stack.remove(old)

        if scene is None:
            if self.stack.get_visible_child_name() == scene_id:
                self.stack.set_visible_child_name("__blank__")
            return

        device_scale = max(1, int(self.monitor_info.scale_factor or 1))
        view = SceneView(
            scene,
            self.media,
            device_scale=device_scale,
            render_limit=(
                self.monitor_info.width,
                self.monitor_info.height,
            ),
        )
        self._views[scene.id] = view
        self.stack.add_named(view, scene.id)
        self.stack.set_visible_child_name("__blank__")

    def flash_scene(self, scene_id: str, frames: int, done: Callable[[], None]) -> None:
        self.cancel_flash()

        view = self._views.get(scene_id)
        if view is None:
            LOG.warning("Scene %s is not built on monitor %s", scene_id, self.monitor_info.connector)
            GLib.idle_add(self._invoke_once, done)
            return

        self._flash_generation += 1
        generation = self._flash_generation

        # Prepare the scene before mapping so KWin's first new surface buffer already
        # contains the flash contents. The actual frame counter starts from map.
        self.stack.set_visible_child_name(scene_id)
        self._active = view
        # Gtk.Fixed may have no useful allocation while the layer-shell window is
        # unmapped. Position synchronously from the monitor geometry before map.
        view.prepare_flash(self.monitor_info.width, self.monitor_info.height)
        self._target_frames = max(1, int(frames))
        self._completed_frames = 0
        self._first_tick_seen = False
        self._pending_flash = (generation, self._target_frames, done)
        # Arm a pre-map watchdog so a monitor that never maps (e.g., DPMS off or
        # lock screen) cannot leave the scheduler stuck in VISIBLE forever.
        self._watchdog_id = GLib.timeout_add(
            PRE_MAP_WATCHDOG_MS,
            self._on_pre_map_watchdog,
            generation,
        )
        # Map invisibly first. The real allocation can differ from monitor
        # geometry under scaling; reveal only after the mapped layout is final.
        self.window.set_opacity(0.0)

        view.queue_draw()
        self.stack.queue_draw()
        self.window.queue_draw()
        self.window.present()

        # Some GTK backends may report mapped synchronously. In that case the map
        # signal has already consumed _pending_flash; otherwise it will do so later.
        if self.window.get_mapped() and self._pending_flash is not None:
            pending = self._pending_flash
            self._pending_flash = None
            self._remove_begin_idle()
            self._begin_idle_id = GLib.idle_add(self._begin_mapped_flash, pending)

    def cancel_flash(self) -> None:
        self._flash_generation += 1
        self._pending_flash = None
        self._remove_begin_idle()
        self._remove_tick()
        self._remove_watchdog()
        self._done = None
        self._hide_surface()

    def destroy(self) -> None:
        self.cancel_flash()
        for view in self._views.values():
            view.stop_animations()
        self._views.clear()
        self.window.destroy()

    def _on_close_request(self, *_args) -> bool:
        # Prevent external window close requests from destroying the overlay surface.
        self.cancel_flash()
        return True

    def _begin_mapped_flash(self, pending: tuple[int, int, Callable[[], None]]) -> bool:
        self._begin_idle_id = None
        generation, frames, done = pending
        if generation != self._flash_generation:
            return GLib.SOURCE_REMOVE
        if not self.window.get_mapped():
            self._remove_watchdog()
            self._hide_surface()
            GLib.idle_add(self._invoke_once, done)
            return GLib.SOURCE_REMOVE

        self._remove_tick()
        self._remove_watchdog()
        self._target_frames = max(1, int(frames))
        self._completed_frames = 0
        self._first_tick_seen = False
        self._done = done

        if self._active is not None:
            actual_width = self.window.get_width() or self.monitor_info.width
            actual_height = self.window.get_height() or self.monitor_info.height
            # Reapply the same fixed/random coordinates after GTK has allocated
            # the mapped surface. This does not reroll random placement.
            self._active.reapply_flash_layout(actual_width, actual_height)
            self._active.start_animations()
            self._active.queue_draw()
        self.stack.queue_draw()
        self.window.queue_draw()

        self._make_click_through()
        # From this point onward every visible frame has final positions/sizes.
        self.window.set_opacity(1.0)
        self.window.queue_draw()
        self._tick_id = self.window.add_tick_callback(self._on_tick)

        refresh = self.monitor_info.refresh_hz or 60.0
        expected_ms = (self._target_frames / refresh) * 1000.0
        watchdog_ms = max(1000, round(expected_ms * 10 + 500))
        self._watchdog_id = GLib.timeout_add(
            watchdog_ms,
            self._on_watchdog,
            generation,
        )

        LOG.debug(
            "Mapped flash on %s for %d frames (%.2f Hz)",
            self.monitor_info.connector,
            self._target_frames,
            refresh,
        )
        return GLib.SOURCE_REMOVE

    def _on_pre_map_watchdog(self, generation: int) -> bool:
        self._watchdog_id = None
        if generation != self._flash_generation or self._pending_flash is None:
            return GLib.SOURCE_REMOVE

        LOG.warning(
            "Pre-map watchdog fired on %s before surface mapped",
            self.monitor_info.connector,
        )
        pending = self._pending_flash
        self._pending_flash = None
        self._remove_begin_idle()
        self._hide_surface()
        GLib.idle_add(self._invoke_once, pending[2])
        return GLib.SOURCE_REMOVE

    def _on_tick(self, _widget, _frame_clock) -> bool:
        if self._done is None:
            self._tick_id = None
            return GLib.SOURCE_REMOVE

        # Tick callbacks run in GTK's Update phase before Paint. Do not count the
        # first tick; it prepares the first frame that can actually be presented.
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

        # Strong clear: unmap the native layer-shell surface. KWin must remove an
        # unmapped surface, so no previously committed transparent buffer can linger.
        self._hide_surface()
        GLib.idle_add(self._invoke_once, done)
        return GLib.SOURCE_REMOVE

    def _on_watchdog(self, generation: int) -> bool:
        self._watchdog_id = None
        if generation != self._flash_generation or self._done is None:
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
        self._hide_surface()
        GLib.idle_add(self._invoke_once, done)
        return GLib.SOURCE_REMOVE

    def _hide_surface(self) -> None:
        if self._active is not None:
            self._active.stop_animations()
        self._active = None

        if hasattr(self, "stack"):
            self.stack.set_visible_child_name("__blank__")

        self.window.set_opacity(0.0)
        # This is intentional. We tried keeping a transparent layer-shell surface
        # mapped, but KWin could retain its last submitted visual buffer. Unmapping
        # removes the surface from composition during every break.
        self.window.set_visible(False)

    def _remove_begin_idle(self) -> None:
        if self._begin_idle_id is not None:
            try:
                GLib.source_remove(self._begin_idle_id)
            except Exception:
                LOG.debug("Begin idle callback was already removed", exc_info=True)
            self._begin_idle_id = None

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
            self._remove_begin_idle()
            self._begin_idle_id = GLib.idle_add(self._begin_mapped_flash, pending)

    def _on_unmapped(self, *_args) -> None:
        LOG.debug("Overlay unmapped on %s", self.monitor_info.connector)

    def _make_click_through(self, *_args) -> bool:
        surface = self.window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())
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
        self._monitor_prop_handlers: list[tuple[object, int]] = []
        self._sync_debounce_id: int | None = None
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
        display = Gdk.Display.get_default()
        if display is not None and self._monitor_model is None:
            self._monitor_model = display.get_monitors()
            self._monitors_handler = self._monitor_model.connect(
                "items-changed",
                self._on_monitors_changed,
            )
        if not self.windows:
            self.sync_monitors()

    def stop(self) -> None:
        self.cancel_flash()
        if self._sync_debounce_id is not None:
            GLib.source_remove(self._sync_debounce_id)
            self._sync_debounce_id = None
        self._disconnect_monitor_props()
        for window in list(self.windows.values()):
            window.destroy()
        self.windows.clear()
        if self._monitor_model is not None and self._monitors_handler is not None:
            self._monitor_model.disconnect(self._monitors_handler)
        self._monitor_model = None
        self._monitors_handler = None

    def sync_monitors(self) -> None:
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
                self.windows.pop(key).destroy()

        for key, info in wanted.items():
            existing = self.windows.get(key)
            if existing is None:
                self.windows[key] = OverlayWindow(self.application, info, self.media)
            elif (
                existing.monitor_info.width != info.width
                or existing.monitor_info.height != info.height
                or existing.monitor_info.scale_factor != info.scale_factor
                or existing.monitor_info.refresh_hz != info.refresh_hz
                or existing.monitor_info.monitor is not info.monitor
            ):
                existing.update_monitor_info(info)

        self._watch_monitor_props(infos)
        self.rebuild_scenes()

    def _disconnect_monitor_props(self) -> None:
        for monitor, handler_id in self._monitor_prop_handlers:
            try:
                monitor.disconnect(handler_id)
            except Exception:
                pass
        self._monitor_prop_handlers.clear()

    def _watch_monitor_props(self, infos: list[MonitorInfo]) -> None:
        self._disconnect_monitor_props()
        for info in infos:
            monitor = info.monitor
            for signal in ("notify::geometry", "notify::scale-factor", "notify::refresh-rate"):
                try:
                    handler_id = monitor.connect(signal, self._on_monitors_changed)
                    self._monitor_prop_handlers.append((monitor, handler_id))
                except Exception:
                    LOG.debug("Could not connect %s on monitor %s", signal, info.connector)

    def rebuild_scenes(self) -> None:
        self._abort_presentation(notify=True)
        scenes = self.get_config().scenes
        for window in self.windows.values():
            window.rebuild(scenes)

    def sync_scene(self, scene_id: str) -> None:
        self._abort_presentation(notify=True)
        scene = next(
            (
                item for item in self.get_config().scenes
                if item.id == scene_id
            ),
            None,
        )
        for window in self.windows.values():
            window.sync_scene(scene, scene_id)

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
        if self._sync_debounce_id is not None:
            GLib.source_remove(self._sync_debounce_id)
        self._sync_debounce_id = GLib.timeout_add(
            MONITOR_SYNC_DEBOUNCE_MS,
            self._sync_after_change,
        )

    def _sync_after_change(self) -> bool:
        self._sync_debounce_id = None
        self.sync_monitors()
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _invoke_once(callback: Callable[[], None]) -> bool:
        callback()
        return GLib.SOURCE_REMOVE
