#!/usr/bin/env python3
"""
Full USB entity scanner for Audient EVO 16.
Scans ALL possible entity/CS combinations and vendor-specific requests,
then detects which values changed after the user moves the physical knob.
"""
import subprocess
import json
import sys
import time
import os

BINARY = os.path.join(os.path.dirname(__file__), "mac-evo16")
VID = "0x2708"
PID = "0x000a"

def send_cmd(proc, cmd):
    """Send JSON command and read response."""
    proc.stdin.write(json.dumps(cmd) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"raw": line.strip()}

def uac2_gain_to_db(data_bytes):
    """Convert UAC2 16-bit signed gain (1/256 dB per step) to float dB."""
    if len(data_bytes) < 2:
        return None
    val = int.from_bytes(data_bytes[:2], 'little', signed=True)
    return round(val / 256.0, 1)

def bytes_to_hex(data_bytes):
    return " ".join(f"{b:02x}" for b in data_bytes)

# ====================
# SCAN PLAN
# ====================

# 1. Standard entity units (UAC2)
# Entity 10 = Output volume, Entity 11 = Input gain, etc.
standard_entities = [
    # (wIndex, description, cs_values)
    (0x0A00, "FU10_OUT", [0, 1, 2]),   # Output Volume
    (0x0B00, "FU11_IN",  [0, 1, 2]),   # Input Gain
    (0x0C00, "FU12",     [0, 1, 2]),   # Extra EVO16
    (0x0D00, "FU13",     [0, 1, 2]),   # Extra EVO16
    (0x3A00, "EU58",     [0, 1, 2]),   # Extension Unit (mute/phantom)
    (0x3B00, "EU59",     [0, 1, 2]),   # Extension Unit (output mute)
    (0x3C00, "MU60",     [0, 1, 2]),   # Mixer Unit
]

# 2. Vendor-specific requests through DFU interface
# bmReqType = 0xC1 (vendor, device→host, interface)
# Try common bRequest values with various wValue/wIndex
vendor_requests = [
    # (bmReqType, bRequest, wValue, wIndex, length, description)
    (0xC1, 0x01, 0x0100, 0x0000, 8, "VENDOR_GET_FW_VERSION"),
    (0xC1, 0x02, 0x0100, 0x0000, 16, "VENDOR_GET_STATUS"),
    (0xC1, 0x03, 0x0100, 0x0000, 4, "VENDOR_GET_GAINS"),
    (0xC1, 0x03, 0x0200, 0x0000, 4, "VENDOR_GET_GAINS2"),
    (0xC1, 0x03, 0x0100, 0x0100, 32, "VENDOR_GET_FULLSTATE"),
    (0xC1, 0x83, 0x0100, 0x0000, 4, "VENDOR_83"),
    (0xC1, 0x83, 0x0200, 0x0000, 4, "VENDOR_83_2"),
    # HID-style vendor requests
    (0xA1, 0x01, 0x0100, 0x0000, 4, "HID_GET_REPORT"),
    (0xA1, 0x06, 0x0100, 0x0000, 16, "HID_GET_PROTOCOL"),
]

def run_scan():
    print("🔄 Starting mac-evo16 binary...", file=sys.stderr)
    proc = subprocess.Popen(
        [BINARY, VID, PID],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for READY
    ready_line = proc.stdout.readline()
    if "READY" not in ready_line:
        print(f"ERROR: Binary didn't say READY: {ready_line}", file=sys.stderr)
        proc.kill()
        return
    
    results = {}
    
    # Scan standard entities
    print("📡 Scanning standard UAC2 entities...", file=sys.stderr)
    for wIndex, desc, cs_values in standard_entities:
        for cs in cs_values:
            # Try different lengths: 1, 2, 4, 8 bytes
            for length in [1, 2, 4]:
                resp = send_cmd(proc, {
                    "type": "get_cur",
                    "wValue": (cs << 8),  # CS<<8 | channel
                    "wIndex": wIndex,
                    "length": length
                })
                if resp and "data" in resp and resp["data"]:
                    key = f"{desc}_CS{cs}_L{length}"
                    hex_str = bytes_to_hex(bytes(resp["data"]))
                    # Try to interpret as gain if it's 2 bytes from a Feature Unit
                    if length == 2 and (wIndex & 0xFF00) in [0x0A00, 0x0B00, 0x0C00, 0x0D00]:
                        db = uac2_gain_to_db(bytes(resp["data"]))
                        results[key] = {"hex": hex_str, "db": db, "raw": resp["data"]}
                    else:
                        results[key] = {"hex": hex_str}
    
    # Scan vendor-specific requests
    print("📡 Scanning vendor-specific requests...", file=sys.stderr)
    for bmReqType, bReq, wValue, wIndex, wLength, desc in vendor_requests:
        resp = send_cmd(proc, {
            "type": "ctrl",
            "bmReqType": bmReqType,
            "bReq": bReq,
            "wValue": wValue,
            "wIndex": wIndex,
            "length": wLength
        })
        if resp and "data" in resp and resp["data"]:
            hex_str = bytes_to_hex(bytes(resp["data"]))
            results[desc] = {"hex": hex_str}
        elif resp and "raw" not in str(resp):
            pass  # Error, skip
    
    # Also scan FU10 and FU11 with all CS selectors 0-15
    print("📡 Deep scan FU10/FU11 (all CS 0-15)...", file=sys.stderr)
    for entity, entity_name in [(0x0A00, "FU10_OUT"), (0x0B00, "FU11_IN")]:
        for cs in range(0, 16):
            for length in [2, 4]:
                resp = send_cmd(proc, {
                    "type": "get_cur",
                    "wValue": (cs << 8),
                    "wIndex": entity,
                    "length": length
                })
                if resp and "data" in resp and resp["data"]:
                    key = f"{entity_name}_CS{cs}_L{length}"
                    hex_str = bytes_to_hex(bytes(resp["data"]))
                    results[key] = {"hex": hex_str}
    
    # Close
    send_cmd(proc, {"type": "quit"})
    proc.wait()
    
    # Output results
    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    run_scan()
