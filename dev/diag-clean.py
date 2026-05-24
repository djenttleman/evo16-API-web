#!/usr/bin/env python3
"""Clean FU11 test: write 13 dB, read back, verify byte encoding."""
import subprocess, json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c)+"\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

# Read all gains
print("=== Initial FU11 ===")
for ch in range(1, 3):
    r = cmd(p, {"type":"get","wValue":0x0200|ch,"wIndex":0x0B00,"length":2})
    raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
    print(f"  IN{ch}: raw={raw:#06x} -> {raw/256.0:.1f} dB")

# Write IN1 to 13 dB: 13*256=3328=0x0D00 -> bytes [0x00, 0x0D] = [0, 13]
print("\n=== Write IN1 = 13 dB ===")
r = cmd(p, {"type":"set","wValue":0x0201,"wIndex":0x0B00,"data":[0,13]})
print(f"  SET response: {r}")

# Read IN1 immediately
print("\n=== Readback ===")
r = cmd(p, {"type":"get","wValue":0x0201,"wIndex":0x0B00,"length":2})
raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
print(f"  IN1: raw={raw:#06x} -> {raw/256.0:.1f} dB")

# Read IN2 as control
r = cmd(p, {"type":"get","wValue":0x0202,"wIndex":0x0B00,"length":2})
raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
print(f"  IN2: raw={raw:#06x} -> {raw/256.0:.1f} dB")

# Read IN1 again after a pause
import time; time.sleep(1)
print("\n=== Readback after 1s ===")
r = cmd(p, {"type":"get","wValue":0x0201,"wIndex":0x0B00,"length":2})
raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
print(f"  IN1: raw={raw:#06x} -> {raw/256.0:.1f} dB")

# Test -8 dB (minimum)
print("\n=== Write IN1 = -8 dB ===")
raw_m8 = round(-8.0 * 256) & 0xFFFF
print(f"  raw_m8 = {raw_m8:#06x}, bytes = {list(raw_m8.to_bytes(2,'little',signed=True))}")
# Must use signed encoding for negative
data = list((round(-8.0 * 256)).to_bytes(2, 'little', signed=True))
print(f"  data = {data}")
r = cmd(p, {"type":"set","wValue":0x0201,"wIndex":0x0B00,"data":data})
print(f"  SET: {r}")
r = cmd(p, {"type":"get","wValue":0x0201,"wIndex":0x0B00,"length":2})
raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
print(f"  IN1: raw={raw:#06x} -> {raw/256.0:.1f} dB")

# Now 0 dB
print("\n=== Write IN1 = 0 dB ===")
r = cmd(p, {"type":"set","wValue":0x0201,"wIndex":0x0B00,"data":[0,0]})
print(f"  SET: {r}")
r = cmd(p, {"type":"get","wValue":0x0201,"wIndex":0x0B00,"length":2})
raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
print(f"  IN1: raw={raw:#06x} -> {raw/256.0:.1f} dB")

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()
print("\n✅ Done")
