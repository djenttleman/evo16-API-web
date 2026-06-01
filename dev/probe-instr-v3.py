#!/usr/bin/env python3
"""Compare EU58 CS=7 across channels, deep probe FU11 2-byte writes."""
import subprocess, json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c, separators=(',',':')) + "\n")
    p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

print("=== EU58 CS=7 capability flags across channels ===\n")
for ch in [1, 2, 3, 8, 9, 17]:
    cn = ch - 1
    r = cmd(p, {"type":"get_cur","wValue":(7<<8)|cn,"wIndex":0x3A00,"length":4})
    if "data" in r:
        val = bytes(r["data"])[0]
        bits = f"{val:08b}".replace("0","·").replace("1","█")
        print(f"  CH{ch:2d} (CN={cn:2d}): 0x{val:02x} = {bits}")

print("\n=== FU11 2-byte writes (UAC2 standard) on CH1 ===")
# CS=1 is MUTE, CS=2 is VOLUME, CS=3 is BASS, CS=4 is MID, CS=5 is TREBLE
for cs in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]:
    # Read 2-byte
    r = cmd(p, {"type":"get_cur","wValue":(cs<<8)|0,"wIndex":0x0B00,"length":2})
    if "data" in r:
        raw = int.from_bytes(bytes(r["data"]), 'little', signed=True)
        db = raw/256.0
        initial = f"{db:.1f}dB"

    # Write 2-byte value
    val = (1 << 8) if cs == 1 else (50 << 8)  # mute on for CS1, 50 for others
    wdata = list(val.to_bytes(2, 'little'))
    r = cmd(p, {"type":"set_cur","wValue":(cs<<8)|0,"wIndex":0x0B00,"data":wdata})
    can_write = "status" in r

    if can_write:
        rr = cmd(p, {"type":"get_cur","wValue":(cs<<8)|0,"wIndex":0x0B00,"length":2})
        if "data" in rr:
            raw2 = int.from_bytes(bytes(rr["data"]), 'little', signed=True)
            after = f"{raw2/256.0:.1f}dB"
            changed = after != initial
            marker = " ← CHANGED" if changed else ""
            print(f"  CS={cs:2d}: R={initial:8s} W → {after:8s}{marker}")

    # Reset to 0
    cmd(p, {"type":"set_cur","wValue":(cs<<8)|0,"wIndex":0x0B00,"data":[0,0]})

print("\n=== Can we write FU11 CS=2 with larger CH numbers? ===")
# Maybe instrument mode uses CN > 2 on FU11?
for cn in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 32, 64, 128, 255]:
    r = cmd(p, {"type":"get_cur","wValue":(2<<8)|cn,"wIndex":0x0B00,"length":2})
    can_r = "data" in r
    if can_r:
        raw = int.from_bytes(bytes(r["data"]), 'little', signed=True)
        print(f"  CN={cn:3d}: R={raw/256.0:.1f}dB")
    else:
        pass  # STALL

print("\n=== Explore entities 0x38-0x3F for CH1 ===")
for eid in range(0x38, 0x40):
    entity = (eid << 8) | 0
    for cs in [0, 1, 2, 3, 4, 5, 6, 7]:
        r = cmd(p, {"type":"get_cur","wValue":(cs<<8)|0,"wIndex":entity,"length":4})
        if "data" in r and r["data"]:
            vals = bytes(r["data"])
            if any(b != 0 for b in vals):
                print(f"  Entity 0x{entity:04x} CS={cs}: {vals.hex()}")

p.stdin.write("QUIT\n")
p.stdin.flush()
p.wait()
print("\n✅ Done")
