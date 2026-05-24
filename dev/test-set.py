#!/usr/bin/env python3
"""Simple test: one SET command then QUIT."""
import subprocess
import json
import sys

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

proc = subprocess.Popen(
    [HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True
)

# Read READY
line = proc.stdout.readline()
print(f"Got: {line.strip()}")

# Write SET command
cmd = json.dumps({"type": "set", "wValue": 0x0201, "wIndex": 0x0B00, "data": [0, 50]})
print(f"Sending: {cmd}")
proc.stdin.write(cmd + "\n")
proc.stdin.flush()

# Read response
resp = proc.stdout.readline()
print(f"Response: {resp.strip()}")

# QUIT
proc.stdin.write("QUIT\n")
proc.stdin.flush()
proc.wait(timeout=5)
print("Done!")
