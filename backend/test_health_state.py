"""Tests del estado de alto nivel (backend/health_state.py). No tocan el equipo."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from health_state import STATES, reset, state_for, state_from   # noqa: E402

CASOS = [
    # (device que devuelve service.health(), app oficial abierta?, estado esperado)
    ({"connected": True, "helper": True, "mainVolume": -30.7}, False, "connected"),
    ({"connected": True, "helper": True}, True, "connected"),          # si responde, manda el equipo
    ({"connected": False, "helper": False, "error": "Broken pipe"}, False, "helper_down"),
    ({"connected": False, "helper": True, "error": "GET_CUR failed"}, True, "usb_busy"),
    ({"connected": False, "helper": True, "error": "timeout"}, False, "device_unreachable"),
    ({"connected": False, "helper": True, "reconnecting": True}, False, "reconnecting"),
    ({"connected": False, "error": "servicio sin inicializar"}, False, "not_ready"),
]


def main() -> int:
    fallos = 0

    print("── mapeo de estados ──")
    for dev, app, esperado in CASOS:
        got = state_from(dev, app)
        ok = got == esperado
        fallos += 0 if ok else 1
        print(f"  {'✓' if ok else '✗'} {esperado:<19} (helper={dev.get('helper')}, "
              f"app={app}, reconectando={bool(dev.get('reconnecting'))})"
              + ("" if ok else f" → dio {got}"))

    print("── ok y detalle ──")
    reset()
    r = state_for({"connected": True}, False)
    chk = [("state", r["state"], "connected"), ("ok", r["ok"], True),
           ("detalle no vacío", bool(r["stateDetail"]), True),
           ("stateSeconds", r["stateSeconds"], 0.0)]
    for nombre, got, esperado in chk:
        ok = got == esperado
        fallos += 0 if ok else 1
        print(f"  {'✓' if ok else '✗'} {nombre} = {got!r}")

    print("── la memoria de 'desde cuándo' ──")
    reset()
    a = state_for({"connected": True}, False, now=1000.0)
    b = state_for({"connected": True}, False, now=1012.5)      # mismo estado: no reinicia
    c = state_for({"connected": False, "helper": False}, False, now=1020.0)   # cambia: reinicia
    d = state_for({"connected": False, "helper": False}, False, now=1023.0)
    pruebas = [
        ("primer reporte = 0 s", a["stateSeconds"], 0.0),
        ("12,5 s después sigue contando", b["stateSeconds"], 12.5),
        ("al cambiar de estado vuelve a 0", c["stateSeconds"], 0.0),
        ("y sigue contando el nuevo", d["stateSeconds"], 3.0),
        ("estado tras el cambio", d["state"], "helper_down"),
        ("ok=False cuando no está conectado", d["ok"], False),
    ]
    for nombre, got, esperado in pruebas:
        ok = got == esperado
        fallos += 0 if ok else 1
        print(f"  {'✓' if ok else '✗'} {nombre}: {got!r}")

    print("── que 'offline' quede documentado para el launcher ──")
    ok = "offline" in STATES
    fallos += 0 if ok else 1
    print(f"  {'✓' if ok else '✗'} 'offline' está en STATES (lo reporta el launcher)")

    total = len(CASOS) + len(chk) + len(pruebas) + 1
    print(f"\n  Resultados: {total - fallos}/{total} passed, {fallos}/{total} failed")
    print("  ✅ ESTADOS OK" if fallos == 0 else "  ❌ HAY FALLOS")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
