from __future__ import annotations

import logging
from dataclasses import dataclass

from .gtk_runtime import Gdk, GLib, Gtk, Pango
from .media import MediaAsset, MediaCache
from .model import ImageLayer, Layer, Scene, TextLayer, calculate_position

LOG = logging.getLogger(__name__)


class AnimatedPicture(Gtk.Picture):
    def __init__(self, asset: MediaAsset) -> None:
        super().__init__()
        self._asset = asset
        self._index = 0
        self._timer_id: int | None = None
        self.set_can_shrink(False)
        self.set_content_fit(Gtk.ContentFit.FILL)
        self.set_size_request(asset.width, asset.height)
        self.set_paintable(asset.frames[0])

    def start(self) -> None:
        self.stop()
        self._index = 0
        self.set_paintable(self._asset.frames[0])
        if self._asset.animated:
            self._schedule_next()

    def stop(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _schedule_next(self) -> None:
        delay = self._asset.durations_ms[self._index]
        self._timer_id = GLib.timeout_add(max(20, delay), self._advance)

    def _advance(self) -> bool:
        self._timer_id = None
        self._index = (self._index + 1) % len(self._asset.frames)
        self.set_paintable(self._asset.frames[self._index])
        self._schedule_next()
        return GLib.SOURCE_REMOVE


@dataclass(slots=True)
class RenderedLayer:
    model: Layer
    widget: Gtk.Widget


class SceneView(Gtk.Fixed):
    """Renders a Scene using actual GTK widgets; used by both overlay and preview."""

    def __init__(
        self,
        scene: Scene,
        media: MediaCache,
        *,
        scale: float = 1.0,
        preview: bool = False,
    ) -> None:
        super().__init__()
        self.scene = scene
        self.media = media
        self.scale = scale
        self.preview = preview
        self._layers: list[RenderedLayer] = []
        self._animations: list[AnimatedPicture] = []
        self._layout_pending = False
        self.add_css_class("subliminal-scene")
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.connect("notify::width", self._on_size_changed)
        self.connect("notify::height", self._on_size_changed)
        self._build()

    def start_animations(self) -> None:
        for animation in self._animations:
            animation.start()

    def stop_animations(self) -> None:
        for animation in self._animations:
            animation.stop()

    def _build(self) -> None:
        for layer in self.scene.layers:
            if not layer.enabled:
                continue
            try:
                widget = self._make_widget(layer)
            except Exception as exc:
                LOG.warning("Cannot render layer %s: %s", layer.id, exc)
                if not self.preview:
                    continue
                widget = Gtk.Label(label=f"⚠ {self._layer_label(layer)}")
                widget.add_css_class("preview-error")
            self.put(widget, 0.0, 0.0)
            self._layers.append(RenderedLayer(layer, widget))
        GLib.idle_add(self._relayout)

    def _make_widget(self, layer: Layer) -> Gtk.Widget:
        if isinstance(layer, TextLayer):
            return self._make_text(layer)
        return self._make_image(layer)

    def _make_text(self, layer: TextLayer) -> Gtk.Widget:
        label = Gtk.Label(label=layer.text)
        label.set_wrap(False)
        label.set_selectable(False)
        label.set_xalign(0.0)
        label.set_yalign(0.5)

        desc = Pango.FontDescription.new()
        desc.set_family(layer.font_family)
        desc.set_absolute_size(max(1, layer.font_size_px * self.scale) * Pango.SCALE)
        desc.set_weight(Pango.Weight.BOLD if layer.bold else Pango.Weight.NORMAL)
        desc.set_style(Pango.Style.ITALIC if layer.italic else Pango.Style.NORMAL)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_font_desc_new(desc))
        if layer.underline:
            attrs.insert(Pango.attr_underline_new(Pango.Underline.SINGLE))

        rgba = Gdk.RGBA()
        if not rgba.parse(layer.color):
            rgba.parse("#FFFFFFFF")
        attrs.insert(
            Pango.attr_foreground_new(
                round(rgba.red * 65535),
                round(rgba.green * 65535),
                round(rgba.blue * 65535),
            )
        )
        label.set_attributes(attrs)
        label.set_opacity(max(0.0, min(1.0, layer.opacity * rgba.alpha)))
        return label

    def _make_image(self, layer: ImageLayer) -> Gtk.Widget:
        if not layer.path:
            raise FileNotFoundError("No image selected")
        asset = self.media.load(layer, self.scale)
        picture = AnimatedPicture(asset)
        picture.set_opacity(max(0.0, min(1.0, layer.opacity)))
        if asset.animated:
            self._animations.append(picture)
        return picture

    def _on_size_changed(self, *_args) -> None:
        if not self._layout_pending:
            self._layout_pending = True
            GLib.idle_add(self._relayout)

    def _relayout(self) -> bool:
        self._layout_pending = False
        width = self.get_width()
        height = self.get_height()
        if width <= 1 or height <= 1:
            return GLib.SOURCE_REMOVE
        for rendered in self._layers:
            widget = rendered.widget
            _, natural_w, _, _ = widget.measure(Gtk.Orientation.HORIZONTAL, -1)
            _, natural_h, _, _ = widget.measure(Gtk.Orientation.VERTICAL, natural_w)
            item_w = max(1, natural_w)
            item_h = max(1, natural_h)
            x, y = calculate_position(
                rendered.model.position,
                width,
                height,
                item_w,
                item_h,
                self.scale,
            )
            self.move(widget, x, y)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _layer_label(layer: Layer) -> str:
        if isinstance(layer, TextLayer):
            return layer.text or "text"
        return layer.path or "image"
