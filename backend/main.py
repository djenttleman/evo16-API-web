"""EVO 16 Web API — FastAPI server for remote preamp control."""

import sys
import os
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

app = FastAPI(title="EVO 16 Remote", version="1.0.0")


def _cleanup_conflicts():
    """Kill any process using port 3000 and any lingering mac-evo16 helpers."""
    import signal
    killed = False
    # Kill process on port 3000
    try:
        r = subprocess.run(["lsof", "-ti", ":3000"], capture_output=True, text=True, timeout=5)
        for pid in r.stdout.strip().split():
            try:
                os.kill(int(pid), signal.SIGKILL)
                killed = True
            except Exception:
                pass
    except Exception:
        pass
    # Kill lingering mac-evo16 helpers
    try:
        subprocess.run(["pkill", "-9", "-f", "mac-evo16"], timeout=5)
    except Exception:
        pass
    if killed:
        print("🧹 Cleaned up previous instance (port 3000 was in use)")

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
        inputs.append({"channel": i, "gain": 0.0, "mute": False, "phantom": False})
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
