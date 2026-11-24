from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
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

LOG = logging.getLogger(__name__)

APP_DIR_NAME = "subliminal"
CONFIG_FILE_NAME = "config.json"


class ConfigImportError(ValueError):
    pass


def _xdg_dir(env_var: str, fallback: Path) -> Path:
    raw = os.environ.get(env_var, "").strip()
    if raw:
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
    return fallback


def config_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config") / APP_DIR_NAME


def state_dir() -> Path:
    return _xdg_dir("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP_DIR_NAME


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def export_config(config: AppConfig, path: Path) -> None:
    normalize_config(config)
    _write_json_atomic(path, config_to_dict(config))


def import_config(path: Path, *, strict_media: bool = True) -> AppConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigImportError(f"Could not read configuration: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigImportError("Imported configuration must contain a JSON object.")
    try:
        config = config_from_dict(raw)
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        raise ConfigImportError(f"Invalid configuration data: {exc}") from exc
    errors = validate_config(config, strict_media=strict_media)
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
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            # Do not destroy a valid config file on transient I/O or permission errors.
            LOG.warning("Could not read %s (%s); using in-memory defaults", self.path, exc)
            return default_config()
        except UnicodeError:
            self._backup_corrupt_file()
            cfg = default_config()
            self.save(cfg)
            return cfg
        try:
            raw = json.loads(text)
            if not isinstance(raw, dict):
                raise ConfigImportError("Configuration must contain a JSON object.")
            cfg = config_from_dict(raw)
            errors = validate_config(cfg, strict_media=False)
            if errors:
                raise ConfigImportError("; ".join(errors))
            return cfg
        except (
            ConfigImportError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            KeyError,
            AttributeError,
            OverflowError,
        ):
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
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = self.path.with_name(f"config.corrupt-{stamp}.json")
        try:
            shutil.move(str(self.path), str(backup))
        except OSError:
            pass
