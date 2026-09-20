# Subliminal

A native Fedora KDE Plasma **Wayland** application that flashes configurable text and images in a true click-through compositor overlay.

The overlay is implemented with GTK4 + `gtk4-layer-shell`: it stays mapped, never takes keyboard focus, and uses an empty GDK input region so mouse/touch input continues to the application underneath.

## Features

- Frame-synchronized flash duration: choose an integer number of real display frames, with detected monitor Hz and ms/frame shown in the UI.
- Adjustable wall-clock break between flashes.
- Multiple scenes, selected randomly or sequentially.
- Multiple mixed layers per scene: text and images can appear together.
- Text: any Unicode/emoji text, installed font, pixel size, color/alpha, bold, italic, underline, and 0–100% opacity.
- Images: PNG, JPEG, WebP, SVG, GIF; source alpha where the format supports it plus 0–100% layer opacity.
- Animated GIF and animated WebP playback.
- 9-point anchoring, normalized X/Y position, and pixel offsets.
- Per-monitor overlays; all displays or a selected set; monitor hot-plug handling.
- Persistent layer-shell surfaces rather than repeatedly creating/destroying topmost windows.
- Live GTK preview, Start/Pause/Stop/Test controls, JSON auto-save, login autostart, and rotating logs.
- `--diagnose` command for Wayland/layer-shell/monitor checks.

> JPEG has no per-pixel alpha channel. JPEG layers still support whole-layer opacity.

## Supported environment

Target: **Fedora KDE Plasma on Wayland / KWin**.

This deliberately does not fall back to an ordinary always-on-top window. If layer-shell is unavailable (for example an X11 session or a compositor without the protocol), the GUI opens but overlay Start/Test is disabled with a clear warning.

## Install on Fedora

Clone the repository and run:

```bash
git clone https://github.com/Neb963/python-subliminal-app.git
cd python-subliminal-app
./install.sh
```

The installer uses `dnf` for the native runtime packages, then installs the app for the current user under `~/.local/share/subliminal`, creates `~/.local/bin/subliminal`, and adds a KDE application-menu desktop entry.

If the Fedora packages are already installed:

```bash
./install.sh --skip-packages
```

Then launch **Subliminal** from the KDE application menu, or run:

```bash
subliminal
```

If `~/.local/bin` is not in your shell PATH, run `~/.local/bin/subliminal` directly or log out/in after installation.

## Verify overlay support

Before troubleshooting the UI, run:

```bash
subliminal --diagnose
```

Expected important lines on the target environment are similar to:

```text
XDG_SESSION_TYPE: wayland
GDK display: OK (...)
Layer shell: OK
Monitors: 1
```

If `Layer shell` is unavailable, confirm that the Plasma session is **Wayland**, not Plasma (X11).

## Using the app

1. Open **Content**. The default scene contains `Focus 🎯`.
2. Add text or image layers. A scene can contain any mixture of both.
3. Select each layer and set its font/image size, opacity, anchor, X/Y percentage and offsets.
4. Open **Timing**. Set **Visible for (frames)** and **Break after flash (seconds)**. The detected refresh rate and conversion to milliseconds are shown automatically.
5. Open **Displays** to target all monitors or selected connectors.
6. Use **Test flash** while stopped/paused, then **Start**.
7. Closing the settings window hides it while the scheduler continues. Launch Subliminal again to reopen it. Use **Quit** to exit the process.

Flash duration is intentionally **frame-based**. For example: at 60 Hz, 1 frame ≈ 16.67 ms, 2 frames ≈ 33.3 ms, and 3 frames ≈ 50 ms; at 144 Hz, 1 frame ≈ 6.94 ms. The overlay uses GTK's compositor-driven frame clock and hides only after the configured number of display-frame ticks. The break between flashes remains ordinary wall-clock seconds.

## Configuration and logs

Configuration:

```text
~/.config/subliminal/config.json
```

The file is written atomically. If it becomes invalid/corrupt, it is renamed to `config.corrupt-<timestamp>.json` and a default configuration is created.

Logs:

```text
~/.local/state/subliminal/subliminal.log
```

## Run directly from a checkout

Install the Fedora dependencies first:

```bash
sudo dnf install python3 python3-gobject gtk4 gtk4-layer-shell python3-cairo python3-pillow gdk-pixbuf2 librsvg2
```

Then:

```bash
./run.sh
```

or:

```bash
./run.sh --diagnose
```

## Tests

The core model/config/scheduler tests do not require a graphical session:

```bash
python3 -m pytest
```

The compositor integration must be tested in an actual Plasma Wayland session because a headless CI runner cannot validate KWin layer-shell stacking, input pass-through, fullscreen interaction, or monitor hot-plug behavior.

## Uninstall

```bash
./uninstall.sh
```

This preserves your configuration. To remove configuration and logs as well:

```bash
./uninstall.sh --purge
```

## Architecture

The process is intentionally simple:

```text
Gtk.Application
    └─ AppController
       ├─ ConfigStore (JSON)
       ├─ Scheduler (GLib timers)
       ├─ GTK settings/editor window
       └─ OverlayManager
          ├─ OverlayWindow / monitor 1
          └─ OverlayWindow / monitor 2
             └─ Gtk.Stack
                ├─ blank
                └─ SceneView
                   ├─ TextLayer -> Gtk.Label/Pango
                   └─ ImageLayer -> Gtk.Picture/Gdk.Texture
```

Overlay windows are created once and kept mapped. A flash switches the stack from `blank` to the chosen scene; after the requested duration it switches back to `blank`. Mouse input is not caught and ignored by the application—the overlay surface itself has an empty input region.

## Development scope

The project intentionally targets KDE Plasma/Wayland first. It does not currently attempt GNOME/Mutter, X11, Windows, macOS, video/audio layers, cloud synchronization, or a web UI.
