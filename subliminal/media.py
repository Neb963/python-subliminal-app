from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence

from .gtk_runtime import Gdk, GdkPixbuf, GLib
from .model import ImageLayer

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class MediaAsset:
    width: int
    height: int
    frames: list[object]
    durations_ms: list[int]

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1


class MediaCache:
    MAX_ENTRIES = 48
    MAX_APPROX_BYTES = 256 * 1024 * 1024

    def __init__(self) -> None:
        self._cache: OrderedDict[tuple, MediaAsset] = OrderedDict()
        self._approx_bytes = 0

    def clear(self) -> None:
        self._cache.clear()
        self._approx_bytes = 0

    @staticmethod
    def _asset_bytes(asset: MediaAsset) -> int:
        # Textures are RGBA8 in the Pillow path; SVG/GdkPixbuf is comparable.
        return max(1, asset.width) * max(1, asset.height) * 4 * max(1, len(asset.frames))

    def _remember(self, key: tuple, asset: MediaAsset) -> None:
        existing = self._cache.pop(key, None)
        if existing is not None:
            self._approx_bytes -= self._asset_bytes(existing)
        self._cache[key] = asset
        self._approx_bytes += self._asset_bytes(asset)
        while (
            len(self._cache) > self.MAX_ENTRIES
            or self._approx_bytes > self.MAX_APPROX_BYTES
        ) and len(self._cache) > 1:
            _, old = self._cache.popitem(last=False)
            self._approx_bytes -= self._asset_bytes(old)

    def load(
        self,
        layer: ImageLayer,
        scale: float = 1.0,
        *,
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> MediaAsset:
        path = Path(layer.path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        stat = path.stat()
        width = None if layer.width_px is None else max(1, round(layer.width_px * scale))
        height = None if layer.height_px is None else max(1, round(layer.height_px * scale))
        max_width = None if max_width is None else max(1, int(max_width))
        max_height = None if max_height is None else max(1, int(max_height))
        key = (
            str(path.resolve()),
            stat.st_mtime_ns,
            stat.st_size,
            width,
            height,
            layer.keep_aspect_ratio,
            max_width,
            max_height,
        )
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        if path.suffix.lower() == ".svg":
            asset = self._load_svg(
                path,
                width,
                height,
                layer.keep_aspect_ratio,
                max_width=max_width,
                max_height=max_height,
            )
        else:
            asset = self._load_pillow(
                path,
                width,
                height,
                layer.keep_aspect_ratio,
                max_width=max_width,
                max_height=max_height,
            )
        self._remember(key, asset)
        return asset

    def _load_svg(
        self,
        path: Path,
        width: int | None,
        height: int | None,
        keep_aspect: bool,
        *,
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> MediaAsset:
        """Rasterize SVG without ever allocating beyond the render limit.

        GdkPixbuf's one-dimension (-1) scaling can derive a very large implicit
        dimension for extreme SVG aspect ratios. When a render limit is known,
        always rasterize into a bounded aspect-preserving box first. Gtk.Picture
        may subsequently stretch that bounded texture if the layer explicitly
        disables aspect-ratio preservation.
        """
        if max_width is not None or max_height is not None:
            limit_w = max_width or max(1, width or 4096)
            limit_h = max_height or max(1, height or 4096)

            # Explicit requested dimensions may reduce the rasterization target,
            # but never enlarge it beyond the monitor/preview box. Missing
            # dimensions use the full bounded box so extreme source aspect ratios
            # are still constrained on both axes.
            target_w = min(limit_w, max(1, width)) if width is not None else limit_w
            target_h = min(limit_h, max(1, height)) if height is not None else limit_h

            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path),
                target_w,
                target_h,
                True,
            )
        elif width is None and height is None:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        else:
            # No monitor limit is known (principally direct/library use). Preserve
            # the user's legacy sizing semantics here.
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path),
                width or -1,
                height or -1,
                keep_aspect,
            )

        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        return MediaAsset(
            texture.get_width(),
            texture.get_height(),
            [texture],
            [0],
        )

    def _load_pillow(
        self,
        path: Path,
        width: int | None,
        height: int | None,
        keep_aspect: bool,
        *,
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> MediaAsset:
        with Image.open(path) as source:
            target = self._target_size(
                source.width,
                source.height,
                width,
                height,
                keep_aspect,
                max_width=max_width,
                max_height=max_height,
            )
            animated = bool(getattr(source, "is_animated", False))
            frames: list[object] = []
            durations: list[int] = []
            iterator = ImageSequence.Iterator(source) if animated else [source]
            for frame in iterator:
                rgba = frame.convert("RGBA")
                if rgba.size != target:
                    rgba = rgba.resize(target, Image.Resampling.LANCZOS)
                frames.append(self._texture_from_rgba(rgba))
                if animated:
                    duration = int(frame.info.get("duration", source.info.get("duration", 100)) or 100)
                    durations.append(max(20, duration))
                else:
                    durations.append(0)
            if not frames:
                raise ValueError(f"No image frames decoded from {path}")
            return MediaAsset(target[0], target[1], frames, durations)

    @staticmethod
    def _target_size(
        src_w: int,
        src_h: int,
        width: int | None,
        height: int | None,
        keep_aspect: bool,
        *,
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> tuple[int, int]:
        auto_both = width is None and height is None
        if auto_both:
            width, height = src_w, src_h
        elif width is None:
            width = max(1, round(src_w * (height / src_h)))
        elif height is None:
            height = max(1, round(src_h * (width / src_w)))

        assert width is not None and height is not None

        # Auto sizing means "use the source dimensions", so monitor limiting must
        # preserve the source aspect ratio even when the layer's explicit
        # keep-aspect toggle is off.
        if keep_aspect or auto_both:
            ratio = min(width / src_w, height / src_h)
            if auto_both:
                ratio = min(1.0, ratio)
            if max_width is not None:
                ratio = min(ratio, max_width / src_w)
            if max_height is not None:
                ratio = min(ratio, max_height / src_h)
            return (
                max(1, round(src_w * ratio)),
                max(1, round(src_h * ratio)),
            )

        target_w, target_h = max(1, width), max(1, height)
        if max_width is not None:
            target_w = min(target_w, max_width)
        if max_height is not None:
            target_h = min(target_h, max_height)
        return target_w, target_h

    @staticmethod
    def _texture_from_rgba(image: Image.Image):
        width, height = image.size
        raw = image.tobytes("raw", "RGBA")
        blob = GLib.Bytes.new(raw)
        return Gdk.MemoryTexture.new(
            width,
            height,
            Gdk.MemoryFormat.R8G8B8A8,
            blob,
            width * 4,
        )
