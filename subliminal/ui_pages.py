from __future__ import annotations

from . import __version__
from .gtk_runtime import Gtk


class TimingPage(Gtk.Box):
    def __init__(self, controller) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self._loading = False
        self.set_margin_top(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        title = Gtk.Label(label="Timing")
        title.add_css_class("title-2")
        title.set_xalign(0.0)
        self.append(title)

        intro = Gtk.Label(
            label="Flash length is measured in display frames, not arbitrary milliseconds."
        )
        intro.set_xalign(0.0)
        intro.set_wrap(True)
        intro.add_css_class("dim-label")
        self.append(intro)

        grid = Gtk.Grid(column_spacing=16, row_spacing=12)
        self.append(grid)

        self.refresh_value = Gtk.Label()
        self.refresh_value.set_xalign(0.0)
        self.break_seconds = Gtk.SpinButton.new_with_range(0.1, 3600, 0.1)
        self.break_seconds.set_digits(1)
        self.visible_frames = Gtk.SpinButton.new_with_range(1, 120, 1)
        self.selection = Gtk.DropDown.new_from_strings(["Random", "Sequential"])

        self.break_seconds.connect("value-changed", self._changed)
        self.visible_frames.connect("value-changed", self._changed)
        self.selection.connect("notify::selected", self._changed)

        self._attach(grid, 0, "Display refresh", self.refresh_value)
        self._attach(grid, 1, "Visible for (frames)", self.visible_frames)
        self._attach(grid, 2, "Break after flash (seconds)", self.break_seconds)
        self._attach(grid, 3, "Scene order", self.selection)

        self.hint = Gtk.Label()
        self.hint.set_xalign(0.0)
        self.hint.set_wrap(True)
        self.hint.set_selectable(True)
        self.hint.add_css_class("dim-label")
        grid.attach(self.hint, 0, 4, 2, 1)

    @staticmethod
    def _attach(grid, row, label, widget):
        lab = Gtk.Label(label=label)
        lab.set_xalign(1.0)
        grid.attach(lab, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)

    def refresh(self) -> None:
        self._loading = True
        cfg = self.controller.config.schedule
        self.break_seconds.set_value(cfg.break_ms / 1000.0)
        self.visible_frames.set_value(cfg.visible_frames)
        self.selection.set_selected(0 if cfg.selection == "random" else 1)
        self._loading = False
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        cfg = self.controller.config.schedule
        monitors = self.controller.overlay.monitors()
        refreshes = [
            (m.connector, m.refresh_hz)
            for m in monitors
            if m.refresh_hz
        ]
        if not refreshes:
            hz = 60.0
            self.refresh_value.set_label("Not detected (60 Hz reference)")
            ms = cfg.visible_frames * 1000.0 / hz
            self.hint.set_label(
                f"{cfg.visible_frames} frame(s) at 60 Hz ≈ {ms:.1f} ms visible."
            )
            return

        self.refresh_value.set_label(
            ", ".join(
                f"{connector}: {hz:.1f} Hz"
                for connector, hz in refreshes
            )
        )
        lines = []
        for connector, hz in refreshes:
            frame_ms = 1000.0 / hz
            visible_ms = cfg.visible_frames * frame_ms
            lines.append(
                f"{connector}: 1 frame ≈ {frame_ms:.2f} ms; "
                f"{cfg.visible_frames} frame(s) ≈ {visible_ms:.1f} ms."
            )
        self.hint.set_label("\n".join(lines))

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        cfg = self.controller.config.schedule
        cfg.break_ms = max(
            100,
            round(self.break_seconds.get_value() * 1000),
        )
        cfg.visible_frames = max(
            1,
            self.visible_frames.get_value_as_int(),
        )
        cfg.selection = (
            "random"
            if self.selection.get_selected() == 0
            else "sequential"
        )
        self.controller.config_changed("timing")
        self._refresh_summary()


class DisplaysPage(Gtk.Box):
    def __init__(self, controller) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self._loading = False
        self.set_margin_top(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        title = Gtk.Label(label="Displays")
        title.add_css_class("title-2")
        title.set_xalign(0.0)
        self.append(title)

        self.all_radio = Gtk.CheckButton(label="All displays")
        self.selected_radio = Gtk.CheckButton(label="Selected displays")
        self.selected_radio.set_group(self.all_radio)
        self.all_radio.connect("toggled", self._mode_changed)
        self.selected_radio.connect("toggled", self._mode_changed)
        self.append(self.all_radio)
        self.append(self.selected_radio)

        self.monitor_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )
        self.monitor_box.set_margin_start(24)
        self.append(self.monitor_box)

        refresh = Gtk.Button(label="Refresh displays")
        refresh.set_halign(Gtk.Align.START)
        refresh.connect("clicked", lambda *_: self.refresh())
        self.append(refresh)

    def refresh(self) -> None:
        self._loading = True
        cfg = self.controller.config.display
        self.all_radio.set_active(cfg.mode == "all")
        self.selected_radio.set_active(cfg.mode == "selected")

        child = self.monitor_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.monitor_box.remove(child)
            child = nxt

        for info in self.controller.overlay.monitors():
            refresh = (
                f", {info.refresh_hz:.1f} Hz"
                if info.refresh_hz else ""
            )
            check = Gtk.CheckButton(
                label=(
                    f"{info.connector} — {info.description} — "
                    f"{info.width}×{info.height}, scale {info.scale_factor}×"
                    f"{refresh}"
                )
            )
            check.connector = info.connector
            check.set_active(info.connector in cfg.connectors)
            check.set_sensitive(cfg.mode == "selected")
            check.connect("toggled", self._connector_changed)
            self.monitor_box.append(check)
        self._loading = False

    def _mode_changed(self, button, *_args) -> None:
        if self._loading or not button.get_active():
            return
        self.controller.config.display.mode = (
            "all" if self.all_radio.get_active() else "selected"
        )
        self.controller.config_changed("display")
        self.refresh()

    def _connector_changed(self, check) -> None:
        if self._loading:
            return
        connector = check.connector
        connectors = self.controller.config.display.connectors
        if check.get_active() and connector not in connectors:
            connectors.append(connector)
        elif not check.get_active() and connector in connectors:
            connectors.remove(connector)
        self.controller.config_changed("display")


class SettingsPage(Gtk.Box):
    def __init__(self, controller) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self._loading = False
        self.set_margin_top(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        title = Gtk.Label(label="Settings")
        title.add_css_class("title-2")
        title.set_xalign(0.0)
        self.append(title)

        self.start_on_launch = Gtk.CheckButton(
            label="Start flashing automatically when the app launches"
        )
        self.autostart = Gtk.CheckButton(
            label="Launch Subliminal when I log in"
        )
        self.start_on_launch.connect("toggled", self._changed)
        self.autostart.connect("toggled", self._changed)
        self.append(self.start_on_launch)
        self.append(self.autostart)

        self.autostart_hint = Gtk.Label(
            label=(
                "Note: launching on login starts in the background. Enable "
                "'Start flashing automatically' too if you want flashing to begin on login."
            )
        )
        self.autostart_hint.set_wrap(True)
        self.autostart_hint.set_xalign(0.0)
        self.autostart_hint.add_css_class("warning-banner")
        self.autostart_hint.set_visible(False)
        self.append(self.autostart_hint)

        version_label = Gtk.Label(label=f"Version: {__version__}")
        version_label.set_selectable(True)
        version_label.set_xalign(0.0)
        version_label.add_css_class("dim-label")
        self.append(version_label)

        cfg_label = Gtk.Label(
            label=f"Configuration: {self.controller.store.path}"
        )
        cfg_label.set_selectable(True)
        cfg_label.set_xalign(0.0)
        cfg_label.add_css_class("dim-label")
        self.append(cfg_label)

        export_note = Gtk.Label(
            label=(
                "Import/Export saves the full JSON configuration. "
                "Image paths remain references to files on disk and are not copied."
            )
        )
        export_note.set_wrap(True)
        export_note.set_xalign(0.0)
        export_note.add_css_class("dim-label")
        self.append(export_note)

        note = Gtk.Label(
            label=(
                "Closing the window hides it while the scheduler keeps running. "
                "Launch Subliminal again to reopen it, or use Quit to exit."
            )
        )
        note.set_wrap(True)
        note.set_xalign(0.0)
        note.set_max_width_chars(80)
        self.append(note)

    def _update_autostart_hint(self) -> None:
        self.autostart_hint.set_visible(
            self.controller.config.autostart
            and not self.controller.config.start_on_launch
        )

    def refresh(self) -> None:
        self._loading = True
        self.start_on_launch.set_active(
            self.controller.config.start_on_launch
        )
        self.autostart.set_active(self.controller.config.autostart)
        self._loading = False
        self._update_autostart_hint()

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        previous_autostart = self.controller.config.autostart
        self.controller.config.start_on_launch = (
            self.start_on_launch.get_active()
        )
        self.controller.config.autostart = self.autostart.get_active()
        if self.controller.config.autostart != previous_autostart:
            self.controller.set_autostart(self.controller.config.autostart)
        self._update_autostart_hint()
        self.controller.config_changed("settings")
