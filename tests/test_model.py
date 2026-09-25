from subliminal.model import config_from_dict, default_config


def test_config_round_trip_defaults_and_clamping() -> None:
    cfg = config_from_dict({
        "schedule": {"interval_ms": 1000, "duration_ms": 50},
        "scenes": [{
            "name": "A",
            "layers": [{
                "kind": "text",
                "opacity": 2,
                "position": {"x": -1, "y": 3},
            }],
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
    assert cfg.scenes[0].layers[0].name == "Focus message"


def test_old_layers_receive_names() -> None:
    cfg = config_from_dict({
        "scenes": [{
            "name": "Legacy",
            "layers": [
                {"kind": "text", "text": "Remember this"},
                {"kind": "image", "path": "/tmp/logo.svg"},
            ],
        }],
    })
    assert cfg.scenes[0].layers[0].name == "Remember this"
    assert cfg.scenes[0].layers[1].name == "logo.svg"


def test_folder_membership_and_invalid_folder_migration() -> None:
    cfg = config_from_dict({
        "folders": [{"id": "work", "name": "Work"}],
        "scenes": [
            {"name": "A", "folder_id": "work", "layers": [{"kind": "text"}]},
            {"name": "B", "folder_id": "missing", "layers": [{"kind": "text"}]},
        ],
    })
    assert cfg.folders[0].name == "Work"
    assert cfg.scenes[0].folder_id == "work"
    assert cfg.scenes[1].folder_id is None


def test_random_position_config_round_trip() -> None:
    cfg = config_from_dict({
        "scenes": [{
            "name": "Random",
            "layers": [{
                "kind": "text",
                "name": "Mover",
                "text": "move",
                "position": {"x": 0.2, "y": 0.7, "randomize": True},
            }],
        }],
    })
    assert cfg.scenes[0].layers[0].position.randomize is True
    assert cfg.scenes[0].layers[0].name == "Mover"


def test_text_background_and_alignment_defaults_migrate() -> None:
    cfg = config_from_dict({
        "version": 4,
        "scenes": [{
            "name": "Legacy text",
            "layers": [{"kind": "text", "text": "hello"}],
        }],
    })
    layer = cfg.scenes[0].layers[0]
    assert layer.alignment == "left"
    assert layer.background_enabled is False
    assert layer.background_color == "#00000099"
    assert layer.background_padding_px == 8


def test_invalid_text_visual_values_are_normalized() -> None:
    cfg = config_from_dict({
        "scenes": [{
            "name": "Bad values",
            "layers": [{
                "kind": "text",
                "text": "hello",
                "alignment": "diagonal",
                "background_enabled": True,
                "background_color": "not-a-color",
                "background_padding_px": 999999,
            }],
        }],
    })
    layer = cfg.scenes[0].layers[0]
    assert layer.alignment == "left"
    assert layer.background_color == "#00000099"
    assert layer.background_padding_px == 500


def test_schema_4_migrates_to_schema_5() -> None:
    cfg = config_from_dict({
        "version": 4,
        "scenes": [{
            "name": "Old",
            "layers": [{"kind": "text", "text": "legacy"}],
        }],
    })
    assert cfg.version == 5
    layer = cfg.scenes[0].layers[0]
    assert layer.alignment == "left"
    assert layer.background_enabled is False
