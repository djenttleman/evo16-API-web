#!/usr/bin/env python3
"""Prueba clave: ¿FU11 cambia cuando giras el knob físico?"""
import subprocess, json, sys

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def cmd(p, c):
    p.stdin.write(json.dumps(c)+"\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdout.readline()

print("=== FU11 actual (antes de tocar nada) ===")
for ch in [1, 2]:
    r = cmd(p, {"type":"get","wValue":0x0200|ch,"wIndex":0x0B00,"length":2})
    raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
    print(f"  IN{ch}: {raw/256.0:.1f} dB")

print("\n🎯 Ahora girar el KNOB FISICO del canal 1")
print("   Ponlo en cualquier valor DISTINTO al actual")
print("   Luego presiona ENTER en el terminal de Telegram")

# Note: input() won't work in this context, so we'll just do timed reads
# Instead, let me read FU11 continuously for 10 seconds
print("\nLeyendo FU11 cada segundo por 10 segundos...")
print("👉 DAVID: GIRA EL KNOB FISICO DEL CANAL 1 AHORA")
for i in range(10):
    r = cmd(p, {"type":"get","wValue":0x0201,"wIndex":0x0B00,"length":2})
    raw = int.from_bytes(bytes(r["data"]),'little',signed=True)
    print(f"  t={i}s: IN1 = {raw/256.0:.1f} dB", end="")
    r2 = cmd(p, {"type":"get","wValue":0x0202,"wIndex":0x0B00,"length":2})
    raw2 = int.from_bytes(bytes(r2["data"]),'little',signed=True)
    print(f"  IN2 = {raw2/256.0:.1f} dB")
    import time; time.sleep(1)

p.stdin.write("QUIT\n"); p.stdin.flush(); p.wait()
print("\n✅ Monitoreo completo")
print("\n🔍 INTERPRETACION:")
print("   Si FU11 CAMBIO mientras girabas el knob:")
print("     → FU11 SÍ es el preamp. Nuestro SET es interceptado por macOS.")
print("   Si FU11 NO CAMBIO (se queda igual):")
print("     → El preamp físico es otro mecanismo. FU11 es otra cosa.")
