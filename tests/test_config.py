from pathlib import Path

import pytest

from subliminal.config import (
    ConfigImportError,
    ConfigStore,
    export_config,
    import_config,
)
from subliminal.model import Folder, default_config


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
    cfg.scenes[0].layers[0].name = "Primary message"
    export_config(cfg, path)
    loaded = import_config(path)
    assert loaded.scenes[0].name == "Renamed"
    assert loaded.scenes[0].layers[0].name == "Primary message"


def test_import_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
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
