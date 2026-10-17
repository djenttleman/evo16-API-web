"""Estado de alto nivel del servicio, para clientes de terceros (RLM, extensiones de REAPER).

El problema que resuelve: `/api/health` devuelve la verdad cruda (¿responde el helper?, ¿contesta el
equipo?, ¿tiene la app oficial el USB?) y cada cliente terminaba interpretando esos campos por su
cuenta. Acá todo eso se traduce a **un solo valor** `state`, más `ok` y desde cuándo está así (para
que un cliente que consulta cada 2 s no muestre parpadeos).

`offline` NO está en esta lista a propósito: el servicio no puede informar de su propia ausencia. Ese
estado lo da el launcher del puerto 3100, que sí vive fuera del servicio.
"""

STATE_HELP: dict[str, str] = {
    "connected":           "Equipo conectado",
    "usb_busy":            "La app oficial EVO Control está utilizando el USB. Ciérrala y selecciona Reconectar equipo en Preferencias.",
    "device_disconnected": "EVO 16 no conectada: revisa el cable USB y la alimentación",
    "helper_down":         "No se pudo iniciar el control USB. Selecciona Reconectar equipo en Preferencias.",
    "device_unreachable":  "El equipo no responde. Revisa la conexión USB y la alimentación.",
    "reconnecting":        "Reconectando con el equipo",
    "not_ready":           "Preparando la conexión con el equipo",
    "offline":             "Servicio apagado. Inícialo desde el menú de la app.",
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
