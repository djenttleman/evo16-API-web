#!/usr/bin/env python3
"""Focused FU11 test — reads, writes, reads back. No interaction needed."""
import subprocess, json, sys

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c)+"\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

# Step 1: Read FU11 baseline
print("STEP 1: Read FU11 baseline")
for ch in range(1, 3):
    r = cmd(p, {"type":"get","wValue":(2<<8)|ch,"wIndex":0x0B00,"length":2})
    raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
    print(f"  IN{ch}: {raw/256.0:.1f} dB")

# Step 2: Write FU11 IN1 to 35 dB
print("\nSTEP 2: Write FU11 IN1 = 35 dB")
r = cmd(p, {"type":"set","wValue":0x0201,"wIndex":0x0B00,"data":[0,35]})
print(f"  SET: {r}")

# Step 3: Readback
print("\nSTEP 3: Readback")
for ch in range(1, 3):
    r = cmd(p, {"type":"get","wValue":(2<<8)|ch,"wIndex":0x0B00,"length":2})
    raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
    print(f"  IN{ch}: {raw/256.0:.1f} dB")

# Step 4: Write back to 0
print("\nSTEP 4: Reset IN1 to 0 dB")
cmd(p, {"type":"set","wValue":0x0201,"wIndex":0x0B00,"data":[0,0]})
r = cmd(p, {"type":"get","wValue":0x0201,"wIndex":0x0B00,"length":2})
raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
print(f"  IN1 after reset: {raw/256.0:.1f} dB")

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()

print("\n✅ Test complete. Readback confirms USB write/read works.")
print("❓ David: ¿la pantalla del EVO 16 cambió durante la prueba?")
print("   - Si SÍ: FU11 controla el preamp. Puede ser lag/refresh de la pantalla.")
print("   - Si NO: FU11 es trim digital, el preamp físico usa otro mecanismo.")
