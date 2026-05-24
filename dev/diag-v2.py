#!/usr/bin/env python3
"""v2 helper: compact JSON + full probe."""
import subprocess, json, sys

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    # Send compact JSON (no spaces) for C parser compatibility
    line = json.dumps(c, separators=(',', ':'))
    p.stdin.write(line + "\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

# 1. Config descriptor
print("=== Config Descriptor ===")
r = cmd(p, {"type":"config_desc"})
if "data" in r:
    raw = bytes(r["data"])
    print(f"  Got {len(raw)} bytes")
    for i in range(0, min(1024, len(raw)), 16):
        hexp = ' '.join(f'{b:02x}' for b in raw[i:i+16])
        asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw[i:i+16])
        print(f"  {i:04x}: {hexp}  {asc}")

# 2. Interrupt read
print("\n=== Interrupt read (2s timeout) ===")
print("DAVID: Gira el knob del canal 1 ahora!")
r = cmd(p, {"type":"interrupt"})
if "data" in r:
    raw = bytes(r["data"])
    print(f"  Data ({len(raw)}B): {' '.join(f'{b:02x}' for b in raw)}")
else:
    print(f"  Result: {r}")  # timeout is expected if knob not turned

# 3. Try vendor-specific on FU11 (0xB00) with different control selectors
print("\n=== Vendor ctrl (0xC1) on entities ===")
for eid in [0x0A, 0x0B, 0x0C, 0x0D, 0x3A, 0x3B, 0x3C]:
    wI = (eid << 8) | 0
    for cs in range(0, 3):
        r = cmd(p, {"type":"ctrl","bmReqType":0xC1,"bReq":0x01,
                     "wValue":(cs<<8)|1,"wIndex":wI,"length":4})
        if "data" in r:
            d = bytes(r["data"])
            if any(b != 0 for b in d):
                print(f"  Entity {eid:#04x} CS={cs}: {d.hex()}")
        # "error" means stall - normal for unsupported

# 4. Vendor OUT (0x41)
print("\n=== Vendor OUT (0x41) on EU58 ===")
r = cmd(p, {"type":"ctrl","bmReqType":0x41,"bReq":0x01,
             "wValue":0,"wIndex":0x3A00,"data":[1,0,0,0]})
print(f"  EU58 phantom ON via vendor: {r}")
r = cmd(p, {"type":"ctrl","bmReqType":0x41,"bReq":0x01,
             "wValue":0,"wIndex":0x3A00,"data":[0,0,0,0]})
print(f"  EU58 phantom OFF: {r}")

# 5. Try reading FU11 again with standard UAC2
print("\n=== FU11 standard (0xA1) ===")
r = cmd(p, {"type":"get_cur","wValue":0x0201,"wIndex":0x0B00,"length":2})
if "data" in r:
    raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
    print(f"  FU11 IN1: {raw/256.0:.1f} dB")

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()
print("\n✅ Done")
