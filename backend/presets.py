"""Perfiles de preamps del EVO 16 — un archivo JSON por perfil.

Un perfil guarda el estado de los 24 canales (gain, 48V, DI, link de par y mute) tal como estaban
en el equipo en un momento dado, para poder reinyectarlo por escena.

Almacenamiento: archivos en disco, uno por perfil. Por defecto en la carpeta de datos del usuario
de macOS (sobrevive a limpiezas del repo y no ensucia `git status`); se puede cambiar con la
variable de entorno EVO16_PRESETS_DIR — por ejemplo para versionarlos dentro del proyecto:

    EVO16_PRESETS_DIR="/Users/djenttleman/dev/evo16-web/presets" \\
      /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 backend/main.py

Formato del archivo (JSON, legible y editable a mano):

    {
      "name": "Sala chica",
      "savedAt": "2026-10-15T19:40:12-03:00",
      "device": "Audient EVO 16",
      "channels": [
        {"channel": 1, "gain": 28, "phantom": false, "mute": false,
         "instrument": false, "linked": false, "linkPair": [1, 2]},
        ...
      ]
    }

Los canales se guardan SIEMPRE los 24 (aunque el canal no tenga DI, `instrument` va en false):
así un perfil es un estado completo y aplicarlo no deja nada a medias.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

# Carpeta de perfiles: por defecto ~/Library/Application Support/EVO16Remote/presets
PRESETS_DIR = Path(
    os.environ.get("EVO16_PRESETS_DIR")
    or (Path.home() / "Library" / "Application Support" / "EVO16Remote" / "presets")
)

# Nombres seguros: letras, números, espacios y unos pocos signos. Sin "/" ni "..": el nombre es
# además el nombre del archivo, así que un nombre con barras podría escribir fuera de la carpeta.
NAME_RE = re.compile(r"^[A-Za-z0-9 _\-áéíóúÁÉÍÓÚñÑ()]{1,64}$")

# Reservados para que no choquen con las rutas /api/presets/import y .../export
RESERVED = {"import", "export"}


class PresetError(ValueError):
    """Nombre inválido, perfil inexistente o archivo corrupto."""


def valid_name(name: str) -> bool:
    n = (name or "").strip()
    # "import"/"export" se rechazan: son rutas de la API, un perfil con ese nombre sería confuso.
    return bool(isinstance(name, str) and NAME_RE.match(n) and n.lower() not in RESERVED)


def _path(name: str) -> Path:
    if not valid_name(name):
        raise PresetError(
            "Nombre inválido: usá letras, números, espacios, guiones o paréntesis (máx. 64)."
        )
    return PRESETS_DIR / f"{name.strip()}.json"


def list_presets() -> list[dict]:
    """Perfiles guardados, ordenados por fecha de modificación (el más nuevo primero)."""
    if not PRESETS_DIR.is_dir():
        return []
    out = []
    for f in sorted(PRESETS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        item = {"name": f.stem, "file": str(f), "savedAt": None, "channels": None}
        try:
            data = json.loads(f.read_text())
            item["savedAt"] = data.get("savedAt")
            item["channels"] = len(data.get("channels") or [])
        except Exception:
            item["error"] = "archivo ilegible"
        out.append(item)
    return out


def load(name: str) -> dict:
    f = _path(name)
    if not f.is_file():
        raise PresetError(f"No existe el perfil «{name}».")
    try:
        data = json.loads(f.read_text())
    except Exception as e:
        raise PresetError(f"El perfil «{name}» está corrupto: {e}") from e
    if not isinstance(data.get("channels"), list) or not data["channels"]:
        raise PresetError(f"El perfil «{name}» no tiene canales.")
    return data


def save(name: str, channels: list[dict], device: str = "Audient EVO 16") -> dict:
    """Guarda (o sobrescribe) un perfil con el estado de los canales dado."""
    f = _path(name)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "name": name.strip(),
        "savedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "device": device,
        "channels": channels,
    }
    # Escritura atómica: si se corta a mitad, no queda un perfil a medias.
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(f)
    return data


def delete(name: str) -> bool:
    f = _path(name)
    if not f.is_file():
        raise PresetError(f"No existe el perfil «{name}».")
    f.unlink()
    return True


def export_preset(name: str, dest: str, overwrite: bool = False) -> Path:
    """Copia el perfil a un archivo en la ubicación que indique el usuario.

    `dest` puede venir con `~`; el directorio destino se crea si falta. Si el archivo ya existe
    se rechaza salvo `overwrite=True` (exportar nunca debe pisar algo por accidente).
    """
    data = load(name)                       # valida que exista y que sea legible
    dst = Path(dest).expanduser()
    if dst.suffix.lower() != ".json":
        raise PresetError("El destino tiene que ser un archivo .json.")
    if dst.exists() and not overwrite:
        raise PresetError(f"Ya existe {dst}. Mandá overwrite=true para reemplazarlo.")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        tmp.replace(dst)
    except OSError as e:
        raise PresetError(f"No se pudo escribir en {dst}: {e}") from e
    return dst


def import_preset(src: str, name: str | None = None) -> dict:
    """Trae un perfil desde un archivo de cualquier ubicación al banco local.

    El nombre sale de `name` si se pasa, si no del `name` dentro del archivo, y si no del nombre
    del archivo. Valida la estructura antes de guardar (un JSON cualquiera no entra).
    """
    p = Path(src).expanduser()
    if not p.is_file():
        raise PresetError(f"No existe el archivo {p}.")
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        raise PresetError(f"{p} no es un JSON válido: {e}") from e

    canales = data.get("channels")
    if not isinstance(canales, list) or not canales:
        raise PresetError("El archivo no tiene una lista de canales (¿es un perfil de preamps?).")
    for c in canales:
        if not isinstance(c, dict) or "channel" not in c:
            raise PresetError("El archivo tiene canales mal formados (falta 'channel').")

    destino = name or data.get("name") or p.stem
    return save(str(destino), canales, device=data.get("device", "Audient EVO 16"))
