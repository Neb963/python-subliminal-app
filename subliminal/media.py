from __future__ import annotations

import logging
import math
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

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
    MAX_ANIMATED_FRAMES = 180
    MAX_ASSET_BYTES = 128 * 1024 * 1024

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
        asset_bytes = self._asset_bytes(asset)
        if asset_bytes > self.MAX_APPROX_BYTES:
            return
        existing = self._cache.pop(key, None)
        if existing is not None:
            self._approx_bytes -= self._asset_bytes(existing)
        self._cache[key] = asset
        self._approx_bytes += asset_bytes
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
        safe_scale = max(0.01, float(scale))
        width = None if layer.width_px is None else max(1, round(layer.width_px * safe_scale))
        height = None if layer.height_px is None else max(1, round(layer.height_px * safe_scale))
        max_width = None if max_width is None else max(1, int(max_width))
        max_height = None if max_height is None else max(1, int(max_height))
        auto_scale_key = round(safe_scale, 4) if (width is None and height is None) else None
        key = (
            str(path.resolve()),
            stat.st_mtime_ns,
            stat.st_size,
            width,
            height,
            auto_scale_key,
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
                scale=safe_scale,
                max_width=max_width,
                max_height=max_height,
            )
        else:
            asset = self._load_pillow(
                path,
                width,
                height,
                layer.keep_aspect_ratio,
                scale=safe_scale,
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
        scale: float = 1.0,
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> MediaAsset:
        """Rasterize SVG without ever allocating beyond the render limit.

        When both width and height are Auto (None), preserve intrinsic SVG
        dimensions (scaled by `scale` and clamped to `max_width`/`max_height`)
        rather than upscaling small SVGs to fill the entire monitor.
        """
        auto_both = width is None and height is None
        if auto_both:
            fmt, intrinsic_w, intrinsic_h = GdkPixbuf.Pixbuf.get_file_info(str(path))
            if fmt is not None and intrinsic_w > 0 and intrinsic_h > 0:
                scaled_w = max(1, round(intrinsic_w * scale))
                scaled_h = max(1, round(intrinsic_h * scale))
                if max_width is not None or max_height is not None:
                    ratio = 1.0
                    if max_width is not None:
                        ratio = min(ratio, max_width / scaled_w)
                    if max_height is not None:
                        ratio = min(ratio, max_height / scaled_h)
                    target_w = max(1, round(scaled_w * ratio))
                    target_h = max(1, round(scaled_h * ratio))
                else:
                    target_w, target_h = scaled_w, scaled_h
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    str(path),
                    target_w,
                    target_h,
                    True,
                )
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                return MediaAsset(
                    texture.get_width(),
                    texture.get_height(),
                    [texture],
                    [0],
                )

        if max_width is not None or max_height is not None:
            limit_w = max_width or max(1, width or 4096)
            limit_h = max_height or max(1, height or 4096)

            if width is not None and height is not None and not keep_aspect:
                target_w = min(limit_w, max(1, width))
                target_h = min(limit_h, max(1, height))
                preserve = False
            else:
                target_w = (
                    min(limit_w, max(1, width))
                    if width is not None
                    else limit_w
                )
                target_h = (
                    min(limit_h, max(1, height))
                    if height is not None
                    else limit_h
                )
                preserve = True

            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path),
                target_w,
                target_h,
                preserve,
            )
        elif auto_both:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        else:
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
        scale: float = 1.0,
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> MediaAsset:
        with Image.open(path) as source:
            animated = bool(getattr(source, "is_animated", False))
            if not animated:
                source_img = ImageOps.exif_transpose(source)
            else:
                source_img = source

            eff_width = width
            eff_height = height
            if width is None and height is None and scale != 1.0:
                eff_width = max(1, round(source_img.width * scale))
                eff_height = max(1, round(source_img.height * scale))

            target = self._target_size(
                source_img.width,
                source_img.height,
                eff_width,
                eff_height,
                keep_aspect,
                max_width=max_width,
                max_height=max_height,
            )

            if animated:
                n_frames = min(
                    max(1, int(getattr(source_img, "n_frames", 1) or 1)),
                    self.MAX_ANIMATED_FRAMES,
                )
                est_bytes = target[0] * target[1] * 4 * n_frames
                if est_bytes > self.MAX_ASSET_BYTES:
                    factor = math.sqrt(self.MAX_ASSET_BYTES / est_bytes)
                    target = (
                        max(1, round(target[0] * factor)),
                        max(1, round(target[1] * factor)),
                    )
                    LOG.warning(
                        "Downscaling animated %s (%d frames) to %dx%d to stay within memory budget",
                        path.name,
                        n_frames,
                        target[0],
                        target[1],
                    )

            frames: list[object] = []
            durations: list[int] = []
            iterator = ImageSequence.Iterator(source_img) if animated else [source_img]
            for frame_index, frame in enumerate(iterator):
                if animated and frame_index >= self.MAX_ANIMATED_FRAMES:
                    break
                rgba = frame.convert("RGBA")
                if rgba.size != target:
                    rgba = rgba.resize(target, Image.Resampling.LANCZOS)
                frames.append(self._texture_from_rgba(rgba))
                if animated:
                    raw_duration = frame.info.get(
                        "duration",
                        source_img.info.get("duration", 100),
                    )
                    try:
                        duration = int(raw_duration or 100)
                    except (TypeError, ValueError):
                        duration = 100
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
        if src_w <= 0 or src_h <= 0:
            raise ValueError(f"Invalid source image dimensions: {src_w}x{src_h}")

        auto_both = width is None and height is None
        one_auto = (width is None) != (height is None)
        if auto_both:
            width, height = src_w, src_h
        elif width is None:
            width = max(1, round(src_w * (height / src_h)))
        elif height is None:
            height = max(1, round(src_h * (width / src_w)))

        assert width is not None and height is not None

        # Auto sizing means "use the source dimensions / aspect", so monitor
        # limiting preserves the source aspect ratio unless both axes are explicit.
        if keep_aspect or auto_both or one_auto:
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
