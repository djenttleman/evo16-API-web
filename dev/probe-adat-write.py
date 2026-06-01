#!/usr/bin/env python3
"""Probe all write paths for ADAT (SP8) channels on EVO 16."""
import subprocess, json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c, separators=(',',':')) + "\n")
    p.stdin.flush()
    l = p.stdout.readline()
    return json.loads(l) if l else {"error": "no response"}

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

print("=== BASELINE: CH17 (ADAT2) current state ===")
# Read current gain (EU58 CS=1)
r = cmd(p, {"type":"get_cur","wValue":0x0110,"wIndex":0x3A00,"length":4})
print(f"  EU58 CH17 gain: {bytes(r.get('data',[])).hex()}")
# Read phantom
r = cmd(p, {"type":"get_cur","wValue":0x0010,"wIndex":0x3A00,"length":4})
print(f"  EU58 CH17 phantom: {bytes(r.get('data',[])).hex()}")

print("\n=== PATH A: Write via EU58 CS=1 (current method) ===")
r = cmd(p, {"type":"set_cur","wValue":0x0110,"wIndex":0x3A00,"data":[0,35,0,0]})
print(f"  SET CH17 gain 35dB: {r}")
r = cmd(p, {"type":"get_cur","wValue":0x0110,"wIndex":0x3A00,"length":4})
print(f"  Readback: {bytes(r.get('data',[])).hex()}")

print("\n=== PATH B: Write via DFU interface (wIndex=entity|3) ===")
# Try vendor-specific OUT with DFU interface number
r = cmd(p, {"type":"ctrl","bmReqType":0x41,"bReq":0x01,
            "wValue":0x0110,"wIndex":0x3A03,"data":[0,35,0,0]})
print(f"  Vendor OUT (0x41) wI=0x3A03: {r}")

# Try standard SET_CUR to DFU interface  
r = cmd(p, {"type":"set_cur","wValue":0x0110,"wIndex":0x3A03,"data":[0,20,0,0]})
print(f"  SET_CUR wI=0x3A03: {r}")
# Readback via DFU
r = cmd(p, {"type":"get_cur","wValue":0x0110,"wIndex":0x3A03,"length":4})
print(f"  GET_CUR wI=0x3A03: {r}")

print("\n=== PATH C: Try FU11 entity for ADAT gain ===")
r = cmd(p, {"type":"get_cur","wValue":0x0209,"wIndex":0x0B00,"length":2})
print(f"  FU11 CH9 gain: {bytes(r.get('data',[])).hex()}")
r = cmd(p, {"type":"get_cur","wValue":0x0211,"wIndex":0x0B00,"length":2})
print(f"  FU11 CH17 gain: {bytes(r.get('data',[])).hex()}")

print("\n=== PATH D: Vendor-specific entity (0xE0-0xFF) scan ===")
for eid in range(0x80, 0x100, 0x10):
    wI = (eid << 8) | 0
    r = cmd(p, {"type":"get_cur","wValue":0x0100,"wIndex":wI,"length":4})
    if "data" in r and r["data"] and any(b != 0 for b in r["data"]):
        print(f"  Entity {eid:#04x} ({wI:#06x}): {bytes(r['data']).hex()}")

print("\n=== PATH E: Try all entity IDs 0-255 for CH17 write ===")
for eid in range(1, 128):
    wI = (eid << 8) | 0
    r = cmd(p, {"type":"set_cur","wValue":0x0110,"wIndex":wI,"data":[0,42,0,0]})
    if "status" in r:
        # Read back to see if anything accepted it
        rr = cmd(p, {"type":"get_cur","wValue":0x0110,"wIndex":wI,"length":4})
        if "data" in rr and rr["data"]:
            data = bytes(rr["data"])
            if data[1] == 42:  # Gain changed to our value!
                print(f"  ✅ Entity {eid} ({wI:#06x}) ACCEPTED write! Data: {data.hex()}")

# Read back final state
print(f"\n=== FINAL STATE ===")
r = cmd(p, {"type":"get_cur","wValue":0x0110,"wIndex":0x3A00,"length":4})
print(f"  EU58 CH17 final: {bytes(r.get('data',[])).hex()}")

p.stdin.write("QUIT\n")
p.stdin.flush()
p.wait()
