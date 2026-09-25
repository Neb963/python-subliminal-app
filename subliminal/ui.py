from __future__ import annotations

import copy
from pathlib import Path

from . import __version__
from .config import ConfigImportError
from .gtk_runtime import Gdk, GLib, Gtk, Pango
from .model import ANCHORS, Folder, ImageLayer, Scene, TextLayer, new_id
from .render import SceneView


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application, controller) -> None:
        super().__init__(application=application, title="Subliminal")
        self.controller = controller
        self.set_default_size(1320, 820)
        self.set_size_request(1000, 650)
        self.connect("close-request", self._on_close_request)

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
        if button.get_active() and hasattr(self, "page_stack"):
            self.page_stack.set_visible_child_name(name)

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
            self.show_warning(None)
        finally:
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
                path = path.with_suffix(".json")
            try:
                self.controller.export_to(path)
            except OSError as exc:
                self.show_warning(f"Export failed: {exc}")
                return
            self.show_warning(None)
        finally:
            dialog.destroy()

    def _on_close_request(self, *_args) -> bool:
        self.set_visible(False)
        return True


class EditorPage(Gtk.Box):
    def __init__(self, controller) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.controller = controller
        self._scene_id: str | None = None
        self._folder_id: str | None = None
        self._layer_id: str | None = None
        self._sync_depth = 0
        self._preview_view: SceneView | None = None
        self._folder_choices: list[str | None] = []
        self._library_refresh_id: int | None = None
        self._folder_model_refresh_id: int | None = None
        self._preview_refresh_id: int | None = None

        outer = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        outer.set_hexpand(True)
        outer.set_vexpand(True)
        self.append(outer)

        library = self._build_library()
        outer.set_start_child(library)
        outer.set_resize_start_child(False)
        outer.set_shrink_start_child(False)

        right_paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        outer.set_end_child(right_paned)
        outer.set_resize_end_child(True)

        canvas = self._build_canvas()
        inspector = self._build_inspector()
        right_paned.set_start_child(canvas)
        right_paned.set_end_child(inspector)
        right_paned.set_resize_start_child(True)
        right_paned.set_resize_end_child(False)
        right_paned.set_shrink_end_child(False)

    @property
    def _loading(self) -> bool:
        return self._sync_depth > 0

    @_loading.setter
    def _loading(self, value: bool) -> None:
        if value:
            self._sync_depth += 1
        else:
            self._sync_depth = max(0, self._sync_depth - 1)

    def _build_library(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_size_request(245, -1)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(8)

        title = Gtk.Label(label="Library")
        title.add_css_class("heading")
        title.set_xalign(0.0)
        box.append(title)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.library_list = Gtk.ListBox()
        self.library_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.library_list.connect("row-selected", self._on_library_selected)
        scroll.set_child(self.library_list)
        box.append(scroll)

        name_label = Gtk.Label(label="Selected name")
        name_label.set_xalign(0.0)
        name_label.add_css_class("dim-label")
        box.append(name_label)
        self.library_name = Gtk.Entry()
        self.library_name.set_placeholder_text("Select a folder or scene")
        self.library_name.connect("changed", self._library_name_changed)
        box.append(self.library_name)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_folder = Gtk.Button(label="+ Folder")
        add_scene = Gtk.Button(label="+ Scene")
        add_folder.connect("clicked", self._add_folder)
        add_scene.connect("clicked", self._add_scene)
        row1.append(add_folder)
        row1.append(add_scene)
        box.append(row1)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        duplicate = Gtk.Button(label="Duplicate")
        delete = Gtk.Button(label="Delete")
        duplicate.connect("clicked", self._duplicate_scene)
        delete.connect("clicked", self._delete_library_item)
        row2.append(duplicate)
        row2.append(delete)
        box.append(row2)

        hint = Gtk.Label(
            label="Deleting a folder moves its scenes to Unfiled; it never deletes them."
        )
        hint.set_wrap(True)
        hint.set_xalign(0.0)
        hint.add_css_class("dim-label")
        box.append(hint)
        return box

    def _build_canvas(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(8)
        box.set_margin_end(8)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(header)

        scene_label = Gtk.Label(label="Scene")
        scene_label.add_css_class("heading")
        header.append(scene_label)

        self.scene_enabled = Gtk.CheckButton(label="Enabled")
        self.scene_enabled.connect("toggled", self._scene_enabled_changed)
        header.append(self.scene_enabled)

        folder_label = Gtk.Label(label="Folder")
        folder_label.set_margin_start(12)
        header.append(folder_label)

        self._folder_model = Gtk.StringList.new(["Unfiled"])
        self.scene_folder = Gtk.DropDown(model=self._folder_model)
        self.scene_folder.connect("notify::selected", self._scene_folder_changed)
        self.scene_folder.set_hexpand(True)
        header.append(self.scene_folder)

        reroll = Gtk.Button(label="Reroll preview")
        reroll.connect("clicked", lambda *_: self._refresh_preview())
        header.append(reroll)

        self.preview_frame = Gtk.Frame()
        self.preview_frame.add_css_class("preview-canvas")
        self.preview_frame.set_hexpand(True)
        self.preview_frame.set_vexpand(True)
        self.preview_frame.set_size_request(620, 350)
        box.append(self.preview_frame)

        note = Gtk.Label(
            label="Random layers are rerolled once per flash and avoid other visible elements when space permits."
        )
        note.set_wrap(True)
        note.set_xalign(0.0)
        note.add_css_class("dim-label")
        box.append(note)
        return box

    def _build_inspector(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_size_request(365, -1)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(8)
        box.set_margin_end(10)

        title = Gtk.Label(label="Layers")
        title.add_css_class("heading")
        title.set_xalign(0.0)
        box.append(title)

        layer_scroll = Gtk.ScrolledWindow()
        layer_scroll.set_min_content_height(170)
        self.layer_list = Gtk.ListBox()
        self.layer_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.layer_list.connect("row-selected", self._on_layer_selected)
        layer_scroll.set_child(self.layer_list)
        box.append(layer_scroll)

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_text = Gtk.Button(label="+ Text")
        add_image = Gtk.Button(label="+ Image")
        up = Gtk.Button(label="↑")
        down = Gtk.Button(label="↓")
        delete = Gtk.Button(label="Delete")
        add_text.connect("clicked", self._add_text_layer)
        add_image.connect("clicked", self._choose_new_image)
        up.connect("clicked", lambda *_: self._move_layer(-1))
        down.connect("clicked", lambda *_: self._move_layer(1))
        delete.connect("clicked", self._delete_layer)
        for button in (add_text, add_image, up, down, delete):
            add_row.append(button)
        box.append(add_row)

        prop_title = Gtk.Label(label="Properties")
        prop_title.add_css_class("heading")
        prop_title.set_xalign(0.0)
        box.append(prop_title)

        prop_scroll = Gtk.ScrolledWindow()
        prop_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        prop_scroll.set_vexpand(True)
        self.property_stack = Gtk.Stack()
        self.property_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.property_stack.add_named(
            Gtk.Label(label="Select a layer to edit it."),
            "empty",
        )
        self.text_props = self._build_text_properties()
        self.image_props = self._build_image_properties()
        self.property_stack.add_named(self.text_props, "text")
        self.property_stack.add_named(self.image_props, "image")
        prop_scroll.set_child(self.property_stack)
        box.append(prop_scroll)
        return box

    def _build_text_properties(self) -> Gtk.Widget:
        grid = self._property_grid()
        row = 0

        self.text_name = Gtk.Entry()
        self.text_name.connect("changed", self._update_text_name)
        row = self._attach(grid, row, "Name", self.text_name)

        self.text_enabled = Gtk.CheckButton(label="Enabled")
        self.text_enabled.connect("toggled", self._update_text)
        grid.attach(self.text_enabled, 1, row, 1, 1)
        row += 1

        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_scroll = Gtk.ScrolledWindow()
        text_scroll.set_min_content_height(80)
        text_scroll.set_child(self.text_view)
        self.text_view.get_buffer().connect("changed", self._update_text)
        row = self._attach(grid, row, "Text", text_scroll)

        self.font_dialog = Gtk.FontDialog.new()
        self.font_dialog.set_title("Choose font")
        self.font_button = Gtk.FontDialogButton.new(self.font_dialog)
        self.font_button.set_level(Gtk.FontLevel.FAMILY)
        self.font_button.set_use_font(True)
        self.font_button.set_use_size(False)
        self.font_button.connect("notify::font-desc", self._update_text)
        row = self._attach(grid, row, "Font", self.font_button)

        self.font_size = Gtk.SpinButton.new_with_range(1, 500, 1)
        self.font_size.connect("value-changed", self._update_text)
        row = self._attach(grid, row, "Size (px)", self.font_size)

        style_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.bold = Gtk.ToggleButton(label="B")
        self.italic = Gtk.ToggleButton(label="I")
        self.underline = Gtk.ToggleButton(label="U")
        for button in (self.bold, self.italic, self.underline):
            button.connect("toggled", self._update_text)
            style_box.append(button)
        row = self._attach(grid, row, "Style", style_box)

        self.color = Gtk.ColorButton()
        self.color.set_use_alpha(True)
        self.color.connect("color-set", self._update_text)
        row = self._attach(grid, row, "Color", self.color)

        self.text_alignment = Gtk.DropDown.new_from_strings(
            ["Left", "Center", "Right"]
        )
        self.text_alignment.connect("notify::selected", self._update_text)
        row = self._attach(grid, row, "Alignment", self.text_alignment)

        self.text_background_enabled = Gtk.CheckButton(
            label="Colored background"
        )
        self.text_background_enabled.connect(
            "toggled",
            self._on_text_background_toggled,
        )
        row = self._attach(
            grid,
            row,
            "Background",
            self.text_background_enabled,
        )

        self.text_background_color = Gtk.ColorButton()
        self.text_background_color.set_use_alpha(True)
        self.text_background_color.connect("color-set", self._update_text)
        row = self._attach(
            grid,
            row,
            "Background color",
            self.text_background_color,
        )

        self.text_background_padding = Gtk.SpinButton.new_with_range(
            0,
            500,
            1,
        )
        self.text_background_padding.connect(
            "value-changed",
            self._update_text,
        )
        row = self._attach(
            grid,
            row,
            "Background padding",
            self.text_background_padding,
        )

        self.text_opacity = self._opacity_scale(self._update_text)
        row = self._attach(grid, row, "Opacity", self.text_opacity)
        self.text_pos, row = self._position_controls(grid, row, self._update_text)
        return grid

    def _build_image_properties(self) -> Gtk.Widget:
        grid = self._property_grid()
        row = 0

        self.image_name = Gtk.Entry()
        self.image_name.connect("changed", self._update_image_name)
        row = self._attach(grid, row, "Name", self.image_name)

        self.image_enabled = Gtk.CheckButton(label="Enabled")
        self.image_enabled.connect("toggled", self._update_image)
        grid.attach(self.image_enabled, 1, row, 1, 1)
        row += 1

        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.image_path = Gtk.Entry()
        self.image_path.set_editable(False)
        self.image_path.set_hexpand(True)
        choose = Gtk.Button(label="Choose…")
        choose.connect("clicked", self._choose_existing_image)
        file_box.append(self.image_path)
        file_box.append(choose)
        row = self._attach(grid, row, "File", file_box)

        size_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        width_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        height_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.image_width = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.image_height = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.auto_width = Gtk.CheckButton(label="Auto")
        self.auto_height = Gtk.CheckButton(label="Auto")
        self.image_width.connect("value-changed", self._update_image)
        self.image_height.connect("value-changed", self._update_image)
        self.auto_width.connect("toggled", self._on_auto_size_toggled)
        self.auto_height.connect("toggled", self._on_auto_size_toggled)
        width_row.append(Gtk.Label(label="W"))
        width_row.append(self.image_width)
        width_row.append(self.auto_width)
        height_row.append(Gtk.Label(label="H"))
        height_row.append(self.image_height)
        height_row.append(self.auto_height)
        size_box.append(width_row)
        size_box.append(height_row)
        row = self._attach(grid, row, "Size (px)", size_box)

        self.keep_aspect = Gtk.CheckButton(label="Keep aspect ratio")
        self.keep_aspect.connect("toggled", self._update_image)
        grid.attach(self.keep_aspect, 1, row, 1, 1)
        row += 1

        self.image_opacity = self._opacity_scale(self._update_image)
        row = self._attach(grid, row, "Opacity", self.image_opacity)
        self.image_pos, row = self._position_controls(grid, row, self._update_image)
        return grid

    @staticmethod
    def _property_grid() -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=10, row_spacing=7)
        grid.set_hexpand(True)
        grid.set_margin_end(6)
        grid.set_margin_bottom(10)
        return grid

    @staticmethod
    def _attach(grid, row: int, label: str, widget: Gtk.Widget) -> int:
        lab = Gtk.Label(label=label)
        lab.set_xalign(1.0)
        lab.add_css_class("dim-label")
        grid.attach(lab, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)
        return row + 1

    @staticmethod
    def _opacity_scale(callback) -> Gtk.Scale:
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        scale.connect("value-changed", callback)
        return scale

    def _position_controls(self, grid, row: int, callback):
        randomize = Gtk.CheckButton(label="New position on every flash")
        row = self._attach(grid, row, "Random", randomize)

        anchor = Gtk.DropDown.new_from_strings(list(ANCHORS))
        anchor.connect("notify::selected", callback)
        row = self._attach(grid, row, "Anchor", anchor)

        x = Gtk.SpinButton.new_with_range(0, 100, 0.1)
        y = Gtk.SpinButton.new_with_range(0, 100, 0.1)
        x.connect("value-changed", callback)
        y.connect("value-changed", callback)
        xy = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        xy.append(Gtk.Label(label="X"))
        xy.append(x)
        xy.append(Gtk.Label(label="Y"))
        xy.append(y)
        row = self._attach(grid, row, "Position %", xy)

        ox = Gtk.SpinButton.new_with_range(-10000, 10000, 1)
        oy = Gtk.SpinButton.new_with_range(-10000, 10000, 1)
        ox.connect("value-changed", callback)
        oy.connect("value-changed", callback)
        offsets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        offsets.append(Gtk.Label(label="X"))
        offsets.append(ox)
        offsets.append(Gtk.Label(label="Y"))
        offsets.append(oy)
        row = self._attach(grid, row, "Offset px", offsets)

        controls = {
            "random": randomize,
            "anchor": anchor,
            "x": x,
            "y": y,
            "ox": ox,
            "oy": oy,
        }

        def on_random_toggled(button):
            self._set_fixed_position_sensitive(controls, not button.get_active())
            callback(button)

        randomize.connect("toggled", on_random_toggled)
        return controls, row

    @staticmethod
    def _set_fixed_position_sensitive(controls: dict, sensitive: bool) -> None:
        for key in ("anchor", "x", "y", "ox", "oy"):
            controls[key].set_sensitive(sensitive)

    def refresh(self) -> None:
        for attr in (
            "_library_refresh_id",
            "_folder_model_refresh_id",
        ):
            source_id = getattr(self, attr)
            if source_id is not None:
                GLib.source_remove(source_id)
                setattr(self, attr, None)
        if self._preview_refresh_id is not None:
            GLib.source_remove(self._preview_refresh_id)
            self._preview_refresh_id = None
        old_scene = self._scene_id
        old_folder = self._folder_id

        self._loading = True
        self._clear_listbox(self.library_list)

        for folder in self.controller.config.folders:
            self.library_list.append(self._folder_row(folder))
            for scene in self.controller.config.scenes:
                if scene.folder_id == folder.id:
                    self.library_list.append(self._scene_row(scene))

        unfiled = [
            scene
            for scene in self.controller.config.scenes
            if scene.folder_id is None
        ]
        self.library_list.append(self._unfiled_row())
        for scene in unfiled:
            self.library_list.append(self._scene_row(scene))

        target = None
        if old_scene is not None:
            target = self._row_with_attr(self.library_list, "scene_id", old_scene)
        elif old_folder is not None:
            target = self._row_with_attr(self.library_list, "folder_id", old_folder)

        if target is None:
            target = next(
                (
                    row
                    for row in self._rows(self.library_list)
                    if getattr(row, "row_kind", None) == "scene"
                ),
                None,
            )

        self._refresh_folder_dropdown()
        self._loading = False

        if target is not None:
            self.library_list.select_row(target)
        else:
            self._scene_id = None
            self._folder_id = None
            self._refresh_library_name()
            self._refresh_layers()
            self._refresh_scene_controls()
            self._refresh_properties()
            self._refresh_preview()

    def selected_scene(self) -> Scene | None:
        return self._find_scene(self._scene_id)

    def _folder_row(self, folder: Folder) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.row_kind = "folder"
        row.folder_id = folder.id
        row.scene_id = None
        label = Gtk.Label(label=f"▾  {folder.name}")
        label.set_xalign(0.0)
        label.set_margin_top(7)
        label.set_margin_bottom(5)
        label.set_margin_start(6)
        label.add_css_class("heading")
        row.set_child(label)
        return row

    @staticmethod
    def _unfiled_row() -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.row_kind = "unfiled"
        row.folder_id = None
        row.scene_id = None
        label = Gtk.Label(label="▾  Unfiled")
        label.set_xalign(0.0)
        label.set_margin_top(7)
        label.set_margin_bottom(5)
        label.set_margin_start(6)
        label.add_css_class("heading")
        row.set_child(label)
        return row

    @staticmethod
    def _scene_row(scene: Scene) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.row_kind = "scene"
        row.folder_id = scene.folder_id
        row.scene_id = scene.id
        label = Gtk.Label(label=scene.name)
        label.set_xalign(0.0)
        label.set_margin_top(5)
        label.set_margin_bottom(5)
        label.set_margin_start(28)
        label.set_margin_end(6)
        row.set_child(label)
        return row

    def _on_library_selected(self, _list, row) -> None:
        if self._loading or row is None:
            return
        kind = getattr(row, "row_kind", None)
        if kind == "scene":
            self._scene_id = getattr(row, "scene_id", None)
            self._folder_id = None
            self._layer_id = None
        elif kind == "folder":
            self._folder_id = getattr(row, "folder_id", None)
            self._scene_id = None
            self._layer_id = None
        elif kind == "unfiled":
            self._folder_id = None
            self._scene_id = None
            self._layer_id = None

        self._refresh_library_name()
        self._refresh_layers()
        self._refresh_scene_controls()
        self._refresh_properties()
        self._refresh_preview()

    def _refresh_library_name(self) -> None:
        self._loading = True
        try:
            scene = self.selected_scene()
            folder = self._find_folder(self._folder_id)
            if scene is not None:
                self.library_name.set_text(scene.name)
                self.library_name.set_sensitive(True)
            elif folder is not None:
                self.library_name.set_text(folder.name)
                self.library_name.set_sensitive(True)
            else:
                self.library_name.set_text("")
                self.library_name.set_sensitive(False)
        finally:
            self._loading = False

    def _library_name_changed(self, entry) -> None:
        if self._loading:
            return
        value = entry.get_text().strip()
        if not value:
            return
        scene = self.selected_scene()
        folder = self._find_folder(self._folder_id)
        if scene is not None:
            scene.name = value
        elif folder is not None:
            folder.name = value
        else:
            return
        self.controller.config_changed("metadata")
        self._refresh_library_row_labels()
        if folder is not None:
            self._schedule_folder_model_refresh()

    def _refresh_library_row_labels(self) -> None:
        for row in self._rows(self.library_list):
            label = row.get_child()
            if not isinstance(label, Gtk.Label):
                continue
            if getattr(row, "row_kind", None) == "scene":
                scene = self._find_scene(getattr(row, "scene_id", None))
                if scene is not None:
                    label.set_label(scene.name)
            elif getattr(row, "row_kind", None) == "folder":
                folder = self._find_folder(getattr(row, "folder_id", None))
                if folder is not None:
                    label.set_label(f"▾  {folder.name}")

    def _refresh_folder_dropdown(self) -> None:
        self._folder_choices = [None] + [
            folder.id for folder in self.controller.config.folders
        ]
        labels = ["Unfiled"] + [
            folder.name for folder in self.controller.config.folders
        ]
        self._loading = True
        try:
            # Keep the model object stable. Replacing a GtkDropDown model can emit
            # selection notifications while GTK is still processing the old one.
            self._folder_model.splice(
                0,
                self._folder_model.get_n_items(),
                labels,
            )
        finally:
            self._loading = False
        self._refresh_scene_controls()

    def _refresh_scene_controls(self) -> None:
        scene = self.selected_scene()
        self._loading = True
        try:
            sensitive = scene is not None
            self.scene_enabled.set_sensitive(sensitive)
            self.scene_folder.set_sensitive(sensitive)
            if scene is None:
                self.scene_enabled.set_active(False)
                self.scene_folder.set_selected(0)
                return
            self.scene_enabled.set_active(scene.enabled)
            try:
                index = self._folder_choices.index(scene.folder_id)
            except ValueError:
                index = 0
            self.scene_folder.set_selected(index)
        finally:
            self._loading = False

    def _scene_enabled_changed(self, button) -> None:
        if self._loading:
            return
        scene = self.selected_scene()
        if scene is None:
            return
        scene.enabled = button.get_active()
        self.controller.config_changed("visual")

    def _scene_folder_changed(self, dropdown, *_args) -> None:
        if self._loading:
            return
        scene = self.selected_scene()
        if scene is None:
            return
        index = dropdown.get_selected()
        if index >= len(self._folder_choices):
            index = 0
        new_folder_id = self._folder_choices[index]
        if scene.folder_id == new_folder_id:
            return
        scene.folder_id = new_folder_id
        self.controller.config_changed("metadata")
        # Never rebuild list/dropdown models from inside notify::selected.
        # GTK is still iterating the dropdown model at this point.
        self._schedule_library_refresh(scene.id)

    def _schedule_library_refresh(self, scene_id: str | None = None) -> None:
        if self._library_refresh_id is not None:
            GLib.source_remove(self._library_refresh_id)
        self._library_refresh_id = GLib.idle_add(
            self._run_library_refresh,
            scene_id,
        )

    def _run_library_refresh(self, scene_id: str | None) -> bool:
        self._library_refresh_id = None
        if scene_id is not None:
            self._scene_id = scene_id
            self._folder_id = None
        self._refresh_library_only()
        return GLib.SOURCE_REMOVE

    def _refresh_library_only(self) -> None:
        selected_scene = self._scene_id
        selected_folder = self._folder_id
        self._loading = True
        try:
            self._clear_listbox(self.library_list)
            for folder in self.controller.config.folders:
                self.library_list.append(self._folder_row(folder))
                for scene in self.controller.config.scenes:
                    if scene.folder_id == folder.id:
                        self.library_list.append(self._scene_row(scene))
            self.library_list.append(self._unfiled_row())
            for scene in self.controller.config.scenes:
                if scene.folder_id is None:
                    self.library_list.append(self._scene_row(scene))
        finally:
            self._loading = False

        target = None
        if selected_scene is not None:
            target = self._row_with_attr(
                self.library_list,
                "scene_id",
                selected_scene,
            )
        elif selected_folder is not None:
            target = self._row_with_attr(
                self.library_list,
                "folder_id",
                selected_folder,
            )

        if target is None:
            # A deferred refresh may outlive a delete/import. Never keep stale
            # model IDs in the editor; fall back to the first real scene.
            target = next(
                (
                    row
                    for row in self._rows(self.library_list)
                    if getattr(row, "row_kind", None) == "scene"
                ),
                None,
            )
            if target is None:
                self._scene_id = None
                self._folder_id = None
                self._layer_id = None
                self._refresh_library_name()
                self._refresh_layers()
                self._refresh_scene_controls()
                self._refresh_properties()
                self._request_preview_refresh(0)
                return

        self.library_list.select_row(target)

    def _schedule_folder_model_refresh(self) -> None:
        if self._folder_model_refresh_id is not None:
            GLib.source_remove(self._folder_model_refresh_id)
        self._folder_model_refresh_id = GLib.timeout_add(
            80,
            self._run_folder_model_refresh,
        )

    def _run_folder_model_refresh(self) -> bool:
        self._folder_model_refresh_id = None
        self._refresh_folder_dropdown()
        return GLib.SOURCE_REMOVE

    def _refresh_layers(self) -> None:
        previous = self._layer_id
        self._loading = True
        self._clear_listbox(self.layer_list)
        scene = self.selected_scene()
        if scene is not None:
            for layer in scene.layers:
                row = Gtk.ListBoxRow()
                row.layer_id = layer.id
                prefix = "T" if isinstance(layer, TextLayer) else "▧"
                label = Gtk.Label(label=f"{prefix}  {layer.name}")
                label.set_xalign(0.0)
                label.set_margin_top(6)
                label.set_margin_bottom(6)
                label.set_margin_start(8)
                label.set_margin_end(8)
                row.set_child(label)
                self.layer_list.append(row)
        self._loading = False

        target = self._row_with_attr(self.layer_list, "layer_id", previous)
        if target is None:
            target = self.layer_list.get_row_at_index(0)
        if target is not None:
            self.layer_list.select_row(target)
        else:
            self._layer_id = None
            self._refresh_properties()

    def _on_layer_selected(self, _list, row) -> None:
        if self._loading:
            return
        self._layer_id = getattr(row, "layer_id", None) if row else None
        self._refresh_properties()

    def _refresh_properties(self) -> None:
        layer = self._find_layer(self._layer_id)
        self._loading = True
        try:
            if isinstance(layer, TextLayer):
                self.property_stack.set_visible_child_name("text")
                self.text_name.set_text(layer.name)
                self.text_enabled.set_active(layer.enabled)
                self.text_view.get_buffer().set_text(layer.text)
                font_desc = Pango.FontDescription.new()
                font_desc.set_family(layer.font_family)
                font_desc.set_size(12 * Pango.SCALE)
                self.font_button.set_font_desc(font_desc)
                self.font_size.set_value(layer.font_size_px)
                self.bold.set_active(layer.bold)
                self.italic.set_active(layer.italic)
                self.underline.set_active(layer.underline)
                rgba = Gdk.RGBA()
                rgba.parse(layer.color)
                self.color.set_rgba(rgba)
                alignment_index = {
                    "left": 0,
                    "center": 1,
                    "right": 2,
                }.get(layer.alignment, 0)
                self.text_alignment.set_selected(alignment_index)
                self.text_background_enabled.set_active(
                    layer.background_enabled
                )
                background_rgba = Gdk.RGBA()
                background_rgba.parse(layer.background_color)
                self.text_background_color.set_rgba(background_rgba)
                self.text_background_padding.set_value(
                    layer.background_padding_px
                )
                self._set_text_background_sensitive(
                    layer.background_enabled
                )
                self.text_opacity.set_value(layer.opacity * 100)
                self._load_position(self.text_pos, layer.position)
            elif isinstance(layer, ImageLayer):
                self.property_stack.set_visible_child_name("image")
                self.image_name.set_text(layer.name)
                self.image_enabled.set_active(layer.enabled)
                self.image_path.set_text(layer.path)
                self.auto_width.set_active(layer.width_px is None)
                self.auto_height.set_active(layer.height_px is None)
                self.image_width.set_sensitive(layer.width_px is not None)
                self.image_height.set_sensitive(layer.height_px is not None)
                self.image_width.set_value(layer.width_px or 320)
                self.image_height.set_value(layer.height_px or 240)
                self.keep_aspect.set_active(layer.keep_aspect_ratio)
                self.image_opacity.set_value(layer.opacity * 100)
                self._load_position(self.image_pos, layer.position)
            else:
                self.property_stack.set_visible_child_name("empty")
        finally:
            self._loading = False

    def _load_position(self, controls: dict, position) -> None:
        controls["random"].set_active(position.randomize)
        self._set_fixed_position_sensitive(controls, not position.randomize)
        controls["anchor"].set_selected(ANCHORS.index(position.anchor))
        controls["x"].set_value(position.x * 100)
        controls["y"].set_value(position.y * 100)
        controls["ox"].set_value(position.offset_x)
        controls["oy"].set_value(position.offset_y)

    @staticmethod
    def _read_position(controls: dict, position) -> None:
        position.randomize = controls["random"].get_active()
        position.anchor = ANCHORS[controls["anchor"].get_selected()]
        position.x = controls["x"].get_value() / 100.0
        position.y = controls["y"].get_value() / 100.0
        position.offset_x = controls["ox"].get_value_as_int()
        position.offset_y = controls["oy"].get_value_as_int()

    def _update_text_name(self, entry) -> None:
        if self._loading:
            return
        layer = self._find_layer(self._layer_id)
        if not isinstance(layer, TextLayer):
            return
        value = entry.get_text().strip()
        if not value or value == layer.name:
            return
        layer.name = value
        self.controller.config_changed("metadata")
        self._refresh_layer_label()

    def _update_image_name(self, entry) -> None:
        if self._loading:
            return
        layer = self._find_layer(self._layer_id)
        if not isinstance(layer, ImageLayer):
            return
        value = entry.get_text().strip()
        if not value or value == layer.name:
            return
        layer.name = value
        self.controller.config_changed("metadata")
        self._refresh_layer_label()

    def _update_text(self, *_args) -> None:
        if self._loading:
            return
        layer = self._find_layer(self._layer_id)
        if not isinstance(layer, TextLayer):
            return

        start, end = self.text_view.get_buffer().get_bounds()
        layer.text = self.text_view.get_buffer().get_text(start, end, True)
        layer.enabled = self.text_enabled.get_active()
        desc = self.font_button.get_font_desc()
        layer.font_family = (
            desc.get_family()
            if desc is not None and desc.get_family()
            else "Sans"
        )
        layer.font_size_px = self.font_size.get_value_as_int()
        layer.bold = self.bold.get_active()
        layer.italic = self.italic.get_active()
        layer.underline = self.underline.get_active()
        layer.alignment = ("left", "center", "right")[
            min(2, self.text_alignment.get_selected())
        ]
        rgba = self.color.get_rgba()
        layer.color = "#{:02X}{:02X}{:02X}{:02X}".format(
            round(rgba.red * 255),
            round(rgba.green * 255),
            round(rgba.blue * 255),
            round(rgba.alpha * 255),
        )
        layer.background_enabled = (
            self.text_background_enabled.get_active()
        )
        background_rgba = self.text_background_color.get_rgba()
        layer.background_color = "#{:02X}{:02X}{:02X}{:02X}".format(
            round(background_rgba.red * 255),
            round(background_rgba.green * 255),
            round(background_rgba.blue * 255),
            round(background_rgba.alpha * 255),
        )
        layer.background_padding_px = (
            self.text_background_padding.get_value_as_int()
        )
        layer.opacity = self.text_opacity.get_value() / 100.0
        self._read_position(self.text_pos, layer.position)
        self._changed_layer()

    def _on_text_background_toggled(self, button) -> None:
        if self._loading:
            return
        self._set_text_background_sensitive(button.get_active())
        self._update_text()

    def _set_text_background_sensitive(self, enabled: bool) -> None:
        self.text_background_color.set_sensitive(enabled)
        self.text_background_padding.set_sensitive(enabled)

    def _update_image(self, *_args) -> None:
        if self._loading:
            return
        layer = self._find_layer(self._layer_id)
        if not isinstance(layer, ImageLayer):
            return

        layer.enabled = self.image_enabled.get_active()
        layer.width_px = (
            None if self.auto_width.get_active()
            else self.image_width.get_value_as_int()
        )
        layer.height_px = (
            None if self.auto_height.get_active()
            else self.image_height.get_value_as_int()
        )
        layer.keep_aspect_ratio = self.keep_aspect.get_active()
        layer.opacity = self.image_opacity.get_value() / 100.0
        self._read_position(self.image_pos, layer.position)
        self._changed_layer()

    def _changed_layer(self) -> None:
        self.controller.config_changed("visual")
        self._refresh_layer_label()
        self._request_preview_refresh()

    def _refresh_layer_label(self) -> None:
        row = self.layer_list.get_selected_row()
        layer = self._find_layer(self._layer_id)
        if row is None or layer is None:
            return
        prefix = "T" if isinstance(layer, TextLayer) else "▧"
        child = row.get_child()
        if isinstance(child, Gtk.Label):
            child.set_label(f"{prefix}  {layer.name}")

    def _on_auto_size_toggled(self, *_args) -> None:
        self.image_width.set_sensitive(not self.auto_width.get_active())
        self.image_height.set_sensitive(not self.auto_height.get_active())
        self._update_image()

    def _request_preview_refresh(self, delay_ms: int = 75) -> None:
        if self._preview_refresh_id is not None:
            GLib.source_remove(self._preview_refresh_id)
        self._preview_refresh_id = GLib.timeout_add(
            delay_ms,
            self._run_preview_refresh,
        )

    def _run_preview_refresh(self) -> bool:
        self._preview_refresh_id = None
        self._refresh_preview()
        return GLib.SOURCE_REMOVE

    def _refresh_preview(self) -> None:
        scene = self.selected_scene()
        if scene is None:
            if self._preview_view is not None:
                self._preview_view.stop_animations()
                self._preview_view = None
            self.preview_frame.set_child(Gtk.Label(label="Select a scene"))
            return

        # Build the replacement first. SceneView remains hidden until it has a
        # valid layout, so the old preview can stay visible during construction.
        view = SceneView(
            scene,
            self.controller.overlay.media,
            scale=0.33,
            preview=True,
        )
        old_view = self._preview_view
        self._preview_view = view
        self.preview_frame.set_child(view)
        view.start_animations()
        if old_view is not None:
            old_view.stop_animations()

    def _add_folder(self, *_args) -> None:
        folder = Folder(name=f"Folder {len(self.controller.config.folders) + 1}")
        self.controller.config.folders.append(folder)
        self._folder_id = folder.id
        self._scene_id = None
        self.controller.config_changed("metadata")
        self.refresh()
        row = self._row_with_attr(self.library_list, "folder_id", folder.id)
        if row is not None:
            self.library_list.select_row(row)
            self.library_name.grab_focus()
            self.library_name.select_region(0, -1)

    def _add_scene(self, *_args) -> None:
        folder_id = self._folder_id
        current = self.selected_scene()
        if current is not None:
            folder_id = current.folder_id
        scene = Scene(
            name=f"Scene {len(self.controller.config.scenes) + 1}",
            folder_id=folder_id,
            layers=[TextLayer(name="Message", text="New message")],
        )
        self.controller.config.scenes.append(scene)
        self._scene_id = scene.id
        self._folder_id = None
        self._layer_id = scene.layers[0].id
        self.controller.config_changed("structural")
        self.refresh()

    def _duplicate_scene(self, *_args) -> None:
        scene = self.selected_scene()
        if scene is None:
            return
        duplicate = copy.deepcopy(scene)
        duplicate.id = new_id()
        duplicate.name = f"{scene.name} copy"
        for layer in duplicate.layers:
            layer.id = new_id()
        self.controller.config.scenes.append(duplicate)
        self._scene_id = duplicate.id
        self._folder_id = None
        self.controller.config_changed("structural")
        self.refresh()

    def _delete_library_item(self, *_args) -> None:
        scene = self.selected_scene()
        folder = self._find_folder(self._folder_id)

        if scene is not None:
            if len(self.controller.config.scenes) <= 1:
                self.controller.warn("At least one scene must remain.")
                return
            self.controller.config.scenes[:] = [
                item for item in self.controller.config.scenes
                if item.id != scene.id
            ]
            self._scene_id = None
            self._layer_id = None
            self.controller.config_changed("structural")
            self.refresh()
            return

        if folder is not None:
            for item in self.controller.config.scenes:
                if item.folder_id == folder.id:
                    item.folder_id = None
            self.controller.config.folders[:] = [
                item for item in self.controller.config.folders
                if item.id != folder.id
            ]
            self._folder_id = None
            self.controller.config_changed("metadata")
            self.refresh()

    def _add_text_layer(self, *_args) -> None:
        scene = self.selected_scene()
        if scene is None:
            return
        layer = TextLayer(
            name=f"Text {len(scene.layers) + 1}",
            text="New message",
        )
        scene.layers.append(layer)
        self._layer_id = layer.id
        self.controller.config_changed("structural")
        self._refresh_layers()
        self._refresh_preview()

    def _choose_new_image(self, *_args) -> None:
        self._open_image_dialog(self._new_image_chosen)

    def _choose_existing_image(self, *_args) -> None:
        self._open_image_dialog(self._existing_image_chosen)

    def _open_image_dialog(self, callback) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Choose image",
            self.get_root(),
            Gtk.FileChooserAction.OPEN,
            "Open",
            "Cancel",
        )

        image_filter = Gtk.FileFilter()
        image_filter.set_name("Supported images")
        for pattern in (
            "*.png", "*.PNG",
            "*.jpg", "*.JPG", "*.jpeg", "*.JPEG",
            "*.webp", "*.WEBP",
            "*.gif", "*.GIF",
            "*.svg", "*.SVG",
        ):
            image_filter.add_pattern(pattern)
        for mime in (
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/gif",
            "image/svg+xml",
        ):
            image_filter.add_mime_type(mime)
        dialog.add_filter(image_filter)

        svg_filter = Gtk.FileFilter()
        svg_filter.set_name("SVG files")
        svg_filter.add_pattern("*.svg")
        svg_filter.add_pattern("*.SVG")
        svg_filter.add_mime_type("image/svg+xml")
        dialog.add_filter(svg_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All files")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)

        dialog.connect("response", callback)
        dialog.show()

    def _new_image_chosen(self, dialog, response) -> None:
        try:
            if response != Gtk.ResponseType.ACCEPT:
                return
            file = dialog.get_file()
            if file is None or file.get_path() is None:
                return
            scene = self.selected_scene()
            if scene is None:
                return
            path = file.get_path()
            layer = ImageLayer(
                name=Path(path).name,
                path=path,
            )
            scene.layers.append(layer)
            self._layer_id = layer.id
            self.controller.config_changed("structural")
            self._refresh_layers()
            self._refresh_preview()
        finally:
            dialog.destroy()

    def _existing_image_chosen(self, dialog, response) -> None:
        try:
            if response != Gtk.ResponseType.ACCEPT:
                return
            file = dialog.get_file()
            layer = self._find_layer(self._layer_id)
            if (
                file is None
                or file.get_path() is None
                or not isinstance(layer, ImageLayer)
            ):
                return
            layer.path = file.get_path()
            self.image_path.set_text(layer.path)
            self._changed_layer()
        finally:
            dialog.destroy()

    def _delete_layer(self, *_args) -> None:
        scene = self.selected_scene()
        if scene is None or self._layer_id is None:
            return
        scene.layers[:] = [
            layer for layer in scene.layers
            if layer.id != self._layer_id
        ]
        self._layer_id = None
        self.controller.config_changed("structural")
        self._refresh_layers()
        self._refresh_properties()
        self._refresh_preview()

    def _move_layer(self, delta: int) -> None:
        scene = self.selected_scene()
        if scene is None or self._layer_id is None:
            return
        index = next(
            (
                i for i, layer in enumerate(scene.layers)
                if layer.id == self._layer_id
            ),
            None,
        )
        if index is None:
            return
        new_index = max(0, min(len(scene.layers) - 1, index + delta))
        if new_index == index:
            return
        layer = scene.layers.pop(index)
        scene.layers.insert(new_index, layer)
        self.controller.config_changed("structural")
        self._refresh_layers()
        self._refresh_preview()

    def _find_scene(self, scene_id: str | None) -> Scene | None:
        return next(
            (
                scene for scene in self.controller.config.scenes
                if scene.id == scene_id
            ),
            None,
        )

    def _find_folder(self, folder_id: str | None) -> Folder | None:
        if folder_id is None:
            return None
        return next(
            (
                folder for folder in self.controller.config.folders
                if folder.id == folder_id
            ),
            None,
        )

    def _find_layer(self, layer_id: str | None):
        scene = self.selected_scene()
        if scene is None:
            return None
        return next(
            (layer for layer in scene.layers if layer.id == layer_id),
            None,
        )

    @staticmethod
    def _clear_listbox(listbox: Gtk.ListBox) -> None:
        child = listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt

    @staticmethod
    def _rows(listbox: Gtk.ListBox):
        row = listbox.get_first_child()
        while row is not None:
            yield row
            row = row.get_next_sibling()

    @staticmethod
    def _row_with_attr(listbox: Gtk.ListBox, attr: str, value):
        if value is None:
            return None
        row = listbox.get_first_child()
        while row is not None:
            if getattr(row, attr, None) == value:
                return row
            row = row.get_next_sibling()
        return None


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
        self.refresh()


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

    def _mode_changed(self, *_args) -> None:
        if self._loading:
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

    def refresh(self) -> None:
        self._loading = True
        self.start_on_launch.set_active(
            self.controller.config.start_on_launch
        )
        self.autostart.set_active(self.controller.config.autostart)
        self._loading = False

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        self.controller.config.start_on_launch = (
            self.start_on_launch.get_active()
        )
        self.controller.config.autostart = self.autostart.get_active()
        self.controller.set_autostart(self.controller.config.autostart)
        self.controller.config_changed("settings")
