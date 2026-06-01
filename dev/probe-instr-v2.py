#!/usr/bin/env python3
"""Deep probe: find instrument mode across all entities and CS values.
Tests FU11, EU58, FU12, FU13 for CH1 and CH2 with every CS 0-15."""

import subprocess, json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c, separators=(',',':')) + "\n")
    p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

entities = [
    (0x0B00, "FU11 (Input Gain)"),
    (0x3A00, "EU58 (Input Config)"),
    (0x0C00, "FU12 (EVO16 extra)"),
    (0x0D00, "FU13 (EVO16 extra)"),
    (0x3D00, "EU61 (unknown)"),
]

for entity, name in entities:
    print(f"\n{'='*55}")
    print(f"=== {name} — 0x{entity:04x} ===")

    for cn in [0, 1]:  # CH1, CH2
        print(f"\n  CH{cn+1} (CN={cn}):")
        for cs in range(0, 16):
            wV = (cs << 8) | cn

            # Read current
            r = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":entity,"length":4})
            can_read = "data" in r
            read_val = bytes(r.get("data",[])).hex() if can_read else "STALL"

            # Only print non-trivial reads
            is_interesting = can_read and any(b != 0 for b in r.get("data",[]))

            if can_read:
                # Try writing [1,0,0,0] and see if readback changes
                rw = cmd(p, {"type":"set_cur","wValue":wV,"wIndex":entity,"data":[1,0,0,0]})
                can_write = "status" in rw

                if can_write:
                    # Read back
                    rr = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":entity,"length":4})
                    after = bytes(rr.get("data",[])).hex()
                    changed = after != read_val

                    # Only print if write was accepted and something interesting
                    marker = ""
                    if changed:
                        marker = " ← CHANGED"
                    marquee = " ◀◀" if is_interesting and changed else ""
                    print(f"    CS={cs:2d}: R={read_val:10s}  W=✓ → {after:10s}{marker}{marquee}")
                    # Reset to original
                    cmd(p, {"type":"set_cur","wValue":wV,"wIndex":entity,"data":list(bytes.fromhex(read_val))})
                else:
                    # Write failed, read-only register
                    pass  # Most are RO, don't clutter
            elif is_interesting:
                print(f"    CS={cs:2d}: R={read_val:10s}  (read-only)")

# Also try 2-byte reads on FU11 for all CS
print(f"\n{'='*55}")
print("=== FU11 2-byte reads (UAC2 standard format) ===")
for cn in [0, 1]:
    print(f"\n  CH{cn+1} (CN={cn}):")
    for cs in range(0, 16):
        wV = (cs << 8) | cn
        r = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x0B00,"length":2})
        if "data" in r:
            raw = int.from_bytes(bytes(r["data"]), 'little', signed=True)
            db = raw / 256.0
            hex_str = bytes(r["data"]).hex()
            if raw != 0 or cs in [0,1,2,3,4,5,6,7,8,9]:
                print(f"    CS={cs:2d}: {hex_str} = {db:.1f} dB (raw={raw})")

# Try writing different byte patterns to EU58 CS=5
print(f"\n{'='*55}")
print("=== EU58 CS=5 — different byte patterns ===")
patterns = [
    ([0,0,0,0], "0x00000000"),
    ([1,0,0,0], "0x01000000 (tried)"),
    ([2,0,0,0], "0x02000000"),
    ([255,0,0,0], "0xFF000000 (default)"),
    ([1,1,0,0], "0x01010000"),
    ([255,255,0,0], "0xFFFF0000"),
    ([0,1,0,0], "0x00010000"),
    ([128,0,0,0], "0x80000000"),
]
for data, desc in patterns:
    cmd(p, {"type":"set_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"data":data})
    r = cmd(p, {"type":"get_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"length":4})
    after = bytes(r["data"]).hex()
    # Also check if gain got affected
    rg = cmd(p, {"type":"get_cur","wValue":(1<<8)|0,"wIndex":0x3A00,"length":4})
    gain_byte = bytes(rg["data"])[1] if "data" in rg else "?"
    print(f"  Write {desc:20s} → CS5={after:10s}  gain byte[1]={gain_byte}")

# Reset
cmd(p, {"type":"set_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"data":[255,0,0,0]})

p.stdin.write("QUIT\n")
p.stdin.flush()
p.wait()
print("\n✅ Probe complete")
