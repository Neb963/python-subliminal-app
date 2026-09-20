from subliminal.model import (
    Position,
    calculate_position,
    config_from_dict,
    default_config,
    random_top_left,
)


def test_center_position() -> None:
    pos = Position(x=0.5, y=0.5, anchor="center")
    assert calculate_position(pos, 1000, 500, 200, 100) == (400.0, 200.0)


def test_config_round_trip_defaults_and_clamping() -> None:
    cfg = config_from_dict({
        "schedule": {"interval_ms": 1000, "duration_ms": 50},
        "scenes": [{
            "name": "A",
            "layers": [{"kind": "text", "opacity": 2, "position": {"x": -1, "y": 3}}],
        }],
    })
    layer = cfg.scenes[0].layers[0]
    assert cfg.schedule.break_ms == 1000
    assert cfg.schedule.visible_frames == 3
    assert layer.opacity == 1.0
    assert layer.position.x == 0.0
    assert layer.position.y == 1.0


def test_default_config_has_enabled_scene() -> None:
    cfg = default_config()
    assert cfg.enabled_scenes()


def test_random_position_stays_inside_screen() -> None:
    for rx, ry in ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0)):
        x, y = random_top_left(1920, 1080, 400, 100, rx, ry, margin=8)
        assert 8 <= x <= 1920 - 400 - 8
        assert 8 <= y <= 1080 - 100 - 8


def test_random_position_config_round_trip() -> None:
    cfg = config_from_dict({
        "scenes": [{
            "name": "Random",
            "layers": [{
                "kind": "text",
                "text": "move",
                "position": {"x": 0.2, "y": 0.7, "randomize": True},
            }],
        }],
    })
    assert cfg.scenes[0].layers[0].position.randomize is True
