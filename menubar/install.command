#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Applications/EVO 16 Remote.app"
if [ -d "$HERE/EVO 16 Remote.app" ]; then
    mkdir -p "$HOME/Applications"
    ditto "$HERE/EVO 16 Remote.app" "$DEST"
else
    "$HERE/build.sh" --release --install
fi
mkdir -p "$HOME/bin"
if [ -f "$HERE/../bin/evo16-remote" ]; then
    cp "$HERE/../bin/evo16-remote" "$HOME/bin/evo16-remote"
    chmod +x "$HOME/bin/evo16-remote"
fi
printf 'Instalada: %s\n' "$DEST"
printf 'Abre la app. En Preferencias están la conexión, la integración y el diagnóstico.\n'
