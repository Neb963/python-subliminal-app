import random

from subliminal.layout import (
    choose_random_position,
    fit_dimensions,
    fixed_top_left,
    rect_within_bounds,
    safe_rect,
)
from subliminal.model import Position


def test_fixed_positions_are_always_clamped_inside_safe_rect() -> None:
    bounds = safe_rect(1920, 1080, 12)
    rng = random.Random(1234)
    anchors = [
        "top-left", "top", "top-right",
        "left", "center", "right",
        "bottom-left", "bottom", "bottom-right",
    ]
    for _ in range(5000):
        width = rng.uniform(1, 4000)
        height = rng.uniform(1, 3000)
        fitted_w, fitted_h, _ = fit_dimensions(width, height, bounds)
        pos = Position(
            x=rng.uniform(-2, 3),
            y=rng.uniform(-2, 3),
            anchor=rng.choice(anchors),
            offset_x=rng.randint(-10000, 10000),
            offset_y=rng.randint(-10000, 10000),
        )
        x, y = fixed_top_left(pos, fitted_w, fitted_h, bounds)
        assert rect_within_bounds((x, y, fitted_w, fitted_h), bounds)


def test_random_positions_are_always_inside_safe_rect() -> None:
    bounds = safe_rect(320, 180, 12)
    rng = random.Random(9)
    for _ in range(2000):
        raw_w = rng.uniform(1, 1000)
        raw_h = rng.uniform(1, 1000)
        width, height, _ = fit_dimensions(raw_w, raw_h, bounds)
        candidates = [(rng.random(), rng.random()) for _ in range(32)]
        x, y = choose_random_position(
            bounds,
            width,
            height,
            candidates,
            [],
        )
        assert rect_within_bounds((x, y, width, height), bounds)


def test_oversized_aspect_image_scales_down_without_enlarging() -> None:
    bounds = safe_rect(800, 600, 20)
    width, height, scale = fit_dimensions(4000, 1000, bounds)
    assert scale < 1
    assert width <= bounds.width
    assert height <= bounds.height
    assert width / height == 4


def test_nonuniform_fit_caps_each_axis() -> None:
    bounds = safe_rect(800, 600, 20)
    width, height, _ = fit_dimensions(
        4000,
        20,
        bounds,
        preserve_aspect=False,
    )
    assert width == bounds.width
    assert height == 20


def test_random_avoids_occupied_when_candidate_exists() -> None:
    bounds = safe_rect(1000, 600, 10)
    occupied = [(10, 10, 300, 200)]
    x, y = choose_random_position(
        bounds,
        120,
        80,
        [(0.0, 0.0), (1.0, 1.0)],
        occupied,
        spacing=20,
    )
    assert x > 500
    assert y > 300


def test_tiny_container_still_produces_valid_bounds() -> None:
    bounds = safe_rect(1, 1, 100)
    assert bounds.width == 1
    assert bounds.height == 1
    width, height, _ = fit_dimensions(100, 100, bounds)
    x, y = fixed_top_left(Position(), width, height, bounds)
    assert rect_within_bounds((x, y, width, height), bounds)
