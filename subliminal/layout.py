from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .model import Position

RectTuple = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class SafeRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


def safe_rect(
    container_width: float,
    container_height: float,
    margin: float = 12.0,
) -> SafeRect:
    width = max(1.0, _finite(container_width, 1.0))
    height = max(1.0, _finite(container_height, 1.0))
    requested_margin = max(0.0, _finite(margin, 0.0))
    # Never let margins consume the complete drawable area.
    horizontal = min(requested_margin, max(0.0, (width - 1.0) / 2.0))
    vertical = min(requested_margin, max(0.0, (height - 1.0) / 2.0))
    return SafeRect(
        horizontal,
        vertical,
        max(1.0, width - 2.0 * horizontal),
        max(1.0, height - 2.0 * vertical),
    )


def fit_dimensions(
    width: float,
    height: float,
    bounds: SafeRect,
    *,
    preserve_aspect: bool = True,
) -> tuple[float, float, float]:
    """Return a size that fits bounds and the applied scale (<= 1)."""
    item_w = max(1.0, _finite(width, 1.0))
    item_h = max(1.0, _finite(height, 1.0))

    if preserve_aspect:
        scale = min(
            1.0,
            bounds.width / item_w,
            bounds.height / item_h,
        )
        return (
            max(1.0, item_w * scale),
            max(1.0, item_h * scale),
            scale,
        )

    fitted_w = min(item_w, bounds.width)
    fitted_h = min(item_h, bounds.height)
    # Scale is informational for non-uniform fitting; report the tighter factor.
    scale = min(fitted_w / item_w, fitted_h / item_h, 1.0)
    return max(1.0, fitted_w), max(1.0, fitted_h), scale


def clamp_top_left(
    x: float,
    y: float,
    item_width: float,
    item_height: float,
    bounds: SafeRect,
) -> tuple[float, float]:
    item_w = min(max(1.0, _finite(item_width, 1.0)), bounds.width)
    item_h = min(max(1.0, _finite(item_height, 1.0)), bounds.height)
    max_x = bounds.right - item_w
    max_y = bounds.bottom - item_h
    return (
        min(max(_finite(x, bounds.x), bounds.x), max_x),
        min(max(_finite(y, bounds.y), bounds.y), max_y),
    )


def fixed_top_left(
    position: Position,
    item_width: float,
    item_height: float,
    bounds: SafeRect,
    *,
    scale: float = 1.0,
) -> tuple[float, float]:
    item_w = min(max(1.0, _finite(item_width, 1.0)), bounds.width)
    item_h = min(max(1.0, _finite(item_height, 1.0)), bounds.height)
    safe_scale = _finite(scale, 1.0)

    anchor_x, anchor_y = _anchor_fraction(position.anchor)
    pos_x = min(1.0, max(0.0, _finite(position.x, 0.5)))
    pos_y = min(1.0, max(0.0, _finite(position.y, 0.5)))
    target_x = bounds.x + bounds.width * pos_x
    target_y = bounds.y + bounds.height * pos_y

    requested_x = (
        target_x
        - item_w * anchor_x
        + _finite(position.offset_x, 0.0) * safe_scale
    )
    requested_y = (
        target_y
        - item_h * anchor_y
        + _finite(position.offset_y, 0.0) * safe_scale
    )
    return clamp_top_left(
        requested_x,
        requested_y,
        item_w,
        item_h,
        bounds,
    )


def random_top_left(
    bounds: SafeRect,
    item_width: float,
    item_height: float,
    random_x: float,
    random_y: float,
) -> tuple[float, float]:
    item_w = min(max(1.0, _finite(item_width, 1.0)), bounds.width)
    item_h = min(max(1.0, _finite(item_height, 1.0)), bounds.height)
    span_x = max(0.0, bounds.width - item_w)
    span_y = max(0.0, bounds.height - item_h)
    rx = min(1.0, max(0.0, _finite(random_x, 0.5)))
    ry = min(1.0, max(0.0, _finite(random_y, 0.5)))
    return bounds.x + rx * span_x, bounds.y + ry * span_y


def rects_overlap(a: RectTuple, b: RectTuple, spacing: float = 0.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    gap = max(0.0, _finite(spacing, 0.0))
    return not (
        ax + aw + gap <= bx
        or bx + bw + gap <= ax
        or ay + ah + gap <= by
        or by + bh + gap <= ay
    )


def choose_random_position(
    bounds: SafeRect,
    item_width: float,
    item_height: float,
    candidates: list[tuple[float, float]],
    occupied: list[RectTuple],
    *,
    spacing: float = 16.0,
) -> tuple[float, float]:
    """First collision-free candidate; structured free-strip probes; least-visual-overlap fallback."""
    item_w = min(max(1.0, _finite(item_width, 1.0)), bounds.width)
    item_h = min(max(1.0, _finite(item_height, 1.0)), bounds.height)
    gap = max(0.0, _finite(spacing, 0.0))
    samples = candidates or [(0.5, 0.5)]
    evaluated: list[tuple[float, float, float, float]] = []

    def evaluate_point(x: float, y: float) -> bool:
        cx, cy = clamp_top_left(x, y, item_w, item_h, bounds)
        rect = (cx, cy, item_w, item_h)
        collisions = [
            other for other in occupied
            if rects_overlap(rect, other, gap)
        ]
        if not collisions:
            evaluated.append((0.0, 0.0, cx, cy))
            return True
        visual_overlap = sum(
            _visual_overlap_area(rect, other)
            for other in collisions
        )
        spacing_overlap = sum(
            _intersection_area(rect, other, gap)
            for other in collisions
        )
        evaluated.append((visual_overlap, spacing_overlap, cx, cy))
        return False

    for rx, ry in samples:
        x, y = random_top_left(bounds, item_w, item_h, rx, ry)
        if evaluate_point(x, y):
            return evaluated[-1][2], evaluated[-1][3]

    # When uniform random samples all collide (e.g., two large text blocks),
    # probe structured positions around occupied strips and a coarse grid so
    # any physically valid non-overlapping slot is deterministically found.
    if occupied:
        seed_rx = min(1.0, max(0.0, _finite(samples[0][0], 0.5)))
        seed_ry = min(1.0, max(0.0, _finite(samples[0][1], 0.5)))
        base_x, base_y = random_top_left(bounds, item_w, item_h, seed_rx, seed_ry)
        structured_points: list[tuple[float, float]] = []
        for ox, oy, ow, oh in occupied:
            for pad in (gap, 0.0):
                structured_points.append((base_x, oy - item_h - pad))
                structured_points.append((base_x, oy + oh + pad))
                structured_points.append((ox - item_w - pad, base_y))
                structured_points.append((ox + ow + pad, base_y))
        for gx in (0.0, 0.25, 0.5, 0.75, 1.0):
            for gy in (0.0, 0.25, 0.5, 0.75, 1.0):
                structured_points.append(
                    random_top_left(bounds, item_w, item_h, gx, gy)
                )
        for px, py in structured_points:
            if evaluate_point(px, py):
                return evaluated[-1][2], evaluated[-1][3]

    # Lexicographic ranking: zero actual visual overlap strictly beats any
    # visual overlap, even if spacing margin is tighter than requested.
    _, _, best_x, best_y = min(evaluated, key=lambda item: (item[0], item[1]))
    return best_x, best_y


def rect_within_bounds(
    rect: RectTuple,
    bounds: SafeRect,
    *,
    epsilon: float = 0.01,
) -> bool:
    x, y, width, height = rect
    return (
        x >= bounds.x - epsilon
        and y >= bounds.y - epsilon
        and x + width <= bounds.right + epsilon
        and y + height <= bounds.bottom + epsilon
    )


def _visual_overlap_area(a: RectTuple, b: RectTuple) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    return max(0.0, right - left) * max(0.0, bottom - top)


def _intersection_area(
    a: RectTuple,
    b: RectTuple,
    spacing: float,
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    half = max(0.0, spacing) * 0.5
    left = max(ax - half, bx - half)
    top = max(ay - half, by - half)
    right = min(ax + aw + half, bx + bw + half)
    bottom = min(ay + ah + half, by + bh + half)
    return max(0.0, right - left) * max(0.0, bottom - top)


def _anchor_fraction(anchor: str) -> tuple[float, float]:
    horizontal = {
        "top-left": 0.0,
        "left": 0.0,
        "bottom-left": 0.0,
        "top": 0.5,
        "center": 0.5,
        "bottom": 0.5,
        "top-right": 1.0,
        "right": 1.0,
        "bottom-right": 1.0,
    }
    vertical = {
        "top-left": 0.0,
        "top": 0.0,
        "top-right": 0.0,
        "left": 0.5,
        "center": 0.5,
        "right": 0.5,
        "bottom-left": 1.0,
        "bottom": 1.0,
        "bottom-right": 1.0,
    }
    return horizontal.get(anchor, 0.5), vertical.get(anchor, 0.5)


def _finite(value: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return number if isfinite(number) else fallback
