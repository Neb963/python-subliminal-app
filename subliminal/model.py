from __future__ import annotations

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

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ANCHORS: tuple[Anchor, ...] = (
    "top-left", "top", "top-right",
    "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
)


def new_id() -> str:
    return uuid4().hex[:12]


@dataclass(slots=True)
class Position:
    x: float = 0.5
    y: float = 0.5
    anchor: Anchor = "center"
    offset_x: int = 0
    offset_y: int = 0


@dataclass(slots=True)
class TextLayer:
    id: str = field(default_factory=new_id)
    kind: Literal["text"] = "text"
    enabled: bool = True
    text: str = "Focus 🎯"
    position: Position = field(default_factory=Position)
    font_family: str = "Sans"
    font_size_px: int = 52
    color: str = "#FFFFFFFF"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    opacity: float = 0.65


@dataclass(slots=True)
class ImageLayer:
    id: str = field(default_factory=new_id)
    kind: Literal["image"] = "image"
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
    enabled: bool = True
    layers: list[Layer] = field(default_factory=list)


@dataclass(slots=True)
class ScheduleConfig:
    # Wall-clock pause after a flash completes.
    break_ms: int = 5000
    # Visible lifetime measured in actual GTK/compositor frame-clock ticks.
    visible_frames: int = 3
    selection: SelectionMode = "random"


@dataclass(slots=True)
class DisplayConfig:
    mode: DisplayMode = "all"
    connectors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    version: int = 1
    start_on_launch: bool = False
    autostart: bool = False
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    scenes: list[Scene] = field(default_factory=list)

    def enabled_scenes(self) -> list[Scene]:
        return [scene for scene in self.scenes if scene.enabled and any(layer.enabled for layer in scene.layers)]


def default_config() -> AppConfig:
    return AppConfig(
        scenes=[
            Scene(
                name="Focus",
                layers=[TextLayer(text="Focus 🎯", bold=True, opacity=0.55)],
            )
        ]
    )


def position_from_dict(data: dict) -> Position:
    anchor = data.get("anchor", "center")
    if anchor not in ANCHORS:
        anchor = "center"
    return Position(
        x=float(data.get("x", 0.5)),
        y=float(data.get("y", 0.5)),
        anchor=anchor,
        offset_x=int(data.get("offset_x", 0)),
        offset_y=int(data.get("offset_y", 0)),
    )


def layer_from_dict(data: dict) -> Layer:
    kind = data.get("kind", data.get("type", "text"))
    position = position_from_dict(data.get("position", {}))
    if kind == "image":
        width = data.get("width_px", 320)
        height = data.get("height_px")
        return ImageLayer(
            id=str(data.get("id") or new_id()),
            enabled=bool(data.get("enabled", True)),
            path=str(data.get("path", "")),
            position=position,
            width_px=None if width is None else int(width),
            height_px=None if height is None else int(height),
            keep_aspect_ratio=bool(data.get("keep_aspect_ratio", True)),
            opacity=float(data.get("opacity", 0.65)),
        )
    return TextLayer(
        id=str(data.get("id") or new_id()),
        enabled=bool(data.get("enabled", True)),
        text=str(data.get("text", "")),
        position=position,
        font_family=str(data.get("font_family", "Sans")),
        font_size_px=int(data.get("font_size_px", 52)),
        color=str(data.get("color", "#FFFFFFFF")),
        bold=bool(data.get("bold", False)),
        italic=bool(data.get("italic", False)),
        underline=bool(data.get("underline", False)),
        opacity=float(data.get("opacity", 0.65)),
    )


def config_from_dict(data: dict) -> AppConfig:
    schedule_data = data.get("schedule", {})
    display_data = data.get("display", {})
    scenes: list[Scene] = []
    for raw_scene in data.get("scenes", []):
        scenes.append(
            Scene(
                id=str(raw_scene.get("id") or new_id()),
                name=str(raw_scene.get("name", "Scene")),
                enabled=bool(raw_scene.get("enabled", True)),
                layers=[layer_from_dict(item) for item in raw_scene.get("layers", [])],
            )
        )
    cfg = AppConfig(
        version=int(data.get("version", 1)),
        start_on_launch=bool(data.get("start_on_launch", False)),
        autostart=bool(data.get("autostart", False)),
        schedule=ScheduleConfig(
            # v1 migration: interval_ms was effectively a break after each flash.
            break_ms=int(schedule_data.get("break_ms", schedule_data.get("interval_ms", 5000))),
            # v1 migration assumes a 60 Hz reference: 16.67 ms per frame.
            visible_frames=int(
                schedule_data.get(
                    "visible_frames",
                    max(1, round(float(schedule_data.get("duration_ms", 50)) / (1000.0 / 60.0))),
                )
            ),
            selection=schedule_data.get("selection", "random") if schedule_data.get("selection", "random") in {"random", "sequential"} else "random",
        ),
        display=DisplayConfig(
            mode=display_data.get("mode", "all") if display_data.get("mode", "all") in {"all", "selected"} else "all",
            connectors=[str(v) for v in display_data.get("connectors", [])],
        ),
        scenes=scenes,
    )
    if not cfg.scenes:
        cfg.scenes = default_config().scenes
    normalize_config(cfg)
    return cfg


def config_to_dict(config: AppConfig) -> dict:
    return asdict(config)


def normalize_config(config: AppConfig) -> None:
    config.version = 2
    config.schedule.break_ms = max(100, int(config.schedule.break_ms))
    config.schedule.visible_frames = max(1, min(120, int(config.schedule.visible_frames)))
    if config.schedule.selection not in {"random", "sequential"}:
        config.schedule.selection = "random"
    if config.display.mode not in {"all", "selected"}:
        config.display.mode = "all"

    seen_ids: set[str] = set()
    for scene in config.scenes:
        if not scene.id or scene.id in seen_ids:
            scene.id = new_id()
        seen_ids.add(scene.id)
        scene.name = scene.name.strip() or "Scene"
        for layer in scene.layers:
            if not layer.id or layer.id in seen_ids:
                layer.id = new_id()
            seen_ids.add(layer.id)
            layer.opacity = min(1.0, max(0.0, float(layer.opacity)))
            layer.position.x = min(1.0, max(0.0, float(layer.position.x)))
            layer.position.y = min(1.0, max(0.0, float(layer.position.y)))
            if layer.position.anchor not in ANCHORS:
                layer.position.anchor = "center"
            if isinstance(layer, TextLayer):
                layer.font_size_px = max(1, int(layer.font_size_px))
                layer.font_family = layer.font_family.strip() or "Sans"
                if not _valid_color(layer.color):
                    layer.color = "#FFFFFFFF"
            else:
                if layer.width_px is not None:
                    layer.width_px = max(1, int(layer.width_px))
                if layer.height_px is not None:
                    layer.height_px = max(1, int(layer.height_px))


def validate_config(config: AppConfig) -> list[str]:
    errors: list[str] = []
    if config.schedule.break_ms <= 0:
        errors.append("Break between flashes must be positive.")
    if config.schedule.visible_frames <= 0:
        errors.append("Visible frame count must be positive.")
    if not config.scenes:
        errors.append("At least one scene is required.")
    for scene in config.scenes:
        if not scene.name.strip():
            errors.append("Scene names cannot be empty.")
        for layer in scene.layers:
            if isinstance(layer, ImageLayer) and layer.path:
                suffix = Path(layer.path).suffix.lower()
                if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
                    errors.append(f"Unsupported image format: {layer.path}")
    return errors


def _valid_color(value: str) -> bool:
    if not value.startswith("#") or len(value) not in {7, 9}:
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def anchor_offset(anchor: Anchor, width: float, height: float) -> tuple[float, float]:
    columns = {
        "top-left": 0.0, "left": 0.0, "bottom-left": 0.0,
        "top": 0.5, "center": 0.5, "bottom": 0.5,
        "top-right": 1.0, "right": 1.0, "bottom-right": 1.0,
    }
    rows = {
        "top-left": 0.0, "top": 0.0, "top-right": 0.0,
        "left": 0.5, "center": 0.5, "right": 0.5,
        "bottom-left": 1.0, "bottom": 1.0, "bottom-right": 1.0,
    }
    return width * columns[anchor], height * rows[anchor]


def calculate_position(
    position: Position,
    container_width: float,
    container_height: float,
    item_width: float,
    item_height: float,
    scale: float = 1.0,
) -> tuple[float, float]:
    anchor_x, anchor_y = anchor_offset(position.anchor, item_width, item_height)
    return (
        container_width * position.x - anchor_x + position.offset_x * scale,
        container_height * position.y - anchor_y + position.offset_y * scale,
    )
