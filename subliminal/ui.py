from __future__ import annotations

from pathlib import Path

from . import __version__
from .gtk_runtime import Gdk, Gtk, Pango
from .model import ANCHORS, ImageLayer, Scene, TextLayer, new_id
from .render import SceneView


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application, controller) -> None:
        super().__init__(application=application, title="Subliminal")
        self.controller = controller
        self.set_default_size(1180, 760)
        self.set_size_request(900, 620)
        self.connect("close-request", self._on_close_request)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_top(10)
        toolbar.set_margin_bottom(10)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        root.append(toolbar)

        title = Gtk.Label(label="Subliminal")
        title.add_css_class("title-2")
        title.set_hexpand(True)
        title.set_xalign(0.0)
        toolbar.append(title)

        self.status_label = Gtk.Label(label="Stopped")
        self.status_label.add_css_class("dim-label")
        toolbar.append(self.status_label)

        self.start_button = Gtk.Button(label="Start")
        self.pause_button = Gtk.Button(label="Pause")
        self.stop_button = Gtk.Button(label="Stop")
        self.test_button = Gtk.Button(label="Test flash")
        self.quit_button = Gtk.Button(label="Quit")
        for button in (self.start_button, self.pause_button, self.stop_button, self.test_button, self.quit_button):
            toolbar.append(button)
        self.start_button.add_css_class("suggested-action")
        self.start_button.connect("clicked", lambda *_: self.controller.start())
        self.pause_button.connect("clicked", lambda *_: self.controller.pause())
        self.stop_button.connect("clicked", lambda *_: self.controller.stop())
        self.test_button.connect("clicked", lambda *_: self.controller.test_flash(self.content_page.selected_scene()))
        self.quit_button.connect("clicked", lambda *_: self.controller.quit())

        self.banner = Gtk.Label()
        self.banner.set_wrap(True)
        self.banner.set_xalign(0.0)
        self.banner.set_margin_start(12)
        self.banner.set_margin_end(12)
        self.banner.set_margin_bottom(8)
        self.banner.add_css_class("warning-banner")
        self.banner.set_visible(False)
        root.append(self.banner)

        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        root.append(notebook)

        self.content_page = ContentPage(controller)
        self.timing_page = TimingPage(controller)
        self.displays_page = DisplaysPage(controller)
        self.settings_page = SettingsPage(controller)
        notebook.append_page(self.content_page, Gtk.Label(label="Content"))
        notebook.append_page(self.timing_page, Gtk.Label(label="Timing"))
        notebook.append_page(self.displays_page, Gtk.Label(label="Displays"))
        notebook.append_page(self.settings_page, Gtk.Label(label="Settings"))
        self.refresh_all()

    def refresh_all(self) -> None:
        self.content_page.refresh()
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

    def _on_close_request(self, *_args) -> bool:
        self.set_visible(False)
        return True


class ContentPage(Gtk.Box):
    def __init__(self, controller) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.controller = controller
        self._scene_id: str | None = None
        self._layer_id: str | None = None
        self._loading = False
        self._preview_view = None
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        body = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        body.set_hexpand(True)
        body.set_vexpand(True)
        self.append(body)

        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        body.set_start_child(left)
        body.set_resize_start_child(False)
        body.set_shrink_start_child(False)

        scene_col = self._build_scene_column()
        layer_col = self._build_layer_column()
        left.append(scene_col)
        left.append(layer_col)

        right_scroll = Gtk.ScrolledWindow()
        right_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        right.set_margin_start(12)
        right.set_margin_end(12)
        right.set_margin_bottom(12)
        right_scroll.set_child(right)
        body.set_end_child(right_scroll)
        body.set_resize_end_child(True)

        preview_label = Gtk.Label(label="Preview")
        preview_label.add_css_class("heading")
        preview_label.set_xalign(0.0)
        right.append(preview_label)
        self.preview_frame = Gtk.Frame()
        self.preview_frame.add_css_class("preview-canvas")
        self.preview_frame.set_size_request(640, 360)
        self.preview_frame.set_hexpand(True)
        right.append(self.preview_frame)

        self.properties_title = Gtk.Label(label="Layer properties")
        self.properties_title.add_css_class("heading")
        self.properties_title.set_xalign(0.0)
        right.append(self.properties_title)

        self.property_stack = Gtk.Stack()
        self.property_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        right.append(self.property_stack)
        self.property_stack.add_named(Gtk.Label(label="Select a layer to edit it."), "empty")
        self.text_props = self._build_text_properties()
        self.image_props = self._build_image_properties()
        self.property_stack.add_named(self.text_props, "text")
        self.property_stack.add_named(self.image_props, "image")

    def _build_scene_column(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(180, -1)
        label = Gtk.Label(label="Scenes")
        label.add_css_class("heading")
        label.set_xalign(0.0)
        box.append(label)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.scene_list = Gtk.ListBox()
        self.scene_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.scene_list.connect("row-selected", self._on_scene_selected)
        scroll.set_child(self.scene_list)
        box.append(scroll)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add = Gtk.Button(label="+")
        duplicate = Gtk.Button(label="Duplicate")
        delete = Gtk.Button(label="−")
        add.set_tooltip_text("Add scene")
        delete.set_tooltip_text("Delete scene")
        add.connect("clicked", self._add_scene)
        duplicate.connect("clicked", self._duplicate_scene)
        delete.connect("clicked", self._delete_scene)
        buttons.append(add)
        buttons.append(duplicate)
        buttons.append(delete)
        box.append(buttons)
        return box

    def _build_layer_column(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(210, -1)
        label = Gtk.Label(label="Layers")
        label.add_css_class("heading")
        label.set_xalign(0.0)
        box.append(label)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.layer_list = Gtk.ListBox()
        self.layer_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.layer_list.connect("row-selected", self._on_layer_selected)
        scroll.set_child(self.layer_list)
        box.append(scroll)

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_text = Gtk.Button(label="+ Text")
        add_image = Gtk.Button(label="+ Image")
        add_text.connect("clicked", self._add_text_layer)
        add_image.connect("clicked", self._choose_new_image)
        add_row.append(add_text)
        add_row.append(add_image)
        box.append(add_row)

        move_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        up = Gtk.Button(label="↑")
        down = Gtk.Button(label="↓")
        delete = Gtk.Button(label="Delete")
        up.connect("clicked", lambda *_: self._move_layer(-1))
        down.connect("clicked", lambda *_: self._move_layer(1))
        delete.connect("clicked", self._delete_layer)
        move_row.append(up)
        move_row.append(down)
        move_row.append(delete)
        box.append(move_row)
        return box

    def _build_text_properties(self) -> Gtk.Widget:
        grid = self._property_grid()
        row = 0
        self.text_enabled = Gtk.CheckButton(label="Enabled")
        self.text_enabled.connect("toggled", self._update_text)
        grid.attach(self.text_enabled, 0, row, 2, 1); row += 1

        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_scroll = Gtk.ScrolledWindow()
        text_scroll.set_min_content_height(80)
        text_scroll.set_child(self.text_view)
        self.text_view.get_buffer().connect("changed", self._update_text)
        row = self._attach(grid, row, "Text", text_scroll)

        self.font_button = Gtk.FontButton()
        self.font_button.set_use_font(True)
        self.font_button.set_use_size(False)
        self.font_button.connect("font-set", self._update_text)
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

        self.text_opacity = self._opacity_scale(self._update_text)
        row = self._attach(grid, row, "Opacity", self.text_opacity)
        self.text_pos, row = self._position_controls(grid, row, self._update_text)
        return grid

    def _build_image_properties(self) -> Gtk.Widget:
        grid = self._property_grid()
        row = 0
        self.image_enabled = Gtk.CheckButton(label="Enabled")
        self.image_enabled.connect("toggled", self._update_image)
        grid.attach(self.image_enabled, 0, row, 2, 1); row += 1

        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.image_path = Gtk.Entry()
        self.image_path.set_editable(False)
        self.image_path.set_hexpand(True)
        choose = Gtk.Button(label="Choose…")
        choose.connect("clicked", self._choose_existing_image)
        file_box.append(self.image_path)
        file_box.append(choose)
        row = self._attach(grid, row, "File", file_box)

        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.image_width = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.image_height = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.auto_width = Gtk.CheckButton(label="Auto W")
        self.auto_height = Gtk.CheckButton(label="Auto H")
        self.image_width.connect("value-changed", self._update_image)
        self.image_height.connect("value-changed", self._update_image)
        self.auto_width.connect("toggled", self._on_auto_size_toggled)
        self.auto_height.connect("toggled", self._on_auto_size_toggled)
        size_box.append(self.image_width)
        size_box.append(self.auto_width)
        size_box.append(self.image_height)
        size_box.append(self.auto_height)
        row = self._attach(grid, row, "Size (px)", size_box)

        self.keep_aspect = Gtk.CheckButton(label="Keep aspect ratio")
        self.keep_aspect.connect("toggled", self._update_image)
        grid.attach(self.keep_aspect, 1, row, 1, 1); row += 1

        self.image_opacity = self._opacity_scale(self._update_image)
        row = self._attach(grid, row, "Opacity", self.image_opacity)
        self.image_pos, row = self._position_controls(grid, row, self._update_image)
        return grid

    def _property_grid(self) -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        grid.set_hexpand(True)
        return grid

    def _attach(self, grid, row: int, label: str, widget: Gtk.Widget) -> int:
        lab = Gtk.Label(label=label)
        lab.set_xalign(1.0)
        lab.add_css_class("dim-label")
        grid.attach(lab, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)
        return row + 1

    def _opacity_scale(self, callback) -> Gtk.Scale:
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        scale.connect("value-changed", callback)
        return scale

    def _position_controls(self, grid, row: int, callback):
        anchor = Gtk.DropDown.new_from_strings(list(ANCHORS))
        anchor.connect("notify::selected", callback)
        row = self._attach(grid, row, "Anchor", anchor)
        x = Gtk.SpinButton.new_with_range(0, 100, 0.1)
        y = Gtk.SpinButton.new_with_range(0, 100, 0.1)
        x.connect("value-changed", callback)
        y.connect("value-changed", callback)
        xy = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        xy.append(Gtk.Label(label="X")); xy.append(x)
        xy.append(Gtk.Label(label="Y")); xy.append(y)
        row = self._attach(grid, row, "Position (%)", xy)
        ox = Gtk.SpinButton.new_with_range(-10000, 10000, 1)
        oy = Gtk.SpinButton.new_with_range(-10000, 10000, 1)
        ox.connect("value-changed", callback)
        oy.connect("value-changed", callback)
        offsets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        offsets.append(Gtk.Label(label="X")); offsets.append(ox)
        offsets.append(Gtk.Label(label="Y")); offsets.append(oy)
        row = self._attach(grid, row, "Offset (px)", offsets)
        return {"anchor": anchor, "x": x, "y": y, "ox": ox, "oy": oy}, row

    def refresh(self) -> None:
        previous_scene = self._scene_id
        self._clear_listbox(self.scene_list)
        for scene in self.controller.config.scenes:
            row = Gtk.ListBoxRow()
            row.scene_id = scene.id
            label = Gtk.Label(label=scene.name)
            label.set_xalign(0.0)
            label.set_margin_top(6); label.set_margin_bottom(6); label.set_margin_start(8); label.set_margin_end(8)
            row.set_child(label)
            self.scene_list.append(row)
        target = self._row_with_attr(self.scene_list, "scene_id", previous_scene)
        if target is None:
            target = self.scene_list.get_row_at_index(0)
        if target is not None:
            self.scene_list.select_row(target)
        else:
            self._scene_id = None
            self._layer_id = None
            self._refresh_layers()
            self._refresh_properties()
            self._refresh_preview()

    def selected_scene(self) -> Scene | None:
        return self._find_scene(self._scene_id)

    def _on_scene_selected(self, _list, row) -> None:
        if row is None:
            return
        self._scene_id = getattr(row, "scene_id", None)
        self._layer_id = None
        self._refresh_layers()
        self._refresh_properties()
        self._refresh_preview()

    def _on_layer_selected(self, _list, row) -> None:
        self._layer_id = getattr(row, "layer_id", None) if row is not None else None
        self._refresh_properties()

    def _refresh_layers(self) -> None:
        previous = self._layer_id
        self._clear_listbox(self.layer_list)
        scene = self.selected_scene()
        if scene is None:
            return
        for layer in scene.layers:
            row = Gtk.ListBoxRow()
            row.layer_id = layer.id
            if isinstance(layer, TextLayer):
                text = layer.text.replace("\n", " ").strip() or "Text"
                title = f"T  {text[:22]}"
            else:
                title = f"▧  {Path(layer.path).name or 'Image'}"
            label = Gtk.Label(label=title)
            label.set_xalign(0.0)
            label.set_margin_top(6); label.set_margin_bottom(6); label.set_margin_start(8); label.set_margin_end(8)
            row.set_child(label)
            self.layer_list.append(row)
        target = self._row_with_attr(self.layer_list, "layer_id", previous)
        if target is None:
            target = self.layer_list.get_row_at_index(0)
        if target is not None:
            self.layer_list.select_row(target)

    def _refresh_properties(self) -> None:
        layer = self._find_layer(self._layer_id)
        self._loading = True
        try:
            if isinstance(layer, TextLayer):
                self.property_stack.set_visible_child_name("text")
                self.text_enabled.set_active(layer.enabled)
                self.text_view.get_buffer().set_text(layer.text)
                self.font_button.set_font(f"{layer.font_family} 12")
                self.font_size.set_value(layer.font_size_px)
                self.bold.set_active(layer.bold)
                self.italic.set_active(layer.italic)
                self.underline.set_active(layer.underline)
                rgba = Gdk.RGBA()
                rgba.parse(layer.color)
                self.color.set_rgba(rgba)
                self.text_opacity.set_value(layer.opacity * 100)
                self._load_position(self.text_pos, layer.position)
            elif isinstance(layer, ImageLayer):
                self.property_stack.set_visible_child_name("image")
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
        controls["anchor"].set_selected(ANCHORS.index(position.anchor))
        controls["x"].set_value(position.x * 100)
        controls["y"].set_value(position.y * 100)
        controls["ox"].set_value(position.offset_x)
        controls["oy"].set_value(position.offset_y)

    def _read_position(self, controls: dict, position) -> None:
        position.anchor = ANCHORS[controls["anchor"].get_selected()]
        position.x = controls["x"].get_value() / 100.0
        position.y = controls["y"].get_value() / 100.0
        position.offset_x = controls["ox"].get_value_as_int()
        position.offset_y = controls["oy"].get_value_as_int()

    def _update_text(self, *_args) -> None:
        if self._loading:
            return
        layer = self._find_layer(self._layer_id)
        if not isinstance(layer, TextLayer):
            return
        start, end = self.text_view.get_buffer().get_bounds()
        layer.text = self.text_view.get_buffer().get_text(start, end, True)
        layer.enabled = self.text_enabled.get_active()
        desc = Pango.FontDescription.from_string(self.font_button.get_font() or "Sans 12")
        layer.font_family = desc.get_family() or "Sans"
        layer.font_size_px = self.font_size.get_value_as_int()
        layer.bold = self.bold.get_active()
        layer.italic = self.italic.get_active()
        layer.underline = self.underline.get_active()
        rgba = self.color.get_rgba()
        layer.color = "#{:02X}{:02X}{:02X}{:02X}".format(
            round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255), round(rgba.alpha * 255)
        )
        layer.opacity = self.text_opacity.get_value() / 100.0
        self._read_position(self.text_pos, layer.position)
        self._changed("content")

    def _update_image(self, *_args) -> None:
        if self._loading:
            return
        layer = self._find_layer(self._layer_id)
        if not isinstance(layer, ImageLayer):
            return
        layer.enabled = self.image_enabled.get_active()
        layer.width_px = None if self.auto_width.get_active() else self.image_width.get_value_as_int()
        layer.height_px = None if self.auto_height.get_active() else self.image_height.get_value_as_int()
        layer.keep_aspect_ratio = self.keep_aspect.get_active()
        layer.opacity = self.image_opacity.get_value() / 100.0
        self._read_position(self.image_pos, layer.position)
        self._changed("content")

    def _on_auto_size_toggled(self, *_args) -> None:
        self.image_width.set_sensitive(not self.auto_width.get_active())
        self.image_height.set_sensitive(not self.auto_height.get_active())
        self._update_image()

    def _changed(self, kind: str) -> None:
        self.controller.config_changed(kind)
        self._refresh_preview()
        self._refresh_layer_label()

    def _refresh_preview(self) -> None:
        if self._preview_view is not None:
            self._preview_view.stop_animations()
            self._preview_view = None
        scene = self.selected_scene()
        if scene is None:
            self.preview_frame.set_child(Gtk.Label(label="No scene"))
            return
        view = SceneView(scene, self.controller.overlay.media, scale=0.33, preview=True)
        self._preview_view = view
        self.preview_frame.set_child(view)
        view.start_animations()

    def _refresh_layer_label(self) -> None:
        row = self.layer_list.get_selected_row()
        layer = self._find_layer(self._layer_id)
        if row is None or layer is None:
            return
        if isinstance(layer, TextLayer):
            title = f"T  {(layer.text.replace(chr(10), ' ').strip() or 'Text')[:22]}"
        else:
            title = f"▧  {Path(layer.path).name or 'Image'}"
        if isinstance(row.get_child(), Gtk.Label):
            row.get_child().set_label(title)

    def _add_scene(self, *_args) -> None:
        scene = Scene(name=f"Scene {len(self.controller.config.scenes) + 1}", layers=[TextLayer(text="New message")])
        self.controller.config.scenes.append(scene)
        self._scene_id = scene.id
        self._layer_id = scene.layers[0].id
        self.controller.config_changed("content")
        self.refresh()

    def _duplicate_scene(self, *_args) -> None:
        scene = self.selected_scene()
        if scene is None:
            return
        # Round-trip through model dictionaries would be overkill; copy fields explicitly via deepcopy.
        import copy
        duplicate = copy.deepcopy(scene)
        duplicate.id = new_id()
        duplicate.name = f"{scene.name} copy"
        for layer in duplicate.layers:
            layer.id = new_id()
        self.controller.config.scenes.append(duplicate)
        self._scene_id = duplicate.id
        self.controller.config_changed("content")
        self.refresh()

    def _delete_scene(self, *_args) -> None:
        if len(self.controller.config.scenes) <= 1:
            self.controller.warn("At least one scene must remain.")
            return
        self.controller.config.scenes[:] = [s for s in self.controller.config.scenes if s.id != self._scene_id]
        self._scene_id = None
        self._layer_id = None
        self.controller.config_changed("content")
        self.refresh()

    def _add_text_layer(self, *_args) -> None:
        scene = self.selected_scene()
        if scene is None:
            return
        layer = TextLayer(text="New message")
        scene.layers.append(layer)
        self._layer_id = layer.id
        self.controller.config_changed("content")
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
        image_filter.set_name("Images")
        for mime in ("image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"):
            image_filter.add_mime_type(mime)
        dialog.add_filter(image_filter)
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
            layer = ImageLayer(path=file.get_path())
            scene.layers.append(layer)
            self._layer_id = layer.id
            self.controller.config_changed("content")
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
            if file is None or file.get_path() is None or not isinstance(layer, ImageLayer):
                return
            layer.path = file.get_path()
            self.image_path.set_text(layer.path)
            self._changed("content")
        finally:
            dialog.destroy()

    def _delete_layer(self, *_args) -> None:
        scene = self.selected_scene()
        if scene is None or self._layer_id is None:
            return
        scene.layers[:] = [layer for layer in scene.layers if layer.id != self._layer_id]
        self._layer_id = None
        self.controller.config_changed("content")
        self._refresh_layers()
        self._refresh_properties()
        self._refresh_preview()

    def _move_layer(self, delta: int) -> None:
        scene = self.selected_scene()
        if scene is None or self._layer_id is None:
            return
        index = next((i for i, layer in enumerate(scene.layers) if layer.id == self._layer_id), None)
        if index is None:
            return
        new_index = max(0, min(len(scene.layers) - 1, index + delta))
        if new_index == index:
            return
        layer = scene.layers.pop(index)
        scene.layers.insert(new_index, layer)
        self.controller.config_changed("content")
        self._refresh_layers()
        self._refresh_preview()

    def _find_scene(self, scene_id: str | None) -> Scene | None:
        return next((scene for scene in self.controller.config.scenes if scene.id == scene_id), None)

    def _find_layer(self, layer_id: str | None):
        scene = self.selected_scene()
        if scene is None:
            return None
        return next((layer for layer in scene.layers if layer.id == layer_id), None)

    @staticmethod
    def _clear_listbox(listbox: Gtk.ListBox) -> None:
        child = listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt

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
        self.set_margin_top(24); self.set_margin_start(24); self.set_margin_end(24)

        intro = Gtk.Label(
            label="Flash length is measured in real display frames, not arbitrary milliseconds."
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

    def _attach(self, grid, row, label, widget):
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
        refreshes = [(m.connector, m.refresh_hz) for m in monitors if m.refresh_hz]
        if not refreshes:
            reference_hz = 60.0
            self.refresh_value.set_label("Not detected (60 Hz reference)")
            ms = cfg.visible_frames * 1000.0 / reference_hz
            cycles = cfg.break_ms * reference_hz / 1000.0
            self.hint.set_label(
                f"{cfg.visible_frames} frame(s) at 60 Hz ≈ {ms:.1f} ms visible. "
                f"A {cfg.break_ms / 1000.0:.1f} s break is ≈ {cycles:.0f} refresh cycles. "
                "The actual overlay uses the monitor frame clock when available."
            )
            return

        self.refresh_value.set_label(
            ", ".join(f"{connector}: {hz:.1f} Hz" for connector, hz in refreshes)
        )
        lines = []
        for connector, hz in refreshes:
            frame_ms = 1000.0 / hz
            visible_ms = cfg.visible_frames * frame_ms
            break_cycles = cfg.break_ms * hz / 1000.0
            lines.append(
                f"{connector}: 1 frame ≈ {frame_ms:.2f} ms; "
                f"{cfg.visible_frames} frame(s) ≈ {visible_ms:.1f} ms; "
                f"break ≈ {break_cycles:.0f} refresh cycles."
            )
        if len(refreshes) > 1:
            lines.append(
                "With mixed-refresh monitors the same frame count is applied independently "
                "to each monitor, so wall-clock flash length differs by refresh rate."
            )
        self.hint.set_label("\n".join(lines))

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        cfg = self.controller.config.schedule
        cfg.break_ms = max(100, round(self.break_seconds.get_value() * 1000))
        cfg.visible_frames = max(1, self.visible_frames.get_value_as_int())
        cfg.selection = "random" if self.selection.get_selected() == 0 else "sequential"
        self.controller.config_changed("timing")
        self.refresh()


class DisplaysPage(Gtk.Box):
    def __init__(self, controller) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.controller = controller
        self._loading = False
        self.set_margin_top(24); self.set_margin_start(24); self.set_margin_end(24)
        title = Gtk.Label(label="Show overlays on")
        title.add_css_class("heading"); title.set_xalign(0.0)
        self.append(title)
        self.all_radio = Gtk.CheckButton(label="All displays")
        self.selected_radio = Gtk.CheckButton(label="Selected displays")
        self.selected_radio.set_group(self.all_radio)
        self.all_radio.connect("toggled", self._mode_changed)
        self.selected_radio.connect("toggled", self._mode_changed)
        self.append(self.all_radio); self.append(self.selected_radio)
        self.monitor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
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
            nxt = child.get_next_sibling(); self.monitor_box.remove(child); child = nxt
        for info in self.controller.overlay.monitors():
            refresh = f", {info.refresh_hz:.1f} Hz" if info.refresh_hz else ""
            check = Gtk.CheckButton(label=f"{info.connector} — {info.description} — {info.width}×{info.height}, scale {info.scale_factor}×{refresh}")
            check.connector = info.connector
            check.set_active(info.connector in cfg.connectors)
            check.set_sensitive(cfg.mode == "selected")
            check.connect("toggled", self._connector_changed)
            self.monitor_box.append(check)
        self._loading = False

    def _mode_changed(self, *_args) -> None:
        if self._loading:
            return
        self.controller.config.display.mode = "all" if self.all_radio.get_active() else "selected"
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
        self.set_margin_top(24); self.set_margin_start(24); self.set_margin_end(24)
        self.start_on_launch = Gtk.CheckButton(label="Start flashing automatically when the app launches")
        self.autostart = Gtk.CheckButton(label="Launch Subliminal when I log in")
        self.start_on_launch.connect("toggled", self._changed)
        self.autostart.connect("toggled", self._changed)
        self.append(self.start_on_launch)
        self.append(self.autostart)
        version_label = Gtk.Label(label=f"Version: {__version__}")
        version_label.set_selectable(True); version_label.set_xalign(0.0); version_label.add_css_class("dim-label")
        self.append(version_label)
        cfg_label = Gtk.Label(label=f"Configuration: {self.controller.store.path}")
        cfg_label.set_selectable(True); cfg_label.set_xalign(0.0); cfg_label.add_css_class("dim-label")
        self.append(cfg_label)
        note = Gtk.Label(label="Closing the settings window hides it; the scheduler keeps running. Launch Subliminal again to reopen this window, or use Quit above to exit completely.")
        note.set_wrap(True); note.set_xalign(0.0); note.set_max_width_chars(80)
        self.append(note)

    def refresh(self) -> None:
        self._loading = True
        self.start_on_launch.set_active(self.controller.config.start_on_launch)
        self.autostart.set_active(self.controller.config.autostart)
        self._loading = False

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        self.controller.config.start_on_launch = self.start_on_launch.get_active()
        self.controller.config.autostart = self.autostart.get_active()
        self.controller.set_autostart(self.controller.config.autostart)
        self.controller.config_changed("settings")
