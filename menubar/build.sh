#!/bin/bash
# Build an isolated development app; --release bundles Python + API + helper.
# --install explicitly replaces ~/Applications; --open opens the build result.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SRC/.." && pwd)"
PY="${EVO16_PYTHON:-$(command -v python3)}"
OUT="${EVO16_BUILD_DIR:-$REPO/build}"
APP="$OUT/EVO 16 Remote.app"
RELEASE=0
INSTALL=0
OPEN=0
for arg in "$@"; do
    case "$arg" in
        --release) RELEASE=1 ;;
        --install) INSTALL=1 ;;
        --open) OPEN=1 ;;
        *) echo "Opción desconocida: $arg" >&2; exit 1 ;;
    esac
done
# Build only inside the selected output directory; never destroy the installed app by default.
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
make -C "$REPO/mac-evo16"
cp "$SRC/Info.plist" "$APP/Contents/Info.plist"
swiftc -O -swift-version 5 -target "$(uname -m)-apple-macosx13.0" -framework AppKit -framework Network -framework Security \
    -o "$APP/Contents/MacOS/EVO16RemoteApp" "$SRC/main.swift"
if [ "$RELEASE" -eq 1 ]; then
    "$PY" -m PyInstaller --noconfirm --distpath "$OUT/frozen" --workpath "$OUT/pyinstaller" "$REPO/EVO16-Remote.spec"
    rm -rf "$APP/Contents/Resources/service"
    cp -R "$OUT/frozen/EVO16Service" "$APP/Contents/Resources/service"
    rm -f "$APP/Contents/Resources/Development.plist"
else
    "$PY" - "$APP/Contents/Resources/Development.plist" "$REPO" <<'PY'
import plistlib, sys
with open(sys.argv[1], 'wb') as f:
    plistlib.dump({'repo': sys.argv[2], 'python': sys.executable}, f)
PY
    rm -rf "$APP/Contents/Resources/service"
fi
codesign --force --deep --sign - "$APP"
if [ "$INSTALL" -eq 1 ]; then
    DEST="$HOME/Applications/EVO 16 Remote.app"
    mkdir -p "$HOME/Applications"
    ditto "$APP" "$DEST"
    APP="$DEST"
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"
fi
printf 'App compilada: %s\n' "$APP"
if [ "$OPEN" -eq 1 ]; then open "$APP"; fi
