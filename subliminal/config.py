from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .model import AppConfig, config_from_dict, config_to_dict, default_config, normalize_config

APP_DIR_NAME = "subliminal"
CONFIG_FILE_NAME = "config.json"


def config_dir() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / APP_DIR_NAME


def state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / APP_DIR_NAME


@dataclass(slots=True)
class ConfigStore:
    path: Path | None = None

    def __post_init__(self) -> None:
        if self.path is None:
            self.path = config_dir() / CONFIG_FILE_NAME

    def load(self) -> AppConfig:
        assert self.path is not None
        if not self.path.exists():
            cfg = default_config()
            self.save(cfg)
            return cfg
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON value must be an object")
            cfg = config_from_dict(raw)
            normalize_config(cfg)
            return cfg
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._backup_corrupt_file()
            cfg = default_config()
            self.save(cfg)
            return cfg

    def save(self, config: AppConfig) -> None:
        assert self.path is not None
        normalize_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(config_to_dict(config), ensure_ascii=False, indent=2) + "\n"
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)

    def _backup_corrupt_file(self) -> None:
        assert self.path is not None
        if not self.path.exists():
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"config.corrupt-{stamp}.json")
        try:
            shutil.move(str(self.path), str(backup))
        except OSError:
            pass
