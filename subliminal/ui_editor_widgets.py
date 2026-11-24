from __future__ import annotations

from .gtk_runtime import Gtk
from .model import ANCHORS


class EditorWidgetsMixin:
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
