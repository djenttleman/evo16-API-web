"""Estado de alto nivel del servicio, para clientes de terceros (RLM, extensiones de REAPER).

El problema que resuelve: `/api/health` devuelve la verdad cruda (¿responde el helper?, ¿contesta el
equipo?, ¿tiene la app oficial el USB?) y cada cliente terminaba interpretando esos campos por su
cuenta. Acá todo eso se traduce a **un solo valor** `state`, más `ok` y desde cuándo está así (para
que un cliente que consulta cada 2 s no muestre parpadeos).

`offline` NO está en esta lista a propósito: el servicio no puede informar de su propia ausencia. Ese
estado lo da el launcher del puerto 3100, que sí vive fuera del servicio.
"""

STATE_HELP: dict[str, str] = {
    "connected":          "el equipo responde",
    "usb_busy":           "la app oficial EVO Control tiene el USB: cerrala y hacé POST /api/reconnect",
    "device_disconnected": "EVO 16 no conectada: revisá el cable USB y la alimentación",
    "helper_down":        "el helper USB no está corriendo: POST /api/reconnect lo vuelve a levantar",
    "device_unreachable": "el helper vive pero el equipo no contesta (¿cable? ¿encendido?)",
    "reconnecting":       "reconectando con el equipo",
    "not_ready":          "el servicio todavía no inicializó el dispositivo",
    "offline":            "el servicio no está corriendo: POST /api/start en el launcher (:3100)",
}

STATES = tuple(STATE_HELP)

# memoria del estado actual (proceso único): para saber desde cuándo estamos así
_memoria: dict = {"state": "", "since": 0.0}


def state_from(device: dict, app_running: bool) -> str:
    """Traduce la sonda del equipo (`service.health()`) a un estado único.

    El orden importa: una reconexión en curso se reporta primero, y si el equipo responde se acabó la
    discusión (aunque la app oficial esté abierta).
    """
    if device.get("reconnecting"):
        return "reconnecting"
    if device.get("connected"):
        return "connected"
    if "helper" not in device:
        return "not_ready"
    if device.get("reason") == "device_not_found":
        return "device_disconnected"
    if device.get("reason") == "usb_busy":
        return "usb_busy"
    if app_running:
        return "usb_busy"
    if not device.get("helper"):
        return "helper_down"
    return "device_unreachable"


def state_for(device: dict, app_running: bool, now: float | None = None) -> dict:
    """`{state, ok, stateDetail, stateSeconds}` — recuerda desde cuándo está en ese estado."""
    import time as _t
    ahora = _t.time() if now is None else now
    st = state_from(device, app_running)
    if st != _memoria["state"]:
        _memoria["state"], _memoria["since"] = st, ahora
    return {
        "state": st,
        "ok": st == "connected",
        "stateDetail": STATE_HELP.get(st, ""),
        "stateSeconds": round(ahora - _memoria["since"], 1),
    }


def reset() -> None:
    """Sólo para tests: olvida el estado memorizado."""
    _memoria["state"], _memoria["since"] = "", 0.0
