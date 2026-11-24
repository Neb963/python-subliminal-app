from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias
from uuid import uuid4

Anchor = Literal[
    "top-left", "top", "top-right",
    "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
]
SelectionMode = Literal["random", "sequential"]
DisplayMode = Literal["all", "selected"]
TextAlignment = Literal["left", "center", "right"]

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ANCHORS: tuple[Anchor, ...] = (
    "top-left", "top", "top-right",
    "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
)
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")


def new_id() -> str:
    return uuid4().hex[:12]


def _finite_float(value: object, default: float) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _finite_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    number = _finite_float(value, float(default))
    try:
        return int(number)
    except (ValueError, OverflowError):
        return default


def _require_dict(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object for '{field_name}'.")
    return value


def _require_list(value: object, field_name: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"Expected list for '{field_name}'.")
    return value


@dataclass(slots=True)
class Folder:
    id: str = field(default_factory=new_id)
    name: str = "Folder"


@dataclass(slots=True)
class Position:
    x: float = 0.5
    y: float = 0.5
    anchor: Anchor = "center"
    offset_x: int = 0
    offset_y: int = 0
    randomize: bool = False


@dataclass(slots=True)
class TextLayer:
    id: str = field(default_factory=new_id)
    kind: Literal["text"] = "text"
    name: str = "Text"
    enabled: bool = True
    text: str = "Focus 🎯"
    position: Position = field(default_factory=Position)
    font_family: str = "Sans"
    font_size_px: int = 52
    color: str = "#FFFFFFFF"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    alignment: TextAlignment = "left"
    background_enabled: bool = False
    background_color: str = "#00000099"
    background_padding_px: int = 8
    opacity: float = 0.65


@dataclass(slots=True)
class ImageLayer:
    id: str = field(default_factory=new_id)
    kind: Literal["image"] = "image"
    name: str = "Image"
    enabled: bool = True
    path: str = ""
    position: Position = field(default_factory=Position)
    width_px: int | None = 320
    height_px: int | None = None
    keep_aspect_ratio: bool = True
    opacity: float = 0.65


Layer: TypeAlias = TextLayer | ImageLayer


@dataclass(slots=True)
class Scene:
    id: str = field(default_factory=new_id)
    name: str = "Scene"
    folder_id: str | None = None
    enabled: bool = True
    layers: list[Layer] = field(default_factory=list)


@dataclass(slots=True)
class ScheduleConfig:
    break_ms: int = 5000
    visible_frames: int = 3
    selection: SelectionMode = "random"


@dataclass(slots=True)
class DisplayConfig:
    mode: DisplayMode = "all"
    connectors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    version: int = 5
    start_on_launch: bool = False
    autostart: bool = False
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    folders: list[Folder] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)

    def enabled_scenes(self) -> list[Scene]:
        return [
            scene
            for scene in self.scenes
            if scene.enabled and any(layer.enabled for layer in scene.layers)
        ]


def default_config() -> AppConfig:
    return AppConfig(
        scenes=[
            Scene(
                name="Focus",
                layers=[
                    TextLayer(
                        name="Focus message",
                        text="Focus 🎯",
                        bold=True,
                        opacity=0.55,
                    )
                ],
            )
        ]
    )


def position_from_dict(data: dict) -> Position:
    mapping = _require_dict(data, "position")
    anchor = mapping.get("anchor", "center")
    if anchor not in ANCHORS:
        anchor = "center"
    return Position(
        x=_finite_float(mapping.get("x", 0.5), 0.5),
        y=_finite_float(mapping.get("y", 0.5), 0.5),
        anchor=anchor,
        offset_x=_finite_int(mapping.get("offset_x", 0), 0),
        offset_y=_finite_int(mapping.get("offset_y", 0), 0),
        randomize=bool(mapping.get("randomize", False)),
    )


def _legacy_layer_name(data: dict, kind: str) -> str:
    explicit = str(data.get("name", "")).strip()
    if explicit:
        return explicit
    if kind == "image":
        path = str(data.get("path", "")).strip()
        return Path(path).name if path else "Image"
    text = str(data.get("text", "")).replace("\n", " ").strip()
    return text[:40] if text else "Text"


def layer_from_dict(data: dict) -> Layer:
    mapping = _require_dict(data, "layer")
    kind = mapping.get("kind", mapping.get("type", "text"))
    raw_position = mapping["position"] if "position" in mapping else {}
    position = position_from_dict(raw_position)
    if kind == "image":
        width = mapping.get("width_px", 320)
        height = mapping.get("height_px")
        return ImageLayer(
            id=str(mapping.get("id") or new_id()),
            name=_legacy_layer_name(mapping, "image"),
            enabled=bool(mapping.get("enabled", True)),
            path=str(mapping.get("path", "")),
            position=position,
            width_px=None if width is None else _finite_int(width, 320),
            height_px=None if height is None else _finite_int(height, 240),
            keep_aspect_ratio=bool(mapping.get("keep_aspect_ratio", True)),
            opacity=_finite_float(mapping.get("opacity", 0.65), 0.65),
        )
    return TextLayer(
        id=str(mapping.get("id") or new_id()),
        name=_legacy_layer_name(mapping, "text"),
        enabled=bool(mapping.get("enabled", True)),
        text=str(mapping.get("text", "")),
        position=position,
        font_family=str(mapping.get("font_family", "Sans")),
        font_size_px=_finite_int(mapping.get("font_size_px", 52), 52),
        color=str(mapping.get("color", "#FFFFFFFF")),
        bold=bool(mapping.get("bold", False)),
        italic=bool(mapping.get("italic", False)),
        underline=bool(mapping.get("underline", False)),
        alignment=(
            mapping.get("alignment", "left")
            if mapping.get("alignment", "left") in {"left", "center", "right"}
            else "left"
        ),
        background_enabled=bool(mapping.get("background_enabled", False)),
        background_color=str(mapping.get("background_color", "#00000099")),
        background_padding_px=_finite_int(mapping.get("background_padding_px", 8), 8),
        opacity=_finite_float(mapping.get("opacity", 0.65), 0.65),
    )


def config_from_dict(data: dict) -> AppConfig:
    mapping = _require_dict(data, "config")
    schedule_data = _require_dict(
        mapping["schedule"] if "schedule" in mapping else {},
        "schedule",
    )
    display_data = _require_dict(
        mapping["display"] if "display" in mapping else {},
        "display",
    )
    raw_folders = _require_list(
        mapping["folders"] if "folders" in mapping else [],
        "folders",
    )
    raw_scenes = _require_list(
        mapping["scenes"] if "scenes" in mapping else [],
        "scenes",
    )
    raw_connectors = _require_list(
        display_data["connectors"] if "connectors" in display_data else [],
        "display.connectors",
    )

    folders = [
        Folder(
            id=str(_require_dict(item, "folder").get("id") or new_id()),
            name=str(item.get("name", "Folder")),
        )
        for item in raw_folders
    ]

    scenes: list[Scene] = []
    for raw_scene in raw_scenes:
        scene_dict = _require_dict(raw_scene, "scene")
        raw_layers = _require_list(
            scene_dict["layers"] if "layers" in scene_dict else [],
            "scene.layers",
        )
        scenes.append(
            Scene(
                id=str(scene_dict.get("id") or new_id()),
                name=str(scene_dict.get("name", "Scene")),
                folder_id=(
                    str(scene_dict["folder_id"])
                    if scene_dict.get("folder_id") is not None
                    else None
                ),
                enabled=bool(scene_dict.get("enabled", True)),
                layers=[layer_from_dict(item) for item in raw_layers],
            )
        )

    duration_ms = _finite_float(schedule_data.get("duration_ms", 50), 50.0)
    default_frames = max(1, round(duration_ms / (1000.0 / 60.0)))

    cfg = AppConfig(
        version=_finite_int(mapping.get("version", 1), 1),
        start_on_launch=bool(mapping.get("start_on_launch", False)),
        autostart=bool(mapping.get("autostart", False)),
        schedule=ScheduleConfig(
            break_ms=_finite_int(
                schedule_data.get("break_ms", schedule_data.get("interval_ms", 5000)),
                5000,
            ),
            visible_frames=_finite_int(
                schedule_data.get("visible_frames", default_frames),
                default_frames,
            ),
            selection=(
                schedule_data.get("selection", "random")
                if schedule_data.get("selection", "random") in {"random", "sequential"}
                else "random"
            ),
        ),
        display=DisplayConfig(
            mode=(
                display_data.get("mode", "all")
                if display_data.get("mode", "all") in {"all", "selected"}
                else "all"
            ),
            connectors=[str(v) for v in raw_connectors],
        ),
        folders=folders,
        scenes=scenes,
    )
    if not cfg.scenes:
        cfg.scenes = default_config().scenes
    normalize_config(cfg)
    return cfg


def config_to_dict(config: AppConfig) -> dict:
    return asdict(config)


def normalize_config(config: AppConfig) -> None:
    config.version = 5
    config.schedule.break_ms = max(100, _finite_int(config.schedule.break_ms, 5000))
    config.schedule.visible_frames = max(
        1, min(120, _finite_int(config.schedule.visible_frames, 3))
    )
    if config.schedule.selection not in {"random", "sequential"}:
        config.schedule.selection = "random"
    if config.display.mode not in {"all", "selected"}:
        config.display.mode = "all"

    seen_ids: set[str] = set()

    for folder in config.folders:
        if not folder.id or folder.id in seen_ids:
            folder.id = new_id()
        seen_ids.add(folder.id)
        folder.name = folder.name.strip() or "Folder"

    valid_folder_ids = {folder.id for folder in config.folders}

    for scene in config.scenes:
        if not scene.id or scene.id in seen_ids:
            scene.id = new_id()
        seen_ids.add(scene.id)
        scene.name = scene.name.strip() or "Scene"
        if scene.folder_id not in valid_folder_ids:
            scene.folder_id = None

        for layer in scene.layers:
            if not layer.id or layer.id in seen_ids:
                layer.id = new_id()
            seen_ids.add(layer.id)
            layer.name = layer.name.strip() or (
                "Text" if isinstance(layer, TextLayer) else "Image"
            )
            layer.opacity = min(1.0, max(0.0, _finite_float(layer.opacity, 0.65)))
            layer.position.x = min(1.0, max(0.0, _finite_float(layer.position.x, 0.5)))
            layer.position.y = min(1.0, max(0.0, _finite_float(layer.position.y, 0.5)))
            layer.position.offset_x = _finite_int(layer.position.offset_x, 0)
            layer.position.offset_y = _finite_int(layer.position.offset_y, 0)
            if layer.position.anchor not in ANCHORS:
                layer.position.anchor = "center"
            layer.position.randomize = bool(layer.position.randomize)

            if isinstance(layer, TextLayer):
                layer.font_size_px = max(1, _finite_int(layer.font_size_px, 52))
                layer.font_family = layer.font_family.strip() or "Sans"
                if layer.alignment not in {"left", "center", "right"}:
                    layer.alignment = "left"
                layer.background_padding_px = max(
                    0,
                    min(500, _finite_int(layer.background_padding_px, 8)),
                )
                if not _valid_color(layer.color):
                    layer.color = "#FFFFFFFF"
                if not _valid_color(layer.background_color):
                    layer.background_color = "#00000099"
            else:
                if layer.width_px is not None:
                    layer.width_px = max(1, _finite_int(layer.width_px, 320))
                if layer.height_px is not None:
                    layer.height_px = max(1, _finite_int(layer.height_px, 240))


def validate_config(config: AppConfig, *, strict_media: bool = True) -> list[str]:
    errors: list[str] = []
    if config.schedule.break_ms <= 0:
        errors.append("Break between flashes must be positive.")
    if config.schedule.visible_frames <= 0:
        errors.append("Visible frame count must be positive.")
    if not config.scenes:
        errors.append("At least one scene is required.")

    for folder in config.folders:
        if not folder.name.strip():
            errors.append("Folder names cannot be empty.")

    for scene in config.scenes:
        if not scene.name.strip():
            errors.append("Scene names cannot be empty.")
        for layer in scene.layers:
            if not layer.name.strip():
                errors.append("Layer names cannot be empty.")
            if strict_media and isinstance(layer, ImageLayer) and layer.path:
                suffix = Path(layer.path).suffix.lower()
                if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
                    errors.append(f"Unsupported image format: {layer.path}")
    return errors


def _valid_color(value: object) -> bool:
    return isinstance(value, str) and _HEX_COLOR_RE.fullmatch(value) is not None
