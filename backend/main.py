"""EVO 16 Web API — FastAPI server for remote preamp control."""

import sys
import os
import tempfile
import webbrowser
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from backend.service import Evo16Service
from backend.presets import (
    PRESETS_DIR,
    PresetError,
    delete as delete_preset,
    list_presets,
    load as load_preset,
    save as save_preset,
)

app = FastAPI(title="EVO 16 Remote", version="1.0.0")


PID_FILE = Path(tempfile.gettempdir()) / "evo16-remote.pid"
SERVER_PORT = 3000


def _cmdline(pid: int) -> str:
    """Línea de comandos de un pid (para no matar un proceso ajeno si el pid se recicló)."""
    try:
        r = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int, why: str, require: str | None = None) -> bool:
    """Cierra un proceso: SIGTERM y, si no muere en ~3 s, SIGKILL.

    Cerrar limpio importa: el server libera el USB (helper mac-evo16) recién en su shutdown, así
    que un SIGKILL seco deja el dispositivo tomado y la instancia nueva no puede arrancar.
    `require`: si se pasa, sólo mata si esa cadena aparece en la línea de comandos del pid
    (evita matar un proceso cualquiera por un pid reciclado).
    """
    import signal
    import time

    if pid <= 0 or pid == os.getpid() or not _pid_alive(pid):
        return False
    if require and require not in _cmdline(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return False
    for _ in range(30):
        time.sleep(0.1)
        if not _pid_alive(pid):
            print(f"🧹 {why} (pid {pid}) cerrada limpiamente")
            return True
    try:
        os.kill(pid, signal.SIGKILL)
        print(f"🧹 {why} (pid {pid}) no respondió a SIGTERM: SIGKILL")
    except Exception:
        pass
    return True


def _cleanup_conflicts() -> None:
    """Deja SIEMPRE una sola instancia: mata las viejas antes de tomar el puerto.

    Cuatro frentes, en orden:
      1. el pid anotado en /tmp/evo16-remote.pid (la instancia anterior),
      2. cualquier proceso escuchando en el puerto del server,
      3. helpers mac-evo16 huérfanos (si el server murió mal, quedan con el USB tomado y hacen
         fallar el arranque),
      4. aviso si la app oficial EVO Control tiene el equipo (esa NO se mata: es del usuario).
    """
    import signal

    # 1. la instancia anterior, si dejó su pid
    try:
        if PID_FILE.is_file():
            prev = int((PID_FILE.read_text().strip() or "0"))
            _kill_pid(prev, "instancia anterior de evo16-remote", require="main.py")
    except Exception:
        pass

    # 2. quien tenga el puerto (sea o no nuestro)
    try:
        r = subprocess.run(["lsof", "-ti", f":{SERVER_PORT}"],
                           capture_output=True, text=True, timeout=5)
        for pid in r.stdout.split():
            _kill_pid(int(pid), f"proceso ocupando el puerto {SERVER_PORT}")
    except Exception:
        pass

    # 3. helpers mac-evo16 sueltos
    try:
        r = subprocess.run(["pgrep", "-f", "mac-evo16"],
                           capture_output=True, text=True, timeout=5)
        for pid in r.stdout.split():
            _kill_pid(int(pid), "helper mac-evo16 huérfano")
        # resto que no haya respondido a SIGTERM
        subprocess.run(["pkill", "-9", "-f", "mac-evo16"], timeout=5)
    except Exception:
        pass

    # 4. la app oficial: avisar, nunca matar
    try:
        r = subprocess.run(["pgrep", "-f", "EVO.app/Contents/MacOS/EVO"],
                           capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            print("⚠️  EVO Control está ABIERTA: es la dueña del USB. Cerrála para controlar el "
                  "hardware (el server arranca igual, pero los controles van a fallar).")
    except Exception:
        pass

    # Anotamos nuestro pid para que la próxima instancia nos encuentre
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass

# CORS for tablet access from LAN
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Device service
service: Evo16Service | None = None

# Models
class GainRequest(BaseModel):
    db: int

class MuteRequest(BaseModel):
    muted: bool

class PhantomRequest(BaseModel):
    on: bool


@app.on_event("startup")
async def startup():
    global service
    try:
        service = Evo16Service()
        service.connect()
        print("✅ EVO 16 connected")
    except Exception as e:
        print(f"⚠️  EVO 16 not available: {e}")
        print("   Is the EVO 16 connected via USB?")
        print("   Is the official EVO Control app closed?")
        print("   Web UI will show demo/simulated mode")
        service = None
    webbrowser.open("http://localhost:3000")


@app.on_event("shutdown")
async def shutdown():
    if service:
        service.disconnect()


# === REST API ===

@app.get("/api/status")
async def get_status():
    """Get full device status (gains, phantom, mutes)."""
    if service and service._connected:
        try:
            return service.get_all_status()
        except Exception as e:
            return JSONResponse({"error": str(e)}, 503)
    # Mock response for when device is not connected
    inputs = []
    for i in range(1, 25):
        a = i if i % 2 == 1 else i - 1
        inputs.append({
            "channel": i, "gain": 0.0, "mute": False, "phantom": False,
            "instrument": False, "linked": False, "linkPair": [a, a + 1],
        })
    return {
        "device": "Audient EVO 16 (DEMO MODE)",
        "inputs": inputs,
        "outputs": [
            {"pair": 1, "mute": False, "label": "Main"},
            {"pair": 2, "mute": False, "label": "Line 3-4"},
            {"pair": 3, "mute": False, "label": "Line 5-6"},
            {"pair": 4, "mute": False, "label": "Line 7-8"},
            {"pair": 5, "mute": False, "label": "Phones"},
        ],
    }


@app.post("/api/gain/{channel}")
async def set_gain(channel: int, req: GainRequest):
    """Set preamp gain for a channel (1-24, dB 0 to 50)."""
    if channel < 1 or channel > 24:
        raise HTTPException(400, "Channel must be 1-24")
    if not service or not service._connected:
        # Mock — just return success
        return {"channel": channel, "gain": req.db, "status": "mock"}
    actual = service.set_gain(channel, req.db)
    return {"channel": channel, "gain": actual, "status": "ok"}


@app.post("/api/phantom/{channel}")
async def set_phantom(channel: int, req: PhantomRequest):
    """Toggle 48V phantom power for channel (1-24)."""
    if channel < 1 or channel > 24:
        raise HTTPException(400, "Channel must be 1-24")
    if not service or not service._connected:
        return {"channel": channel, "phantom": req.on, "status": "mock"}
    service.set_phantom(channel, req.on)
    return {"channel": channel, "phantom": req.on, "status": "ok"}


@app.post("/api/mute/{channel}")
async def set_mute(channel: int, req: MuteRequest):
    """Mute/unmute an input channel (1-24)."""
    if channel < 1 or channel > 24:
        raise HTTPException(400, "Channel must be 1-24")
    if not service or not service._connected:
        return {"channel": channel, "muted": req.muted, "status": "mock"}
    service.set_mute(channel, req.muted)
    return {"channel": channel, "muted": req.muted, "status": "ok"}


# === EXPERIMENTAL API ===

class InstrRequest(BaseModel):
    on: bool

# Canales con hardware de instrumento/DI: locales 1-2 + ADAT 9-10 (ADAT1) y 17-18 (ADAT2).
# Debe coincidir con Evo16Service.INSTR_CHANNELS.
INSTRUMENT_CHANNELS = (1, 2, 9, 10, 17, 18)

@app.get("/api/instrument/{channel}")
async def get_instrument(channel: int):
    """Get instrument mode. Canales con hardware de DI: 1-2 (locales), 9-10 y 17-18 (ADAT)."""
    if channel not in INSTRUMENT_CHANNELS:
        raise HTTPException(400, f"Instrument mode only available on channels {INSTRUMENT_CHANNELS}")
    if not service or not service._connected:
        return {"channel": channel, "instrument": None, "status": "mock"}
    result = service.get_instrument(channel)
    return {"channel": channel, "instrument": result, "status": "ok"}

@app.post("/api/instrument/{channel}")
async def set_instrument(channel: int, req: InstrRequest):
    """Set instrument/DI mode. Ver service.py: CS=4 con read-modify-write del bit 1."""
    if channel not in INSTRUMENT_CHANNELS:
        raise HTTPException(400, f"Instrument mode only available on channels {INSTRUMENT_CHANNELS}")
    if not service or not service._connected:
        return {"channel": channel, "instrument": req.on, "status": "mock"}
    service.set_instrument(channel, req.on)
    return {"channel": channel, "instrument": req.on, "status": "ok"}


class LinkRequest(BaseModel):
    on: bool

# Link de par estéreo (ver service.py → LINK_CS; es CS=3 del EVO 16). El par de un canal es
# (impar, impar+1): 1-2, 3-4, 5-6, … Con el par linkeado el FIRMWARE espeja el preamp (gain, DI),
# así que el cliente NO necesita duplicar escrituras: le basta linkear y escribir en un lado.
@app.get("/api/link/{channel}")
async def get_link(channel: int):
    """Estado de link del par al que pertenece el canal (1..24)."""
    if not (1 <= channel <= 24):
        raise HTTPException(400, "Channel out of range (1-24)")
    pair = service.link_pair(channel) if service else (channel, channel)
    if not service or not service._connected:
        return {"channel": channel, "linked": False, "pair": list(pair), "status": "mock"}
    return {"channel": channel, "linked": service.get_link(channel), "pair": list(pair), "status": "ok"}

@app.post("/api/link/{channel}")
async def set_link(channel: int, req: LinkRequest):
    """Linkea/deslinkea el par del canal (escribe CS3 en ambos canales del par)."""
    if not (1 <= channel <= 24):
        raise HTTPException(400, "Channel out of range (1-24)")
    if not service or not service._connected:
        return {"channel": channel, "linked": req.on, "status": "mock"}
    pair = service.set_link(channel, req.on)
    return {"channel": channel, "linked": req.on, "pair": list(pair), "status": "ok"}


# === Perfiles de preamps (un archivo JSON por perfil; ver backend/presets.py) ===

@app.get("/api/presets")
async def get_presets():
    """Perfiles guardados + la carpeta donde viven los archivos."""
    return {"dir": str(PRESETS_DIR), "presets": list_presets()}

@app.get("/api/presets/{name}")
async def get_preset(name: str):
    """Contenido completo de un perfil (para inspeccionarlo o editarlo a mano)."""
    try:
        return load_preset(name)
    except PresetError as e:
        raise HTTPException(400, str(e))

@app.post("/api/presets/{name}")
async def save_preset_endpoint(name: str):
    """Guarda el estado ACTUAL del equipo como perfil «name» (sobrescribe si existe)."""
    if not service or not service._connected:
        raise HTTPException(503, "EVO 16 no conectada")
    try:
        channels = service.capture_state()
        data = save_preset(name, channels, device="Audient EVO 16")
    except PresetError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok", "name": data["name"], "savedAt": data["savedAt"],
            "channels": len(channels), "file": str(PRESETS_DIR / (name.strip() + ".json"))}

@app.post("/api/presets/{name}/apply")
async def apply_preset(name: str):
    """Inyecta el perfil en el equipo (gain, 48V, DI, link de par y mute de los 24 canales)."""
    if not service or not service._connected:
        raise HTTPException(503, "EVO 16 no conectada")
    try:
        data = load_preset(name)
    except PresetError as e:
        raise HTTPException(400, str(e))
    result = service.apply_state(data["channels"])
    return {
        "status": "ok" if not result["errors"] else "partial",
        "name": data.get("name", name),
        "applied": len(result["applied"]),
        "errors": result["errors"],
    }

@app.delete("/api/presets/{name}")
async def delete_preset_endpoint(name: str):
    """Borra el archivo del perfil."""
    try:
        delete_preset(name)
    except PresetError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok", "name": name}


# === Serve frontend ===

def _get_web_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).parent.parent / "web"

WEB_DIR = _get_web_dir()


@app.get("/")
async def serve_index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/{filename:path}")
async def serve_static(filename: str):
    filepath = WEB_DIR / filename
    if filepath.is_file():
        return FileResponse(filepath)
    raise HTTPException(404)


if __name__ == "__main__":
    _cleanup_conflicts()
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
