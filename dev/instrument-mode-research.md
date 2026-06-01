# Instrument Mode — Investigación Exhaustiva

> **Fecha:** 2026-05-31  
> **Estado:** ❌ NO FUNCIONA — Requiere captura USB de bajo nivel  
> **Autor:** Auri + OpenCode (GPT-5.5)  
> **Dispositivo:** Audient EVO 16 + SP8 en ADAT 1 y ADAT 2

---

## Resumen

El **instrument mode** (modo DI de alta impedancia para guitarra/bajo en los jacks TS frontales de CH1 y CH2) **no es controlable por software** a través de los protocolos UAC2 estándar (GET_CUR/SET_CUR).

La app oficial **Audient EVO Control** sí puede activarlo, pero lo hace mediante un **vendor-specific control transfer** (bmRequestType 0x40) que no es visible en el espacio UAC2. Capturar ese comando requiere sniffing USB de bajo nivel (Wireshark, dtruss, o hardware analyzer).

---

## Lo que NO funciona

### 1. EU58 CS=5 — "input impedance/gain staging"

El DESIGN.md del EVO4 documenta EU58 CS=5 como posible control de impedancia de entrada. En el EVO 16:

| Payload | Formato | Resultado |
|---------|---------|-----------|
| `[0x01, 0x00, 0x00, 0x00]` | 4 bytes | FAIL — sin efecto |
| `[0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]` | 8 bytes | **OK** — pero sin efecto físico |
| `[0xFF, ...]` | 8 bytes | OK — sin efecto |
| `[0x80, ...]` | 8 bytes | OK — sin efecto |
| `[0x02, ...]` | 8 bytes | OK — sin efecto |

**Conclusión:** CS=5 acepta escritura de 8 bytes (NO 4), pero el firmware del EVO 16 **no commuta el hardware** al recibir este valor. Es un eco fantasma.

### 2. Botón físico INSTR

El botón físico del panel frontal del EVO 16 maneja la conmutación internamente en el microcontrolador. **No se refleja en ningún registro USB** visible vía GET_CUR. El DESIGN.md del EVO4 ya lo documenta: "No HID interface. Front panel buttons/knob are internal to the device microcontroller."

### 3. Toggle INSTR desde Audient EVO Control

Al hacer toggle del botón INSTR en la app oficial, **ningún registro UAC2 cambia** en las siguientes entidades monitoreadas:

- **EU58** (0x3A00) — CS=0 a 15 para CH1, CH2, CH3
- **FU11** (0x0B00) — CS=2 para CH1, CH2, CH3
- **MU60** (0x3C00) — CS=0, 1, 6 para CH1, CH2, CH3
- **EU62** (0x3E00) — CS=0, 1, 3, 6 para CH1, CH2, CH3

**Total:** 40 registros monitoreados, **cero cambios detectados.**

### 4. state.xml manipulation

Modificar `instrument="0"` → `instrument="1"` en `~/Library/Application Support/Audient/EVO/state.xml` y luego cargar la app **no produce cambios** en los registros USB al abrir/cerrar la app. La app parece persistir el valor en disco pero no siempre lo envía al dispositivo al arrancar.

### 5. DFU interface

Probar CS=5 a través de la interfaz DFU (wIndex 0x3A03 en vez de 0x3A00) produce el mismo resultado fantasma — escritura aceptada, zero efecto hardware.

### 6. MU60 (0x3C00) como mixer/control

MU60 es un mixer unit (CS=1, UAC2 estándar) para loopback, no controla impedancia de entrada. Registro `0x3C00 CS=0` tiene `00 80 00 00` constante para todos los canales.

---

## Lo que SÍ se descubrió

### state.xml structure

El archivo de estado de la app contiene un atributo `instrument` por canal:

```xml
<inputs>
  <input index="0" phantom="0" gain="0" mute="0" link="0" instrument="0"/>   <!-- CH1 -->
  <input index="1" phantom="0" gain="0" mute="0" link="0" instrument="0"/>   <!-- CH2 -->
  <input index="2" phantom="0" gain="0" mute="0" link="0" instrument="0"/>   <!-- CH3 -->
  <input index="3" phantom="0" gain="0" mute="0" link="0" instrument="5"/>   <!-- CH4 -->
</inputs>
```

Valores observados de `instrument`:
- `0` = line/mic (off)
- `1` = instrument (on, CH1-2 solamente)
- `5` = ??? (visto en CH4, posiblemente un tipo de entrada diferente)

Esto sugiere que **no es un booleano simple** sino un enum o bitmask interno.

### Protocolo 8-byte para CS=5

A diferencia de otros controles EU58 (phantom=4 bytes, gain=4 bytes, mute=4 bytes), el CS=5 requiere **exactamente 8 bytes** de payload. Escribir 4 bytes resulta en `status: fail` (aunque el valor fantasma cambia). Escribir 8 bytes da `status: ok`.

### Reverse engineering del binario

Strings extraídos de `/Applications/EVO.app/Contents/MacOS/EVO`:

| String | Interpretación |
|--------|---------------|
| `FEATURE_UNIT`, `EXTENSION_UNIT` | Entidades UAC2 |
| `GAIN`, `MUTE`, `Gain Boost Button` | Controles de ganancia |
| `IOUSBDevice`, `IOService` | Acceso USB vía IOKit |
| `Could not open interface` | Manejo de error de interfaz USB |
| `juce21AudioIODeviceCallback` | JUCE v21 — framework de audio |
| `DFU Download/Upload/Sync/Idle` | Solo firmware update (no runtime) |
| `HID` | Posible interfaz HID, no confirmada para EVO16 |
| `InputChannelModel`, `InputControlModel` | Modelos de canal en UI |

**Conclusión de OpenCode (GPT-5.5):** La app usa un vendor-specific control transfer (bmRequestType 0x40) a través de IOKit/IOUSB, fuera del espacio UAC2 visible. No es DFU (firmware update), probablemente no es HID. El comando real requiere captura USB de bajo nivel para ser replicado.

---

## Próximos pasos (si se retoma)

1. **Wireshark con captura USB** en macOS 14 — requiere configuración especial
2. **dtruss/dtrace** sobre el proceso EVO Control mientras togglea INSTR — requiere sudo + posiblemente SIP relajado
3. **Hardware USB analyzer** — overkill pero definitivo

---

## Configuración del setup de prueba

| Dispositivo | Ajuste | Valor |
|-------------|--------|-------|
| macOS | Sample Rate | 48 kHz |
| EVO 16 | Clock Source | Internal |
| SP8 | Sample Rate | AUTO |
| SP8 | Clock Source | Digital |
| SP8 | World Clock Termination | OFF |

---

## Referencias

- DESIGN.md: EU58 CS=5 "may control input impedance/gain staging" (EVO4, unconfirmed)
- state.xml: `~/Library/Application Support/Audient/EVO/state.xml`
- Binario: `/Applications/EVO.app/Contents/MacOS/EVO`
- Protocolo verificado: ver `backend/service.py` constantes `VERIFIED_*`
