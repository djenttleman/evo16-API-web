#!/usr/bin/env python3
"""
Quick differential scanner for EVO 16.
Only scans entities we KNOW respond, with fast timeout.
"""
import subprocess, json, sys, os, signal

BINARY = os.path.join(os.path.dirname(__file__), "mac-evo16")
RESULTS = []

def run_cmd(proc, cmd_json, timeout=2):
    try:
        proc.stdin.write(json.dumps(cmd_json) + "\n")
        proc.stdin.flush()
    except:
        return None
    line = proc.stdout.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except:
        return {"raw": line.strip()}

# Start binary
proc = subprocess.Popen(
    [BINARY, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True
)
ready = proc.stdout.readline()
if "READY" not in ready:
    print(f"FATAL: {ready}", file=sys.stderr)
    sys.exit(1)

# Quick scan: entities 10-13 with CS 0-2, lengths 1,2,4
# plus EU58, EU59, MU60
entities = [
    (0x0A00, "FU10_OUT"),
    (0x0B00, "FU11_IN"),
    (0x0C00, "FU12"),
    (0x0D00, "FU13"),
    (0x3A00, "EU58"),
    (0x3B00, "EU59"),
    (0x3C00, "MU60"),
]

out = {}
for wIndex, name in entities:
    for cs in [0, 1, 2]:
        for length in [2, 4]:
            resp = run_cmd(proc, {
                "type": "get_cur",
                "wValue": (cs << 8),
                "wIndex": wIndex,
                "length": length
            })
            if resp and "data" in resp and resp["data"]:
                key = f"{name}_CS{cs}_L{length}"
                hex_str = " ".join(f"{b:02x}" for b in resp["data"])
                # Try DB conversion for 2-byte reads on FUs
                if length == 2 and "FU" in name:
                    raw_val = int.from_bytes(bytes(resp["data"]), 'little', signed=True)
                    db = raw_val / 256.0
                    out[key] = f"{hex_str}  ({db:.1f} dB)"
                else:
                    out[key] = hex_str

# Kill process (QUIT may not be handled)
proc.kill()
proc.wait(timeout=1)

# Output as JSON for diffing
print(json.dumps(out, indent=1))
