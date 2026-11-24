from __future__ import annotations

from .gtk_runtime import Gtk, Pango
from .model import ANCHORS


class EditorWidgetsMixin:
    def _build_library(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_size_request(205, -1)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(8)

        title = Gtk.Label(label="Library")
        title.add_css_class("heading")
        title.set_xalign(0.0)
        box.append(title)

        self.library_scroll = Gtk.ScrolledWindow()
        self.library_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )
        self.library_scroll.set_overlay_scrolling(True)
        self.library_scroll.set_vexpand(True)
        self.library_list = Gtk.ListBox()
        self.library_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.library_list.connect("row-selected", self._on_library_selected)
        self.library_scroll.set_child(self.library_list)
        box.append(self.library_scroll)

        footer_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        box.append(footer_sep)

        self.library_name_label = Gtk.Label(label="Scene name")
        self.library_name_label.set_xalign(0.0)
        self.library_name_label.add_css_class("dim-label")
        box.append(self.library_name_label)

        self.library_name = Gtk.Entry()
        self.library_name.set_width_chars(8)
        self.library_name.set_max_width_chars(28)
        self.library_name.set_placeholder_text("Select a folder or scene")
        self.library_name.connect("changed", self._library_name_changed)
        box.append(self.library_name)

        row1 = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            homogeneous=True,
        )
        self.add_folder_button = Gtk.Button(label="+ Folder")
        self.add_scene_button = Gtk.Button(label="+ Scene")
        self.add_folder_button.connect("clicked", self._add_folder)
        self.add_scene_button.connect("clicked", self._add_scene)
        row1.append(self.add_folder_button)
        row1.append(self.add_scene_button)
        box.append(row1)

        row2 = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            homogeneous=True,
        )
        self.duplicate_scene_button = Gtk.Button(label="Duplicate")
        self.library_delete_button = Gtk.Button(label="Delete")
        self.duplicate_scene_button.connect("clicked", self._duplicate_scene)
        self.library_delete_button.connect("clicked", self._delete_library_item)
        row2.append(self.duplicate_scene_button)
        row2.append(self.library_delete_button)
        box.append(row2)
        return box

    def _build_canvas(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(8)
        box.set_margin_end(8)

        self.canvas_header = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
        )
        box.append(self.canvas_header)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.canvas_header.append(top_row)

        self.scene_label = Gtk.Label(label="Scene")
        self.scene_label.add_css_class("heading")
        self.scene_label.set_xalign(0.0)
        top_row.append(self.scene_label)

        self.scene_enabled = Gtk.CheckButton(label="Enabled")
        self.scene_enabled.connect("toggled", self._scene_enabled_changed)
        top_row.append(self.scene_enabled)

        header_spacer = Gtk.Box()
        header_spacer.set_hexpand(True)
        top_row.append(header_spacer)

        self.preview_info = Gtk.Label(label="Preview")
        self.preview_info.add_css_class("dim-label")
        self.preview_info.set_xalign(1.0)
        self.preview_info.set_ellipsize(Pango.EllipsizeMode.END)
        self.preview_info.set_max_width_chars(28)
        top_row.append(self.preview_info)

        folder_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.canvas_header.append(folder_row)

        self.folder_label = Gtk.Label(label="Folder")
        self.folder_label.add_css_class("dim-label")
        folder_row.append(self.folder_label)

        self._folder_model = Gtk.StringList.new(["Unfiled"])
        self.scene_folder = Gtk.DropDown(model=self._folder_model)
        self.scene_folder.connect("notify::selected", self._scene_folder_changed)
        self.scene_folder.set_hexpand(True)
        folder_row.append(self.scene_folder)

        self.reroll_button = Gtk.Button(label="Reroll")
        self.reroll_button.set_tooltip_text(
            "Choose a fresh preview for layers using random position. "
            "Random layers avoid other visible elements when space permits."
        )
        self.reroll_button.connect(
            "clicked",
            lambda *_: self._refresh_preview(),
        )
        folder_row.append(self.reroll_button)

        self.preview_aspect = Gtk.AspectFrame.new(0.5, 0.5, 16 / 9, False)
        self.preview_aspect.set_hexpand(True)
        self.preview_aspect.set_vexpand(True)
        self.preview_aspect.set_overflow(Gtk.Overflow.HIDDEN)
        box.append(self.preview_aspect)

        self.preview_frame = Gtk.Frame()
        self.preview_frame.add_css_class("preview-canvas")
        self.preview_frame.set_hexpand(True)
        self.preview_frame.set_vexpand(True)
        self.preview_frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.preview_frame.connect(
            "notify::width",
            self._on_preview_allocation_changed,
        )
        self.preview_frame.connect(
            "notify::height",
            self._on_preview_allocation_changed,
        )
        self.preview_aspect.set_child(self.preview_frame)
        return box

    def _build_inspector(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_size_request(322, -1)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(8)
        box.set_margin_end(10)

        title = Gtk.Label(label="Layers")
        title.add_css_class("heading")
        title.set_xalign(0.0)
        box.append(title)

        self.layer_scroll = Gtk.ScrolledWindow()
        self.layer_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )
        self.layer_scroll.set_overlay_scrolling(True)
        self.layer_scroll.set_min_content_height(44)
        self.layer_scroll.set_max_content_height(136)
        self.layer_scroll.set_propagate_natural_height(True)
        self.layer_list = Gtk.ListBox()
        self.layer_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.layer_list.connect("row-selected", self._on_layer_selected)
        self.layer_scroll.set_child(self.layer_list)
        box.append(self.layer_scroll)

        layer_actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
        )
        add_text = Gtk.Button(label="+ Text")
        add_image = Gtk.Button(label="+ Image")
        add_text.connect("clicked", self._add_text_layer)
        add_image.connect("clicked", self._choose_new_image)
        layer_actions.append(add_text)
        layer_actions.append(add_image)

        layer_action_spacer = Gtk.Box()
        layer_action_spacer.set_hexpand(True)
        layer_actions.append(layer_action_spacer)

        up = Gtk.Button.new_from_icon_name("go-up-symbolic")
        down = Gtk.Button.new_from_icon_name("go-down-symbolic")
        delete = Gtk.Button.new_from_icon_name("edit-delete-symbolic")
        up.set_tooltip_text("Move layer up")
        down.set_tooltip_text("Move layer down")
        delete.set_tooltip_text("Delete selected layer")
        up.connect("clicked", lambda *_: self._move_layer(-1))
        down.connect("clicked", lambda *_: self._move_layer(1))
        delete.connect("clicked", self._delete_layer)
        layer_actions.append(up)
        layer_actions.append(down)
        layer_actions.append(delete)
        box.append(layer_actions)

        prop_title = Gtk.Label(label="Properties")
        prop_title.add_css_class("heading")
        prop_title.set_xalign(0.0)
        box.append(prop_title)

        self.property_scroll = Gtk.ScrolledWindow()
        self.property_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )
        self.property_scroll.set_overlay_scrolling(True)
        self.property_scroll.set_vexpand(True)
        self.property_stack = Gtk.Stack()
        self.property_stack.set_hhomogeneous(False)
        self.property_stack.set_vhomogeneous(False)
        self.property_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.property_stack.add_named(
            Gtk.Label(label="Select a layer to edit it."),
            "empty",
        )
        self.text_props = self._build_text_properties()
        self.image_props = self._build_image_properties()
        self.property_stack.add_named(self.text_props, "text")
        self.property_stack.add_named(self.image_props, "image")
        self.property_scroll.set_child(self.property_stack)
        box.append(self.property_scroll)
        return box

    def _build_text_properties(self) -> Gtk.Widget:
        box = self._property_box()

        self.text_name = Gtk.Entry()
        self.text_name.set_width_chars(8)
        self.text_name.set_max_width_chars(28)
        self.text_name.connect("changed", self._update_text_name)
        self.text_enabled = Gtk.CheckButton(label="Enabled")
        self.text_enabled.connect("toggled", self._update_text)
        box.append(
            self._name_enabled_row(
                "Name",
                self.text_name,
                self.text_enabled,
            )
        )

        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_left_margin(4)
        self.text_view.set_right_margin(4)
        text_scroll = Gtk.ScrolledWindow()
        text_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )
        text_scroll.set_overlay_scrolling(True)
        text_scroll.set_min_content_height(64)
        text_scroll.set_max_content_height(96)
        text_scroll.set_propagate_natural_height(True)
        text_scroll.set_child(self.text_view)
        self.text_view.get_buffer().connect("changed", self._update_text)
        box.append(self._labeled_field("Text", text_scroll))

        box.append(self._section_title("Text style"))

        self.font_dialog = Gtk.FontDialog.new()
        self.font_dialog.set_title("Choose font")
        self._selected_font_family = "Sans"
        self.font_button = Gtk.Button(label="Sans")
        self.font_button.set_tooltip_text("Choose font family")
        self.font_button.connect("clicked", self._choose_font_family)

        self.font_size = Gtk.SpinButton.new_with_range(1, 500, 1)
        self.font_size.set_width_chars(5)
        self.font_size.connect("value-changed", self._update_text)
        box.append(
            self._paired_fields(
                "Font",
                self.font_button,
                "Size (px)",
                self.font_size,
            )
        )

        style_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.bold = Gtk.ToggleButton(label="B")
        self.italic = Gtk.ToggleButton(label="I")
        self.underline = Gtk.ToggleButton(label="U")
        for button in (self.bold, self.italic, self.underline):
            button.connect("toggled", self._update_text)
            style_box.append(button)

        self.text_alignment = Gtk.DropDown.new_from_strings(
            ["Left", "Center", "Right"]
        )
        self.text_alignment.connect("notify::selected", self._update_text)
        box.append(
            self._paired_fields(
                "Style",
                style_box,
                "Alignment",
                self.text_alignment,
            )
        )

        self.color = Gtk.ColorButton()
        self.color.set_use_alpha(True)
        self.color.connect("color-set", self._update_text)
        self.text_opacity = self._opacity_scale(self._update_text)
        box.append(
            self._paired_fields(
                "Color",
                self.color,
                "Opacity (%)",
                self.text_opacity,
            )
        )

        self.text_background_enabled = Gtk.CheckButton(
            label="Colored background"
        )
        self.text_background_enabled.connect(
            "toggled",
            self._on_text_background_toggled,
        )
        self.text_background_enabled.set_margin_top(4)
        box.append(self.text_background_enabled)

        self.text_background_color = Gtk.ColorButton()
        self.text_background_color.set_use_alpha(True)
        self.text_background_color.connect("color-set", self._update_text)
        self.text_background_padding = Gtk.SpinButton.new_with_range(
            0,
            500,
            1,
        )
        self.text_background_padding.set_width_chars(5)
        self.text_background_padding.connect(
            "value-changed",
            self._update_text,
        )
        background_fields = self._paired_fields(
            "Color",
            self.text_background_color,
            "Padding (px)",
            self.text_background_padding,
        )
        self.text_background_revealer = Gtk.Revealer()
        self.text_background_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self.text_background_revealer.set_transition_duration(120)
        self.text_background_revealer.set_child(background_fields)
        box.append(self.text_background_revealer)

        self.text_pos = self._position_controls(box, self._update_text)
        return box

    def _build_image_properties(self) -> Gtk.Widget:
        box = self._property_box()

        self.image_name = Gtk.Entry()
        self.image_name.set_width_chars(8)
        self.image_name.set_max_width_chars(28)
        self.image_name.connect("changed", self._update_image_name)
        self.image_enabled = Gtk.CheckButton(label="Enabled")
        self.image_enabled.connect("toggled", self._update_image)
        box.append(
            self._name_enabled_row(
                "Name",
                self.image_name,
                self.image_enabled,
            )
        )

        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.image_path = Gtk.Entry()
        self.image_path.set_editable(False)
        self.image_path.set_width_chars(1)
        self.image_path.set_max_width_chars(1)
        self.image_path.set_hexpand(True)
        self.image_path.set_tooltip_text("Image file")
        choose = Gtk.Button(label="Choose…")
        choose.connect("clicked", self._choose_existing_image)
        file_box.append(self.image_path)
        file_box.append(choose)
        box.append(self._labeled_field("File", file_box))

        box.append(self._section_title("Image"))

        self.image_width = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.image_height = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.image_width.set_width_chars(6)
        self.image_height.set_width_chars(6)
        self.auto_width = Gtk.CheckButton(label="Auto")
        self.auto_height = Gtk.CheckButton(label="Auto")
        self.image_width.connect("value-changed", self._update_image)
        self.image_height.connect("value-changed", self._update_image)
        self.auto_width.connect("toggled", self._on_auto_size_toggled)
        self.auto_height.connect("toggled", self._on_auto_size_toggled)

        dimensions = Gtk.Grid(column_spacing=8, row_spacing=6)
        dimensions.set_hexpand(True)

        width_label = self._field_label("Width")
        height_label = self._field_label("Height")
        width_label.set_valign(Gtk.Align.CENTER)
        height_label.set_valign(Gtk.Align.CENTER)
        dimensions.attach(width_label, 0, 0, 1, 1)
        dimensions.attach(height_label, 0, 1, 1, 1)

        self.image_width.set_hexpand(True)
        self.image_height.set_hexpand(True)
        dimensions.attach(self.image_width, 1, 0, 1, 1)
        dimensions.attach(self.image_height, 1, 1, 1, 1)
        dimensions.attach(self.auto_width, 2, 0, 1, 1)
        dimensions.attach(self.auto_height, 2, 1, 1, 1)

        box.append(self._labeled_field("Dimensions (px)", dimensions))

        self.keep_aspect = Gtk.CheckButton(label="Keep aspect ratio")
        self.keep_aspect.connect("toggled", self._update_image)
        box.append(self.keep_aspect)

        self.image_opacity = self._opacity_scale(self._update_image)
        box.append(self._labeled_field("Opacity (%)", self.image_opacity))

        self.image_pos = self._position_controls(box, self._update_image)
        return box

    @staticmethod
    def _property_box() -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_hexpand(True)
        box.set_margin_end(6)
        box.set_margin_bottom(10)
        return box

    @staticmethod
    def _section_title(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.add_css_class("heading")
        label.set_xalign(0.0)
        label.set_margin_top(4)
        return label

    @staticmethod
    def _field_label(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.add_css_class("dim-label")
        label.set_xalign(0.0)
        return label

    @classmethod
    def _labeled_field(cls, label_text: str, widget: Gtk.Widget) -> Gtk.Box:
        field = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        field.set_hexpand(True)
        field.append(cls._field_label(label_text))
        widget.set_hexpand(True)
        field.append(widget)
        return field

    @classmethod
    def _paired_fields(
        cls,
        left_label: str,
        left_widget: Gtk.Widget,
        right_label: str,
        right_widget: Gtk.Widget,
    ) -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=8, row_spacing=3)
        grid.set_column_homogeneous(False)
        grid.set_hexpand(True)

        left_lab = cls._field_label(left_label)
        right_lab = cls._field_label(right_label)
        grid.attach(left_lab, 0, 0, 1, 1)
        grid.attach(right_lab, 1, 0, 1, 1)

        left_widget.set_hexpand(True)
        right_widget.set_hexpand(True)
        grid.attach(left_widget, 0, 1, 1, 1)
        grid.attach(right_widget, 1, 1, 1, 1)
        return grid

    @classmethod
    def _name_enabled_row(
        cls,
        label_text: str,
        entry: Gtk.Entry,
        enabled: Gtk.CheckButton,
    ) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        field = cls._labeled_field(label_text, entry)
        field.set_hexpand(True)
        row.append(field)
        enabled.set_valign(Gtk.Align.END)
        enabled.set_margin_bottom(4)
        row.append(enabled)
        return row

    @staticmethod
    def _opacity_scale(callback) -> Gtk.Scale:
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        scale.connect("value-changed", callback)
        return scale

    def _position_controls(self, box: Gtk.Box, callback) -> dict:
        position_header = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
        )
        position_title = self._section_title("Position")
        position_header.append(position_title)
        position_spacer = Gtk.Box()
        position_spacer.set_hexpand(True)
        position_header.append(position_spacer)

        randomize = Gtk.CheckButton(label="Random each flash")
        randomize.set_tooltip_text(
            "Choose a new on-screen position for this layer on every flash. "
            "Random layers avoid other visible elements when space permits."
        )
        randomize.set_valign(Gtk.Align.CENTER)
        position_header.append(randomize)
        box.append(position_header)

        anchor = Gtk.DropDown.new_from_strings(list(ANCHORS))
        anchor.connect("notify::selected", callback)
        box.append(self._labeled_field("Anchor", anchor))

        x = Gtk.SpinButton.new_with_range(0, 100, 0.1)
        y = Gtk.SpinButton.new_with_range(0, 100, 0.1)
        x.set_width_chars(6)
        y.set_width_chars(6)
        x.connect("value-changed", callback)
        y.connect("value-changed", callback)
        box.append(self._paired_fields("X (%)", x, "Y (%)", y))

        ox = Gtk.SpinButton.new_with_range(-10000, 10000, 1)
        oy = Gtk.SpinButton.new_with_range(-10000, 10000, 1)
        ox.set_width_chars(6)
        oy.set_width_chars(6)
        ox.connect("value-changed", callback)
        oy.connect("value-changed", callback)
        box.append(
            self._paired_fields(
                "X offset (px)",
                ox,
                "Y offset (px)",
                oy,
            )
        )

        controls = {
            "random": randomize,
            "anchor": anchor,
            "x": x,
            "y": y,
            "ox": ox,
            "oy": oy,
        }

        def on_random_toggled(button):
            self._set_fixed_position_sensitive(
                controls,
                not button.get_active(),
            )
            callback(button)

        randomize.connect("toggled", on_random_toggled)
        return controls

    @staticmethod
    def _set_fixed_position_sensitive(controls: dict, sensitive: bool) -> None:
        for key in ("anchor", "x", "y", "ox", "oy"):
            controls[key].set_sensitive(sensitive)

    @staticmethod
    def _short_name(value: str, limit: int = 32) -> str:
        clean = value.replace("\n", " ").strip()
        if len(clean) <= limit:
            return clean
        return clean[: max(1, limit - 1)].rstrip() + "…"
