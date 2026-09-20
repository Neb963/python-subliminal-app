#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export SUBLIMINAL_EXECUTABLE="$ROOT/run.sh"
exec /usr/bin/python3 -m subliminal "$@"
