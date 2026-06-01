#!/usr/bin/env python3
"""Dump EVO 16 USB config descriptor to see all interfaces."""
import subprocess, json

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
ready = p.stdout.readline().strip()
print(f"READY: {ready}")

# Get config descriptor
p.stdin.write('{"type":"config_desc"}\n')
p.stdin.flush()
resp = json.loads(p.stdout.readline())

if "data" not in resp:
    print(f"FAILED: {resp}")
    p.kill()
    exit(1)

raw = bytes(resp["data"])
print(f"\nConfig descriptor: {len(raw)} bytes")
print(f"First 128 bytes hex:")
for i in range(0, min(128, len(raw)), 16):
    hexp = ' '.join(f'{b:02x}' for b in raw[i:i+16])
    asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw[i:i+16])
    print(f"  {i:04x}: {hexp}  {asc}")

# Parse descriptors
print("\n=== Interface & Endpoint descriptors ===")
i = 0
class_names = {
    0x01: "Audio", 0x02: "CDC/Comm", 0x03: "HID", 0x05: "Physical",
    0x06: "Image", 0x07: "Printer", 0x08: "MSD", 0x09: "Hub",
    0x0A: "CDC/Data", 0x0B: "SmartCard", 0x0D: "Security",
    0x0E: "Video", 0x0F: "Health", 0x10: "AV",
    0xDC: "Diag", 0xE0: "WLC", 0xEF: "Misc", 0xFE: "AppSpecific",
    0xFF: "Vendor"
}
sub_names = {
    (1, 1): "UAC1 Ctrl", (1, 2): "UAC1 Stream", (1, 3): "MIDI",
    (1, 0x20): "UAC2 Ctrl", (1, 0x21): "UAC2 Stream",
    (1, 0x30): "UAC3 Ctrl", (1, 0x31): "UAC3 Stream",
    (254, 1): "DFU", (254, 2): "DFU-RT", (3, 0): "NoSub",
}

ep_names = {0x01: "Isoch", 0x02: "Bulk", 0x03: "Interrupt"}
ep_dir = {0x00: "OUT", 0x20: "IN"}

while i < len(raw):
    blen = raw[i] if i < len(raw) else 0
    if blen == 0: break
    bdesc = raw[i+1] if i+1 < len(raw) else 0
    desc_types = {
        1: "DEVICE", 2: "CONFIG", 4: "INTERFACE", 5: "ENDPOINT",
        11: "CS_INTERFACE", 12: "CS_ENDPOINT", 15: "BOS",
        16: "DEVICE_CAP", 36: "IAD",
    }
    dt = desc_types.get(bdesc, f"#{bdesc}")
    
    if bdesc == 4 and i+8 < len(raw):
        intf_num = raw[i+2]
        alt_set = raw[i+3]
        num_eps = raw[i+4]
        cls = raw[i+5]
        sub = raw[i+6]
        prot = raw[i+7]
        cname = class_names.get(cls, f"{cls:#04x}")
        sname = sub_names.get((cls, sub), f"sub={sub:#04x}")
        print(f"  INTERFACE {intf_num}.{alt_set}: {num_eps}EPs {cname}/{sname} prot={prot:#04x}")
        
    elif bdesc == 5 and i+6 < len(raw):
        ep_addr = raw[i+2]
        attrs = raw[i+3]
        maxpkt = raw[i+4] | (raw[i+5] << 8)
        dir_s = ep_dir.get(ep_addr & 0x80, f"#{ep_addr & 0x80:#04x}")
        ep_n = ep_addr & 0x0F
        ep_t = ep_names.get(attrs & 0x03, f"#{attrs & 0x03}")
        print(f"    EP {ep_n:02d} {dir_s:4s}: {ep_t} maxpkt={maxpkt}")
    
    elif bdesc == 36 and i+7 < len(raw):
        func = raw[i+2]
        cls = raw[i+3]
        sub = raw[i+4]
        prot = raw[i+5]
        nintfs = raw[i+6]
        print(f"  IAD: func={func} cls={cls:#04x} sub={sub:#04x} prot={prot:#04x} ({nintfs} intfs)")
        
    elif bdesc == 1:
        vid = raw[i+8] | (raw[i+9] << 8)
        pid = raw[i+10] | (raw[i+11] << 8)
        print(f"  DEVICE: VID={vid:#06x} PID={pid:#06x}")
        
    i += max(blen, 1)

p.stdin.write("QUIT\n")
p.stdin.flush()
p.wait()
