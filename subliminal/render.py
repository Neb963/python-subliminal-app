from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from .gtk_runtime import Gdk, GLib, Gtk, Pango
from .layout import (
    RectTuple,
    choose_random_position,
    fit_dimensions,
    fixed_top_left,
    rect_within_bounds,
    safe_rect,
)
from .media import MediaAsset, MediaCache
from .model import ImageLayer, Layer, Scene, TextLayer

LOG = logging.getLogger(__name__)

RANDOM_CANDIDATES = 64
RANDOM_SPACING_PX = 16.0
SAFE_MARGIN_PX = 12.0


class AnimatedPicture(Gtk.Picture):
    def __init__(self, asset: MediaAsset) -> None:
        super().__init__()
        self._asset = asset
        self._index = 0
        self._timer_id: int | None = None
        self._effective_size = (float(asset.width), float(asset.height))
        self.set_can_shrink(True)
        self.set_content_fit(Gtk.ContentFit.FILL)
        self.set_size_request(asset.width, asset.height)
        self.set_paintable(asset.frames[0])

    def fit_to(
        self,
        max_width: float,
        max_height: float,
        *,
        preserve_aspect: bool,
    ) -> tuple[float, float]:
        bounds = safe_rect(max_width, max_height, 0)
        width, height, _ = fit_dimensions(
            self._asset.width,
            self._asset.height,
            bounds,
            preserve_aspect=preserve_aspect,
        )
        self._effective_size = (width, height)
        self.set_size_request(max(1, round(width)), max(1, round(height)))
        return self._effective_size

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


class TextLayerWidget(Gtk.Box):
    """Gtk.Label-based text rendering with an optional padded background."""

    def __init__(self, layer: TextLayer, scale: float) -> None:
        super().__init__()
        self.layer = layer
        self.scale = max(0.01, float(scale))
        self.label = Gtk.Label(label=layer.text)
        self.label.set_wrap(False)
        self.label.set_selectable(False)
        self.label.set_yalign(0.5)
        self.append(self.label)
        self._css_provider: Gtk.CssProvider | None = None
        self._effective_font_px = max(0.1, layer.font_size_px * self.scale)
        self._effective_padding = 0
        self._apply_alignment()
        self._apply_colors()
        self._set_effective_padding(
            layer.background_padding_px * self.scale
            if layer.background_enabled
            else 0.0
        )
        self._apply_font(self._effective_font_px)
        self.set_opacity(max(0.0, min(1.0, layer.opacity)))

    def fit_to(self, max_width: float, max_height: float) -> tuple[float, float]:
        max_width = max(1.0, float(max_width))
        max_height = max(1.0, float(max_height))

        # Padding is part of the layer's outer bounds. Cap pathological padding
        # before text fitting so it can never make the layer larger than the screen.
        requested_padding = (
            self.layer.background_padding_px * self.scale
            if self.layer.background_enabled
            else 0.0
        )
        max_padding = max(
            0.0,
            min((max_width - 1.0) / 2.0, (max_height - 1.0) / 2.0),
        )
        self._set_effective_padding(min(requested_padding, max_padding))

        base_px = max(0.1, self.layer.font_size_px * self.scale)
        self.label.set_wrap(False)
        self.label.set_max_width_chars(-1)
        self._apply_font(base_px)
        width, height = self._measure()

        if width <= max_width and height <= max_height:
            return width, height

        # Text dimensions scale almost linearly with absolute Pango font size.
        # Apply a direct estimate first, then tighten iteratively for rounding,
        # hinting, emoji fallback, and font-specific extents.
        ratio = min(max_width / width, max_height / height, 1.0)
        effective_px = max(0.1, base_px * ratio * 0.985)
        self._apply_font(effective_px)

        for _ in range(12):
            width, height = self._measure()
            if width <= max_width + 0.01 and height <= max_height + 0.01:
                return width, height
            correction = min(max_width / width, max_height / height, 0.98)
            effective_px = max(0.05, effective_px * correction * 0.985)
            self._apply_font(effective_px)

        # Truly extreme text (for example megabytes of glyphs) has no physically
        # lossless representation on a finite display. Keep shrinking below one
        # logical pixel rather than letting GTK place the widget off-screen.
        width, height = self._measure()
        if width > max_width or height > max_height:
            correction = min(max_width / width, max_height / height, 1.0)
            self._apply_font(max(0.01, effective_px * correction))
            width, height = self._measure()

        return min(width, max_width), min(height, max_height)

    def _apply_font(self, pixel_size: float) -> None:
        self._effective_font_px = max(0.01, pixel_size)
        desc = Pango.FontDescription.new()
        desc.set_family(self.layer.font_family)
        desc.set_absolute_size(
            max(1, round(self._effective_font_px * Pango.SCALE))
        )
        desc.set_weight(
            Pango.Weight.BOLD if self.layer.bold else Pango.Weight.NORMAL
        )
        desc.set_style(
            Pango.Style.ITALIC if self.layer.italic else Pango.Style.NORMAL
        )

        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_font_desc_new(desc))
        if self.layer.underline:
            attrs.insert(Pango.attr_underline_new(Pango.Underline.SINGLE))

        foreground = _parse_rgba(self.layer.color, "#FFFFFFFF")
        attrs.insert(
            Pango.attr_foreground_new(
                round(foreground.red * 65535),
                round(foreground.green * 65535),
                round(foreground.blue * 65535),
            )
        )
        try:
            attrs.insert(
                Pango.attr_foreground_alpha_new(round(foreground.alpha * 65535))
            )
            self.label.set_opacity(1.0)
        except AttributeError:
            # Older Pango introspection fallback.
            self.label.set_opacity(foreground.alpha)

        self.label.set_attributes(attrs)

    def _apply_alignment(self) -> None:
        mapping = {
            "left": (Gtk.Justification.LEFT, 0.0),
            "center": (Gtk.Justification.CENTER, 0.5),
            "right": (Gtk.Justification.RIGHT, 1.0),
        }
        justification, xalign = mapping.get(
            self.layer.alignment,
            mapping["left"],
        )
        self.label.set_justify(justification)
        self.label.set_xalign(xalign)

    def _apply_colors(self) -> None:
        background = _parse_rgba(
            self.layer.background_color,
            "#00000099",
        )
        alpha = background.alpha if self.layer.background_enabled else 0.0
        css = (
            "box {"
            f"background-color: rgba({round(background.red * 255)},"
            f"{round(background.green * 255)},"
            f"{round(background.blue * 255)},{alpha:.6f});"
            "}"
        )
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        self.get_style_context().add_provider(
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self._css_provider = provider

    def _set_effective_padding(self, padding: float) -> None:
        value = max(0, round(padding))
        self._effective_padding = value
        self.label.set_margin_start(value)
        self.label.set_margin_end(value)
        self.label.set_margin_top(value)
        self.label.set_margin_bottom(value)

    def _measure(self) -> tuple[float, float]:
        _, natural_w, _, _ = self.measure(Gtk.Orientation.HORIZONTAL, -1)
        _, natural_h, _, _ = self.measure(
            Gtk.Orientation.VERTICAL,
            max(1, natural_w),
        )
        return max(1.0, float(natural_w)), max(1.0, float(natural_h))


@dataclass(slots=True)
class RenderedLayer:
    model: Layer
    widget: Gtk.Widget


class SceneView(Gtk.Fixed):
    """Renders one scene with strict safe-screen placement."""

    def __init__(
        self,
        scene: Scene,
        media: MediaCache,
        *,
        scale: float = 1.0,
        preview: bool = False,
        render_limit: tuple[int, int] | None = None,
    ) -> None:
        super().__init__()
        self.scene = scene
        self.media = media
        self.scale = max(0.01, float(scale))
        self.preview = preview
        self.render_limit = render_limit
        self._layers: list[RenderedLayer] = []
        self._animations: list[AnimatedPicture] = []
        self._layout_pending = False
        self._rng = random.Random()
        self._random_candidates: dict[str, list[tuple[float, float]]] = {}

        self.add_css_class("subliminal-scene")
        self.set_hexpand(True)
        self.set_vexpand(True)
        # Children are initially inserted at (0, 0). Never expose that temporary
        # state: reveal only after a complete valid layout has been applied.
        self.set_opacity(0.0)
        self.connect("notify::width", self._on_size_changed)
        self.connect("notify::height", self._on_size_changed)
        self._build()

    def prepare_flash(self, width: float, height: float) -> None:
        self._reroll_random_candidates()
        self._layout_for_bounds(width, height)

    def reapply_flash_layout(self, width: float, height: float) -> None:
        self._layout_for_bounds(width, height)

    def start_animations(self) -> None:
        for animation in self._animations:
            animation.start()

    def stop_animations(self) -> None:
        for animation in self._animations:
            animation.stop()

    def _reroll_random_candidates(self) -> None:
        self._random_candidates = {
            rendered.model.id: [
                (self._rng.random(), self._rng.random())
                for _ in range(RANDOM_CANDIDATES)
            ]
            for rendered in self._layers
            if rendered.model.position.randomize
        }

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
                widget = Gtk.Label(label=f"⚠ {layer.name}")
                widget.add_css_class("preview-error")
            self.put(widget, 0.0, 0.0)
            self._layers.append(RenderedLayer(layer, widget))

        if self.preview:
            self._reroll_random_candidates()
        GLib.idle_add(self._relayout)

    def _make_widget(self, layer: Layer) -> Gtk.Widget:
        if isinstance(layer, TextLayer):
            return TextLayerWidget(layer, self.scale)
        return self._make_image(layer)

    def _make_image(self, layer: ImageLayer) -> Gtk.Widget:
        if not layer.path:
            raise FileNotFoundError("No image selected")
        max_width = None
        max_height = None
        if self.render_limit is not None:
            max_width = max(1, round(self.render_limit[0] * self.scale))
            max_height = max(1, round(self.render_limit[1] * self.scale))
        asset = self.media.load(
            layer,
            self.scale,
            max_width=max_width,
            max_height=max_height,
        )
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
        if width > 1 and height > 1:
            self._layout_for_bounds(width, height)
        return GLib.SOURCE_REMOVE

    def _fit_layer(
        self,
        rendered: RenderedLayer,
        max_width: float,
        max_height: float,
    ) -> tuple[float, float]:
        widget = rendered.widget
        if isinstance(widget, TextLayerWidget):
            return widget.fit_to(max_width, max_height)
        if isinstance(widget, AnimatedPicture):
            preserve = (
                rendered.model.keep_aspect_ratio
                if isinstance(rendered.model, ImageLayer)
                else True
            )
            return widget.fit_to(
                max_width,
                max_height,
                preserve_aspect=preserve,
            )

        _, natural_w, _, _ = widget.measure(Gtk.Orientation.HORIZONTAL, -1)
        _, natural_h, _, _ = widget.measure(
            Gtk.Orientation.VERTICAL,
            max(1, natural_w),
        )
        fitted_w, fitted_h, _ = fit_dimensions(
            max(1, natural_w),
            max(1, natural_h),
            safe_rect(max_width, max_height, 0),
        )
        widget.set_size_request(round(fitted_w), round(fitted_h))
        return fitted_w, fitted_h

    def _layout_for_bounds(self, width: float, height: float) -> None:
        if width <= 1 or height <= 1:
            return

        margin = max(4.0, SAFE_MARGIN_PX * self.scale)
        bounds = safe_rect(width, height, margin)

        measured = [
            (
                rendered,
                *self._fit_layer(
                    rendered,
                    bounds.width,
                    bounds.height,
                ),
            )
            for rendered in self._layers
        ]
        occupied: list[RectTuple] = []
        placements: list[tuple[RenderedLayer, float, float, float, float]] = []

        # Fixed layers are obstacles for randomized layers. Fixed layers may
        # intentionally overlap one another, but each one is independently clamped.
        for rendered, item_w, item_h in measured:
            if rendered.model.position.randomize:
                continue
            x, y = fixed_top_left(
                rendered.model.position,
                item_w,
                item_h,
                bounds,
                scale=self.scale,
            )
            placements.append((rendered, x, y, item_w, item_h))
            occupied.append((x, y, item_w, item_h))

        spacing = max(4.0, RANDOM_SPACING_PX * self.scale)
        for rendered, item_w, item_h in measured:
            if not rendered.model.position.randomize:
                continue
            candidates = self._random_candidates.get(rendered.model.id)
            if not candidates:
                candidates = [(0.5, 0.5)]
            x, y = choose_random_position(
                bounds,
                item_w,
                item_h,
                candidates,
                occupied,
                spacing=spacing,
            )
            placements.append((rendered, x, y, item_w, item_h))
            occupied.append((x, y, item_w, item_h))

        for rendered, x, y, item_w, item_h in placements:
            rect = (x, y, item_w, item_h)
            if not rect_within_bounds(rect, bounds):
                # This should be unreachable. Keep a loud diagnostic rather than
                # silently allowing a regression to draw outside the safe screen.
                LOG.error(
                    "Layout invariant failed for layer %s: rect=%r bounds=%r",
                    rendered.model.id,
                    rect,
                    bounds,
                )
                x, y = fixed_top_left(
                    rendered.model.position,
                    min(item_w, bounds.width),
                    min(item_h, bounds.height),
                    bounds,
                    scale=self.scale,
                )
            self.move(rendered.widget, x, y)

        self.set_opacity(1.0)


def _parse_rgba(value: str, fallback: str) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    if not rgba.parse(value):
        rgba.parse(fallback)
    return rgba
