"""EVO 16 device service — EU58-based (DISCOVERED protocol)."""

import subprocess
import json
import threading
from pathlib import Path


class Evo16Service:
    """Manages the mac-evo16 helper process with the CORRECT EU58 protocol."""

    EU58 = 0x3A00

    def __init__(self, helper_path: str | None = None):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._connected = False
        self._helper_path = helper_path or self._find_helper()

    def _find_helper(self) -> str:
        import sys
        # Bundled app: PyInstaller unpacks to sys._MEIPASS
        if getattr(sys, 'frozen', False):
            bundled = Path(sys._MEIPASS) / "mac-evo16" / "mac-evo16"
            if bundled.is_file():
                return str(bundled)
        # Development mode
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
            [self._helper_path, "0x2708", "0x000a"],
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

    # ============================================================
    #  GAIN — EU58 CS=1, 4 bytes [0, dB, 0, 0]   (0-50 linear)
    # ============================================================
    def get_gain(self, channel: int) -> float:
        """Read input gain in dB (channel 1-10). EU58 CS=1, 4 bytes."""
        wValue = (1 << 8) | (channel - 1)
        r = self._send({
            "type": "get_cur",
            "wValue": wValue,
            "wIndex": self.EU58,
            "length": 4,
        })
        data = bytes(r["data"])
        raw = data[1]  # byte 1 = dB value
        return float(raw)

    def set_gain(self, channel: int, db: int) -> int:
        """Set input gain in dB. Range 0..50 (integers only)."""
        db = max(0, min(50, db))
        wValue = (1 << 8) | (channel - 1)
        data = [0, db, 0, 0]
        r = self._send({
            "type": "set_cur",
            "wValue": wValue,
            "wIndex": self.EU58,
            "data": data,
        })
        if "error" in r:
            raise RuntimeError(r["error"])
        return db

    # ============================================================
    #  MUTE — EU58 CS=2, 4 bytes [0/1, 0, 0, 0]
    # ============================================================
    def get_mute(self, channel: int) -> bool:
        wValue = (2 << 8) | (channel - 1)
        r = self._send({
            "type": "get_cur",
            "wValue": wValue,
            "wIndex": self.EU58,
            "length": 4,
        })
        return bool(bytes(r["data"])[0])

    def set_mute(self, channel: int, muted: bool) -> None:
        wValue = (2 << 8) | (channel - 1)
        data = [1 if muted else 0, 0, 0, 0]
        r = self._send({
            "type": "set_cur",
            "wValue": wValue,
            "wIndex": self.EU58,
            "data": data,
        })
        if "error" in r:
            raise RuntimeError(r["error"])

    # ============================================================
    #  PHANTOM — EU58 CS=0, 4 bytes [0/1, 0, 0, 0]
    # ============================================================
    def get_phantom(self, channel: int) -> bool:
        r = self._send({
            "type": "get_cur",
            "wValue": channel - 1,
            "wIndex": self.EU58,
            "length": 4,
        })
        return bool(bytes(r["data"])[0])

    def set_phantom(self, channel: int, on: bool) -> None:
        data = [1 if on else 0, 0, 0, 0]
        r = self._send({
            "type": "set_cur",
            "wValue": channel - 1,
            "wIndex": self.EU58,
            "data": data,
        })
        if "error" in r:
            raise RuntimeError(r["error"])

    # ============================================================
    #  FULL STATUS
    # ============================================================
    def get_all_status(self) -> dict:
        status = {"device": "Audient EVO 16", "inputs": [], "outputs": []}
        for ch in range(1, 25):
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
            status["inputs"].append({
                "channel": ch, "gain": gain, "mute": mute, "phantom": phantom,
            })
        for pair in range(5):
            status["outputs"].append({
                "pair": pair + 1, "mute": False,
                "label": ["Main", "Line 3-4", "Line 5-6", "Line 7-8", "Phones"][pair],
            })
        return status
