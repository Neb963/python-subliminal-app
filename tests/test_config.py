import os
from pathlib import Path

import pytest

from subliminal.config import (
    ConfigImportError,
    ConfigStore,
    config_dir,
    export_config,
    import_config,
    state_dir,
)
from subliminal.model import Folder, ImageLayer, Scene, default_config


def test_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    cfg = default_config()
    cfg.schedule.break_ms = 1234
    cfg.folders.append(Folder(id="work", name="Work"))
    cfg.scenes[0].folder_id = "work"
    store.save(cfg)
    loaded = store.load()
    assert loaded.schedule.break_ms == 1234
    assert loaded.scenes[0].layers[0].text == "Focus 🎯"
    assert loaded.scenes[0].folder_id == "work"
    assert loaded.folders[0].name == "Work"


def test_export_and_import_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "export.json"
    cfg = default_config()
    cfg.scenes[0].name = "Renamed"
    layer = cfg.scenes[0].layers[0]
    layer.name = "Primary message"
    layer.alignment = "right"
    layer.background_enabled = True
    layer.background_color = "#11223388"
    layer.background_padding_px = 17
    export_config(cfg, path)
    loaded = import_config(path)
    loaded_layer = loaded.scenes[0].layers[0]
    assert loaded.scenes[0].name == "Renamed"
    assert loaded_layer.name == "Primary message"
    assert loaded_layer.alignment == "right"
    assert loaded_layer.background_enabled is True
    assert loaded_layer.background_color == "#11223388"
    assert loaded_layer.background_padding_px == 17


def test_import_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigImportError):
        import_config(path)


@pytest.mark.parametrize(
    "payload",
    [
        '{"schedule": null}',
        '{"display": null}',
        '{"scenes": [null]}',
        '{"scenes": [{"layers": null}]}',
        '{"scenes": [{"layers": [{"position": null}]}]}',
        '{"folders": null}',
    ],
)
def test_import_rejects_null_and_wrong_typed_sections(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "malformed.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ConfigImportError):
        import_config(path)


def test_bad_config_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{bad", encoding="utf-8")
    store = ConfigStore(path)
    loaded = store.load()
    assert loaded.scenes
    assert path.exists()
    assert list(tmp_path.glob("config.corrupt-*.json"))


def test_null_section_config_recovers_instead_of_crashing(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schedule": null}', encoding="utf-8")
    store = ConfigStore(path)
    loaded = store.load()
    assert loaded.scenes
    assert list(tmp_path.glob("config.corrupt-*.json"))


def test_unsupported_image_in_existing_config_does_not_wipe_store(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    cfg = default_config()
    cfg.scenes.append(
        Scene(name="User Work", layers=[ImageLayer(name="bmp", path="/tmp/pic.bmp")])
    )
    store.save(cfg)
    reloaded = store.load()
    assert len(reloaded.scenes) == 2
    assert reloaded.scenes[1].name == "User Work"
    assert not list(tmp_path.glob("config.corrupt-*.json"))


def test_empty_xdg_env_vars_fall_back_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setenv("XDG_STATE_HOME", "")
    assert config_dir().is_absolute()
    assert state_dir().is_absolute()
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")
    assert config_dir().is_absolute()


def test_unreadable_config_does_not_get_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    cfg = default_config()
    cfg.scenes[0].name = "Preserved"
    store.save(cfg)
    original_bytes = path.read_bytes()

    real_read_text = Path.read_text

    def fail_read(self: Path, *args, **kwargs):
        if self == path:
            raise PermissionError("simulated EACCES")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read)
    fallback = store.load()
    assert fallback.scenes
    assert path.read_bytes() == original_bytes
    assert not list(tmp_path.glob("config.corrupt-*.json"))
