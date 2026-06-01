#!/usr/bin/env python3
"""Deep probe: find the write path for ADAT/SP8 channels.
Tests entities 0x3A-0x3F with ALL CS values, plus FU11 2-byte writes."""
import subprocess, json, time

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c, separators=(',',':')) + "\n")
    p.stdin.flush()
    l = p.stdout.readline()
    return json.loads(l) if l else {"error": "no response"}

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()  # READY

CH = 9  # ADAT1 channel 9 (first ADAT channel)
CN = CH - 1  # 8 for ADAT1

print(f"=== Searching write path for CH{CH} (ADAT1) ===")

# First: try entity 0x3D (unknown EU)  
print("\n--- Entity 0x3D00 (unknown Extension Unit) ---")
for cs in range(0, 8):
    wV = (cs << 8) | CN
    r = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3D00,"length":4})
    if "data" in r:
        print(f"  CS={cs} GET: {bytes(r['data']).hex()}")
    r = cmd(p, {"type":"set_cur","wValue":wV,"wIndex":0x3D00,"data":[0,42,0,0]})
    if "status" in r:
        rr = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3D00,"length":4})
        bb = bytes(rr.get("data",[]))
        print(f"  CS={cs} SET accepted → readback: {bb.hex()}")
    else:
        pass  # STALL

print("\n--- Entity 0x3A00 (EU58) with ALL CS 0-15 ---")
for cs in range(0, 16):
    wV = (cs << 8) | CN
    # Read current
    r = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3A00,"length":4})
    read_ok = "data" in r
    if read_ok:
        existing = bytes(r["data"]).hex()
    # Write 42
    r = cmd(p, {"type":"set_cur","wValue":wV,"wIndex":0x3A00,"data":[0,42,0,0]})
    write_ok = "status" in r
    if read_ok or write_ok:
        rr_str = ""
        if "status" in r:
            rr = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3A00,"length":4})
            rr_str = f" → {bytes(rr.get('data',[])).hex()}"
        print(f"  CS={cs:2d}: read={existing}  write={'✓' if write_ok else '✗'}{rr_str}")

print("\n--- EU58 with 8-byte payload (ADAT remote?) ---")
for cs in [0,1,2,3,4,5,6,7,8,16,32]:
    wV = (cs << 8) | CN
    r = cmd(p, {"type":"set_cur","wValue":wV,"wIndex":0x3A00,"data":[0,42]+[0]*6})
    if "status" in r:
        print(f"  CS={cs} 8-byte: ACCEPTED")
        rr = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3A00,"length":8})
        print(f"    readback: {bytes(rr.get('data',[]))[:8].hex()}")

print("\n--- FU11 (0x0B00) 2-byte Q8.8 for CH9-CH24 ---")
for ch in [9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24]:
    wV = (2 << 8) | ch  # CS=2 (VOLUME), CN=channel
    # Read
    r = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x0B00,"length":2})
    if "data" in r:
        raw = int.from_bytes(bytes(r["data"]), 'little', signed=True)
        db = raw/256.0
        print(f"  FU11 CH{ch:2d}: {db:.1f} dB (raw={raw})")

# Try VENDOR OUT (0x41) on EU58
print("\n--- Vendor (0x41) EU58 with different bReq ---")
for breq in [0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0A,0x40,0x41,0x42]:
    wV = (1 << 8) | CN
    r = cmd(p, {"type":"ctrl","bmReqType":0x41,"bReq":breq,
                "wValue":wV,"wIndex":0x3A00,"data":[0,42,0,0]})
    if "status" in r or ("data" in r and r["data"]):
        print(f"  bReq={breq:#04x}: {r}")

# Try same on 0x3D00
print("\n--- Vendor (0x41) 0x3D00 ---")
for breq in [0x01,0x02,0x03,0x04,0x05,0x06]:
    wV = (1 << 8) | CN
    r = cmd(p, {"type":"ctrl","bmReqType":0x41,"bReq":breq,
                "wValue":wV,"wIndex":0x3D00,"data":[0,42,0,0]})
    if "status" in r or ("data" in r and r["data"]):
        print(f"  bReq={breq:#04x}: {r}")

# FINAL: try writing via EU58 CS=6 (might be ADAT commit)
print("\n--- EU58 CS=6 (ADAT commit?) ---")
# First write gain normally
cmd(p, {"type":"set_cur","wValue":0x0108,"wIndex":0x3A00,"data":[0,35,0,0]})
print("  Wrote CH9 gain=35 via EU58")
# Then send CS=6 as "commit to ADAT"
r = cmd(p, {"type":"set_cur","wValue":(6<<8)|CN,"wIndex":0x3A00,"data":[1,0,0,0]})
print(f"  CS=6 commit: {r}")

p.stdin.write("QUIT\n")
p.stdin.flush()
p.wait()
print("\n✅ Probe complete")
