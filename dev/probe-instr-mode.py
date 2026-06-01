#!/usr/bin/env python3
"""Explore Instrument Mode (DI/High-Z) on EVO 16 CH1-2 via EU58 CS=5."""
import subprocess, json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c, separators=(',',':')) + "\n")
    p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

print("=== EU58 CS=5 — Instrument Mode candidates ===\n")

# Read current state for CH1 and CH2
print("── Current state ──")
for cn in [0, 1, 2, 3]:  # CH1-4
    wV = (5 << 8) | cn
    r = cmd(p, {"type":"get_cur","wValue":wV,"wIndex":0x3A00,"length":4})
    if "data" in r:
        vals = bytes(r["data"])
        d0 = vals[0]
        d1 = vals[1]
        d2 = vals[2]
        d3 = vals[3]
        print(f"  CH{cn+1} (CN={cn}): [{d0},{d1},{d2},{d3}]  hex={vals.hex()}")

# Try reading as different lengths
print("\n── Try different read lengths ──")
for length in [1, 2, 3, 4, 8]:
    r = cmd(p, {"type":"get_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"length":length})
    if "data" in r:
        print(f"  CH1 len={length}: {bytes(r['data']).hex()}")

# Now toggle — write 1 to CH1 and read back
print("\n── Toggle CH1 (CN=0) ──")
print("  Before:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"length":4})["data"]).hex())

print("  Writing [0,0,0,0]...")
r = cmd(p, {"type":"set_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"data":[0,0,0,0]})
print(f"  → {r}")
print("  After:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"length":4})["data"]).hex())

print("  Writing [1,0,0,0]...")
r = cmd(p, {"type":"set_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"data":[1,0,0,0]})
print(f"  → {r}")
print("  After:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"length":4})["data"]).hex())

print("\n── Toggle CH2 (CN=1) ──")
print("  Before:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|1,"wIndex":0x3A00,"length":4})["data"]).hex())
print("  Writing [1,0,0,0]...")
r = cmd(p, {"type":"set_cur","wValue":(5<<8)|1,"wIndex":0x3A00,"data":[1,0,0,0]})
print(f"  → {r}")
print("  After:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|1,"wIndex":0x3A00,"length":4})["data"]).hex())

# Try CH3 (shouldn't have instrument mode)
print("\n── CH3 (CN=2) — should NOT have instrument ──")
print("  Before:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|2,"wIndex":0x3A00,"length":4})["data"]).hex())
r = cmd(p, {"type":"set_cur","wValue":(5<<8)|2,"wIndex":0x3A00,"data":[1,0,0,0]})
print(f"  Write [1,0,0,0] → {r}")
print("  After:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|2,"wIndex":0x3A00,"length":4})["data"]).hex())

# Reset to defaults
print("\n── Reset to defaults ──")
cmd(p, {"type":"set_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"data":[0,0,0,0]})
cmd(p, {"type":"set_cur","wValue":(5<<8)|1,"wIndex":0x3A00,"data":[0,0,0,0]})
print("  CH1:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|0,"wIndex":0x3A00,"length":4})["data"]).hex())
print("  CH2:", bytes(cmd(p, {"type":"get_cur","wValue":(5<<8)|1,"wIndex":0x3A00,"length":4})["data"]).hex())

p.stdin.write("QUIT\n")
p.stdin.flush()
p.wait()
print("\n✅ Probe complete")
