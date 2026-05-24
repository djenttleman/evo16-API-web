#!/usr/bin/env python3
"""Probe DFU interface and vendor requests for preamp control."""
import subprocess, json, struct, sys

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    line = json.dumps(c, separators=(',', ':'))
    p.stdin.write(line + "\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

# Known working FU11 read (to confirm connection)
r = cmd(p, {"type":"get_cur","wValue":0x0201,"wIndex":0x0B00,"length":2})
raw = int.from_bytes(bytes(r.get("data",b"")),'little',signed=True)
print(f"FU11 IN1 reference: {raw/256.0:.1f} dB")

# Try vendor-specific on DFU interface (#3)
# bmRequestType for interface #3: 0x21|(3<<0?) No, 0x21 encodes interface 0 in low bits
# Actually, in USB, bmRequestType bits 4:0 = recipient (0=device, 1=interface, 2=endpoint, 3=other)
# For interface-specific, the interface number is in wIndex low byte
print("\n=== Vendor-specific on DFU IF3 ===")
for cs in [0, 1, 2]:
    # Try different bRequest values
    for breq in [0x01, 0x02, 0x03, 0x40, 0x41, 0x80, 0x81]:
        r = cmd(p, {"type":"ctrl","bmReqType":0x41,"bReq":breq,
                     "wValue":cs,"wIndex":0x0300|0x3A00,"length":4})
        if "data" in r:
            d = bytes(r["data"])
            if any(b != 0 for b in d):
                print(f"  0x41 bReq={breq:#04x} wV={cs:#06x} wI=0x3A03: {d.hex()}")
        # Only print errors for first few
        r = cmd(p, {"type":"ctrl","bmReqType":0x41,"bReq":breq,
                     "wValue":(cs<<8)|1,"wIndex":0x0B03,"length":4})
        if "data" in r:
            d = bytes(r["data"])
            if any(b != 0 for b in d):
                print(f"  0x41 bReq={breq:#04x} wV={(cs<<8)|1:#06x} wI=0x0B03: {d.hex()}")

# Try DFU-specific requests (bRequest = 0x00)
print("\n=== DFU class requests ===")
# DFU_GETSTATUS = 0x03, DFU_DNLOAD = 0x01, DFU_UPLOAD = 0x02
# bmRequestType for DFU: 0x21 (host-to-device, class, interface) for OUT, 0xA1 for IN
for breq in [0x00, 0x01, 0x02, 0x03, 0x04, 0x05]:
    r = cmd(p, {"type":"ctrl","bmReqType":0xA1,"bReq":breq,
                 "wValue":0,"wIndex":0x0300,"length":6})
    if "data" in r:
        d = bytes(r["data"])
        print(f"  DFU_GET bReq={breq:#04x}: {d.hex()} <- {' '.join(f'{b:02x}' for b in d)}")
    r = cmd(p, {"type":"ctrl","bmReqType":0x21,"bReq":breq,
                 "wValue":0,"wIndex":0x0300,"data":[0,0,0,0,0,0]})
    if "status" in r:
        print(f"  DFU_SET bReq={breq:#04x}: OK")
    # Ignore stalls (normal for unsupported requests)

# Try audio control through DFU interface instead of interface 0
# Using wIndex = (EntityID << 8) | 3 (interface 3)
print("\n=== Audio control via DFU interface (wIndex=entity|0x03) ===")
for eid in [0x0A, 0x0B]:
    wI = (eid << 8) | 3
    r = cmd(p, {"type":"ctrl","bmReqType":0xA1,"bReq":0x01,
                 "wValue":0x0201,"wIndex":wI,"length":2})
    if "data" in r:
        raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
        print(f"  IF3 Entity {eid:#04x}: {raw/256.0:.1f} dB")
    else:
        print(f"  IF3 Entity {eid:#04x}: {r}")

# Try control transfer to interface 3 with interface-specific recipient
print("\n=== Control with recipient=interface (wIndex=IF3) ===")
r = cmd(p, {"type":"ctrl","bmReqType":0xA1,"bReq":0x01,
             "wValue":0,"wIndex":0x0300,"length":4})
if "data" in r:
    d = bytes(r["data"])
    print(f"  Get IF3 status: {d.hex()}")
else:
    print(f"  Get IF3 status: {r}")

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()
print("\n✅ Done")
