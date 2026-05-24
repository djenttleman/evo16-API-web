#!/usr/bin/env python3
"""Test: write FU11 through DFU interface (bypasses audio driver)."""
import subprocess, json, time

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    line = json.dumps(c, separators=(',', ':'))
    p.stdin.write(line + "\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

# Read current values
print("=== Via Audio IF (standard UAC2) ===")
r = cmd(p, {"type":"get_cur","wValue":0x0201,"wIndex":0x0B00,"length":2})
raw_audio = int.from_bytes(bytes(r.get("data",b"")),'little',signed=True)
print(f"  FU11 IF0: {raw_audio/256.0:.1f} dB")

print("\n=== Via DFU IF3 ===")
r = cmd(p, {"type":"ctrl","bmReqType":0xA1,"bReq":0x01,
             "wValue":0x0201,"wIndex":0x0B03,"length":2})
raw_dfu = int.from_bytes(bytes(r.get("data",b"")),'little',signed=True)
print(f"  FU11 IF3: {raw_dfu/256.0:.1f} dB")

# Write +25 dB via Audio IF
print("\n=== SET +25 dB via Audio IF0 ===")
r = cmd(p, {"type":"set_cur","wValue":0x0201,"wIndex":0x0B00,"data":[0,25]})
print(f"  SET IF0: {r}")
r = cmd(p, {"type":"get_cur","wValue":0x0201,"wIndex":0x0B00,"length":2})
rb = int.from_bytes(bytes(r.get("data",b"")),'little',signed=True)
print(f"  Read IF0: {rb/256.0:.1f} dB")

# Write +25 dB via DFU IF3
print("\n=== SET +25 dB via DFU IF3 ===")
data_bytes = [0, 25]  # 25*256 = 6400 = 0x1900
r = cmd(p, {"type":"ctrl","bmReqType":0x21,"bReq":0x01,
             "wValue":0x0201,"wIndex":0x0B03,"data":data_bytes})
print(f"  SET IF3: {r}")
r = cmd(p, {"type":"ctrl","bmReqType":0xA1,"bReq":0x01,
             "wValue":0x0201,"wIndex":0x0B03,"length":2})
rb = int.from_bytes(bytes(r.get("data",b"")),'little',signed=True)
print(f"  Read IF3: {rb/256.0:.1f} dB")

# Read IF0 again
r = cmd(p, {"type":"get_cur","wValue":0x0201,"wIndex":0x0B00,"length":2})
rb = int.from_bytes(bytes(r.get("data",b"")),'little',signed=True)
print(f"  Read IF0 after IF3 write: {rb/256.0:.1f} dB")

# Reset
cmd(p, {"type":"set_cur","wValue":0x0201,"wIndex":0x0B00,"data":[0,0]})
cmd(p, {"type":"ctrl","bmReqType":0x21,"bReq":0x01,
        "wValue":0x0201,"wIndex":0x0B03,"data":[0,0]})

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()

print("\n🔍 Si IF0 e IF3 comparten el mismo registro, son el mismo control.")
print("   Pero si hay diferencias, la DFU bypass el driver de audio.")
print("DAVID: ¿cambió el nivel de audio durante la prueba? Responde en Telegram.")
