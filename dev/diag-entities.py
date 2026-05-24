#!/usr/bin/env python3
"""Probe ALL possible entity IDs for gain-like controls on EVO 16."""
import subprocess, json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c)+"\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

print("=== Full Entity Probe: CS_VOLUME on CN=1 ===")
results = []
for eid in range(1, 128):
    wI = (eid << 8) | 0
    try:
        r = cmd(p, {"type":"get","wValue":0x0201,"wIndex":wI,"length":2})
        if "error" not in r and "data" in r:
            raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
            if raw != -32768:  # -128 dB = silence/unavailable
                results.append((eid, raw, raw/256.0))
                print(f"  Entity {eid:3d} ({eid:#04x}): raw={raw:#06x} {raw/256.0:.1f} dB")
    except:
        pass

print(f"\n=== Found {len(results)} responsive entities ===")

# Now try different control selectors on entity 0x0B (FU11)
print("\n=== FU11: Different Control Selectors ===")
# CS: 1=MUTE, 2=VOLUME, 3=AUTOMATIC_GAIN, etc.
for cs in range(1, 16):
    for cn in [1]:
        r = cmd(p, {"type":"get","wValue":(cs<<8)|cn,"wIndex":0x0B00,"length":2})
        if "error" not in r and "data" in r:
            raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
            print(f"  CS={cs} CN={cn}: raw={raw:#06x} {raw/256.0:.1f} dB")

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()
