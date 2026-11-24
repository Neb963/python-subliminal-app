# Subliminal

Subliminal is a native Python/GTK desktop application for Fedora KDE Plasma on **Wayland/KWin**. It flashes configurable text and images through a true click-through layer-shell overlay.

The compositor-facing implementation remains deliberately small: GTK4 + PyGObject + `gtk4-layer-shell`. The editor is a native three-pane interface: **Library → Canvas → Layers / Properties**.

## Current release

**1.6.0**

Version 1.6.0 integrates the responsive/native UI refinement pass with comprehensive stability, overlay, rendering, config, and lifecycle bug fixes. It keeps the top toolbar on one stable line across the supported window range, separates navigation buttons cleanly, prevents pane/header clipping in non-maximized windows, contains pathological long text inside preview/overlay bounds, minimizes routine scrollbars, compacts and aligns the Properties inspector, makes long names/paths safe, and makes the editor preview follow the target monitor's aspect ratio and scale — while preserving all audit fixes for overlay lifecycle, HiDPI media rasterization, Pango alpha handling, async dialog safety, atomic persistence, and clean GTK4 shutdown.

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
- The footer shows **Scene name** or **Folder name** according to the current selection.
- **Duplicate** duplicates a scene.
- Deleting a folder moves its scenes to **Unfiled** rather than deleting those scenes.
- The Folder selector above the canvas moves the current scene to another folder.

Folders are metadata only. The render model remains `Scene → Layers`.

Folder selection/movement is deliberately isolated from renderer rebuilding. The folder dropdown uses one persistent GTK model and list relocation is deferred until the dropdown's own selection callback has completed.

### Canvas

The center pane previews the selected scene using the active/selected monitor's aspect ratio and dimensions.

The preview is hidden until its first complete layout is calculated. Property edits are debounced, so intermediate children at `(0, 0)` are never intentionally exposed. Preview scale is derived from the real preview allocation and target monitor rather than using a fixed editor scale.

**Reroll** chooses another randomized placement without modifying saved fixed coordinates.

### Layers / Properties

Every text/image layer has an independent editable **Name**.

The inspector uses compact native sections rather than one wide right-aligned label column. Related controls are paired where that reduces space without sacrificing clarity; optional background controls are revealed only when enabled.

Position can be either:

- fixed Anchor + X/Y + offsets; or
- **Random each flash**.

Visual property edits invalidate only the currently edited scene's renderer rather than rebuilding every scene on every monitor.

The Layers list grows naturally for small scenes and scrolls only when the layer count actually requires it. Properties use vertical scrolling only when the available height is genuinely insufficient; horizontal scrolling is disabled by design.


### Responsive/native layout

The main editor is designed around a supported minimum window size of **1000×650**.

- Library and Inspector keep compact stable widths while Canvas absorbs most window growth.
- Long folder, scene and layer names are ellipsized with full-value tooltips rather than increasing pane requisitions.
- Long image paths stay contained inside the File field.
- The top toolbar remains one row at every supported window width; it no longer reparents controls into a second row.
- Navigation buttons are independent native buttons with deliberate spacing rather than a zero-gap pseudo-segmented group.
- Import and Export remain textual; Start/Pause/Stop/Test/Quit use compact native symbolic controls with tooltips.
- Runtime state reserves a stable width. **Running** stays in the same position while the current waiting/flashing phase is available in the tooltip, so phase changes never move neighboring controls.
- Canvas-header controls are allocation-checked and preview drawing is clipped at the preview/scene boundary so long content cannot paint into adjacent panes or header chrome.
- Hidden Timing/Displays/Settings pages do not dictate the active Editor page's width.


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

`SceneView` also clips child drawing at its own allocation. Extremely long unbroken text uses a last-resort character-wrap fitting pass so GTK cannot retain a natural child allocation wider than the preview/overlay surface.

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
- repeated font-family changes through the asynchronous native `Gtk.FontDialog` family chooser path;
- debounced editor callbacks;
- huge fonts and background padding;
- huge positive/negative offsets;
- oversized images;
- randomized layout rerolls;
- actual `Gtk.Fixed` child allocations staying within the canvas;
- responsive editor allocations at 1000×650, 1100×700, 1324×1010, 1600×900 and 1920×1080;
- single-row toolbar geometry at every supported width, deliberate navigation gaps and phase-stable button positions;
- normal and expanded text properties, image properties and many-layer scrolling;
- pathological long names, paths, monitor descriptions and configuration paths;
- a larger 16px application font to catch theme/font-dependent requisition regressions.

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
