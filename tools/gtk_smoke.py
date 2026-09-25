from __future__ import annotations

import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from subliminal.gtk_runtime import GLib, Gtk, Pango
from subliminal.media import MediaCache
from subliminal.model import (
    Folder,
    ImageLayer,
    Position,
    Scene,
    TextLayer,
    default_config,
)
from subliminal.render import SceneView
from subliminal.ui import EditorPage


def drain(milliseconds: int = 0) -> None:
    if milliseconds:
        deadline = time.monotonic() + milliseconds / 1000.0
        while time.monotonic() < deadline:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            time.sleep(0.002)
    while GLib.MainContext.default().pending():
        GLib.MainContext.default().iteration(False)


class FakeController:
    def __init__(self) -> None:
        self.config = default_config()
        self.config.folders = [
            Folder(id="a", name="Folder A"),
            Folder(id="b", name="Folder B"),
        ]
        self.config.scenes[0].folder_id = "a"
        self.overlay = SimpleNamespace(
            media=MediaCache(),
            monitors=lambda: [],
        )
        self.scheduler = SimpleNamespace(
            state=SimpleNamespace(value="stopped"),
        )
        self.store = SimpleNamespace(path=Path("/tmp/subliminal-smoke.json"))
        self.change_count = 0

    def config_changed(self, *_args, **_kwargs) -> None:
        self.change_count += 1

    def warn(self, message: str) -> None:
        raise AssertionError(message)

    def set_autostart(self, _enabled: bool) -> None:
        pass


def smoke_editor_reentrancy() -> None:
    controller = FakeController()
    page = EditorPage(controller)
    page.refresh()
    drain()

    # Rapidly move the same scene between folder dropdown values. Deferred list
    # rebuilding must complete without recursive notifications or stale selection.
    for index in range(150):
        page.scene_folder.set_selected(1 + (index % 2))
        drain()
    assert page.selected_scene() is not None

    # Programmatic font changes exercise the same notify::font-desc path that the
    # dialog button uses after a user selection.
    families = ("Sans", "Serif", "Monospace")
    for index in range(60):
        desc = Pango.FontDescription.new()
        desc.set_family(families[index % len(families)])
        page.font_button.set_font_desc(desc)
        drain(3)

    # Let debounced preview/model callbacks settle.
    drain(150)
    assert controller.change_count > 0


def smoke_layout_allocations() -> None:
    with tempfile.TemporaryDirectory() as temp:
        image_path = Path(temp) / "large-request.png"
        Image.new("RGBA", (1200, 800), (255, 0, 0, 128)).save(image_path)

        scene = Scene(
            name="Bounds torture",
            layers=[
                TextLayer(
                    name="Huge bottom right",
                    text="WIDE TEXT 🚀\nsecond line",
                    font_size_px=500,
                    bold=True,
                    alignment="right",
                    background_enabled=True,
                    background_color="#2244AA99",
                    background_padding_px=500,
                    position=Position(
                        x=1.0,
                        y=1.0,
                        anchor="bottom-right",
                        offset_x=10000,
                        offset_y=10000,
                    ),
                ),
                ImageLayer(
                    name="Oversized image",
                    path=str(image_path),
                    width_px=5000,
                    height_px=4000,
                    keep_aspect_ratio=True,
                    position=Position(
                        x=0.0,
                        y=0.0,
                        anchor="top-left",
                        offset_x=-5000,
                        offset_y=-5000,
                    ),
                    opacity=0.5,
                ),
                TextLayer(
                    name="Random",
                    text="random",
                    font_size_px=80,
                    position=Position(randomize=True),
                ),
            ],
        )

        window = Gtk.Window()
        window.set_default_size(800, 600)
        view = SceneView(
            scene,
            MediaCache(),
            render_limit=(800, 600),
        )
        window.set_child(view)
        window.present()
        drain(100)

        width = max(1, view.get_width())
        height = max(1, view.get_height())
        for _ in range(80):
            view.prepare_flash(width, height)
            drain(2)

            for rendered in view._layers:
                child = rendered.widget
                x, y = view.get_child_position(child)
                child_w = child.get_width()
                child_h = child.get_height()
                assert x >= -0.01, (
                    rendered.model.name,
                    x,
                    y,
                    child_w,
                    child_h,
                )
                assert y >= -0.01, (
                    rendered.model.name,
                    x,
                    y,
                    child_w,
                    child_h,
                )
                assert x + child_w <= width + 0.01, (
                    rendered.model.name,
                    x,
                    child_w,
                    width,
                )
                assert y + child_h <= height + 0.01, (
                    rendered.model.name,
                    y,
                    child_h,
                    height,
                )

        text_widget = view._layers[0].widget
        assert text_widget.label.get_justify() == Gtk.Justification.RIGHT
        assert text_widget.label.get_margin_start() > 0

        # Extreme SVG aspect ratio + one explicit dimension + non-aspect mode
        # must still rasterize inside the monitor limit before Gtk.Picture sees it.
        svg_path = Path(temp) / "extreme.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100" height="10000" viewBox="0 0 100 10000">'
            '<rect width="100" height="10000" fill="red"/>'
            '</svg>',
            encoding="utf-8",
        )
        svg_layer = ImageLayer(
            name="Extreme SVG",
            path=str(svg_path),
            width_px=5000,
            height_px=None,
            keep_aspect_ratio=False,
        )
        svg_asset = MediaCache().load(
            svg_layer,
            1.0,
            max_width=800,
            max_height=600,
        )
        assert svg_asset.width <= 800
        assert svg_asset.height <= 600

        window.destroy()
        drain()


def main() -> None:
    Gtk.init()
    smoke_editor_reentrancy()
    smoke_layout_allocations()
    print("GTK smoke checks passed")


if __name__ == "__main__":
    main()
