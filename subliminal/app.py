from __future__ import annotations

import logging
from pathlib import Path

from .autostart import APP_ID, set_autostart
from .config import ConfigImportError, ConfigStore, export_config, import_config
from .gtk_runtime import Gdk, GLib, Gtk
from .model import AppConfig, Scene, normalize_config
from .overlay import OverlayManager
from .scheduler import Scheduler, SchedulerState
from .ui import MainWindow

LOG = logging.getLogger(__name__)

CSS = b"""
.subliminal-overlay, .subliminal-overlay > * {
    background-color: transparent;
    background-image: none;
    box-shadow: none;
    border: none;
}
.subliminal-scene, .subliminal-blank {
    background-color: transparent;
}
.preview-canvas {
    background-color: #20242a;
    border: 1px solid alpha(@theme_fg_color, 0.25);
    border-radius: 6px;
}
.preview-error { color: #ff6b6b; }
.warning-banner {
    background: alpha(#d9a400, 0.18);
    border-radius: 6px;
    padding: 8px;
}
"""


class AppController:
    def __init__(self, application: "SubliminalApplication") -> None:
        self.application = application
        self.store = ConfigStore()
        self.config: AppConfig = self.store.load()
        self.overlay = OverlayManager(application, lambda: self.config)
        self.window: MainWindow | None = None
        self._save_timer: int | None = None
        self._overlay_rebuild_timer: int | None = None
        self._overlay_full_dirty = False
        self._overlay_dirty_scenes: set[str] = set()
        self.scheduler = Scheduler(
            lambda: self.config,
            self.overlay.flash_scene,
            self.overlay.cancel_flash,
            self._timer_add,
            GLib.source_remove,
            self._state_changed,
        )

    def ensure_window(self) -> MainWindow:
        if self.window is None:
            self.window = MainWindow(self.application, self)
            if not self.overlay.supported():
                self.window.show_warning(
                    "Layer-shell is not available. This app requires a KDE Plasma Wayland session with gtk4-layer-shell; overlays are disabled."
                )
        return self.window

    def start(self) -> None:
        if not self.overlay.supported():
            self.warn("Cannot start: layer-shell is unavailable. Log into KDE Plasma (Wayland), not X11/GNOME.")
            return
        normalize_config(self.config)
        self.overlay.start()
        self.scheduler.start(immediate=False)

    def pause(self) -> None:
        self.scheduler.pause()

    def stop(self) -> None:
        self.scheduler.stop()

    def test_flash(self, scene: Scene | None = None) -> None:
        if not self.overlay.supported():
            self.warn("Cannot test: layer-shell is unavailable in this session.")
            return
        self.overlay.start()
        self.scheduler.test_flash(scene)

    def config_changed(
        self,
        kind: str = "visual",
        scene_id: str | None = None,
    ) -> None:
        """Persist edits and invalidate only the renderer scope that changed."""
        normalize_config(self.config)
        self._schedule_save()

        if kind in {"visual", "structural", "content"}:
            if scene_id:
                if not self._overlay_full_dirty:
                    self._overlay_dirty_scenes.add(scene_id)
            else:
                self._overlay_full_dirty = True
                self._overlay_dirty_scenes.clear()
            self._schedule_overlay_rebuild()
        elif kind == "display":
            was_running = self.scheduler.running
            if was_running:
                self.scheduler.pause()
            self._clear_overlay_dirty()
            self.overlay.sync_monitors()
            if was_running:
                self.scheduler.start(immediate=False)
        elif kind == "timing" and self.scheduler.running:
            self.scheduler.reload_config()

    def _schedule_overlay_rebuild(self) -> None:
        if not self.overlay.windows:
            return
        if self._overlay_rebuild_timer is None:
            self._overlay_rebuild_timer = GLib.timeout_add(
                100,
                self._try_overlay_rebuild,
            )

    def _try_overlay_rebuild(self) -> bool:
        if not self._overlay_full_dirty and not self._overlay_dirty_scenes:
            self._overlay_rebuild_timer = None
            return GLib.SOURCE_REMOVE
        if self.scheduler.state == SchedulerState.VISIBLE:
            return GLib.SOURCE_CONTINUE

        full_dirty = self._overlay_full_dirty
        dirty_scenes = set(self._overlay_dirty_scenes)
        try:
            if full_dirty:
                self.overlay.rebuild_scenes()
            else:
                for scene_id in dirty_scenes:
                    self.overlay.sync_scene(scene_id)
        except Exception:
            LOG.exception("Targeted overlay rebuild failed; trying full rebuild")
            try:
                self.overlay.rebuild_scenes()
            except Exception:
                LOG.exception("Full overlay rebuild also failed")
        finally:
            self._clear_overlay_dirty()
            self._overlay_rebuild_timer = None
        return GLib.SOURCE_REMOVE

    def _clear_overlay_dirty(self) -> None:
        self._overlay_full_dirty = False
        self._overlay_dirty_scenes.clear()

    def export_to(self, path: Path) -> None:
        export_config(self.config, path)

    def import_from(self, path: Path) -> None:
        imported = import_config(path)
        was_running = self.scheduler.running
        if was_running:
            self.scheduler.pause()
        self.overlay.cancel_flash()
        self._clear_overlay_dirty()
        self.config = imported
        self.store.save(self.config)
        self.set_autostart(self.config.autostart)
        if self.overlay.windows:
            self.overlay.sync_monitors()
            self.overlay.rebuild_scenes()
        if self.window is not None:
            self.window.refresh_all()
            self.window.show_warning(None)
        if was_running:
            self.scheduler.start(immediate=False)

    def set_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError as exc:
            LOG.exception("Failed to update autostart")
            self.warn(f"Could not update autostart: {exc}")

    def warn(self, message: str) -> None:
        LOG.warning(message)
        if self.window is not None:
            self.window.show_warning(message)

    def clear_warning(self) -> None:
        if self.window is not None and self.overlay.supported():
            self.window.show_warning(None)

    def save_now(self) -> None:
        if self._save_timer is not None:
            GLib.source_remove(self._save_timer)
            self._save_timer = None
        self.store.save(self.config)

    def quit(self) -> None:
        self.save_now()
        self.scheduler.stop()
        self.overlay.stop()
        self.application.quit()

    def shutdown(self) -> None:
        if self._overlay_rebuild_timer is not None:
            GLib.source_remove(self._overlay_rebuild_timer)
            self._overlay_rebuild_timer = None
        try:
            self.save_now()
        except Exception:
            LOG.exception("Failed to save configuration during shutdown")
        self.scheduler.stop()
        self.overlay.stop()

    def _schedule_save(self) -> None:
        if self._save_timer is not None:
            GLib.source_remove(self._save_timer)
        self._save_timer = GLib.timeout_add(350, self._save_after_delay)

    def _save_after_delay(self) -> bool:
        self._save_timer = None
        try:
            self.store.save(self.config)
        except Exception as exc:
            LOG.exception("Failed to save configuration")
            self.warn(f"Could not save configuration: {exc}")
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _timer_add(milliseconds: int, callback) -> int:
        return GLib.timeout_add(milliseconds, callback)

    def _state_changed(self, state: SchedulerState) -> None:
        if self.window is not None:
            self.window.set_runtime_state(state.value)
        if (
            state != SchedulerState.VISIBLE
            and (self._overlay_full_dirty or self._overlay_dirty_scenes)
            and self._overlay_rebuild_timer is None
        ):
            self._overlay_rebuild_timer = GLib.idle_add(self._try_overlay_rebuild)


class SubliminalApplication(Gtk.Application):
    def __init__(self, *, background: bool = False) -> None:
        super().__init__(application_id=APP_ID)
        self.background = background
        self.controller: AppController | None = None
        self._first_activation = True

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        self.hold()
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        self.controller = AppController(self)

    def do_activate(self) -> None:
        assert self.controller is not None
        window = self.controller.ensure_window()
        if self.controller.config.start_on_launch and self._first_activation:
            GLib.idle_add(self._start_after_activation)
        should_present = not (self.background and self._first_activation)
        self._first_activation = False
        if should_present:
            window.present()
            self.controller.clear_warning()

    def do_shutdown(self) -> None:
        if self.controller is not None:
            self.controller.shutdown()
        Gtk.Application.do_shutdown(self)

    def _start_after_activation(self) -> bool:
        assert self.controller is not None
        self.controller.start()
        return GLib.SOURCE_REMOVE
