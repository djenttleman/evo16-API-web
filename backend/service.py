"""EVO 16 device service — EU58-based (DISCOVERED protocol).

VERIFIED PROTOCOLS (DO NOT MODIFY without updating tests):
  All verified against hardware on 2026-05-31:
  - EVO 16 (VID 0x2708, PID 0x000A)
  - Audient SP8 on ADAT 1 (CH9-16) and ADAT 2 (CH17-24)
  - Clock config: macOS 48 kHz, EVO 16 Internal, SP8 Digital/AUTO
  - See README § Verified Setup for full configuration
"""

import subprocess
import json
import threading
from pathlib import Path

# ── VERIFIED PROTOCOL CONSTANTS ──────────────────────────
# These values are confirmed working on hardware.
# Changing any of them requires re-verification with SP8 + local preamps.
# ⚠️  DO NOT EDIT below this block unless you have the hardware set up ⚠️

VERIFIED_DEVICE_VID = "0x2708"
VERIFIED_DEVICE_PID = "0x000a"

# Entity IDs (USB Audio Class 2.0 Extension/Feature Units)
VERIFIED_EU58  = 0x3A00   # Extension Unit 58 — primary preamp control
VERIFIED_FU11  = 0x0B00   # Feature Unit 11 — ADAT mute / digital trim

# ── GAIN (verified on CH1-24, analog + ADAT1 + ADAT2) ──
VERIFIED_GAIN_CS           = 1       # Control Selector
VERIFIED_GAIN_PAYLOAD_SIZE = 4       # bytes
VERIFIED_GAIN_BYTE_OFFSET  = 1       # byte index for dB value (0=first)
VERIFIED_GAIN_MIN_DB       = 0
VERIFIED_GAIN_MAX_DB       = 58      # medido 2026-10-15: el firmware CLAMPEA en 58
# El byte del cable es la ganancia física 0..58 (sin signo). La UI de EVO Control
# muestra −8..+50 con referencia de 8 dB ⇒ byte = valor_UI + 8. Escribir >58 (incluido
# 248/0xF8) NO pone el mínimo: el firmware lo lleva al MÁXIMO.
VERIFIED_GAIN_ENTITY       = VERIFIED_EU58  # wIndex

# ── PHANTOM / 48V (verified on CH1-24, analog + ADAT1 + ADAT2) ──
VERIFIED_PHANTOM_CS           = 0   # Control Selector
VERIFIED_PHANTOM_PAYLOAD_SIZE = 4   # bytes
VERIFIED_PHANTOM_BYTE_OFFSET  = 0   # byte index for on/off value
VERIFIED_PHANTOM_ENTITY       = VERIFIED_EU58

# ── MUTE (verified on analog CH1-8 via EU58, ADAT CH9-24 via FU11) ──
#   The entity split is intentional — changing ADAT mutes to EU58
#   was attempted and broke ADAT write forwarding.
VERIFIED_MUTE_CS            = 2     # Control Selector
VERIFIED_MUTE_PAYLOAD_SIZE  = 4     # bytes
VERIFIED_MUTE_BYTE_OFFSET   = 0     # byte index for mute flag
VERIFIED_MUTE_ENTITY_ANALOG = VERIFIED_EU58   # CH1-8
VERIFIED_MUTE_ENTITY_ADAT   = VERIFIED_FU11   # CH9-24

# ── CHANNEL RANGES ──
VERIFIED_CHANNEL_MIN = 1
VERIFIED_CHANNEL_MAX = 24
VERIFIED_ADAT_THRESHOLD = 8   # channels > 8 are ADAT

# ── PROTOCOL VERSION (bump when any verified value changes) ──
PROTOCOL_VERSION = "1.0.0-verified-2026-05-31"


class Evo16Service:
    """Manages the mac-evo16 helper process with VERIFIED EU58/FU11 protocol.

    All verified control paths use the PROTOCOL_VERSION constants above.
    Experimental features should be added BELOW the verified methods
    and clearly marked as EXPERIMENTAL.
    """

    def __init__(self, helper_path: str | None = None):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._connected = False
        self._helper_path = helper_path or self._find_helper()

    @property
    def protocol_version(self) -> str:
        return PROTOCOL_VERSION

    def _find_helper(self) -> str:
        import sys
        if getattr(sys, 'frozen', False):
            bundled = Path(sys._MEIPASS) / "mac-evo16" / "mac-evo16"
            if bundled.is_file():
                return str(bundled)
        here = Path(__file__).parent.absolute()
        candidates = [
            here / ".." / "mac-evo16" / "mac-evo16",
        ]
        for c in candidates:
            if c.resolve().is_file():
                return str(c.resolve())
        raise FileNotFoundError(f"mac-evo16 not found in {candidates}")

    def connect(self) -> None:
        if self._connected:
            return
        self._proc = subprocess.Popen(
            [self._helper_path, VERIFIED_DEVICE_VID, VERIFIED_DEVICE_PID],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        line = self._proc.stdout.readline().strip()
        if line != "READY":
            err = self._proc.stderr.read()
            raise RuntimeError(f"Helper failed: {line}\n{err}")
        self._connected = True

    def disconnect(self) -> None:
        with self._lock:
            if self._proc:
                try:
                    self._proc.stdin.write("quit\n")
                    self._proc.stdin.flush()
                except Exception:
                    pass
                try:
                    self._proc.wait(timeout=2)
                except Exception:
                    self._proc.kill()
                self._proc = None
            self._connected = False

    def _send(self, cmd: dict) -> dict:
        with self._lock:
            if not self._proc:
                raise RuntimeError("Not connected")
            self._proc.stdin.write(json.dumps(cmd, separators=(',', ':')) + "\n")
            self._proc.stdin.flush()
            resp = self._proc.stdout.readline()
            if not resp:
                raise RuntimeError("Helper closed")
            return json.loads(resp)

    # ════════════════════════════════════════════════════════════
    #  VERIFIED METHODS — DO NOT MODIFY
    #  These are confirmed working on hardware (EVO 16 + SP8).
    #  Protocol values reference VERIFIED_* constants above.
    #  Any change MUST pass the smoke tests in test_protocol_smoke.py
    # ════════════════════════════════════════════════════════════

    # ── GAIN (0–50 dB, CH 1–24) ──────────────────────────

    def get_gain(self, channel: int) -> float:
        """Read input gain in dB. Verified on CH 1-24.

        Protocol: EU58 CS=1, 4 bytes [0, dB, 0, 0]
        """
        wValue = (VERIFIED_GAIN_CS << 8) | (channel - 1)
        r = self._send({
            "type": "get_cur",
            "wValue": wValue,
            "wIndex": VERIFIED_GAIN_ENTITY,
            "length": VERIFIED_GAIN_PAYLOAD_SIZE,
        })
        data = bytes(r["data"])
        return float(data[VERIFIED_GAIN_BYTE_OFFSET])

    def set_gain(self, channel: int, db: int) -> int:
        """Set input gain in dB. Verified on CH 1-24.

        Protocol: EU58 CS=1, 4 bytes [0, dB, 0, 0]
        """
        db = max(VERIFIED_GAIN_MIN_DB, min(VERIFIED_GAIN_MAX_DB, db))
        wValue = (VERIFIED_GAIN_CS << 8) | (channel - 1)
        data = [0, db, 0, 0]
        r = self._send({
            "type": "set_cur",
            "wValue": wValue,
            "wIndex": VERIFIED_GAIN_ENTITY,
            "data": data,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return db

    # ── MUTE (CH 1-8 via EU58, CH 9-24 via FU11) ────────

    def get_mute(self, channel: int) -> bool:
        """Read mute state. Verified on CH 1-24.

        Protocol: EU58 CS=2 (analog), FU11 CS=2 (ADAT)
        """
        wValue = (VERIFIED_MUTE_CS << 8) | (channel - 1)
        wIndex = VERIFIED_MUTE_ENTITY_ADAT if channel > VERIFIED_ADAT_THRESHOLD else VERIFIED_MUTE_ENTITY_ANALOG
        r = self._send({
            "type": "get_cur",
            "wValue": wValue,
            "wIndex": wIndex,
            "length": VERIFIED_MUTE_PAYLOAD_SIZE,
        })
        return bool(bytes(r["data"])[VERIFIED_MUTE_BYTE_OFFSET])

    def set_mute(self, channel: int, muted: bool) -> None:
        """Set mute. Verified on CH 1-24.

        Protocol: EU58 CS=2 (analog), FU11 CS=2 (ADAT)
        """
        wValue = (VERIFIED_MUTE_CS << 8) | (channel - 1)
        wIndex = VERIFIED_MUTE_ENTITY_ADAT if channel > VERIFIED_ADAT_THRESHOLD else VERIFIED_MUTE_ENTITY_ANALOG
        data = [1 if muted else 0, 0, 0, 0]
        r = self._send({
            "type": "set_cur",
            "wValue": wValue,
            "wIndex": wIndex,
            "data": data,
        })
        if "error" in r:
            raise RuntimeError(r["error"])

    # ── PHANTOM / 48V (CH 1-24) ─────────────────────────

    def get_phantom(self, channel: int) -> bool:
        """Read phantom power state. Verified on CH 1-24.

        Protocol: EU58 CS=0, 4 bytes [0/1, 0, 0, 0]
        """
        r = self._send({
            "type": "get_cur",
            "wValue": channel - 1,
            "wIndex": VERIFIED_PHANTOM_ENTITY,
            "length": VERIFIED_PHANTOM_PAYLOAD_SIZE,
        })
        return bool(bytes(r["data"])[VERIFIED_PHANTOM_BYTE_OFFSET])

    def set_phantom(self, channel: int, on: bool) -> None:
        """Set phantom power. Verified on CH 1-24.

        Protocol: EU58 CS=0, 4 bytes [0/1, 0, 0, 0]
        """
        data = [1 if on else 0, 0, 0, 0]
        r = self._send({
            "type": "set_cur",
            "wValue": channel - 1,
            "wIndex": VERIFIED_PHANTOM_ENTITY,
            "data": data,
        })
        if "error" in r:
            raise RuntimeError(r["error"])

    # ── FULL STATUS ─────────────────────────────────────

    def get_all_status(self) -> dict:
        status = {"device": "Audient EVO 16", "inputs": [], "outputs": []}
        # Volumen del main mix (0x36 CS=18): una sola lectura extra por poll.
        try:
            status["mainVolume"] = self.get_main_volume()
        except Exception:
            status["mainVolume"] = None
        # El link es POR PAR y CS3 lo devuelve igual cualquiera de los dos canales, así que se
        # lee una sola vez por par (en el maestro) y se comparte con el seguidor: el poll suma
        # 12 lecturas en vez de 24. No bajar el intervalo del poll (ver nota del encabezado).
        link_cache: dict[int, bool] = {}
        for ch in range(VERIFIED_CHANNEL_MIN, VERIFIED_CHANNEL_MAX + 1):
            try:
                gain = self.get_gain(ch)
            except Exception:
                gain = 0.0
            try:
                mute = self.get_mute(ch)
            except Exception:
                mute = False
            try:
                phantom = self.get_phantom(ch)
            except Exception:
                phantom = False
            entry = {
                "channel": ch, "gain": gain, "mute": mute, "phantom": phantom,
            }
            # Modo instrumento / DI: sólo los canales con hardware (ver INSTR_CHANNELS).
            if ch in self.INSTR_CHANNELS:
                try:
                    entry["instrument"] = self.get_instrument(ch)
                except Exception:
                    entry["instrument"] = None
            # Link del par estéreo (CS=3): estado del par al que pertenece el canal.
            a, b = self.link_pair(ch)
            if a not in link_cache:
                try:
                    link_cache[a] = self.get_link(a)
                except Exception:
                    link_cache[a] = False
            entry["linked"] = link_cache[a]
            entry["linkPair"] = [a, b]
            status["inputs"].append(entry)
        for pair in range(5):
            status["outputs"].append({
                "pair": pair + 1, "mute": False,
                "label": ["Main", "Line 3-4", "Line 5-6", "Line 7-8", "Phones"][pair],
            })
        return status

    # ════════════════════════════════════════════════════════════
    #  EXPERIMENTAL AREA — add new features below
    #  These are NOT covered by verified protocol constants.
    #  Mark clearly: status, what it controls, what hardware tested.
    # ════════════════════════════════════════════════════════════

    # ── INSTRUMENT MODE (CS=5, CH 1-2 only) ────────────
    # Status: PROBED — writes confirmed with 8-byte payload, pending physical verification
    # HW:     EVO 16 front TS jacks (CH1, CH2)
    # Desc:   High-impedance DI mode for guitars/basses (XLR/TRS combo jack switching)
    # ── INSTRUMENTO / DI (EU58 CS=4) — VERIFICADO EN HARDWARE 2026-10-15 ──
    # Proto:  EU58 CS=4, 4 bytes. Es un BITMASK por canal: **bit 1 = instrumento/DI**.
    #         Se escribe SIEMPRE el word completo (leer → modificar el bit → escribir),
    #         porque los otros bits llevan otro estado del canal (p. ej. Mic 4 = 0b101).
    # Valor con DI activo = 2 (bit 1). Coincide con el campo `instrument` del
    # state.xml de EVO Control, que es la fuente de verdad del modelo de la app.
    # ⚠️  La implementación anterior (CS=5 con 8 bytes) era INERTE: el equipo aceptaba
    #     la escritura y devolvía eco, pero NO cambiaba el modo DI. Medido el
    #     2026-10-15 con el servicio detenido y lectura directa del registro.
    # Hardware con DI: locales 1-2, y vía ADAT 9-10 (ADAT1) y 17-18 (ADAT2).
    INSTR_CS        = 4
    INSTR_ENTITY    = VERIFIED_EU58  # 0x3A00
    INSTR_BIT       = 1              # bit 1 del bitmask = instrumento / DI
    INSTR_SIZE      = 4              # payload UAC2 estándar (NO 8)
    INSTR_CHANNELS  = (1, 2, 9, 10, 17, 18)

    def _read_flags(self, channel: int) -> int:
        """Lee el bitmask de CS=4 (4 bytes) del canal indicado (1-based)."""
        r = self._send({
            "type": "get_cur",
            "wValue": (self.INSTR_CS << 8) | (channel - 1),
            "wIndex": self.INSTR_ENTITY,
            "length": self.INSTR_SIZE,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return int(bytes(r["data"])[0])

    def get_instrument(self, channel: int) -> bool | None:
        """Lee el modo instrumento. True = DI activo, None si el canal no tiene DI."""
        if channel not in self.INSTR_CHANNELS:
            return None
        return bool(self._read_flags(channel) & (1 << self.INSTR_BIT))

    def set_instrument(self, channel: int, on: bool) -> bool:
        """Fija el modo instrumento con READ-MODIFY-WRITE (preserva los otros bits).

        Devuelve True si se aplicó, False si el canal no tiene hardware de DI.
        """
        if channel not in self.INSTR_CHANNELS:
            return False
        mask = 1 << self.INSTR_BIT
        cur = self._read_flags(channel)
        nuevo = (cur | mask) if on else (cur & ~mask)
        r = self._send({
            "type": "set_cur",
            "wValue": (self.INSTR_CS << 8) | (channel - 1),
            "wIndex": self.INSTR_ENTITY,
            "data": [nuevo, 0, 0, 0],
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return True

    # ── LINK / par estéreo (EU58 CS=3) — VERIFICADO EN HARDWARE 2026-10-15 ──
    # Proto:  EU58 CS=3, 4 bytes. Vale 1 en LOS DOS canales del par y 0 en el resto: es el
    #         bit de "canal estéreo". Con CS3=1 el FIRMWARE ESPEJA el preamp entre el par
    #         (comprobado con gain y con el DI; phantom no se midió): escribir en el maestro
    #         mueve también al seguidor y viceversa, así que NO hay que duplicar escrituras
    #         desde el cliente. Basta con escribirlo en el canal par (maestro).
    #         Apagar = escribir 0 en los dos canales del par.
    # Pares: (1,2), (3,4), (5,6), … — 1-based, (impar, impar+1) = (maestro, seguidor).
    # Descartado: CS5/CS6 NO son el link (son inertes, ver la skill audient-usb-control).
    LINK_CS     = 3
    LINK_ENTITY = VERIFIED_EU58  # 0x3A00
    LINK_SIZE   = 4
    LINK_MAX_CHANNEL = VERIFIED_CHANNEL_MAX

    @staticmethod
    def link_pair(channel: int) -> tuple[int, int]:
        """Par estéreo (1-based) al que pertenece el canal: (maestro impar, seguidor par)."""
        a = channel if channel % 2 == 1 else channel - 1
        return a, a + 1

    def get_link(self, channel: int) -> bool:
        """True si el par al que pertenece el canal está linkeado (lee CS3 del maestro)."""
        a, _ = self.link_pair(channel)
        r = self._send({
            "type": "get_cur",
            "wValue": (self.LINK_CS << 8) | (a - 1),
            "wIndex": self.LINK_ENTITY,
            "length": self.LINK_SIZE,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return bool(bytes(r["data"])[0])

    def set_link(self, channel: int, on: bool) -> tuple[int, int]:
        """Linkea/deslinkea el par del canal. Devuelve el par (maestro, seguidor) afectado.

        Se escribe CS3 en AMBOS canales del par (es el estado que deja la app oficial),
        aunque para crear el espejo baste con el maestro.
        """
        a, b = self.link_pair(channel)
        val = [1 if on else 0, 0, 0, 0]
        for ch in (a, b):
            r = self._send({
                "type": "set_cur",
                "wValue": (self.LINK_CS << 8) | (ch - 1),
                "wIndex": self.LINK_ENTITY,
                "data": val,
            })
            if "error" in r:
                raise RuntimeError(r["error"])
        return a, b

    # ── VOLUMEN DEL MAIN (MonitorController 0x36, CS=18) ──
    # Proto:  GET/SET CS=18, 2 bytes, entero CON SIGNO little-endian en Q8.8: dB = raw / 256.
    #         Lo dio el desensamblado de UacXUAudientMonitorController::setMainVolume
    #         (`mov w2, #0x12` = 18, length 2, `fcvtzs w8, d0, #8` = ×256) y lo confirmó la perilla
    #         física del equipo: al bajarla el registro pasó de [174,199] = −56.3 dB a
    #         [0,160] = −96.0 dB.
    #         Es el volumen del MAIN MIX (las salidas principales). Los volúmenes de CUE usan el
    #         mismo esquema en CS=19 (cue 1) y siguientes.
    MAIN_VOL_CS   = 18
    MAIN_VOL_UNIT = 0x36

    def get_main_volume(self) -> float:
        """Volumen del main mix en dB (Q8.8 con signo)."""
        r = self._send({
            "type": "get_cur",
            "wValue": (self.MAIN_VOL_CS << 8) | 0,
            "wIndex": (self.MAIN_VOL_UNIT << 8) | 0,
            "length": 2,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        d = bytes(r["data"])
        v = d[0] | (d[1] << 8)
        if v >= 0x8000:
            v -= 0x10000
        return v / 256.0

    def set_main_volume(self, db: float) -> float:
        """Fija el volumen del main mix. Devuelve el valor cuantizado que se escribió."""
        raw = int(round(db * 256))
        raw = max(-0x8000, min(0x7FFF, raw))
        u = raw & 0xFFFF
        r = self._send({
            "type": "set_cur",
            "wValue": (self.MAIN_VOL_CS << 8) | 0,
            "wIndex": (self.MAIN_VOL_UNIT << 8) | 0,
            "data": [u & 0xFF, (u >> 8) & 0xFF],
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return raw / 256.0

    # ── STORE STANDALONE STATE (unidad 0x36 CS=24) ──
    # El equipo puede funcionar SIN computadora usando su propia memoria interna: guarda un estado
    # completo (ganancias, DI, 48V, y también el volumen del main). El comando lo dio el
    # desensamblado de UacXUAudientMonitorController::setStandAloneState: SET_CUR a
    # MonitorController (0x36) con CS=24, índice 0 y 4 bytes en cero — es un TRIGGER sin dato
    # (`stur wzr, [x29, #-0x4]`), no un registro que se lea o escriba con un valor.
    # Es de UNA SOLA VÍA: pisa el estado guardado antes y no se puede leer ni restaurar desde acá.
    # Para verificar hace falta ciclar la energía del equipo: al volver debe cargar ESTO.
    STANDALONE_CS   = 24
    STANDALONE_UNIT = 0x36

    def store_standalone(self) -> dict:
        """Guarda el estado ACTUAL en la memoria de la interfaz (trigger CS=24)."""
        r = self._send({
            "type": "set_cur",
            "wValue": (self.STANDALONE_CS << 8) | 0,
            "wIndex": (self.STANDALONE_UNIT << 8) | 0,
            "data": [0, 0, 0, 0],
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return {"stored": True, "verify": "ciclar la energía del equipo y comprobar que vuelve con "
                                          "el estado actual"}

    # ── ESTADO / RECONEXIÓN (para monitoreo y para agentes que consumen esta API) ──

    def health(self) -> dict:
        """Estado de conexión EN VIVO.

        No confía en `self._connected`: hace una lectura real al equipo (el volumen del main, que
        es una lectura barata y siempre disponible) para distinguir "el helper responde" de "el
        helper está vivo pero el equipo no contesta" (p. ej. la app oficial tiene el USB, o el
        endpoint quedó raro). Devuelve además el motivo cuando falla.
        """
        info: dict = {
            "connected": False,
            "helper": self._proc is not None and self._proc.poll() is None,
            "entity": f"0x{self.MAIN_VOL_UNIT:02X}",
        }
        try:
            info["mainVolume"] = self.get_main_volume()
            info["connected"] = True
        except Exception as e:                     # noqa: BLE001
            info["error"] = str(e)
            info["hint"] = ("Si la app oficial EVO Control está abierta, es la dueña del USB: "
                            "cerrala y llamá a /api/reconnect.")
        return info

    def reconnect(self) -> dict:
        """Cierra el helper y lo vuelve a levantar, y devuelve el estado ya verificado.

        Es lo que hay que llamar después de cerrar la app oficial: el server conecta una sola vez
        al arrancar, así que si el equipo estaba ocupado se queda sin dispositivo hasta esto.
        """
        import time as _t
        try:
            self.disconnect()
        except Exception:
            pass
        _t.sleep(0.6)
        self._connected = False
        try:
            self.connect()
        except Exception as e:                     # noqa: BLE001
            return {"connected": False, "error": f"no se pudo abrir el dispositivo: {e}"}
        return self.health()

    # ── PERFILES (capturar / inyectar el estado de los preamps) ──
    # Se apoya en get_all_status() para capturar y en los setters para inyectar. El formato de
    # cada canal es el que espera presets.py (ver ese módulo).

    def capture_state(self) -> list[dict]:
        """Estado guardable de los 24 canales (lo que va dentro de un perfil)."""
        out = []
        for entry in self.get_all_status()["inputs"]:
            out.append({
                "channel": entry["channel"],
                "gain": int(entry["gain"]),
                "phantom": bool(entry["phantom"]),
                "mute": bool(entry["mute"]),
                "instrument": bool(entry.get("instrument") or False),
                "linked": bool(entry.get("linked") or False),
                "linkPair": entry.get("linkPair"),
            })
        return out

    def apply_state(self, channels: list[dict]) -> dict:
        """Escribe un perfil en el equipo. Devuelve {applied: [...], errors: [...]}.

        Orden pensado para no meter saltos de nivel innecesarios:
          1. link de cada par (el espejo queda armado antes de escribir los valores finales)
          2. mute de los canales que van a quedar muteados (así el resto de los cambios no suena)
          3. phantom / gain / instrument por canal
          4. unmute de los que terminan sin mute

        Cada operación se intenta por separado: si una falla, el resto sigue y el error queda
        en el resumen (un canal raro no debe abortar el perfil entero).
        """
        by_ch: dict[int, dict] = {}
        for c in channels:
            try:
                ch = int(c.get("channel", 0))
            except (TypeError, ValueError):
                continue
            if 1 <= ch <= self.LINK_MAX_CHANNEL:
                by_ch[ch] = c

        applied: list[str] = []
        errors: list[str] = []

        def do(desc: str, fn) -> None:
            try:
                fn()
                applied.append(desc)
            except Exception as e:
                errors.append(f"{desc}: {e}")

        # 1. link (una vez por par)
        pares = set()
        for ch in sorted(by_ch):
            a, _b = self.link_pair(ch)
            if a in pares:
                continue
            pares.add(a)
            # Basta con mirar cualquiera de los dos canales del par.
            on = bool(by_ch[ch].get("linked"))
            do(f"link {a}-{a + 1}={int(on)}", lambda a=a, on=on: self.set_link(a, on))

        # 2. mute de los que van a quedar muteados
        for ch, c in sorted(by_ch.items()):
            if c.get("mute"):
                do(f"mute {ch}=1", lambda ch=ch: self.set_mute(ch, True))

        # 3. valores por canal
        for ch, c in sorted(by_ch.items()):
            if "phantom" in c:
                v = bool(c["phantom"])
                do(f"phantom {ch}={int(v)}", lambda ch=ch, v=v: self.set_phantom(ch, v))
            if "gain" in c:
                v = max(0, min(58, int(c["gain"])))
                do(f"gain {ch}={v}", lambda ch=ch, v=v: self.set_gain(ch, v))
            # El DI sólo existe en algunos canales; en el resto el setter devuelve False.
            if ch in self.INSTR_CHANNELS and "instrument" in c:
                v = bool(c["instrument"])
                do(f"instrument {ch}={int(v)}", lambda ch=ch, v=v: self.set_instrument(ch, v))

        # 4. unmute de los que terminan sin mute
        for ch, c in sorted(by_ch.items()):
            if not c.get("mute"):
                do(f"mute {ch}=0", lambda ch=ch: self.set_mute(ch, False))

        return {"applied": applied, "errors": errors}
