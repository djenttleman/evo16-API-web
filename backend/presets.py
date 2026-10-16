"""Validated v2 profiles; legacy byte-valued gains migrate in memory without changing hardware."""
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from backend.config import DATA_DIR

PRESETS_DIR = Path(os.environ.get("EVO16_PRESETS_DIR", DATA_DIR / "presets"))
NAME_RE = re.compile(r"^[A-Za-z0-9 _\-áéíóúÁÉÍÓÚñÑ()]{1,64}$")
RESERVED = {"import", "export"}
DI_CHANNELS = {1, 2, 9, 10, 17, 18}


class PresetError(ValueError):
    pass


def valid_name(name):
    return isinstance(name, str) and bool(NAME_RE.fullmatch(name.strip())) and name.strip().lower() not in RESERVED


def _path(name):
    if not valid_name(name):
        raise PresetError("Nombre inválido: letras, números, espacios, guiones o paréntesis; máximo 64")
    path = PRESETS_DIR / f"{name.strip()}.json"
    if path.is_symlink():
        raise PresetError("No se permiten enlaces simbólicos como perfiles")
    return path


def validate_channels(channels, legacy=False):
    if not isinstance(channels, list) or len(channels) != 24:
        raise PresetError("Un perfil completo debe contener exactamente los 24 canales")
    out = []
    for c in channels:
        if not isinstance(c, dict):
            raise PresetError("Canal mal formado")
        ch, gain = c.get("channel"), c.get("gain")
        if type(ch) is not int or not 1 <= ch <= 24:
            raise PresetError("Canal fuera de rango")
        if type(gain) not in (int, float) or not float(gain).is_integer():
            raise PresetError("La ganancia debe ser un número entero de dB")
        gain = int(gain) - (8 if legacy else 0)
        if not -8 <= gain <= 50:
            raise PresetError("Ganancia fuera de rango: -8…50 dB")
        if any(type(c.get(k)) is not bool for k in ("mute", "phantom", "linked")):
            raise PresetError("Mute, phantom y linked deben ser booleanos")
        instrument = c.get("instrument")
        if ch in DI_CHANNELS and type(instrument) is not bool:
            raise PresetError("Falta un estado DI válido")
        if ch not in DI_CHANNELS and instrument not in (False, None):
            raise PresetError("El canal no tiene hardware DI")
        a = ch if ch % 2 else ch - 1
        out.append({"channel": ch, "gain": gain, "mute": c["mute"],
                    "phantom": c["phantom"], "linked": c["linked"],
                    "instrument": instrument if ch in DI_CHANNELS else None,
                    "linkPair": [a, a + 1]})
    by_ch = {c["channel"]: c for c in out}
    if len(by_ch) != 24:
        raise PresetError("El perfil contiene canales duplicados")
    for a in range(1, 25, 2):
        left, right = by_ch[a], by_ch[a + 1]
        if left["linked"] != right["linked"]:
            raise PresetError(f"Link inconsistente en el par {a}-{a + 1}")
        if left["linked"] and (left["gain"] != right["gain"] or left["instrument"] != right["instrument"]):
            raise PresetError(f"El par {a}-{a + 1} está linkeado pero tiene valores diferentes")
    return sorted(out, key=lambda c: c["channel"])


def normalized(data):
    if not isinstance(data, dict):
        raise PresetError("El perfil debe ser un objeto JSON")
    version = data.get("formatVersion", 1)
    if type(version) is not int or version not in (1, 2):
        raise PresetError("Versión de perfil no soportada")
    if version == 2 and data.get("gainEncoding") != "db":
        raise PresetError("El perfil v2 debe declarar gainEncoding=db")
    return {**data, "formatVersion": 2, "gainEncoding": "db",
            "channels": validate_channels(data.get("channels"), legacy=version == 1)}


def load(name):
    path = _path(name)
    try:
        return normalized(json.loads(path.read_text()))
    except (OSError, ValueError, TypeError) as e:
        raise PresetError(f"No se pudo leer «{name}»: {e}") from e


def list_presets():
    if not PRESETS_DIR.is_dir():
        return []
    out = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        item = {"name": path.stem}
        try:
            data = load(path.stem)
            item.update(savedAt=data.get("savedAt"), channels=len(data["channels"]), formatVersion=2)
        except PresetError:
            item["error"] = "Perfil inválido o ilegible"
        out.append(item)
    return out


def save(name, channels, device="Audient EVO 16"):
    path = _path(name)
    data = {"formatVersion": 2, "gainEncoding": "db", "name": name.strip(),
            "savedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "device": device, "channels": validate_channels(channels)}
    PRESETS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".preset-", dir=PRESETS_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return data


def import_data(data, name=None):
    data = normalized(data)
    return save(name or data.get("name"), data["channels"], data.get("device", "Audient EVO 16"))


def delete(name):
    path = _path(name)
    if not path.is_file():
        raise PresetError("El perfil no existe")
    path.unlink()
    return True
