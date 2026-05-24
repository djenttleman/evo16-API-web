#!/usr/bin/env python3
"""Diagnostic: test if SET_CUR actually reaches the EVO 16 hardware."""
import subprocess, json, struct

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c) + "\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()  # READY

# 1. Read INITIAL gain on input 1 (FU11, CN=1)
r = cmd(p, {"type": "get", "wValue": 0x0201, "wIndex": 0x0B00, "length": 2})
raw = int.from_bytes(bytes(r["data"]), 'little', signed=True)
print(f"INITIAL gain IN1: {raw/256.0:.1f} dB  (raw={raw:#06x})")

# 2. SET gain to 13 dB
raw_13 = round(13.0 * 256)
data = list(raw_13.to_bytes(2, 'little'))
r = cmd(p, {"type": "set", "wValue": 0x0201, "wIndex": 0x0B00, "data": data})
print(f"SET gain to 13 dB -> {r}")

# 3. READ BACK immediately
r = cmd(p, {"type": "get", "wValue": 0x0201, "wIndex": 0x0B00, "length": 2})
raw = int.from_bytes(bytes(r["data"]), 'little', signed=True)
print(f"READBACK after SET: {raw/256.0:.1f} dB  (raw={raw:#06x})")

# 4. Now write a DIFFERENT value to test if it actually persisted
r = cmd(p, {"type": "set", "wValue": 0x0201, "wIndex": 0x0B00, "data": [0, 0]})
print(f"RESET to 0 dB -> {r}")

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()
print("\nDavid: por favor gira físico el knob del preamp 1 y dime si el valor leído cambia.")
print("También: ¿el SET de 13 dB cambió algo en la pantalla del EVO 16?")
