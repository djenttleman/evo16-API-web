#!/bin/bash
# Compila y arma «EVO 16 Remote.app» (barra de menú) en ~/Applications.
#
#   ./menubar/build.sh            compila y reemplaza la app
#   ./menubar/build.sh --open     además la abre
#
# Requiere las Command Line Tools (swiftc). No necesita Xcode.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Applications/EVO 16 Remote.app"
BIN="$APP/Contents/MacOS/EVO16RemoteApp"

echo "compilando…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$SRC/Info.plist" "$APP/Contents/Info.plist"

# -swift-version 5: evita los chequeos estrictos de concurrencia de Swift 6 (no hacen falta acá)
swiftc -O -swift-version 5 -framework AppKit -o "$BIN" "$SRC/main.swift"

codesign --force --sign - "$APP" >/dev/null 2>&1 && echo "firmada (ad-hoc)" || echo "(sin firma)"

# Registra la app y su esquema de URL en LaunchServices
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f "$APP" >/dev/null 2>&1 || true

echo "listo: $APP"
echo "  agregala a «Iniciar sesión» si querés que arranque con el sistema."
echo "  otras apps pueden llamarla:  open -g \"evo16remote://start\""

if [ "${1:-}" = "--open" ]; then
    open "$APP"
    echo "  abierta (mirá la barra de menú)"
fi
