#!/usr/bin/env python3
"""Try entity 0x3D for ADAT-specific writes, and CS=5/9 on EU58."""
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

# Test specific channels
for title, ch, context in [
    ("CH9 ADAT1", 9, 8),
    ("CH17 ADAT2", 17, 16),
]:
    CN = ch - 1
    wV_gain = (1 << 8) | CN  # CS=1 gain
    wV_mute = (2 << 8) | CN  # CS=2 mute
    
    print(f"\n{'='*60}")
    print(f"=== {title} (CN={CN}) ===")
    
    # Read baseline
    r = cmd(p, {"type":"get_cur","wValue":wV_gain,"wIndex":0x3A00,"length":4})
    baseline_gain = bytes(r["data"])[1]
    print(f"  EU58 gain baseline: {baseline_gain}dB")
    
    # Write gain 42dB via NORMAL path
    cmd(p, {"type":"set_cur","wValue":wV_gain,"wIndex":0x3A00,"data":[0,42,0,0]})
    
    # Now write to CS=5 (the unusual one with ff000000 read)
    print(f"\n  --- Writing CS=5 then CS=6 on EU58 ---")
    
    # CS=5 might be some ADAT routing/config
    r = cmd(p, {"type":"set_cur","wValue":(5<<8)|CN,"wIndex":0x3A00,"data":[1,0,0,0]})
    print(f"  CS=5 write [1,...]: {r}")
    r = cmd(p, {"type":"get_cur","wValue":(5<<8)|CN,"wIndex":0x3A00,"length":4})
    print(f"  CS=5 readback: {bytes(r.get('data',[])).hex()}")
    
    # CS=6 might be ADAT gain forward
    r = cmd(p, {"type":"set_cur","wValue":(6<<8)|CN,"wIndex":0x3A00,"data":[0,42,0,0]})
    print(f"  CS=6 write [0,42,...]: {r}")
    r = cmd(p, {"type":"get_cur","wValue":(6<<8)|CN,"wIndex":0x3A00,"length":4})
    print(f"  CS=6 readback: {bytes(r.get('data',[])).hex()}")
    
    # Try the entity 0x3D with ADAT offset
    print(f"\n  --- Entity 0x3D00 (ADAT specific?) ---")
    for cso in [0,1,2,3,4,5,6,7,8]:
        wV = (cso << 8) | CN
        # Read
        r = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3D00,"length":4})
        if "data" in r:
            vals = bytes(r["data"])
            if vals[1] != 0 or any(v != 0 for v in vals):
                print(f"    CS={cso} GET: {vals.hex()}")
        # Write 42
        r = cmd(p, {"type":"set_cur","wValue":wV,"wIndex":0x3D00,"data":[0,42,0,0]})
        if "status" in r:
            rr = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3D00,"length":4})
            print(f"    CS={cso} SET accepted → {bytes(rr.get('data',[])).hex()}")

    # Final: read EU58 to see if anything changed
    r = cmd(p, {"type":"get_cur","wValue":wV_gain,"wIndex":0x3A00,"length":4})
    print(f"\n  EU58 gain final: {bytes(r['data'])[1]}dB")

p.stdin.write("QUIT\n")
p.stdin.flush()
p.wait()
print("\n✅ Done")
