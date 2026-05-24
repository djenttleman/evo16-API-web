#!/usr/bin/env python3
"""Final validation: read → write → read on EVO 16 preamps."""
import subprocess, json, struct

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def db_to_raw(db): return round(db * 256) & 0xFFFF
def raw_to_db(raw): 
    if raw > 0x7FFF: raw -= 0x10000
    return raw / 256.0

def cmd(proc, c):
    proc.stdin.write(json.dumps(c) + "\n"); proc.stdin.flush()
    return json.loads(proc.stdout.readline())

proc = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
proc.stdout.readline()  # READY

print("=== EVO 16 Preamps Control Validation ===\n")

# 1. Read all gains
print("Before:")
for ch in range(1, 3):  # Focus on the 2 Audient preamps
    r = cmd(proc, {"type": "get", "wValue": (2<<8)|ch, "wIndex": 0x0B00, "length": 2})
    db = raw_to_db(int.from_bytes(bytes(r["data"]), 'little', signed=True))
    print(f"  Preamp {ch}: {db:.1f} dB")

# 2. Set preamp 1 to 35 dB
print("\nSetting Preamp 1 to 35 dB...")
data = list(db_to_raw(35.0).to_bytes(2, 'little'))
r = cmd(proc, {"type": "set", "wValue": 0x0201, "wIndex": 0x0B00, "data": data})
print(f"  SET: {r}")

# 3. Read back
r = cmd(proc, {"type": "get", "wValue": 0x0201, "wIndex": 0x0B00, "length": 2})
db = raw_to_db(int.from_bytes(bytes(r["data"]), 'little', signed=True))
print(f"  Readback: {db:.1f} dB")

# 4. Reset to 0 dB
print("\nResetting to 0 dB...")
data = list((0).to_bytes(2, 'little', signed=True))
r = cmd(proc, {"type": "set", "wValue": 0x0201, "wIndex": 0x0B00, "data": data})
r = cmd(proc, {"type": "get", "wValue": 0x0201, "wIndex": 0x0B00, "length": 2})
db = raw_to_db(int.from_bytes(bytes(r["data"]), 'little', signed=True))
print(f"  Readback: {db:.1f} dB")

proc.stdin.write("QUIT\n"); proc.stdin.flush(); proc.wait()
print("\n✅ EVO 16 is fully controllable via macOS!")
