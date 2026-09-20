#!/usr/bin/env bash
set -euo pipefail
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
rm -rf "$DATA_HOME/subliminal"
rm -f "$HOME/.local/bin/subliminal"
rm -f "$DATA_HOME/applications/io.github.neb963.Subliminal.desktop"
rm -f "$CONFIG_HOME/autostart/io.github.neb963.Subliminal.desktop"
if [[ "${1:-}" == "--purge" ]]; then
    rm -rf "$CONFIG_HOME/subliminal"
    rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/subliminal"
    echo "Removed application, configuration, and logs."
else
    echo "Removed application. Configuration was preserved at $CONFIG_HOME/subliminal."
    echo "Run ./uninstall.sh --purge to remove configuration and logs too."
fi
