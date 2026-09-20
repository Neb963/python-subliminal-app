from pathlib import Path

from subliminal.config import ConfigStore
from subliminal.model import default_config


def test_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    cfg = default_config()
    cfg.schedule.break_ms = 1234
    store.save(cfg)
    loaded = store.load()
    assert loaded.schedule.break_ms == 1234
    assert loaded.scenes[0].layers[0].text == "Focus 🎯"


def test_bad_config_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{bad", encoding="utf-8")
    store = ConfigStore(path)
    loaded = store.load()
    assert loaded.scenes
    assert path.exists()
    assert list(tmp_path.glob("config.corrupt-*.json"))
