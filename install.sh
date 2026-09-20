#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/subliminal"
BIN_DIR="$HOME/.local/bin"
BIN_PATH="$BIN_DIR/subliminal"
DESKTOP_DIR="$DATA_HOME/applications"
DESKTOP_PATH="$DESKTOP_DIR/io.github.neb963.Subliminal.desktop"

if [[ "${1:-}" != "--skip-packages" ]]; then
    packages=(python3 python3-gobject gtk4 gtk4-layer-shell python3-cairo python3-pillow gdk-pixbuf2 librsvg2)
    echo "Installing Fedora runtime packages: ${packages[*]}"
    if [[ $EUID -eq 0 ]]; then
        dnf install -y "${packages[@]}"
    else
        sudo dnf install -y "${packages[@]}"
    fi
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
rm -rf "$APP_DIR/subliminal"
cp -a "$ROOT/subliminal" "$APP_DIR/subliminal"
cp "$ROOT/pyproject.toml" "$APP_DIR/pyproject.toml"

cat > "$BIN_PATH" <<EOF
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$APP_DIR"
export PYTHONPATH="\$APP_DIR\${PYTHONPATH:+:\$PYTHONPATH}"
export SUBLIMINAL_EXECUTABLE="$BIN_PATH"
exec /usr/bin/python3 -m subliminal "\$@"
EOF
chmod +x "$BIN_PATH"

cat > "$DESKTOP_PATH" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Subliminal
Comment=Click-through text and image overlay scheduler
Exec="$BIN_PATH"
TryExec=$BIN_PATH
Icon=preferences-desktop-display
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo
echo "Installed Subliminal."
echo "Launcher: $BIN_PATH"
echo "Desktop entry: $DESKTOP_PATH"
echo
echo "Run: subliminal"
echo "Check overlay support: subliminal --diagnose"
echo
echo "If '$BIN_DIR' is not in PATH, start it with: $BIN_PATH"
