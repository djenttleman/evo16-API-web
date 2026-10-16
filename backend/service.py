"""EVO 16 device service — EU58-based (DISCOVERED protocol).

VERIFIED PROTOCOLS (DO NOT MODIFY without updating tests):
  Latest authority: docs/PROTOCOLO-EVO16.md (2026-10-15/16).
  Earlier observations apply only where not superseded:
  - EVO 16 (VID 0x2708, PID 0x000A)
  - Audient SP8 on ADAT 1 (CH9-16) and ADAT 2 (CH17-24)
  - Clock config: macOS 48 kHz, EVO 16 Internal, SP8 Digital/AUTO
  - See docs/PROTOCOLO-EVO16.md; historical observations are archived in docs/history/
"""

import subprocess
import json
import threading
import os
import select
import time
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
# El API v2 conserva un offset +8 por compatibilidad; no prueba dB físicos negativos.
# Corrección del usuario (16-oct): UI −8 produjo 0 en el equipo; UI nueva 0..50.
# El byte transportado sigue siendo sin signo. Escribir >58 (incluido
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
PROTOCOL_VERSION = "evo16-2026-10-16"
GAIN_MIN_DB = -8
GAIN_MAX_DB = 50
GAIN_OFFSET = 8


class DeviceConnectionError(RuntimeError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


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
        self._helper_path = helper_path or os.environ.get("EVO16_HELPER_PATH") or self._find_helper()
        self._deadline = float("inf")

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

    def _readline(self, timeout: float = 2.0) -> str:
        deadline = time.monotonic() + timeout
        while b"\n" not in self._read_buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self._proc.stdout], [], [], remaining)[0]:
                raise TimeoutError("El helper USB no respondió a tiempo")
            chunk = os.read(self._proc.stdout.fileno(), 4096)
            if not chunk:
                raise RuntimeError("El helper USB se cerró")
            self._read_buffer += chunk
            if len(self._read_buffer) > 65536:
                raise RuntimeError("Respuesta del helper demasiado grande")
        line, self._read_buffer = self._read_buffer.split(b"\n", 1)
        return line.decode("utf-8")

    def connect(self) -> None:
        if self._connected:
            return
        self._read_buffer = b""
        self._proc = subprocess.Popen(
            [self._helper_path, VERIFIED_DEVICE_VID, VERIFIED_DEVICE_PID],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            greeting = self._readline(3)
            if greeting == "ERROR DEVICE_NOT_FOUND":
                raise DeviceConnectionError("device_not_found", "EVO 16 no está conectada por USB")
            if greeting == "ERROR USB_BUSY":
                raise DeviceConnectionError("usb_busy", "El USB está ocupado por otra aplicación")
            if greeting != "READY":
                raise DeviceConnectionError("open_failed", "No se pudo abrir EVO 16")
            self._connected = True
        except Exception:
            self.disconnect()
            raise

    def disconnect(self) -> None:
        with self._lock:
            self._close_helper()

    def _close_helper(self) -> None:
        proc, self._proc = self._proc, None
        self._connected = False
        if proc:
            try:
                proc.stdin.write(b"quit\n")
                proc.stdin.flush()
                proc.wait(timeout=0.5)
            except Exception:
                proc.kill()
                proc.wait(timeout=1)
            finally:
                for pipe in (proc.stdin, proc.stdout):
                    try:
                        pipe.close()
                    except OSError:
                        pass

    def _send(self, cmd: dict) -> dict:
        with self._lock:
            if not self._proc or not self._connected:
                raise RuntimeError("Equipo no conectado")
            try:
                if time.monotonic() >= self._deadline:
                    raise TimeoutError("La operación USB superó su plazo total")
                self._proc.stdin.write((json.dumps(cmd, separators=(',', ':')) + "\n").encode())
                self._proc.stdin.flush()
                result = json.loads(self._readline(min(2.0, max(0.001, self._deadline - time.monotonic()))))
            except Exception:
                # A timed-out response cannot be consumed by the next command.
                self._close_helper()
                raise
            if "error" in result:
                # A complete USB-error response is different from a dead helper.
                self._connected = False
                raise RuntimeError(result["error"])
            return result

    # ════════════════════════════════════════════════════════════
    #  VERIFIED METHODS — DO NOT MODIFY
    #  These are confirmed working on hardware (EVO 16 + SP8).
    #  Protocol values reference VERIFIED_* constants above.
    #  Any change MUST pass the smoke tests in test_protocol_smoke.py
    # ════════════════════════════════════════════════════════════

    # ── GAIN (−8…50 dB, CH 1–24) ──────────────────────────

    def get_gain(self, channel: int) -> float:
        """Read input gain in dB. Verified on CH 1-24.

        Protocol: EU58 CS=1, 4 bytes [0, dB + 8, 0, 0]
        """
        wValue = (VERIFIED_GAIN_CS << 8) | (channel - 1)
        r = self._send({
            "type": "get_cur",
            "wValue": wValue,
            "wIndex": VERIFIED_GAIN_ENTITY,
            "length": VERIFIED_GAIN_PAYLOAD_SIZE,
        })
        data = bytes(r["data"])
        return float(data[VERIFIED_GAIN_BYTE_OFFSET] - GAIN_OFFSET)

    def set_gain(self, channel: int, db: int) -> int:
        """Set input gain in dB. Verified on CH 1-24.

        Protocol: EU58 CS=1, 4 bytes [0, dB + 8, 0, 0]
        """
        if not GAIN_MIN_DB <= db <= GAIN_MAX_DB:
            raise ValueError("Ganancia fuera de rango: -8…50 dB")
        wValue = (VERIFIED_GAIN_CS << 8) | (channel - 1)
        data = [0, db + GAIN_OFFSET, 0, 0]
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
        status["mainVolume"] = self.get_main_volume()
        link_cache = {}
        for ch in range(VERIFIED_CHANNEL_MIN, VERIFIED_CHANNEL_MAX + 1):
            a, b = self.link_pair(ch)
            if a not in link_cache:
                link_cache[a] = self.get_link(a)
            status["inputs"].append({
                "channel": ch, "gain": self.get_gain(ch),
                "mute": self.get_mute(ch), "phantom": self.get_phantom(ch),
                "instrument": self.get_instrument(ch),
                "linked": link_cache[a], "linkPair": [a, b],
            })
        # Output mute is not implemented; an empty list is preferable to invented values.
        return status

    # ════════════════════════════════════════════════════════════
    #  EXPERIMENTAL AREA — add new features below
    #  These are NOT covered by verified protocol constants.
    #  Mark clearly: status, what it controls, what hardware tested.
    # ════════════════════════════════════════════════════════════

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
        if not -128 <= db <= 0:
            raise ValueError("Volumen fuera de rango: -128…0 dB")
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

    # ── MEDIDORES (niveles por canal) ──
    # Del desensamblado de MixerModel::updateInputMeterValues / updateOutputMeterValues:
    #   request: bmRequestType=0xA1, bRequest=0x03, wIndex = unidad 0x3C << 8, wLength = 2 × canales
    #   wValue = selector:  0 = niveles de ENTRADA, 1 = niveles de SALIDA,
    #                       2 = clip de entradas, 3 = clip de salidas (1 byte por canal)
    #   Cada nivel son 2 bytes little-endian = AMPLITUD LINEAL, con 65536 = full scale:
    #       dB = 20·log10(raw / 65536)     ← es lo que hace DecibelConversions::meterIntToDB
    #   Verificado en hardware: canales sin señal leen 1 → −96.3 dB, 0 → silencio.
    METER_UNIT          = 0x3C
    METER_SEL_IN        = 0
    METER_SEL_OUT       = 1
    METER_SEL_IN_CLIP   = 2
    METER_SEL_OUT_CLIP  = 3
    NUM_INPUTS          = 24
    NUM_OUTPUTS         = 16

    def _meter_block(self, selector: int, n_bytes: int) -> list[int]:
        r = self._send({
            "type": "ctrl",
            "bmReqType": 0xA1,
            "bReq": 0x03,
            "wValue": selector,
            "wIndex": self.METER_UNIT << 8,
            "length": n_bytes,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return list(r["data"])

    def get_meters(self) -> dict:
        """Niveles en dB de los 24 canales de entrada y de las salidas, más el estado de clip.

        Una sola lectura por bloque (4 transferencias), así que se puede consultar seguido para
        tener medidores en tiempo real.
        """
        import math

        def a_db(lo: int, hi: int) -> float:
            raw = lo | (hi << 8)
            if raw <= 0:
                return -120.0                     # silencio (el firmware usa 20·log10(0) = -inf)
            return round(20 * math.log10(raw / 65536.0), 1)

        e_in = self._meter_block(self.METER_SEL_IN, self.NUM_INPUTS * 2)
        e_out = self._meter_block(self.METER_SEL_OUT, self.NUM_OUTPUTS * 2)
        c_in = self._meter_block(self.METER_SEL_IN_CLIP, self.NUM_INPUTS)
        c_out = self._meter_block(self.METER_SEL_OUT_CLIP, self.NUM_OUTPUTS)
        return {
            "inputs": [a_db(e_in[2 * i], e_in[2 * i + 1]) for i in range(self.NUM_INPUTS)],
            "outputs": [a_db(e_out[2 * i], e_out[2 * i + 1]) for i in range(self.NUM_OUTPUTS)],
            "inputClips": c_in[: self.NUM_INPUTS],
            "outputClips": c_out[: self.NUM_OUTPUTS],
            "note": "dB = 20*log10(raw/65536); -120.0 = silencio. Una llamada = 4 transferencias.",
        }

    # ── CLOCK SOURCE (ClockSelector 0x28, CS=1) ──
    # 1 byte: 1 = Internal, 2 = Óptica 1, 3 = Óptica 2 (leído del equipo; CS=0 no existe).
    # La clase de la app es UacLib::UacClockSelector (setClockSource/clockSourceChanged).
    CLOCK_UNIT  = 0x28
    CLOCK_CS    = 1
    CLOCK_NAMES = {1: "internal", 2: "optical1", 3: "optical2"}

    def get_clock_source(self) -> dict:
        """Fuente de reloj actual del equipo."""
        r = self._send({
            "type": "get_cur",
            "wValue": (self.CLOCK_CS << 8) | 0,
            "wIndex": (self.CLOCK_UNIT << 8) | 0,
            "length": 1,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        val = int(r["data"][0])
        return {"value": val, "name": self.CLOCK_NAMES.get(val, f"desconocido({val})")}

    def set_clock_source(self, value: int) -> dict:
        """Cambia la fuente de reloj (1=internal, 2=optical1, 3=optical2)."""
        if value not in self.CLOCK_NAMES:
            raise ValueError("Fuente inválida: usá 1 (internal), 2 (optical1) o 3 (optical2).")
        r = self._send({
            "type": "set_cur",
            "wValue": (self.CLOCK_CS << 8) | 0,
            "wIndex": (self.CLOCK_UNIT << 8) | 0,
            "data": [value],
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return self.get_clock_source()

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
        if getattr(self, "_reconnecting", False):
            info["reconnecting"] = True            # lo usa health_state para el estado "reconnecting"
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
        self._reconnecting = True                  # /api/health lo reporta como "reconnecting"
        try:
            try:
                self.disconnect()
            except Exception:
                pass
            _t.sleep(0.6)
            self._connected = False
            try:
                self.connect()
            except Exception as e:                 # noqa: BLE001
                return {"connected": False, "error": f"no se pudo abrir el dispositivo: {e}"}
            return self.health()
        finally:
            self._reconnecting = False

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
        from backend.presets import validate_channels
        channels = validate_channels(channels)
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
            # The firmware mirrors gain and DI: write only the master of a linked pair.
            mirrored_follower = bool(c.get("linked")) and ch % 2 == 0
            if "gain" in c and not mirrored_follower:
                v = int(c["gain"])
                do(f"gain {ch}={v}", lambda ch=ch, v=v: self.set_gain(ch, v))
            # Phantom mirroring was not confirmed: preserve per-channel phantom writes.
            if ch in self.INSTR_CHANNELS and "instrument" in c and not mirrored_follower:
                v = bool(c["instrument"])
                do(f"instrument {ch}={int(v)}", lambda ch=ch, v=v: self.set_instrument(ch, v))

        # 4. unmute de los que terminan sin mute
        for ch, c in sorted(by_ch.items()):
            if not c.get("mute"):
                do(f"mute {ch}=0", lambda ch=ch: self.set_mute(ch, False))

        return {"applied": applied, "errors": errors}
