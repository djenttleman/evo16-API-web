"""evo16-launcher — API mínima para ENCENDER y APAGAR el Servicio EVO 16 Remote.

Por qué existe: la UI y la API de control viven DENTRO del servicio del puerto 3000, así que el
servicio no puede arrancarse a sí mismo (si está apagado, no hay quién atienda el pedido). Este
launcher es un proceso chico (sólo stdlib, ~15 MB, sin dependencias) que queda disponible en el
puerto 3100 y maneja el LaunchAgent `com.david.evo16-remote`.

    GET  /                    info + lista de endpoints
    GET  /api/status          servicio arriba/abajo + estado del equipo (proxea /api/health)
    POST /api/start           arranca el servicio y espera a que responda
    POST /api/stop            lo detiene ordenado (SIGTERM, así libera el USB)
    GET  /api/logs?n=80       últimas líneas del log del servicio

No toca el equipo por USB: sólo maneja el proceso. La idea es que una extensión externa (por
ejemplo la de REAPER) pueda levantar/bajar el servicio sin abrir una terminal.

    curl -s http://127.0.0.1:3100/api/status
    curl -X POST http://127.0.0.1:3100/api/start
    curl -X POST http://127.0.0.1:3100/api/stop

Nota: este proceso NO se detiene solo (es el que puede volver a levantar todo). Para sacarlo:
`launchctl bootout gui/$(id -u)/com.david.evo16-launcher`.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("EVO16_LAUNCHER_PORT", "3100"))
SERVICE_URL = os.environ.get("EVO16_SERVICE_URL", "http://127.0.0.1:3000")
LABEL = "com.david.evo16-remote"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = Path.home() / "Library" / "Logs" / "evo16-remote.log"
DOMAIN = f"gui/{os.getuid()}"


def _run(*args: str, timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:                                    # noqa: BLE001
        return 1, str(e)


def service_health(timeout: float = 4.0) -> dict | None:
    """El /api/health del servicio, o None si no responde (está apagado)."""
    try:
        with urllib.request.urlopen(f"{SERVICE_URL}/api/health", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:                                          # noqa: BLE001
        return None


def agent_loaded() -> bool:
    code, _ = _run("launchctl", "print", f"{DOMAIN}/{LABEL}", timeout=10)
    return code == 0


def do_start() -> dict:
    """Arranca el servicio por launchd y espera a que /api/health conteste."""
    h = service_health()
    if h is not None:
        return {"status": "already_running", "device": h.get("device")}
    if not agent_loaded():
        if not PLIST.is_file():
            return {"status": "error", "error": f"No existe {PLIST} (¿falta instalar el agente?)"}
        code, out = _run("launchctl", "bootstrap", DOMAIN, str(PLIST))
        if code != 0 and "already bootstrapped" not in out.lower():
            return {"status": "error", "error": f"bootstrap falló: {out}"}
    code, out = _run("launchctl", "kickstart", f"{DOMAIN}/{LABEL}")
    if code != 0:
        return {"status": "error", "error": f"kickstart falló: {out}"}
    for _ in range(30):                                        # hasta ~15 s
        time.sleep(0.5)
        h = service_health()
        if h is not None:
            return {"status": "running", "device": h.get("device"), "urls": h.get("urls")}
    return {"status": "error", "error": "arrancó pero /api/health no responde (ver /api/logs)"}


def do_stop() -> dict:
    """Detiene el servicio (SIGTERM ordenado: así libera el USB antes de morir)."""
    was = service_health() is not None
    _run("launchctl", "kill", "SIGTERM", f"{DOMAIN}/{LABEL}")
    # por si quedó una instancia fuera de launchd
    _run("pkill", "-f", "backend/main.py")
    for _ in range(20):
        time.sleep(0.4)
        if service_health(timeout=1.5) is None:
            _run("pkill", "-f", "mac-evo16")                   # helper huérfano, si quedó
            return {"status": "stopped", "was_running": was}
    return {"status": "error", "error": "sigue respondiendo después del SIGTERM"}


def log_tail(n: int = 80) -> dict:
    try:
        lineas = LOG.read_text(errors="replace").splitlines()
        return {"file": str(LOG), "lines": lineas[-n:]}
    except Exception as e:                                     # noqa: BLE001
        return {"file": str(LOG), "error": str(e)}


class Handler(BaseHTTPRequestHandler):
    server_version = "evo16-launcher/1.0"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=1, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                                  # noqa: N802
        ruta = self.path.split("?")[0].rstrip("/") or "/"
        if ruta == "/":
            self._send(200, {
                "name": "EVO 16 Launcher",
                "purpose": "encender/apagar el servicio EVO 16 Remote (el servicio no puede "
                           "arrancarse a sí mismo)",
                "endpoints": ["GET /api/status", "POST /api/start", "POST /api/stop",
                              "GET /api/logs?n=80"],
                "service": SERVICE_URL,
                "agent": LABEL,
            })
        elif ruta == "/api/status":
            h = service_health()
            # El launcher es el ÚNICO que puede decir "offline": vive fuera del servicio, así que sabe
            # cuándo no hay nadie escuchando. Es el estado que le falta a un cliente externo.
            estado = (h or {}).get("state") or ("offline" if not h else "not_ready")
            self._send(200, {
                "launcher": "ok",
                "service": "running" if h else "stopped",
                "state": estado,
                "ok": bool((h or {}).get("ok", False)),
                "stateDetail": (h or {}).get("stateDetail") or (
                    "el servicio no está corriendo: POST /api/start" if not h else ""),
                "agentInstalled": agent_loaded(),
                "device": (h or {}).get("device"),
                "audientAppRunning": (h or {}).get("audientAppRunning"),
                "urls": (h or {}).get("urls") or {"loopback": SERVICE_URL},
            })
        elif ruta == "/api/logs":
            n = 80
            if "n=" in self.path:
                try:
                    n = max(1, min(500, int(self.path.split("n=")[1].split("&")[0])))
                except ValueError:
                    pass
            self._send(200, log_tail(n))
        else:
            self._send(404, {"error": "ruta no encontrada", "paths": ["/api/status", "/api/start",
                                                                     "/api/stop", "/api/logs"]})

    def do_POST(self) -> None:                                 # noqa: N802
        ruta = self.path.split("?")[0].rstrip("/")
        if ruta == "/api/start":
            self._send(200, do_start())
        elif ruta == "/api/stop":
            self._send(200, do_stop())
        else:
            self._send(404, {"error": "ruta no encontrada", "paths": ["/api/start", "/api/stop"]})

    def log_message(self, format: str, *args) -> None:         # noqa: A002  (firma de la base)
        pass                                                   # silencio: no ensuciar el log


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"evo16-launcher escuchando en http://127.0.0.1:{PORT}  "
          f"(servicio: {SERVICE_URL}, agente: {LABEL})", flush=True)
    srv.serve_forever()
