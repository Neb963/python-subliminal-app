from subliminal.model import Position, calculate_position, config_from_dict, default_config


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
