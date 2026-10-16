"""EVO 16 Remote API v2. Protocol authority: docs/PROTOCOLO-EVO16.md, Oct 2026."""
import asyncio
import fcntl
import json
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt
import uvicorn

from backend.config import DATA_DIR, VERSION, PROTOCOL_REVISION, api_token
from backend.runtime import DeviceRuntime, Unavailable
from backend.security import AccessControl, COOKIE
from backend import presets
from backend.service import Evo16Service

TEST_MODE = bool(os.environ.get("EVO16_HELPER_PATH"))
STARTED_AT = time.monotonic()
SERVER_PORT = int(os.environ.get("EVO16_PORT", "3000"))
WEB_DIR = Path(sys._MEIPASS) / "web" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app):
    app.state.token = api_token()
    app.state.runtime = DeviceRuntime()
    app.state.runtime.start()
    yield
    await asyncio.to_thread(app.state.runtime.close)


app = FastAPI(title="EVO 16 Remote", version=VERSION, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(AccessControl)


@app.exception_handler(Unavailable)
async def unavailable(request, exc):
    return JSONResponse({"detail": str(exc), "code": "device_unavailable"}, 503,
                        headers={"Retry-After": "2"})


@app.exception_handler(presets.PresetError)
async def invalid_preset(request, exc):
    return JSONResponse({"detail": str(exc), "code": "invalid_preset"}, 400)


def runtime(request: Request) -> DeviceRuntime:
    return request.app.state.runtime


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GainRequest(StrictBody):
    db: int = Field(ge=-8, le=50, strict=True)


class VolumeRequest(StrictBody):
    db: float = Field(ge=-128, le=0, strict=True)


class ToggleRequest(StrictBody):
    on: bool = Field(strict=True)


class MuteRequest(StrictBody):
    muted: bool = Field(strict=True)


class ClockRequest(StrictBody):
    source: StrictInt | str


class PresetImportRequest(StrictBody):
    preset: dict
    name: str | None = None


def channel_ok(channel, di=False):
    if not 1 <= channel <= 24:
        raise HTTPException(400, "El canal debe estar entre 1 y 24")
    if di and channel not in Evo16Service.INSTR_CHANNELS:
        raise HTTPException(400, "DI disponible en canales 1, 2, 9, 10, 17 y 18")


@app.get("/api/health")
def health(request: Request):
    return {"service": "ok", "version": VERSION, "protocolRevision": PROTOCOL_REVISION, "testMode": TEST_MODE,
            "uptimeSeconds": round(time.monotonic() - STARTED_AT, 1),
            "urls": {"loopback": f"http://127.0.0.1:{SERVER_PORT}"},
            **runtime(request).health()}


@app.get("/api/status")
def status(request: Request):
    return {**runtime(request).status(), "testMode": TEST_MODE}


@app.post("/api/reconnect")
def reconnect(request: Request):
    return {"service": "ok", **runtime(request).reconnect()}


@app.get("/api/gain/{channel}")
def get_gain(channel: int, request: Request):
    channel_ok(channel)
    return {"channel": channel, "gain": runtime(request).call("get_gain", channel), "status": "ok"}


@app.post("/api/gain/{channel}")
def set_gain(channel: int, req: GainRequest, request: Request):
    channel_ok(channel)
    return {"channel": channel, "gain": runtime(request).call("set_gain", channel, req.db, write=True), "status": "ok"}


@app.get("/api/phantom/{channel}")
def get_phantom(channel: int, request: Request):
    channel_ok(channel)
    return {"channel": channel, "phantom": runtime(request).call("get_phantom", channel), "status": "ok"}


@app.post("/api/phantom/{channel}")
def set_phantom(channel: int, req: ToggleRequest, request: Request):
    channel_ok(channel)
    runtime(request).call("set_phantom", channel, req.on, write=True)
    return {"channel": channel, "phantom": req.on, "status": "ok"}


@app.get("/api/mute/{channel}")
def get_mute(channel: int, request: Request):
    channel_ok(channel)
    return {"channel": channel, "muted": runtime(request).call("get_mute", channel), "status": "ok"}


@app.post("/api/mute/{channel}")
def set_mute(channel: int, req: MuteRequest, request: Request):
    channel_ok(channel)
    runtime(request).call("set_mute", channel, req.muted, write=True)
    return {"channel": channel, "muted": req.muted, "status": "ok"}


@app.get("/api/instrument/{channel}")
def get_instrument(channel: int, request: Request):
    channel_ok(channel, di=True)
    return {"channel": channel, "instrument": runtime(request).call("get_instrument", channel), "status": "ok"}


@app.post("/api/instrument/{channel}")
def set_instrument(channel: int, req: ToggleRequest, request: Request):
    channel_ok(channel, di=True)
    runtime(request).call("set_instrument", channel, req.on, write=True)
    return {"channel": channel, "instrument": req.on, "status": "ok"}


@app.get("/api/link/{channel}")
def get_link(channel: int, request: Request):
    channel_ok(channel)
    return {"channel": channel, "linked": runtime(request).call("get_link", channel),
            "pair": list(Evo16Service.link_pair(channel)), "status": "ok"}


@app.post("/api/link/{channel}")
def set_link(channel: int, req: ToggleRequest, request: Request):
    channel_ok(channel)
    pair = runtime(request).call("set_link", channel, req.on, write=True)
    return {"channel": channel, "linked": req.on, "pair": list(pair), "status": "ok"}


@app.get("/api/main-volume")
def get_main_volume(request: Request):
    return {"mainVolume": runtime(request).call("get_main_volume"), "status": "ok"}


@app.post("/api/main-volume")
def set_main_volume(req: VolumeRequest, request: Request):
    return {"mainVolume": runtime(request).call("set_main_volume", req.db, write=True), "status": "ok"}


class SmartGainRequest(StrictBody):
    segundos: float | None = Field(default=None, gt=0, le=120)
    objetivoDb: float | None = Field(default=None, ge=-60, le=0)


def _smartgain_plan(ganancia_db: float, pico_db: float, objetivo_db: float) -> int:
    """Ganancia nueva para que el pico medido caiga en el objetivo, recortada al rango real."""
    return int(round(min(50.0, max(-8.0, ganancia_db + (objetivo_db - pico_db)))))


async def _smartgain_medir(rt, canales: list[int], segundos: float, paso: float = 0.25) -> dict:
    """Muestrea los medidores y devuelve el pico por canal (llamadas cortas, ~3 ms cada una).

    A propósito NO se hace dentro de un `runtime.call(...)`: el runtime corta a los 10 s y su worker
    es único, así que la espera vive acá, en el endpoint, con `await` entre lectura y lectura.
    """
    import asyncio
    import time
    picos = {ch: -120.0 for ch in canales}
    t0 = time.monotonic()
    muestras = 0
    while time.monotonic() - t0 < max(1.0, segundos):
        niveles = rt.meter_values().get("inputs") or []
        for ch in canales:
            v = niveles[ch - 1] if len(niveles) >= ch else None
            if v is not None and v > picos[ch]:
                picos[ch] = float(v)
        muestras += 1
        await asyncio.sleep(paso)
    return {"picos": picos, "muestras": muestras, "segundos": round(time.monotonic() - t0, 1)}


@app.post("/api/smartgain/{channel}")
async def smartgain_channel(channel: int, request: Request, req: SmartGainRequest | None = None):
    """Acomoda la ganancia de UN canal midiendo su nivel (el "Smartgain" de la app, hecho acá).

    El equipo no expone un disparador por USB: **CS=5** de la unidad 0x3A es sólo el **estado** del
    soundcheck (verificado en hardware con señal real en el canal 2: escribir 0/1/2/3 lo guarda tal
    cual y la ganancia NO se mueve; en reposo devuelve 255 = "sin estado"). La app oficial lo
    *poll*ea y lo limpia. Así que el análisis lo hace el software: se mide con los medidores del
    propio equipo y se deja la ganancia para que el pico quede en `objetivoDb` (−12 dBFS).

    Cuerpo opcional: `{"segundos": 10, "objetivoDb": -12}`
    """
    if not 1 <= channel <= 24:
        raise HTTPException(400, f"canal fuera de rango (1-24): {channel}")
    segundos = req.segundos if req and req.segundos else 10.0
    objetivo = req.objetivoDb if req and req.objetivoDb is not None else -12.0
    rt = runtime(request)
    med = await _smartgain_medir(rt, [channel], segundos)
    pico = med["picos"][channel]
    antes = rt.call("get_gain", channel)
    if pico <= -119.0:
        return {"status": "ok", "ok": False, "channel": channel, "peakDb": None, "gainDb": antes,
                "objetivoDb": objetivo, "segundos": med["segundos"],
                "resumen": "sin señal en el canal: no lo toqué"}
    nuevo = _smartgain_plan(antes, pico, objetivo)
    aplicado = rt.call("set_gain", channel, nuevo, write=True)
    return {"status": "ok", "ok": True, "channel": channel, "peakDb": round(pico, 1),
            "gainAntesDb": antes, "gainDb": aplicado, "deltaDb": round(aplicado - antes, 1),
            "objetivoDb": objetivo, "segundos": med["segundos"], "muestras": med["muestras"],
            "resumen": f"canal {channel}: pico {round(pico, 1)} dB → ganancia {aplicado} dB"}


@app.post("/api/smartgain")
async def smartgain_todos(request: Request, req: SmartGainRequest | None = None):
    """Igual, para los 24 canales **en una sola pasada**: una lectura de medidores trae todos.

    Los canales sin señal **no se tocan** y vienen marcados `ok: false` con el motivo.
    """
    segundos = req.segundos if req and req.segundos else 10.0
    objetivo = req.objetivoDb if req and req.objetivoDb is not None else -12.0
    rt = runtime(request)
    canales = list(range(1, 25))
    med = await _smartgain_medir(rt, canales, segundos)
    resultados = []
    for ch in canales:
        pico = med["picos"][ch]
        try:
            antes = rt.call("get_gain", ch)
        except Exception as e:                          # noqa: BLE001
            resultados.append({"channel": ch, "ok": False, "peakDb": round(pico, 1),
                               "detail": f"no pude leer la ganancia: {e}"})
            continue
        if pico <= -119.0:
            resultados.append({"channel": ch, "ok": False, "peakDb": None, "gainDb": antes,
                               "detail": "sin señal en el canal: no lo toqué"})
            continue
        nuevo = _smartgain_plan(antes, pico, objetivo)
        aplicado = rt.call("set_gain", ch, nuevo, write=True)
        resultados.append({"channel": ch, "ok": True, "peakDb": round(pico, 1),
                           "gainAntesDb": antes, "gainDb": aplicado,
                           "deltaDb": round(aplicado - antes, 1)})
    ajustados = [r for r in resultados if r["ok"]]
    return {"status": "ok", "ok": bool(ajustados), "objetivoDb": objetivo,
            "segundos": med["segundos"], "muestras": med["muestras"], "canales": resultados,
            "resumen": f"{len(ajustados)} canal(es) ajustado(s) de {len(resultados)}"}

@app.get("/api/meters")
def meters(request: Request):
    return runtime(request).meter_values()


@app.get("/api/clock")
def get_clock(request: Request):
    return {"status": "ok", **runtime(request).call("get_clock_source")}


@app.post("/api/clock")
def set_clock(req: ClockRequest, request: Request):
    source = req.source
    if isinstance(source, str):
        source = {v: k for k, v in Evo16Service.CLOCK_NAMES.items()}.get(source.strip().lower())
    if type(source) is not int or source not in Evo16Service.CLOCK_NAMES:
        raise HTTPException(400, "Fuente inválida: internal, optical1 u optical2")
    return {"status": "ok", **runtime(request).call("set_clock_source", source, write=True)}


@app.post("/api/store-standalone")
def standalone(request: Request):
    return {"status": "ok", **runtime(request).call("store_standalone", write=True)}


@app.get("/api/presets")
def list_presets():
    return {"presets": presets.list_presets()}


@app.post("/api/presets/import")
def import_preset(req: PresetImportRequest):
    data = presets.import_data(req.preset, req.name)
    return {"status": "ok", "name": data["name"], "channels": len(data["channels"])}


@app.get("/api/presets/{name}")
def get_preset(name: str):
    return presets.load(name)


@app.post("/api/presets/{name}/export")
def export_preset(name: str):
    # Return content; the client chooses the destination on its own computer.
    data = presets.load(name)
    return JSONResponse(data, headers={"Content-Disposition": "attachment; filename=preset.json"})


@app.post("/api/presets/{name}")
def save_preset(name: str, request: Request):
    data = presets.save(name, runtime(request).call("capture_state"))
    return {"status": "ok", "name": data["name"], "savedAt": data["savedAt"], "channels": len(data["channels"])}


@app.post("/api/presets/{name}/apply")
def apply_preset(name: str, request: Request):
    result = runtime(request).call("apply_state", presets.load(name)["channels"], write=True)
    return {"status": "partial" if result["errors"] else "ok", "name": name,
            "applied": len(result["applied"]), "errors": result["errors"]}


@app.delete("/api/presets/{name}")
def delete_preset(name: str):
    presets.delete(name)
    return {"status": "ok", "name": name}


@app.get("/api/openapi.json", include_in_schema=False)
def openapi():
    schema = app.openapi()
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer"}}
    schema["security"] = [{"BearerAuth": []}]
    return schema


@app.get("/api/info")
def info():
    return {"name": "EVO 16 Remote", "version": VERSION, "protocolRevision": PROTOCOL_REVISION, "testMode": TEST_MODE,
            "openapi": "/api/openapi.json", "authentication": "Bearer",
            "gain": {"minDb": -8, "maxDb": 50, "wireOffset": 8},
            "mainVolume": {"minDb": -128, "maxDb": 0, "display": "100 * 10 ** (db / 96)"},
            "instrumentChannels": list(Evo16Service.INSTR_CHANNELS),
            "channelRange": [1, 24], "statusIntervalSeconds": 2,
            "lifecycle": "EVO 16 Remote.app (URL scheme o API opcional :3100)",
            "capabilities": sorted(p for p in app.openapi()["paths"] if p.startswith("/api/"))}


@app.get("/")
def index(request: Request):
    response = FileResponse(WEB_DIR / "index.html")
    # Only a local same-origin UI gets a session without copying the native integration token.
    if request.client and request.client.host in {"127.0.0.1", "::1"}:
        response.set_cookie(COOKIE, request.app.state.token, httponly=True, samesite="strict")
    return response


# StaticFiles resolves paths and rejects traversal (including escaped segments and symlinks).
app.mount("/", StaticFiles(directory=WEB_DIR), name="web")


def listen_host():
    if os.environ.get("EVO16_HOST"):
        return os.environ["EVO16_HOST"]
    try:
        prefs = json.loads((DATA_DIR / "prefs.json").read_text())
        return "0.0.0.0" if prefs.get("exponerRed") else "127.0.0.1"
    except (OSError, ValueError):
        return "127.0.0.1"


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        from backend.service import PROTOCOL_VERSION
        print(json.dumps({"version": VERSION, "protocolRevision": PROTOCOL_VERSION,
                          "webIncluded": (WEB_DIR / "index.html").is_file(),
                          "helperIncluded": Path(Evo16Service()._helper_path).is_file(),
                          "routes": len(app.openapi()["paths"])}))
        sys.exit(0)
    api_token()  # Secure private directory before taking the instance lock.
    lock = (DATA_DIR / "service.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("Ya hay una instancia de EVO 16 Remote; no se detuvo ningún proceso")
    server = uvicorn.Server(uvicorn.Config(app, host=listen_host(), port=SERVER_PORT, log_level="warning",
                                         limit_concurrency=64, backlog=64, timeout_keep_alive=5))
    # Bind first, before startup can claim the USB. A foreign port owner is never terminated.
    sock = server.config.bind_socket()
    parent_pid = os.environ.get("EVO16_PARENT_PID")
    if parent_pid:
        import threading
        def watch_parent():
            while not server.should_exit:
                try:
                    os.kill(int(parent_pid), 0)
                except ProcessLookupError:
                    server.should_exit = True
                    return
                time.sleep(1)
        threading.Thread(target=watch_parent, daemon=True).start()
    server.run(sockets=[sock])
