from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .model import (
    AppConfig,
    config_from_dict,
    config_to_dict,
    default_config,
    normalize_config,
    validate_config,
)

APP_DIR_NAME = "subliminal"
CONFIG_FILE_NAME = "config.json"


class ConfigImportError(ValueError):
    pass


def config_dir() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / APP_DIR_NAME


def state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / APP_DIR_NAME


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def export_config(config: AppConfig, path: Path) -> None:
    normalize_config(config)
    _write_json_atomic(path, config_to_dict(config))


def import_config(path: Path) -> AppConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigImportError(f"Could not read configuration: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigImportError("Imported configuration must contain a JSON object.")
    try:
        config = config_from_dict(raw)
    except (TypeError, ValueError, KeyError) as exc:
        raise ConfigImportError(f"Invalid configuration data: {exc}") from exc
    errors = validate_config(config)
    if errors:
        raise ConfigImportError("; ".join(errors))
    return config


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
            return import_config(self.path)
        except ConfigImportError:
            self._backup_corrupt_file()
            cfg = default_config()
            self.save(cfg)
            return cfg

    def save(self, config: AppConfig) -> None:
        assert self.path is not None
        export_config(config, self.path)

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
