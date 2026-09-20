# Subliminal

A native Fedora KDE Plasma **Wayland** application that flashes configurable text and images in a true click-through compositor overlay.

The compositor-facing overlay remains Python + GTK4 + `gtk4-layer-shell`. The editor is a native GTK three-pane interface: **Library → Canvas → Layers/Properties**.

## Features

- Frame-synchronized flash duration using the actual GTK/compositor frame clock.
- Adjustable wall-clock break between flashes.
- Multiple scenes, selected randomly or sequentially.
- Organizational folders for scenes; folders do not affect rendering or scheduling.
- Editable names for every scene and every layer.
- Multiple mixed text/image layers per scene.
- Text: Unicode/emoji, installed font, pixel size, RGBA color, bold, italic, underline and opacity.
- Images: PNG, JPEG, WebP, SVG and GIF.
- SVG file selection works through explicit filename patterns as well as MIME detection.
- Animated GIF and animated WebP playback.
- Fixed positioning with anchor, normalized X/Y and pixel offsets.
- Random position on every flash.
- Randomized layers avoid fixed elements and other randomized layers when space permits; crowded layouts fall back to the least-overlapping candidate rather than dropping content.
- Multi-monitor support and monitor hot-plug handling.
- True click-through overlay with no keyboard focus.
- Import/export of the complete JSON configuration.
- Auto-save, login autostart, diagnostics and rotating logs.

> JPEG has no per-pixel alpha channel. JPEG layers still support whole-layer opacity.

## Supported environment

Target: **Fedora KDE Plasma on Wayland / KWin**.

The application deliberately does not fall back to a normal always-on-top window when layer-shell is unavailable.

## Install on Fedora

```bash
git clone https://github.com/Neb963/python-subliminal-app.git
cd python-subliminal-app
./install.sh
```

If the Fedora dependencies are already installed:

```bash
./install.sh --skip-packages
```

Then run:

```bash
subliminal
```

Verify the installed version:

```bash
subliminal --version
```

Verify Wayland/layer-shell support:

```bash
subliminal --diagnose
```

## Editor

The main editor is organized into three panes.

### Library

The left pane contains folders and scenes.

- **+ Folder** creates an organizational folder.
- **+ Scene** creates a scene in the selected/current folder.
- Select a folder or scene and edit **Selected name** to rename it.
- Duplicate duplicates the selected scene.
- Deleting a folder moves its scenes to **Unfiled**; it never silently deletes those scenes.
- A scene can be moved between folders using the Folder selector above the canvas.

Folders are editor metadata only. Scheduling still operates on the same flat scene list.

### Canvas

The center pane previews the selected scene.

**Reroll preview** generates another randomized layout without affecting saved fixed positions.

### Layers / Properties

The right pane contains the selected scene's layer list and properties.

Every text and image layer has an editable **Name** field. Layer names are independent from text content and image filenames, so renaming content does not overwrite your organizational names.

For position you can use either:

- fixed Anchor + X/Y + pixel offsets, or
- **Random → New position on every flash**.

Random placement uses multiple candidate positions and avoids other visible layer bounding boxes with spacing when possible.

## Timing

Flash duration is intentionally frame-based.

Examples:

| Refresh | 1 frame | 2 frames | 3 frames |
| --- | ---: | ---: | ---: |
| 60 Hz | 16.67 ms | 33.33 ms | 50.00 ms |
| 120 Hz | 8.33 ms | 16.67 ms | 25.00 ms |
| 144 Hz | 6.94 ms | 13.89 ms | 20.83 ms |

The **break after flash** remains ordinary wall-clock seconds.

## Import / export

Use the **Import** and **Export** buttons in the top bar.

Export writes the complete application configuration as JSON, including:

- folders and scene membership;
- scene/layer names;
- text/image properties;
- fixed/random positioning;
- timing;
- display selection;
- autostart/startup preferences.

Image files themselves are **not copied into the export**. Image layers retain their filesystem paths. This keeps export simple and explicit; a portable asset bundle can be added separately later if needed.

## Configuration and logs

Main configuration:

```text
~/.config/subliminal/config.json
```

The configuration is written atomically. Older configuration versions are migrated automatically.

Logs:

```text
~/.local/state/subliminal/subliminal.log
```

Debug overlay lifecycle:

```bash
subliminal --debug
```

## Run directly from a checkout

```bash
sudo dnf install python3 python3-gobject gtk4 gtk4-layer-shell python3-cairo python3-pillow gdk-pixbuf2 librsvg2
./run.sh
```

## Tests

```bash
python3 -m pytest
```

CI covers model migration, configuration persistence/import/export, scheduler behavior, collision-aware random placement, Python compilation and shell syntax. KWin compositor behavior still requires an actual Plasma Wayland session.

## Uninstall

```bash
./uninstall.sh
```

To remove configuration and logs too:

```bash
./uninstall.sh --purge
```

## Architecture

```text
Gtk.Application
    └─ AppController
       ├─ ConfigStore
       ├─ Scheduler
       ├─ GTK editor
       │   ├─ Library (folders + scenes)
       │   ├─ Canvas
       │   └─ Layers / Properties
       └─ OverlayManager
          └─ OverlayWindow per target monitor
             └─ SceneView
                ├─ TextLayer
                └─ ImageLayer
```

Folders are not part of the render tree. The render model remains intentionally simple:

```text
Scene
├── TextLayer
├── ImageLayer
└── ...
```

Overlay surfaces are mapped for the flash and unmapped during the break. This avoids KWin retaining the last committed visual buffer while preserving true layer-shell behavior.

## Development scope

The project currently targets KDE Plasma/Wayland first. It does not attempt GNOME/Mutter, X11, Windows, macOS, video/audio layers, cloud sync or a web frontend.
