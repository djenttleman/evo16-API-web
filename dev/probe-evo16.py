#!/usr/bin/env python3
"""Probe all EVO 16 controls via the mac-evo16 helper binary."""

import subprocess
import json
import sys

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"
VID = "0x2708"
PID = "0x000a"

def send_cmd(proc, cmd):
    proc.stdin.write(json.dumps(cmd) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())

proc = subprocess.Popen(
    [HELPER, VID, PID],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True
)

# Wait for READY
ready = proc.stdout.readline().strip()
print(f"Status: {ready}\n")

# --- Volume (FU10) ---
print("=== Volume (FU10) ===")
for pair in range(5):  # 5 output pairs
    for ch_off in [1, 2]:  # L + R
        cn = pair * 2 + ch_off
        resp = send_cmd(proc, {"type": "get", "wValue": (2 << 8) | cn, "wIndex": 0x0A00, "length": 2})
        raw = int.from_bytes(bytes(resp["data"]), 'little', signed=True)
        db = raw / 256.0
        print(f"  OUT{pair+1}.{ch_off}: raw={raw:#06x}, dB={db:.1f}")

# --- Gain (FU11) ---
print("\n=== Gain (FU11) ===")
for ch in range(1, 11):  # 10 inputs
    resp = send_cmd(proc, {"type": "get", "wValue": (2 << 8) | ch, "wIndex": 0x0B00, "length": 2})
    raw = int.from_bytes(bytes(resp["data"]), 'little', signed=True)
    db = raw / 256.0
    print(f"  IN{ch}: raw={raw:#06x}, dB={db:.1f}")

# --- Phantom (EU58, CS=0) ---
print("\n=== Phantom (EU58) ===")
for ch in range(10):
    resp = send_cmd(proc, {"type": "get", "wValue": ch, "wIndex": 0x3A00, "length": 4})
    val = int.from_bytes(bytes(resp["data"]), 'little')
    print(f"  PHANTOM IN{ch+1}: {'ON' if val else 'OFF'}")

# --- Mute (EU58, CS=0x02) ---
print("\n=== Mute (EU58, CS=0x02) ===")
for ch in range(10):
    resp = send_cmd(proc, {"type": "get", "wValue": 0x0200 + ch, "wIndex": 0x3A00, "length": 4})
    val = int.from_bytes(bytes(resp["data"]), 'little')
    print(f"  MUTE IN{ch+1}: {'MUTED' if val else 'unmuted'}")

# --- Mute outputs (EU59) ---
print("\n=== Mute Outputs (EU59) ===")
for ch in range(5):  # 5 output pairs
    resp = send_cmd(proc, {"type": "get", "wValue": 0x0100 + ch, "wIndex": 0x3B00, "length": 4})
    val = int.from_bytes(bytes(resp["data"]), 'little')
    print(f"  MUTE OUT{pair+1}: {'MUTED' if val else 'unmuted'}")

# --- Test a SET command: set gain on input 1 to ~20 dB ---
print("\n=== Test SET: gain IN1 to 20 dB ===")
raw_20db = round(20.0 * 256) & 0xFFFF
data_bytes = list(raw_20db.to_bytes(2, 'little'))
resp = send_cmd(proc, {"type": "set", "wValue": 0x0201, "wIndex": 0x0B00, "data": data_bytes})
print(f"  Set response: {resp}")

# Read back
resp = send_cmd(proc, {"type": "get", "wValue": 0x0201, "wIndex": 0x0B00, "length": 2})
raw = int.from_bytes(bytes(resp["data"]), 'little', signed=True)
print(f"  Readback: {raw}/{raw/256.0:.1f} dB")

# Reset gain IN1 to 0 dB
raw_0db = list((0).to_bytes(2, 'little', signed=True))
resp = send_cmd(proc, {"type": "set", "wValue": 0x0201, "wIndex": 0x0B00, "data": raw_0db})
print(f"  Reset: {resp}")

proc.stdin.write("QUIT\n")
proc.stdin.flush()
proc.wait()
print("\nDone!")
