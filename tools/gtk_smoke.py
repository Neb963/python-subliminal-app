from __future__ import annotations

import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import gi
gi.require_version("Graphene", "1.0")
from gi.repository import Graphene

from subliminal.gtk_runtime import Gdk, GLib, Gtk, Pango
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
from subliminal.ui import EditorPage, MainWindow


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
            monitors=lambda: [
                SimpleNamespace(
                    connector="eDP-1",
                    description="Smoke Display",
                    width=1920,
                    height=1080,
                    scale_factor=1,
                    refresh_hz=60.0,
                )
            ],
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

    def start(self) -> None:
        pass

    def pause(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def test_flash(self, _scene=None) -> None:
        pass

    def quit(self) -> None:
        pass

    def import_from(self, _path: Path) -> None:
        pass

    def export_to(self, _path: Path) -> None:
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

    # Repeated family changes exercise the same model/update path used after the
    # asynchronous native font dialog returns a selection.
    families = ("Sans", "Serif", "Monospace")
    for index in range(60):
        page._set_font_family_selection(
            families[index % len(families)],
            update_model=True,
        )
        drain(3)

    # Let debounced preview/model callbacks settle.
    drain(150)
    assert controller.change_count > 0


def _measure_min_width(widget: Gtk.Widget) -> int:
    minimum, _natural, _min_baseline, _nat_baseline = widget.measure(
        Gtk.Orientation.HORIZONTAL,
        -1,
    )
    return minimum


def _direct_child_widths(widget: Gtk.Widget) -> list[tuple[str, int]]:
    values: list[tuple[str, int]] = []
    child = widget.get_first_child()
    while child is not None:
        values.append((type(child).__name__, _measure_min_width(child)))
        child = child.get_next_sibling()
    return values


def _assert_inside(
    widget: Gtk.Widget,
    ancestor: Gtk.Widget,
    *,
    label: str,
) -> None:
    origin = Graphene.Point().init(0.0, 0.0)
    ok, point = widget.compute_point(ancestor, origin)
    assert ok, (label, "cannot translate coordinates")
    assert point.x >= -0.5, (label, "left overflow", point.x)
    assert point.y >= -0.5, (label, "top overflow", point.y)
    assert point.x + widget.get_width() <= ancestor.get_width() + 0.5, (
        label,
        "right overflow",
        point.x,
        widget.get_width(),
        ancestor.get_width(),
    )
    assert point.y + widget.get_height() <= ancestor.get_height() + 0.5, (
        label,
        "bottom overflow",
        point.y,
        widget.get_height(),
        ancestor.get_height(),
    )


def _has_horizontal_overflow(scroller: Gtk.ScrolledWindow) -> bool:
    hpolicy, _vpolicy = scroller.get_policy()
    assert hpolicy == Gtk.PolicyType.NEVER
    adjustment = scroller.get_hadjustment()
    return adjustment.get_upper() > adjustment.get_page_size() + 1.0


def _has_vertical_overflow(scroller: Gtk.ScrolledWindow) -> bool:
    adjustment = scroller.get_vadjustment()
    return adjustment.get_upper() > adjustment.get_page_size() + 1.0


def smoke_responsive_editor_layout() -> None:
    controller = FakeController()
    page = EditorPage(controller)
    page.refresh()

    library = page.library_panel
    canvas = page.canvas_panel
    inspector = page.inspector_panel

    # The three-pane editor must fit inside the supported 1000px minimum window
    # without relying on pane-boundary clipping.
    library_min = _measure_min_width(library)
    canvas_min = _measure_min_width(canvas)
    inspector_min = _measure_min_width(inspector)
    assert library_min <= 235, ("library minimum", library_min)
    assert canvas_min <= 360, ("canvas minimum", canvas_min)
    assert inspector_min <= 350, (
        "inspector minimum",
        inspector_min,
        _direct_child_widths(inspector),
        _direct_child_widths(page.text_props),
    )
    assert library_min + canvas_min + inspector_min <= 960, (
        "combined minimum",
        library_min,
        canvas_min,
        inspector_min,
    )

    # User-controlled names must not be able to inflate sidebar requisitions.
    controller.config.folders[0].name = "F" * 500
    controller.config.scenes[0].name = "S" * 500
    controller.config.scenes[0].layers[0].name = "L" * 500
    page.refresh()
    drain()
    long_library_min = _measure_min_width(library)
    long_inspector_min = _measure_min_width(inspector)
    assert long_library_min <= 235, ("long-name library", long_library_min)
    assert long_inspector_min <= 350, (
        "long-name inspector",
        long_inspector_min,
    )

    # At the user's problematic non-maximized size, normal text properties should
    # fit with no horizontal scrolling and no vertical scrollbar.
    window = Gtk.Window()
    window.set_default_size(1324, 1010)
    window.set_child(page)
    window.present()
    drain(180)

    assert not _has_horizontal_overflow(page.property_scroll)
    assert not _has_vertical_overflow(page.property_scroll)
    assert not _has_horizontal_overflow(page.layer_scroll)
    assert not _has_vertical_overflow(page.layer_scroll)
    assert not _has_horizontal_overflow(page.library_scroll)

    preview_w = page.preview_frame.get_width()
    preview_h = page.preview_frame.get_height()
    assert preview_w > 100 and preview_h > 100
    assert abs((preview_w / preview_h) - (16 / 9)) < 0.08, (
        "preview ratio",
        preview_w,
        preview_h,
    )

    # Hidden/alternate property pages must not force the Inspector wider, and a
    # very long file path must stay contained in the File entry.
    image = ImageLayer(
        name="I" * 500,
        path="/" + ("very-long-path/" * 50) + "image.png",
    )
    controller.config.scenes[0].layers.append(image)
    page._layer_id = image.id
    page._refresh_layers()
    drain(80)
    image_inspector_min = _measure_min_width(inspector)
    assert image_inspector_min <= 350, (
        "image inspector minimum",
        image_inspector_min,
    )
    assert not _has_horizontal_overflow(page.property_scroll)
    assert not _has_vertical_overflow(page.property_scroll)

    window.destroy()
    drain()

    # Exercise actual allocations across the supported size range. The smallest
    # height may legitimately need vertical Properties scrolling; horizontal
    # scrolling and pane clipping are never acceptable.
    for width, height in (
        (1000, 650),
        (1100, 700),
        (1324, 1010),
        (1600, 900),
        (1920, 1080),
    ):
        matrix_controller = FakeController()
        matrix_page = EditorPage(matrix_controller)
        matrix_page.refresh()
        matrix_window = Gtk.Window()
        matrix_window.set_default_size(width, height)
        matrix_window.set_child(matrix_page)
        matrix_window.present()
        drain(180)

        for control_name, control in (
            ("scene label", matrix_page.scene_label),
            ("scene enabled", matrix_page.scene_enabled),
            ("preview info", matrix_page.preview_info),
            ("folder label", matrix_page.folder_label),
            ("folder selector", matrix_page.scene_folder),
            ("reroll", matrix_page.reroll_button),
        ):
            _assert_inside(
                control,
                matrix_page.canvas_panel,
                label=f"{width}x{height} {control_name}",
            )

        assert (
            matrix_page.preview_aspect.get_overflow()
            == Gtk.Overflow.HIDDEN
        )
        assert (
            matrix_page.preview_frame.get_overflow()
            == Gtk.Overflow.HIDDEN
        )

        allocations = (
            matrix_page.library_panel.get_width(),
            matrix_page.canvas_panel.get_width(),
            matrix_page.inspector_panel.get_width(),
        )
        assert allocations[0] >= 190, ((width, height), "library", allocations)
        assert allocations[1] >= 300, ((width, height), "canvas", allocations)
        assert allocations[2] >= 300, ((width, height), "inspector", allocations)

        for name, scroller in (
            ("library", matrix_page.library_scroll),
            ("layers", matrix_page.layer_scroll),
            ("properties", matrix_page.property_scroll),
        ):
            assert not _has_horizontal_overflow(scroller), (
                (width, height),
                name,
                "horizontal scrollbar",
            )

        if width >= 1324 and height >= 900:
            assert not _has_vertical_overflow(matrix_page.property_scroll), (
                (width, height),
                "unexpected properties scrollbar",
            )

        matrix_preview_w = matrix_page.preview_frame.get_width()
        matrix_preview_h = matrix_page.preview_frame.get_height()
        assert matrix_preview_w > 80 and matrix_preview_h > 80
        assert abs((matrix_preview_w / matrix_preview_h) - (16 / 9)) < 0.08, (
            (width, height),
            "preview ratio",
            matrix_preview_w,
            matrix_preview_h,
        )

        matrix_window.destroy()
        drain()


def smoke_long_canvas_header_metadata() -> None:
    controller = FakeController()
    controller.overlay.monitors = lambda: [
        SimpleNamespace(
            connector="DISPLAY-" + ("X" * 300),
            description="D" * 500,
            width=3440,
            height=1440,
            scale_factor=1,
            refresh_hz=144.0,
        )
    ]
    page = EditorPage(controller)
    page.refresh()
    window = Gtk.Window()
    window.set_default_size(1324, 1010)
    window.set_child(page)
    window.present()
    drain(220)
    page.refresh_preview_context()
    drain(120)

    assert page.preview_info.get_ellipsize() == Pango.EllipsizeMode.END
    for name, control in (
        ("scene label", page.scene_label),
        ("scene enabled", page.scene_enabled),
        ("preview info", page.preview_info),
        ("folder label", page.folder_label),
        ("folder selector", page.scene_folder),
        ("reroll", page.reroll_button),
    ):
        _assert_inside(control, page.canvas_panel, label=f"long header {name}")

    assert _measure_min_width(page.canvas_panel) <= 360
    window.destroy()
    drain()


def smoke_property_modes_and_necessary_scrolling() -> None:
    # Expanded background controls should still fit at the common 1600x900 size.
    controller = FakeController()
    text_layer = controller.config.scenes[0].layers[0]
    assert isinstance(text_layer, TextLayer)
    text_layer.background_enabled = True

    page = EditorPage(controller)
    page.refresh()
    window = Gtk.Window()
    window.set_default_size(1600, 900)
    window.set_child(page)
    window.present()
    drain(220)

    assert page.text_background_revealer.get_reveal_child()
    assert not _has_horizontal_overflow(page.property_scroll)
    assert not _has_vertical_overflow(page.property_scroll)
    window.destroy()
    drain()

    # Image properties, including dimensions and a pathological path, must also
    # fit at 900p without forcing the whole Inspector wider or adding a routine
    # properties scrollbar.
    image_controller = FakeController()
    image = ImageLayer(
        name="Image layer",
        path="/" + ("deep-directory/" * 80) + "asset.svg",
        width_px=9999,
        height_px=7777,
        keep_aspect_ratio=False,
    )
    image_controller.config.scenes[0].layers = [image]
    image_page = EditorPage(image_controller)
    image_page.refresh()
    image_window = Gtk.Window()
    image_window.set_default_size(1600, 900)
    image_window.set_child(image_page)
    image_window.present()
    drain(220)

    assert _measure_min_width(image_page.inspector_panel) <= 350
    assert not _has_horizontal_overflow(image_page.property_scroll)
    assert not _has_vertical_overflow(image_page.property_scroll)
    image_window.destroy()
    drain()

    # Many layers are a legitimate reason for the Layers list to scroll. The
    # scrollbar should be confined to that list, not force Properties or the
    # whole Inspector to scroll horizontally.
    crowded_controller = FakeController()
    crowded_controller.config.scenes[0].layers = [
        TextLayer(name=f"Layer {index}", text=f"Item {index}")
        for index in range(24)
    ]
    crowded_page = EditorPage(crowded_controller)
    crowded_page.refresh()
    crowded_window = Gtk.Window()
    crowded_window.set_default_size(1324, 1010)
    crowded_window.set_child(crowded_page)
    crowded_window.present()
    drain(220)

    assert _has_vertical_overflow(crowded_page.layer_scroll)
    assert not _has_horizontal_overflow(crowded_page.layer_scroll)
    assert not _has_horizontal_overflow(crowded_page.property_scroll)
    assert not _has_vertical_overflow(crowded_page.property_scroll)
    crowded_window.destroy()
    drain()


def smoke_larger_ui_font_layout() -> None:
    display = Gdk.Display.get_default()
    assert display is not None

    provider = Gtk.CssProvider()
    provider.load_from_data(b"* { font-size: 16px; }")
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10,
    )
    try:
        controller = FakeController()
        app = Gtk.Application(application_id="io.github.subliminal.FontSmoke")
        app.register()
        window = MainWindow(app, controller)
        window.set_default_size(1324, 1010)
        window.present()
        drain(260)

        # The responsive toolbar may choose either mode based on measured font
        # metrics, but all controls must remain inside the window.
        origin = Graphene.Point().init(0.0, 0.0)
        ok, point = window.toolbar_right.compute_point(window, origin)
        assert ok
        assert point.x >= 0
        assert (
            point.x + window.toolbar_right.get_width()
            <= window.get_width() + 0.5
        )

        page = window.editor_page
        assert page.canvas_panel.get_width() >= 280
        assert not _has_horizontal_overflow(page.library_scroll)
        assert not _has_horizontal_overflow(page.layer_scroll)
        assert not _has_horizontal_overflow(page.property_scroll)

        window.destroy()
        drain()
    finally:
        Gtk.StyleContext.remove_provider_for_display(display, provider)
        drain()


def smoke_navigation_page_isolation() -> None:
    controller = FakeController()
    controller.store.path = Path(
        "/tmp/" + ("very-long-config-directory/" * 30) + "config.json"
    )
    controller.overlay.monitors = lambda: [
        SimpleNamespace(
            connector="eDP-1-" + ("X" * 120),
            description="Very long display description " + ("Y" * 300),
            width=1920,
            height=1080,
            scale_factor=1,
            refresh_hz=60.0,
        )
    ]

    app = Gtk.Application(application_id="io.github.subliminal.PagesSmoke")
    app.register()
    window = MainWindow(app, controller)
    window.set_default_size(1000, 650)
    window.present()
    drain(220)

    assert not window.page_stack.get_hhomogeneous()
    assert not window.page_stack.get_vhomogeneous()
    assert window.get_width() <= 1010, ("window widened", window.get_width())

    for button, page in (
        (window.editor_nav, window.editor_page),
        (window.timing_nav, window.timing_page),
        (window.displays_nav, window.displays_page),
        (window.settings_nav, window.settings_page),
    ):
        button.set_active(True)
        drain(100)
        minimum = _measure_min_width(page)
        allocated = window.page_stack.get_width()
        assert minimum <= allocated, (
            type(page).__name__,
            "minimum exceeds stack allocation",
            minimum,
            allocated,
        )
        assert window.get_width() <= 1010, (
            type(page).__name__,
            "navigation widened window",
            window.get_width(),
        )

    window.destroy()
    drain()


def smoke_toolbar_stability() -> None:
    controller = FakeController()
    app = Gtk.Application(application_id="io.github.subliminal.Smoke")
    app.register()

    def point_in_window(window: MainWindow, widget: Gtk.Widget) -> tuple[float, float]:
        origin = Graphene.Point().init(0.0, 0.0)
        ok, point = widget.compute_point(window, origin)
        assert ok
        return point.x, point.y

    for width in (1000, 1324, 1600, 1920):
        window = MainWindow(app, controller)
        window.set_default_size(width, 800)
        window.present()
        drain(220)

        assert window.toolbar.get_width() <= window.get_width()

        left_x, left_y = point_in_window(window, window.toolbar_left)
        right_x, right_y = point_in_window(window, window.toolbar_right)
        assert left_x >= 0 and right_x >= 0
        assert (
            right_x + window.toolbar_right.get_width()
            <= window.get_width() + 0.5
        )

        # The toolbar is structurally one row at every supported width.
        assert not window._toolbar_compact
        assert abs(right_y - left_y) < 2
        assert _measure_min_width(window.toolbar) <= 980, (
            width,
            "toolbar minimum",
            _measure_min_width(window.toolbar),
        )

        # Navigation is deliberately separated native buttons, not a zero-gap
        # pseudo-segmented control.
        nav_buttons = (
            window.editor_nav,
            window.timing_nav,
            window.displays_nav,
            window.settings_nav,
        )
        nav_points = [point_in_window(window, button) for button in nav_buttons]
        for index in range(1, len(nav_buttons)):
            previous = nav_buttons[index - 1]
            previous_x, previous_y = nav_points[index - 1]
            current_x, current_y = nav_points[index]
            gap = current_x - (previous_x + previous.get_width())
            assert gap >= 4, (width, "nav gap", index, gap)
            assert abs(current_y - previous_y) < 2

        positions = []
        for state in ("stopped", "waiting", "visible", "paused", "waiting"):
            window.set_runtime_state(state)
            drain()
            positions.append(
                tuple(
                    point_in_window(window, widget)[0]
                    for widget in (
                        window.import_button,
                        window.export_button,
                        window.start_button,
                    )
                )
            )

        assert all(item == positions[0] for item in positions[1:]), (
            width,
            positions,
        )

        window.destroy()
        drain()


def smoke_long_text_containment() -> None:
    scene = Scene(
        name="Long text containment",
        layers=[
            TextLayer(
                name="Very long line",
                text=("CONFIDENTIAL-WIDE-TEXT-" * 1000),
                font_size_px=96,
                alignment="center",
                background_enabled=True,
                background_padding_px=24,
                position=Position(
                    x=0.0,
                    y=0.0,
                    anchor="top-left",
                    offset_x=-10000,
                    offset_y=-10000,
                ),
            ),
            TextLayer(
                name="Long random line",
                text=("RANDOM-LONG-TEXT-" * 600),
                font_size_px=72,
                position=Position(randomize=True),
            ),
        ],
    )

    window = Gtk.Window()
    window.set_default_size(800, 450)
    view = SceneView(
        scene,
        MediaCache(),
        render_limit=(800, 450),
    )
    window.set_child(view)
    window.present()
    drain(160)

    assert view.get_overflow() == Gtk.Overflow.HIDDEN
    width = max(1, view.get_width())
    height = max(1, view.get_height())

    for _ in range(20):
        view.prepare_flash(width, height)
        drain(4)
        for rendered in view._layers:
            child = rendered.widget
            x, y = view.get_child_position(child)
            child_w = child.get_width()
            child_h = child.get_height()
            assert x >= -0.01
            assert y >= -0.01
            assert child_w <= width + 0.01, (
                rendered.model.name,
                "child width",
                child_w,
                width,
            )
            assert child_h <= height + 0.01, (
                rendered.model.name,
                "child height",
                child_h,
                height,
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

    window.destroy()
    drain()


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

        square_svg = Path(temp) / "square.svg"
        square_svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100" height="100" viewBox="0 0 100 100">'
            '<rect width="100" height="100" fill="blue"/>'
            '</svg>',
            encoding="utf-8",
        )
        stretched = ImageLayer(
            name="Stretched SVG",
            path=str(square_svg),
            width_px=500,
            height_px=100,
            keep_aspect_ratio=False,
        )
        stretched_asset = MediaCache().load(
            stretched,
            1.0,
            max_width=800,
            max_height=600,
        )
        assert (stretched_asset.width, stretched_asset.height) == (500, 100)

        # Auto-sized small SVG must preserve its intrinsic size instead of
        # upscaling to fill the entire monitor limit.
        small_svg = Path(temp) / "small.svg"
        small_svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="64" height="48" viewBox="0 0 64 48">'
            '<rect width="64" height="48" fill="green"/>'
            '</svg>',
            encoding="utf-8",
        )
        auto_svg = ImageLayer(
            name="Small Auto SVG",
            path=str(small_svg),
            width_px=None,
            height_px=None,
            keep_aspect_ratio=True,
        )
        auto_asset = MediaCache().load(
            auto_svg,
            1.0,
            max_width=800,
            max_height=600,
        )
        assert (auto_asset.width, auto_asset.height) == (64, 48), (
            auto_asset.width,
            auto_asset.height,
        )

        # Zero-alpha text color must not crash or pass invalid Pango alpha 0.
        zero_alpha_scene = Scene(
            name="Zero alpha",
            layers=[
                TextLayer(
                    name="Invisible",
                    text="transparent",
                    color="#FFFFFF00",
                    background_enabled=True,
                    background_padding_px=500,
                )
            ],
        )
        zero_view = SceneView(zero_alpha_scene, MediaCache(), render_limit=(400, 300))
        zero_view.prepare_flash(400, 300)
        assert zero_view._layers[0].widget.label.get_opacity() == 0.0

        window.destroy()
        drain()


def main() -> None:
    Gtk.init()
    smoke_editor_reentrancy()
    smoke_responsive_editor_layout()
    smoke_long_canvas_header_metadata()
    smoke_property_modes_and_necessary_scrolling()
    smoke_navigation_page_isolation()
    smoke_toolbar_stability()
    smoke_long_text_containment()
    smoke_larger_ui_font_layout()
    smoke_layout_allocations()
    print("GTK smoke checks passed")


if __name__ == "__main__":
    main()
