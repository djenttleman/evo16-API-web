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
VERIFIED_GAIN_MAX_DB       = 50
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
            # Instrument mode (experimental, CH1-2 only)
            if ch <= 2:
                try:
                    entry["instrument"] = self.get_instrument(ch)
                except Exception:
                    entry["instrument"] = None
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
    # Proto:  EU58 CS=5, 8 bytes [flag, 0, 0, 0, 0, 0, 0, 0]
    #         flag = 0x01 (instrument ON/high-Z), 0x00 (line/mic), 0xFF (alternate state)
    # Note:   MUST send full 8 bytes. 4-byte writes are accepted but may not commit.
    # Ref:    DESIGN.md EU58 CS=5 "may control input impedance/gain staging"
    #          https://audient.com/products/audio-interfaces/evo16

    INSTR_CS     = 5
    INSTR_ENTITY = VERIFIED_EU58  # 0x3A00
    INSTR_ON     = 1
    INSTR_OFF    = 0
    INSTR_SIZE   = 8              # Payload size: 8 bytes required

    def get_instrument(self, channel: int) -> bool | None:
        """Read instrument mode. Only valid for CH 1-2.

        Returns True (instrument/DI), False (line), or None if not supported.
        """
        if channel not in (1, 2):
            return None
        wValue = (self.INSTR_CS << 8) | (channel - 1)
        r = self._send({
            "type": "get_cur",
            "wValue": wValue,
            "wIndex": self.INSTR_ENTITY,
            "length": self.INSTR_SIZE,
        })
        return bool(bytes(r["data"])[0] == self.INSTR_ON)

    def set_instrument(self, channel: int, on: bool) -> bool:
        """Set instrument mode. Only valid for CH 1-2.

        Returns True on success, False if channel not supported.
        """
        if channel not in (1, 2):
            return False
        wValue = (self.INSTR_CS << 8) | (channel - 1)
        data = [self.INSTR_ON if on else self.INSTR_OFF, 0, 0, 0, 0, 0, 0, 0]
        r = self._send({
            "type": "set_cur",
            "wValue": wValue,
            "wIndex": self.INSTR_ENTITY,
            "data": data,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return True
