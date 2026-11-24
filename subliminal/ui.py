from __future__ import annotations

from pathlib import Path

from .config import ConfigImportError
from .gtk_runtime import Gtk
from .ui_editor import EditorPage
from .ui_pages import DisplaysPage, SettingsPage, TimingPage


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application, controller) -> None:
        super().__init__(application=application, title="Subliminal")
        self.controller = controller
        self._active_dialog = None
        self.set_default_size(1320, 820)
        self.set_size_request(1000, 650)
        self.connect("close-request", self._on_close_request)
        self.connect("map", self._on_map)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(8)
        toolbar.set_margin_bottom(8)
        toolbar.set_margin_start(10)
        toolbar.set_margin_end(10)
        root.append(toolbar)

        title = Gtk.Label(label="Subliminal")
        title.add_css_class("title-2")
        title.set_margin_end(8)
        toolbar.append(title)

        self.editor_nav = Gtk.ToggleButton(label="Editor")
        self.timing_nav = Gtk.ToggleButton(label="Timing")
        self.displays_nav = Gtk.ToggleButton(label="Displays")
        self.settings_nav = Gtk.ToggleButton(label="Settings")
        self.timing_nav.set_group(self.editor_nav)
        self.displays_nav.set_group(self.editor_nav)
        self.settings_nav.set_group(self.editor_nav)
        for name, button in (
            ("editor", self.editor_nav),
            ("timing", self.timing_nav),
            ("displays", self.displays_nav),
            ("settings", self.settings_nav),
        ):
            button.connect("toggled", self._nav_toggled, name)
            toolbar.append(button)
        self.editor_nav.set_active(True)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        import_button = Gtk.Button(label="Import")
        export_button = Gtk.Button(label="Export")
        import_button.connect("clicked", self._import_config)
        export_button.connect("clicked", self._export_config)
        toolbar.append(import_button)
        toolbar.append(export_button)

        self.status_label = Gtk.Label(label="Stopped")
        self.status_label.add_css_class("dim-label")
        self.status_label.set_margin_start(8)
        toolbar.append(self.status_label)

        self.start_button = Gtk.Button(label="Start")
        self.pause_button = Gtk.Button(label="Pause")
        self.stop_button = Gtk.Button(label="Stop")
        self.test_button = Gtk.Button(label="Test")
        self.quit_button = Gtk.Button(label="Quit")
        self.start_button.add_css_class("suggested-action")
        for button in (
            self.start_button,
            self.pause_button,
            self.stop_button,
            self.test_button,
            self.quit_button,
        ):
            toolbar.append(button)

        self.start_button.connect("clicked", lambda *_: self.controller.start())
        self.pause_button.connect("clicked", lambda *_: self.controller.pause())
        self.stop_button.connect("clicked", lambda *_: self.controller.stop())
        self.test_button.connect(
            "clicked",
            lambda *_: self.controller.test_flash(self.editor_page.selected_scene()),
        )
        self.quit_button.connect("clicked", lambda *_: self.controller.quit())

        self.banner = Gtk.Label()
        self.banner.set_wrap(True)
        self.banner.set_xalign(0.0)
        self.banner.set_margin_start(10)
        self.banner.set_margin_end(10)
        self.banner.set_margin_bottom(6)
        self.banner.add_css_class("warning-banner")
        self.banner.set_visible(False)
        root.append(self.banner)

        self.page_stack = Gtk.Stack()
        self.page_stack.set_hexpand(True)
        self.page_stack.set_vexpand(True)
        root.append(self.page_stack)

        self.editor_page = EditorPage(controller)
        self.content_page = self.editor_page  # compatibility with existing controller code
        self.timing_page = TimingPage(controller)
        self.displays_page = DisplaysPage(controller)
        self.settings_page = SettingsPage(controller)

        self.page_stack.add_named(self.editor_page, "editor")
        self.page_stack.add_named(self.timing_page, "timing")
        self.page_stack.add_named(self.displays_page, "displays")
        self.page_stack.add_named(self.settings_page, "settings")
        self.page_stack.set_visible_child_name("editor")

        self.refresh_all()

    def refresh_all(self) -> None:
        self.editor_page.refresh()
        self.timing_page.refresh()
        self.displays_page.refresh()
        self.settings_page.refresh()
        self.set_runtime_state(self.controller.scheduler.state.value)

    def set_runtime_state(self, state: str) -> None:
        labels = {
            "stopped": "Stopped",
            "paused": "Paused",
            "waiting": "Running · waiting",
            "visible": "Running · flashing",
        }
        self.status_label.set_label(labels.get(state, state.title()))
        running = state in {"waiting", "visible"}
        self.start_button.set_sensitive(not running)
        self.pause_button.set_sensitive(running)
        self.stop_button.set_sensitive(state != "stopped")
        self.test_button.set_sensitive(not running)

    def show_warning(self, text: str | None) -> None:
        self.banner.set_label(text or "")
        self.banner.set_visible(bool(text))

    def _nav_toggled(self, button: Gtk.ToggleButton, name: str) -> None:
        if not button.get_active() or not hasattr(self, "page_stack"):
            return
        self.page_stack.set_visible_child_name(name)
        if name == "editor":
            self.editor_page.resume_preview()
        else:
            self.editor_page.pause_preview()
            if name == "timing":
                self.timing_page.refresh()
            elif name == "displays":
                self.displays_page.refresh()

    def _import_config(self, *_args) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Import Subliminal configuration",
            self,
            Gtk.FileChooserAction.OPEN,
            "Import",
            "Cancel",
        )
        json_filter = Gtk.FileFilter()
        json_filter.set_name("Subliminal / JSON configuration")
        json_filter.add_pattern("*.json")
        dialog.add_filter(json_filter)
        dialog.connect("response", self._import_response)
        self._active_dialog = dialog
        dialog.show()

    def _import_response(self, dialog, response) -> None:
        try:
            if response != Gtk.ResponseType.ACCEPT:
                return
            file = dialog.get_file()
            if file is None or file.get_path() is None:
                return
            try:
                self.controller.import_from(Path(file.get_path()))
            except (ConfigImportError, OSError, ValueError) as exc:
                self.show_warning(f"Import failed: {exc}")
                return
        finally:
            if self._active_dialog is dialog:
                self._active_dialog = None
            dialog.destroy()

    def _export_config(self, *_args) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Export Subliminal configuration",
            self,
            Gtk.FileChooserAction.SAVE,
            "Export",
            "Cancel",
        )
        dialog.set_current_name("subliminal-config.json")
        json_filter = Gtk.FileFilter()
        json_filter.set_name("JSON configuration")
        json_filter.add_pattern("*.json")
        dialog.add_filter(json_filter)
        dialog.connect("response", self._export_response)
        self._active_dialog = dialog
        dialog.show()

    def _export_response(self, dialog, response) -> None:
        try:
            if response != Gtk.ResponseType.ACCEPT:
                return
            file = dialog.get_file()
            if file is None or file.get_path() is None:
                return
            path = Path(file.get_path())
            if path.suffix.lower() != ".json":
                path = path.with_name(f"{path.name}.json")
            try:
                self.controller.export_to(path)
            except OSError as exc:
                self.show_warning(f"Export failed: {exc}")
                return
            self.controller.clear_warning()
        finally:
            if self._active_dialog is dialog:
                self._active_dialog = None
            dialog.destroy()

    def _on_map(self, *_args) -> None:
        if self.page_stack.get_visible_child_name() == "editor":
            self.editor_page.resume_preview()

    def _on_close_request(self, *_args) -> bool:
        self.editor_page.pause_preview()
        self.set_visible(False)
        return True


__all__ = [
    "DisplaysPage",
    "EditorPage",
    "MainWindow",
    "SettingsPage",
    "TimingPage",
]
