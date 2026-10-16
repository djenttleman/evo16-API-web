#!/bin/bash
# Instalador de «EVO 16 Remote» — la app de barra de menú que enciende/apaga el servicio.
#
# Cómo usarlo: doble clic en el Finder (o `./install.command` desde la Terminal).
#
# Hace tres cosas:
#   1. deja EVO 16 Remote.app en ~/Applications  (la usa del zip de la release o la compila del repo)
#   2. registra el esquema de URL evo16remote://  (así otras apps pueden pedirle encendido/apagado)
#   3. si el repo está presente, refresca el agente del servicio y el comando ~/bin/evo16-remote
set -uo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Applications/EVO 16 Remote.app"
APP_LOCAL="$AQUI/EVO 16 Remote.app"          # caso release: el .app viene al lado de este script
REPO="$HOME/dev/evo16-web"

echo "════════════════════════════════════════════════════════"
echo "  EVO 16 Remote — instalador"
echo "════════════════════════════════════════════════════════"
echo

# ── 1. la app ────────────────────────────────────────────────────────────────────────────────
mkdir -p "$HOME/Applications"
if [ -d "$APP_LOCAL" ]; then
    echo "→ instalando la app que vino con este instalador…"
    rm -rf "$DEST"
    cp -R "$APP_LOCAL" "$DEST"
elif [ -x "$REPO/menubar/build.sh" ]; then
    echo "→ no hay .app al lado; la compilo desde el repo…"
    "$REPO/menubar/build.sh" || { echo "✗ falló la compilación (¿Command Line Tools?)"; exit 1; }
else
    echo "✗ No encontré «EVO 16 Remote.app» ni el repo en $REPO."
    echo "  Bajá el .app desde la release, o cloná el repo."
    exit 1
fi
echo "  ✓ app en $DEST"

# ── 2. registrar el esquema de URL ───────────────────────────────────────────────────────────
LSREG="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
[ -x "$LSREG" ] && "$LSREG" -f "$DEST" >/dev/null 2>&1 && echo "  ✓ esquema evo16remote:// registrado"

# ── 3. el servicio (si está el repo) ─────────────────────────────────────────────────────────
echo
if [ -d "$REPO" ]; then
    echo "→ repo encontrado en $REPO: refresco el agente del servicio…"
    if [ -f "$REPO/bin/evo16-remote" ]; then
        mkdir -p "$HOME/bin"
        cp "$REPO/bin/evo16-remote" "$HOME/bin/evo16-remote"
        chmod +x "$HOME/bin/evo16-remote"
        echo "  ✓ ~/bin/evo16-remote actualizado"
        "$HOME/bin/evo16-remote" install && echo "  ✓ agente del servicio instalado"
    fi
else
    echo "⚠️  No encontré el repo en $REPO (ahí vive el servicio que habla con el equipo)."
    echo "   La app funciona, pero sin el repo no puede encender nada."
fi

echo
echo "════════════════════════════════════════════════════════"
echo "  Listo. Para usarla:"
echo
echo "    1) abrí la app:            open \"$DEST\""
echo "       (si no ves el ícono, puede estar escondido por un ocultador de menú)"
echo "    2) para que arranque sola: Ajustes → General → Ítems de inicio → +"
echo "    3) otras apps pueden pedirle encender/apagar así:"
echo "         open -g \"evo16remote://start\""
echo "         open -g \"evo16remote://stop\""
echo
echo "  El servicio (API/UI en el puerto 3000) también se maneja por Terminal:"
echo "    ~/bin/evo16-remote start | stop | status | url"
echo "════════════════════════════════════════════════════════"
