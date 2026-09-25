from __future__ import annotations

import logging
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
    def __init__(self) -> None:
        self._cache: dict[tuple, MediaAsset] = {}

    def clear(self) -> None:
        self._cache.clear()

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
        self._cache[key] = asset
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
        # GdkPixbuf rasterizes SVG during load. Apply monitor limits here, before
        # allocation, rather than creating a huge bitmap and shrinking it later.
        requested_w = width
        requested_h = height

        if requested_w is None and requested_h is None:
            if max_width is None and max_height is None:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
            else:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    str(path),
                    max_width or -1,
                    max_height or -1,
                    True,
                )
        else:
            target_w = requested_w or -1
            target_h = requested_h or -1
            if max_width is not None and target_w > 0:
                target_w = min(target_w, max_width)
            if max_height is not None and target_h > 0:
                target_h = min(target_h, max_height)

            # If only one dimension is explicit, bound the implicit dimension as
            # well by loading into the monitor box with aspect preservation.
            if keep_aspect and max_width is not None and max_height is not None:
                if requested_w is None or requested_h is None:
                    target_w = min(
                        requested_w or max_width,
                        max_width,
                    )
                    target_h = min(
                        requested_h or max_height,
                        max_height,
                    )

            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path),
                target_w,
                target_h,
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
