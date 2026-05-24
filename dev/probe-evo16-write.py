#!/usr/bin/env python3
"""Test WRITE operations on EVO 16 and read back to verify."""

import subprocess
import json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def send_cmd(proc, cmd):
    proc.stdin.write(json.dumps(cmd) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())

proc = subprocess.Popen(
    [HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True
)
proc.stdout.readline()  # READY

def test_write_read(label, wValue, wIndex, data_bytes):
    """Write bytes, then read back."""
    print(f"\n--- {label} ---")
    # Write
    resp = send_cmd(proc, {"type": "set", "wValue": wValue, "wIndex": wIndex, "data": list(data_bytes)})
    print(f"  SET: {resp}")
    # Read back
    resp = send_cmd(proc, {"type": "get", "wValue": wValue, "wIndex": wIndex, "length": len(data_bytes)})
    raw = bytes(resp["data"])
    print(f"  GET: {raw.hex()} = {raw}")
    return raw

# Test 1: Set gain on IN1 to ~25 dB (raw = 25 * 256 = 6400 = 0x1900)
val_25db = (25 * 256) & 0xFFFF
data = val_25db.to_bytes(2, 'little')
test_write_read("Gain IN1 → 25 dB", 0x0201, 0x0B00, data)

# Test 2: Set gain on IN2 to ~12 dB
val_12db = (12 * 256) & 0xFFFF
data = val_12db.to_bytes(2, 'little')
test_write_read("Gain IN2 → 12 dB", 0x0202, 0x0B00, data)

# Test 3: Phantom ON for input 1
test_write_read("Phantom IN1 → ON", 0x0000, 0x3A00, b"\x01\x00\x00\x00")

# Test 4: Mute input 1
test_write_read("Mute IN1 → ON", 0x0200, 0x3A00, b"\x01\x00\x00\x00")

# Test 5: Reset everything
test_write_read("Gain IN1 → 0 dB", 0x0201, 0x0B00, (0).to_bytes(2, 'little', signed=True))
test_write_read("Phantom IN1 → OFF", 0x0000, 0x3A00, b"\x00\x00\x00\x00")
test_write_read("Mute IN1 → OFF", 0x0200, 0x3A00, b"\x00\x00\x00\x00")

# Test 6: Volume (try a known value)
vol_minus10 = round(-10.0 * 256) & 0xFFFF
test_write_read("Volume OUT1 → -10 dB", 0x0201, 0x0A00, vol_minus10.to_bytes(2, 'little'))

# Test 7: Try writing volume with signed format
vol_data = (-2560).to_bytes(2, 'little', signed=True)
test_write_read("Volume OUT1 → -10 dB (signed)", 0x0201, 0x0A00, vol_data)

# Test 8: Try 0 dB for volume
test_write_read("Volume OUT1 → 0 dB", 0x0201, 0x0A00, (0).to_bytes(2, 'little', signed=True))

proc.stdin.write("QUIT\n")
proc.stdin.flush()
proc.wait()
print("\n✅ All tests complete!")
