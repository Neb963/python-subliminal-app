from __future__ import annotations

import copy
from pathlib import Path

from .gtk_runtime import Gdk, GLib, Gtk, Pango
from .model import (
    ANCHORS,
    SUPPORTED_IMAGE_EXTENSIONS,
    Folder,
    ImageLayer,
    Scene,
    TextLayer,
    new_id,
)
from .render import SceneView
from .ui_editor_widgets import EditorWidgetsMixin


class EditorPage(Gtk.Box, EditorWidgetsMixin):
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
        self._preview_last_size: tuple[int, int] | None = None
        self._preview_used_fallback_scale = False
        self._active_dialog = None
        self.connect("unmap", self._on_unmap)

        self._pane_positions_initialized = False

        self.outer_paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self.outer_paned.set_hexpand(True)
        self.outer_paned.set_vexpand(True)
        self.append(self.outer_paned)

        self.library_panel = self._build_library()
        self.outer_paned.set_start_child(self.library_panel)
        self.outer_paned.set_resize_start_child(False)
        self.outer_paned.set_shrink_start_child(False)

        self.right_paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self.outer_paned.set_end_child(self.right_paned)
        self.outer_paned.set_resize_end_child(True)
        self.outer_paned.set_shrink_end_child(False)

        self.canvas_panel = self._build_canvas()
        self.inspector_panel = self._build_inspector()
        self.right_paned.set_start_child(self.canvas_panel)
        self.right_paned.set_end_child(self.inspector_panel)
        self.right_paned.set_resize_start_child(True)
        self.right_paned.set_shrink_start_child(False)
        self.right_paned.set_resize_end_child(False)
        self.right_paned.set_shrink_end_child(False)

        self.connect("map", self._on_editor_allocation_ready)

    def _on_preview_base_resized(self, _area, _width: int, _height: int) -> None:
        if not self._pane_positions_initialized:
            self._on_editor_allocation_ready()
        self._on_preview_allocation_changed()

    def _on_editor_allocation_ready(self, *_args) -> None:
        if self._pane_positions_initialized:
            return
        right_width = self.right_paned.get_width()
        if right_width < 400:
            return
        self.outer_paned.set_position(220)
        self.right_paned.set_position(max(320, right_width - 340))
        self._pane_positions_initialized = True

    @property
    def _loading(self) -> bool:
        return self._sync_depth > 0

    @_loading.setter
    def _loading(self, value: bool) -> None:
        if value:
            self._sync_depth += 1
        else:
            self._sync_depth = max(0, self._sync_depth - 1)

    def pause_preview(self) -> None:
        if self._preview_view is not None:
            self._preview_view.stop_animations()

    def resume_preview(self) -> None:
        if self._preview_view is not None:
            self._preview_view.start_animations()

    def _on_unmap(self, *_args) -> None:
        for attr in (
            "_library_refresh_id",
            "_folder_model_refresh_id",
            "_preview_refresh_id",
        ):
            source_id = getattr(self, attr)
            if source_id is not None:
                GLib.source_remove(source_id)
                setattr(self, attr, None)
        self.pause_preview()

    @classmethod
    def _set_ellipsized_label(
        cls,
        label: Gtk.Label,
        value: str,
        *,
        max_chars: int,
    ) -> None:
        label.set_label(value)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(max_chars)
        label.set_tooltip_text(value if value else None)

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
        label = Gtk.Label()
        self._set_ellipsized_label(
            label,
            f"▾  {folder.name}",
            max_chars=28,
        )
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
        label = Gtk.Label()
        EditorPage._set_ellipsized_label(
            label,
            scene.name,
            max_chars=28,
        )
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
                self.library_name_label.set_label("Scene name")
                self.library_name.set_text(scene.name)
                self.library_name.set_sensitive(True)
                self.duplicate_scene_button.set_sensitive(True)
                self.library_delete_button.set_sensitive(True)
                self.library_delete_button.set_tooltip_text(
                    "Delete the selected scene"
                )
            elif folder is not None:
                self.library_name_label.set_label("Folder name")
                self.library_name.set_text(folder.name)
                self.library_name.set_sensitive(True)
                self.duplicate_scene_button.set_sensitive(False)
                self.library_delete_button.set_sensitive(True)
                self.library_delete_button.set_tooltip_text(
                    "Delete this folder and move its scenes to Unfiled"
                )
            else:
                self.library_name_label.set_label("Selection")
                self.library_name.set_text("")
                self.library_name.set_sensitive(False)
                self.duplicate_scene_button.set_sensitive(False)
                self.library_delete_button.set_sensitive(False)
                self.library_delete_button.set_tooltip_text(None)
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
                    self._set_ellipsized_label(
                        label,
                        scene.name,
                        max_chars=28,
                    )
            elif getattr(row, "row_kind", None) == "folder":
                folder = self._find_folder(getattr(row, "folder_id", None))
                if folder is not None:
                    self._set_ellipsized_label(
                        label,
                        f"▾  {folder.name}",
                        max_chars=28,
                    )

    def _refresh_folder_dropdown(self) -> None:
        self._folder_choices = [None] + [
            folder.id for folder in self.controller.config.folders
        ]
        labels = ["Unfiled"] + [
            self._short_name(folder.name, 32)
            for folder in self.controller.config.folders
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
            folder = self._find_folder(scene.folder_id)
            self.scene_folder.set_tooltip_text(
                folder.name if folder is not None else "Unfiled"
            )
        finally:
            self._loading = False

    def _scene_enabled_changed(self, button) -> None:
        if self._loading:
            return
        scene = self.selected_scene()
        if scene is None:
            return
        scene.enabled = button.get_active()
        self.controller.config_changed("metadata")

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
                label = Gtk.Label()
                self._set_ellipsized_label(
                    label,
                    f"{prefix}  {layer.name}",
                    max_chars=38,
                )
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
                self._set_font_family_selection(
                    layer.font_family,
                    update_model=False,
                )
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
                self.image_path.set_tooltip_text(layer.path or "No image selected")
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
        selected_anchor = controls["anchor"].get_selected()
        position.anchor = (
            ANCHORS[selected_anchor]
            if 0 <= selected_anchor < len(ANCHORS)
            else "center"
        )
        position.x = controls["x"].get_value() / 100.0
        position.y = controls["y"].get_value() / 100.0
        position.offset_x = controls["ox"].get_value_as_int()
        position.offset_y = controls["oy"].get_value_as_int()

    def _choose_font_family(self, *_args) -> None:
        origin_scene_id = self._scene_id
        origin_layer_id = self._layer_id
        if origin_scene_id is None or origin_layer_id is None:
            return
        parent = self.get_root()
        if not isinstance(parent, Gtk.Window):
            parent = None
        self.font_dialog.choose_family(
            parent,
            None,
            None,
            lambda dialog, result: self._on_font_family_chosen(
                dialog, result, origin_scene_id, origin_layer_id
            ),
        )

    def _on_font_family_chosen(
        self,
        dialog,
        result,
        origin_scene_id: str | None = None,
        origin_layer_id: str | None = None,
    ) -> None:
        try:
            family = dialog.choose_family_finish(result)
        except GLib.Error:
            # Dismissal/cancellation is a normal dialog outcome.
            return
        if family is None:
            return
        value = (family.get_name() or "Sans").strip() or "Sans"
        if origin_scene_id is None or (
            origin_scene_id == self._scene_id
            and origin_layer_id == self._layer_id
        ):
            self._set_font_family_selection(value, update_model=True)
            return
        scene = self._find_scene(origin_scene_id)
        if scene is None:
            return
        layer = next(
            (item for item in scene.layers if item.id == origin_layer_id),
            None,
        )
        if not isinstance(layer, TextLayer):
            return
        layer.font_family = value
        self.controller.config_changed("visual", scene.id)
        if self._scene_id == scene.id:
            self._request_preview_refresh()

    def _set_font_family_selection(
        self,
        family: str,
        *,
        update_model: bool,
    ) -> None:
        value = (family or "Sans").strip() or "Sans"
        self._selected_font_family = value
        self.font_button.set_label(self._short_name(value, 28))
        self.font_button.set_tooltip_text(value)
        if update_model and not self._loading:
            self._update_text()

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
        layer.font_family = self._selected_font_family or "Sans"
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
        self.text_background_revealer.set_reveal_child(enabled)
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
        self.controller.config_changed("visual", self._scene_id)
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
            self._set_ellipsized_label(
                child,
                f"{prefix}  {layer.name}",
                max_chars=38,
            )

    def _on_auto_size_toggled(self, *_args) -> None:
        self.image_width.set_sensitive(not self.auto_width.get_active())
        self.image_height.set_sensitive(not self.auto_height.get_active())
        self._update_image()

    def refresh_preview_context(self) -> None:
        self._request_preview_refresh(0)

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

    def _on_preview_allocation_changed(self, *_args) -> None:
        width = self.preview_frame.get_width()
        height = self.preview_frame.get_height()
        if width < 40 or height < 40:
            return
        size = (width, height)
        if self._preview_last_size is None:
            self._preview_last_size = size
            if self._preview_used_fallback_scale:
                self._request_preview_refresh(0)
            return
        if (
            abs(size[0] - self._preview_last_size[0]) >= 4
            or abs(size[1] - self._preview_last_size[1]) >= 4
        ):
            self._preview_last_size = size
            self._request_preview_refresh(100)

    def _preview_target_monitor(self):
        monitors = self.controller.overlay.monitors()
        if not monitors:
            return None
        display = self.controller.config.display
        if display.mode == "selected" and display.connectors:
            wanted = set(display.connectors)
            for monitor in monitors:
                if monitor.connector in wanted:
                    return monitor
        return monitors[0]

    def _refresh_preview(self) -> None:
        scene = self.selected_scene()
        if scene is None:
            if self._preview_view is not None:
                self._preview_view.stop_animations()
                self._preview_view = None
            self.preview_info.set_label("Preview")
            self.preview_frame.set_child(Gtk.Label(label="Select a scene"))
            return

        monitor = self._preview_target_monitor()
        if monitor is None:
            target_width, target_height = 1920, 1080
            preview_name = f"Preview · {target_width}×{target_height}"
        else:
            target_width = max(1, int(monitor.width))
            target_height = max(1, int(monitor.height))
            preview_name = (
                f"Preview · {monitor.connector} · "
                f"{target_width}×{target_height}"
            )

        self.preview_info.set_label(preview_name)
        self.preview_info.set_tooltip_text(preview_name)
        self.preview_aspect.set_ratio(target_width / target_height)

        preview_width = self.preview_frame.get_width()
        preview_height = self.preview_frame.get_height()
        if preview_width > 10 and preview_height > 10:
            inner_width = max(1, preview_width - 2)
            inner_height = max(1, preview_height - 2)
            preview_scale = min(
                1.0,
                inner_width / target_width,
                inner_height / target_height,
            )
            self._preview_used_fallback_scale = False
        else:
            preview_scale = min(1.0, 0.33)
            self._preview_used_fallback_scale = True

        view = SceneView(
            scene,
            self.controller.overlay.media,
            scale=max(0.01, preview_scale),
            preview=True,
            render_limit=(target_width, target_height),
        )
        view._base.connect("resize", self._on_preview_base_resized)
        old_view = self._preview_view
        self._preview_view = view
        self.preview_frame.set_child(view)
        if preview_width > 10 and preview_height > 10:
            view.reapply_flash_layout(max(1, preview_width - 2), max(1, preview_height - 2))
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
        self.controller.config_changed("structural", scene.id)
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
        self.controller.config_changed("structural", duplicate.id)
        self.refresh()

    def _delete_library_item(self, *_args) -> None:
        scene = self.selected_scene()
        folder = self._find_folder(self._folder_id)

        if scene is not None:
            if len(self.controller.config.scenes) <= 1:
                self.controller.warn("At least one scene must remain.")
                return
            deleted_scene_id = scene.id
            self.controller.config.scenes[:] = [
                item for item in self.controller.config.scenes
                if item.id != deleted_scene_id
            ]
            self._scene_id = None
            self._layer_id = None
            self.controller.config_changed("structural", deleted_scene_id)
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
        self.controller.config_changed("structural", scene.id)
        self._refresh_layers()
        self._refresh_preview()

    def _choose_new_image(self, *_args) -> None:
        origin_scene_id = self._scene_id
        if origin_scene_id is None:
            return
        self._open_image_dialog(
            lambda dialog, response: self._new_image_chosen(
                dialog, response, origin_scene_id
            )
        )

    def _choose_existing_image(self, *_args) -> None:
        origin_scene_id = self._scene_id
        origin_layer_id = self._layer_id
        if origin_scene_id is None or origin_layer_id is None:
            return
        self._open_image_dialog(
            lambda dialog, response: self._existing_image_chosen(
                dialog, response, origin_scene_id, origin_layer_id
            )
        )

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
        self._active_dialog = dialog
        dialog.show()

    def _validate_image_path(self, path: str) -> bool:
        suffix = Path(path).suffix.lower()
        if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
            self.controller.warn(
                f"Unsupported image format '{Path(path).name}'. Supported formats: {supported}."
            )
            return False
        return True

    def _new_image_chosen(
        self,
        dialog,
        response,
        origin_scene_id: str | None = None,
    ) -> None:
        try:
            if response != Gtk.ResponseType.ACCEPT:
                return
            file = dialog.get_file()
            if file is None or file.get_path() is None:
                return
            scene = self._find_scene(origin_scene_id or self._scene_id)
            if scene is None:
                return
            path = file.get_path()
            if not self._validate_image_path(path):
                return
            layer = ImageLayer(
                name=Path(path).name,
                path=path,
            )
            scene.layers.append(layer)
            self.controller.config_changed("structural", scene.id)
            if self._scene_id == scene.id:
                self._layer_id = layer.id
                self._refresh_layers()
                self._refresh_preview()
        finally:
            if self._active_dialog is dialog:
                self._active_dialog = None
            dialog.destroy()

    def _existing_image_chosen(
        self,
        dialog,
        response,
        origin_scene_id: str | None = None,
        origin_layer_id: str | None = None,
    ) -> None:
        try:
            if response != Gtk.ResponseType.ACCEPT:
                return
            file = dialog.get_file()
            scene = self._find_scene(origin_scene_id or self._scene_id)
            if file is None or file.get_path() is None or scene is None:
                return
            target_layer_id = origin_layer_id or self._layer_id
            layer = next(
                (item for item in scene.layers if item.id == target_layer_id),
                None,
            )
            if not isinstance(layer, ImageLayer):
                return
            path = file.get_path()
            if not self._validate_image_path(path):
                return
            layer.path = path
            self.controller.config_changed("visual", scene.id)
            if self._scene_id == scene.id:
                if self._layer_id == layer.id:
                    self.image_path.set_text(layer.path)
                    self.image_path.set_tooltip_text(layer.path)
                    self._refresh_layer_label()
                self._request_preview_refresh()
        finally:
            if self._active_dialog is dialog:
                self._active_dialog = None
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
        self.controller.config_changed("structural", scene.id)
        self._refresh_layers()
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
        self.controller.config_changed("structural", scene.id)
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
