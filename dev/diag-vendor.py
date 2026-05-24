#!/usr/bin/env python3
"""Probe EVO 16: vendor-specific requests & interrupt endpoint data."""
import subprocess, json, struct, time

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c)+"\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

# 1. Try vendor-specific GET requests (bmRequestType=0xC1 instead of 0xA1)
print("=== Vendor-specific GET (bmReqType=0xC1) ===")
for eid in [0x0A, 0x0B, 0x3A, 0x3B, 0x3C]:
    for cs in [0, 1, 2]:
        wI = (eid << 8) | 0
        # Send raw vendor request: type=0xC1 (IN, Vendor, Interface)
        try:
            r = cmd(p, {"type":"vendor_get","wValue":(cs<<8)|1,"wIndex":wI,"length":4})
            if "error" not in r and "data" in r:
                raw = bytes(r["data"])
                print(f"  Entity {eid:#04x} CS={cs}: {raw.hex()}")
            elif "error" in r:
                pass  # Expected for most
        except:
            pass

print("\n=== Try reading the Audio Control descriptor ===")
# Standard request: GET_DESCRIPTOR for UAC2
# bmRequestType=0x81 (IN, Standard, Device)
# bRequest=0x06 (GET_DESCRIPTOR)
# wValue=(0x02<<8)|0 = configuration descriptor
# wIndex=0, wLength=4096
try:
    r = cmd(p, {"type":"standard_get","wValue":0x0200,"wIndex":0,"length":4096})
    if "data" in r:
        raw = bytes(r["data"])
        print(f"  Got {len(raw)} bytes of descriptor data")
        # Print first 256 bytes as hex
        for i in range(0, min(512, len(raw)), 16):
            hexpart = ' '.join(f'{b:02x}' for b in raw[i:i+16])
            asciipart = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw[i:i+16])
            print(f"  {i:04x}: {hexpart}  {asciipart}")
except Exception as e:
    print(f"  Failed: {e}")

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()
print("\nDone")
