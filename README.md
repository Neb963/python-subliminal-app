# Subliminal

Subliminal is a native Python/GTK desktop application for Fedora KDE Plasma on **Wayland/KWin**. It flashes configurable text and images through a true click-through layer-shell overlay.

The compositor-facing implementation remains deliberately small: GTK4 + PyGObject + `gtk4-layer-shell`. The editor is a native three-pane interface: **Library → Canvas → Layers / Properties**.

## Current release

**1.4.0**

Version 1.4 is primarily a stability/layout release. It fixes editor freezes around folders and font selection, prevents temporary top-left preview piles, enforces screen-safe layer placement, and adds text backgrounds and independent text alignment.

## Features

- Frame-synchronized flash duration using GTK's compositor-driven frame clock.
- Configurable break between flashes.
- Random or sequential scene selection.
- Organizational folders for scenes.
- Mandatory editable names for scenes and layers.
- Mixed text and image layers in each scene.
- Text:
  - Unicode and emoji.
  - Installed font family.
  - Pixel font size.
  - Bold, italic and underline.
  - RGBA foreground color.
  - Layer opacity.
  - Left / center / right multiline alignment independent of layer anchor.
  - Optional RGBA colored background with configurable padding.
- Images:
  - PNG.
  - JPEG.
  - WebP.
  - SVG.
  - GIF.
  - Animated GIF and animated WebP.
  - Layer opacity and source alpha where supported.
- Fixed positioning:
  - nine anchors;
  - normalized X/Y;
  - pixel offsets;
  - exact edge semantics: 0% can touch the screen edge;
  - final position is always clamped so the rendered layer cannot cross the screen boundary.
- Random position every flash:
  - new position for every repetition;
  - inset screen margin;
  - collision avoidance against fixed layers and previously placed random layers;
  - least-overlap fallback when a collision-free layout is physically impossible.
- Oversized text/images are reduced to an effective per-monitor render size rather than being clipped off-screen. The configured source values are preserved.
- Multi-monitor support and monitor hot-plug handling.
- True click-through overlay with no keyboard focus.
- Import/export of the complete JSON configuration.
- Atomic auto-save, login autostart, diagnostics and rotating logs.

> JPEG has no per-pixel alpha channel. JPEG layers still support whole-layer opacity.

## Supported environment

Target: **Fedora KDE Plasma on Wayland / KWin**.

The application intentionally does not fall back to an ordinary always-on-top window when layer-shell is unavailable.

## Install / update on Fedora

Clone:

```bash
git clone https://github.com/Neb963/python-subliminal-app.git
cd python-subliminal-app
./install.sh
```

If the native Fedora packages are already installed:

```bash
./install.sh --skip-packages
```

Verify:

```bash
~/.local/bin/subliminal --version
~/.local/bin/subliminal --diagnose
```

Then launch:

```bash
~/.local/bin/subliminal
```

If you use GitHub's downloaded ZIP instead of a Git clone, quit the currently running application completely, replace/extract the new source folder, and run `./install.sh --skip-packages` from the newly extracted folder.

## Editor

### Library

The left pane contains folders and scenes.

- **+ Folder** creates an organizational folder.
- **+ Scene** creates a scene in the selected/current folder.
- **Selected name** renames the selected folder or scene.
- **Duplicate** duplicates a scene.
- Deleting a folder moves its scenes to **Unfiled** rather than deleting those scenes.
- The Folder selector above the canvas moves the current scene to another folder.

Folders are metadata only. The render model remains `Scene → Layers`.

Folder selection/movement is deliberately isolated from renderer rebuilding. The folder dropdown uses one persistent GTK model and list relocation is deferred until the dropdown's own selection callback has completed.

### Canvas

The center pane previews the selected scene.

The preview is now hidden until its first complete layout is calculated. Property edits are debounced, so intermediate children at `(0, 0)` are never intentionally exposed.

**Reroll preview** chooses another randomized placement without modifying saved fixed coordinates.

### Layers / Properties

Every text/image layer has an independent editable **Name**.

Position can be either:

- fixed Anchor + X/Y + offsets; or
- **Random → New position on every flash**.

Visual property edits invalidate only the currently edited scene's renderer rather than rebuilding every scene on every monitor.

## Text background

Enable:

```text
Background
☑ Colored background
```

Then configure:

- background RGBA color;
- background alpha through that color;
- padding in pixels.

The complete padded background box is treated as the layer's geometry. Therefore it participates in screen-boundary enforcement and random collision avoidance.

Layer opacity is applied to the complete text layer, including its background.

## Text alignment

Alignment choices:

```text
Left
Center
Right
```

Alignment affects line arrangement *inside* the text box. It is intentionally independent from:

- anchor;
- X/Y position;
- offsets;
- random placement.

For example, a layer may be anchored at the bottom-right of the screen while its multiline text is center-aligned.

## Screen-safe layout

The renderer follows one invariant:

> Every visible layer's final outer rectangle must fit inside its usable monitor/canvas rectangle.

The sequence is:

```text
determine actual canvas/monitor allocation
        ↓
derive effective content size
        ↓
fit oversized content
        ↓
calculate anchor/random position
        ↓
clamp to valid bounds
        ↓
validate rectangle
        ↓
reveal
```

For the real overlay, the native window maps at opacity 0. Layout is recalculated against the actual mapped GTK allocation, and only then is the overlay revealed and frame counting started. This avoids an incorrect first visible frame under display scaling.

During breaks the layer-shell surface is fully unmapped. That is intentional: it prevents KWin from retaining the previous committed overlay buffer.

### Large media

Raster media is decoded no larger than the target monitor/preview limit. This applies to PNG/JPEG/WebP/GIF, including Auto sizing.

SVG rasterization is likewise bounded before allocating its GdkPixbuf.

The media cache is LRU-bounded by both entry count and approximate decoded memory to prevent repeated image-size editing from growing memory indefinitely.

## Timing

Flash duration is frame-based rather than pretending the compositor can provide arbitrary sub-frame millisecond timing.

| Refresh | 1 frame | 2 frames | 3 frames |
| --- | ---: | ---: | ---: |
| 60 Hz | 16.67 ms | 33.33 ms | 50.00 ms |
| 120 Hz | 8.33 ms | 16.67 ms | 25.00 ms |
| 144 Hz | 6.94 ms | 13.89 ms | 20.83 ms |

The **break after flash** remains ordinary wall-clock seconds.

## Import / export

**Import** and **Export** in the top bar operate on the complete JSON configuration:

- folders;
- scene membership;
- scene/layer names;
- text/image properties;
- background/alignment;
- fixed/random positioning;
- timing;
- display selection;
- startup preferences.

Image files themselves are not embedded. Image layers retain filesystem paths.

Schema 4/v1.3 configurations are automatically migrated to schema 5; text backgrounds default off and alignment defaults to left.

## Configuration and logs

Configuration:

```text
~/.config/subliminal/config.json
```

Logs:

```text
~/.local/state/subliminal/subliminal.log
```

Debug overlay lifecycle:

```bash
subliminal --debug
```

## Development / verification

Core tests:

```bash
python3 -m pytest
```

CI performs two independent jobs.

The core job covers:

- config migrations;
- import/export;
- scheduler lifecycle;
- thousands of randomized layout/bounds combinations;
- oversized/tiny geometry;
- Python compilation;
- shell syntax.

The Fedora runtime job installs the native GTK stack and runs a live GTK session under Xvfb. Its smoke test exercises:

- repeated folder switching;
- repeated font-family changes through the actual `Gtk.FontDialogButton` signal path;
- debounced editor callbacks;
- huge fonts and background padding;
- huge positive/negative offsets;
- oversized images;
- randomized layout rerolls;
- actual `Gtk.Fixed` child allocations staying within the canvas.

KWin-specific layer-shell composition itself still requires a real Plasma Wayland session and cannot be validated by Xvfb.

## Architecture

```text
Gtk.Application
    └─ AppController
       ├─ ConfigStore
       ├─ Scheduler
       ├─ GTK editor
       │   ├─ Library
       │   ├─ Canvas
       │   └─ Layers / Properties
       └─ OverlayManager
          └─ OverlayWindow per monitor
             └─ SceneView
                ├─ TextLayerWidget
                └─ AnimatedPicture
```

Folders never enter the render tree:

```text
Scene
├── TextLayer
├── ImageLayer
└── ...
```

## Uninstall

Preserve configuration:

```bash
./uninstall.sh
```

Remove app, config and logs:

```bash
./uninstall.sh --purge
```

## Scope

The project currently targets KDE Plasma/Wayland first. It does not attempt GNOME/Mutter, X11 production overlays, Windows, macOS, video/audio layers, cloud sync or a web frontend.
