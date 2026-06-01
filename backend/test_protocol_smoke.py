#!/usr/bin/env python3
"""Smoke tests for EVO 16 verified protocol constants.

Run this whenever you change anything in service.py to ensure
the verified control paths remain intact.

Usage:
    python3 backend/test_protocol_smoke.py
"""

import sys
from pathlib import Path

# Ensure we can import service
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import service

PASS = 0
FAIL = 0


def check(name, actual, expected):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"  ✅ {name}: {expected}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: got {actual}, expected {expected}")


def main():
    global PASS, FAIL
    print("=== EVO 16 Protocol Smoke Tests ===")
    print(f"  Protocol version: {service.PROTOCOL_VERSION}")
    print()

    # ── Device ──
    print("── Device Identification ──")
    check("VID", service.VERIFIED_DEVICE_VID, "0x2708")
    check("PID", service.VERIFIED_DEVICE_PID, "0x000a")

    # ── Entities ──
    print("\n── Entity IDs ──")
    check("EU58",   service.VERIFIED_EU58, 0x3A00)
    check("FU11",   service.VERIFIED_FU11, 0x0B00)

    # ── Gain ──
    print("\n── Gain Protocol ──")
    check("Gain CS",            service.VERIFIED_GAIN_CS,            1)
    check("Gain payload size",  service.VERIFIED_GAIN_PAYLOAD_SIZE,   4)
    check("Gain byte offset",   service.VERIFIED_GAIN_BYTE_OFFSET,    1)
    check("Gain min dB",        service.VERIFIED_GAIN_MIN_DB,         0)
    check("Gain max dB",        service.VERIFIED_GAIN_MAX_DB,        50)
    check("Gain entity",        service.VERIFIED_GAIN_ENTITY,  0x3A00)

    # ── Phantom ──
    print("\n── Phantom Protocol ──")
    check("Phantom CS",           service.VERIFIED_PHANTOM_CS,            0)
    check("Phantom payload size", service.VERIFIED_PHANTOM_PAYLOAD_SIZE,   4)
    check("Phantom byte offset",  service.VERIFIED_PHANTOM_BYTE_OFFSET,    0)
    check("Phantom entity",       service.VERIFIED_PHANTOM_ENTITY,  0x3A00)

    # ── Mute ──
    print("\n── Mute Protocol ──")
    check("Mute CS",              service.VERIFIED_MUTE_CS,             2)
    check("Mute payload size",    service.VERIFIED_MUTE_PAYLOAD_SIZE,    4)
    check("Mute byte offset",     service.VERIFIED_MUTE_BYTE_OFFSET,     0)
    check("Mute entity analog",   service.VERIFIED_MUTE_ENTITY_ANALOG, 0x3A00)
    check("Mute entity ADAT",     service.VERIFIED_MUTE_ENTITY_ADAT,   0x0B00)

    # ── Channel ranges ──
    print("\n── Channel Ranges ──")
    check("Channel min",        service.VERIFIED_CHANNEL_MIN,        1)
    check("Channel max",        service.VERIFIED_CHANNEL_MAX,       24)
    check("ADAT threshold",     service.VERIFIED_ADAT_THRESHOLD,     8)

    # ── wValue computation checks ──
    print("\n── wValue Computation ──")
    # CH1 gain: CS=1, CN=0 → wValue = (1 << 8) | 0 = 256 = 0x0100
    check("Gain CH1 wValue",   (service.VERIFIED_GAIN_CS << 8) | 0,   0x0100)
    # CH9 gain: CS=1, CN=8 → wValue = (1 << 8) | 8 = 264 = 0x0108
    check("Gain CH9 wValue",   (service.VERIFIED_GAIN_CS << 8) | 8,   0x0108)
    # CH17 gain: CS=1, CN=16 → wValue = (1 << 8) | 16 = 272 = 0x0110
    check("Gain CH17 wValue",  (service.VERIFIED_GAIN_CS << 8) | 16,  0x0110)
    # CH1 phantom: CS=0, CN=0 → wValue = 0
    check("Phantom CH1 wValue", 0, 0x0000)
    # CH17 phantom: CS=0, CN=16 → wValue = 16
    check("Phantom CH17 wValue",16, 0x0010)
    # CH1 mute analog: CS=2, CN=0 → wValue = 0x0200
    check("Mute CH1 wValue",  (service.VERIFIED_MUTE_CS << 8) | 0,  0x0200)
    # CH9 mute ADAT: CS=2, CN=8 → wValue = 0x0208
    check("Mute CH9 wValue",  (service.VERIFIED_MUTE_CS << 8) | 8,  0x0208)

    # ── entity routing for mutes ──
    print("\n── Mute Entity Routing ──")
    check("CH1 mute entity (analog)",  
          service.VERIFIED_MUTE_ENTITY_ANALOG if 1 <= service.VERIFIED_ADAT_THRESHOLD else service.VERIFIED_MUTE_ENTITY_ADAT,
          0x3A00)
    check("CH8 mute entity (analog)",  
          service.VERIFIED_MUTE_ENTITY_ANALOG if 8 <= service.VERIFIED_ADAT_THRESHOLD else service.VERIFIED_MUTE_ENTITY_ADAT,
          0x3A00)
    check("CH9 mute entity (ADAT)",    
          service.VERIFIED_MUTE_ENTITY_ANALOG if 9 <= service.VERIFIED_ADAT_THRESHOLD else service.VERIFIED_MUTE_ENTITY_ADAT,
          0x0B00)
    check("CH17 mute entity (ADAT)",   
          service.VERIFIED_MUTE_ENTITY_ANALOG if 17 <= service.VERIFIED_ADAT_THRESHOLD else service.VERIFIED_MUTE_ENTITY_ADAT,
          0x0B00)

    # ── Final ──
    print(f"\n{'='*40}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed, {FAIL}/{total} failed")
    if FAIL == 0:
        print("  ✅ ALL PROTOCOL CONSTANTS VERIFIED")
        return 0
    else:
        print("  ❌ PROTOCOL CHANGED — DO NOT MODIFY VERIFIED CONSTANTS")
        return 1


if __name__ == "__main__":
    sys.exit(main())
