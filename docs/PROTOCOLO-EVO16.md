# Protocolo del EVO 16 — referencia verificada

Todo lo de este documento está **verificado contra el hardware** (EVO 16, firmware 1.30, macOS, app
oficial cerrada), salvo lo que diga «pendiente». Reemplaza a las tablas de la investigación EVO8
original del README, cuyos supuestos equivocados se aclaran al final.

## Transporte

- USB Audio Class 2 · VID `0x2708` · PID `0x000A`
- **GET_CUR**: `bmRequestType=0xA1` · **SET_CUR**: `bmRequestType=0x21`
- `wIndex = (bUnitID << 8) | bInterfaceNumber` → para las unidades de control, `wIndex = bUnitID << 8`
  (p. ej. `0x3A00` para la unidad `0x3A`).
  ⚠️ **Ojo con el helper**: `evotool.get(cs, unit, ch)` ya hace el `<< 8` por dentro, así que hay que
  pasarle el **número de unidad** (`0x3A`), no el wIndex completo (`0x3A00`). Con el wIndex completo
  todo devuelve `GET_CUR failed` y parece un endpoint colgado: no lo es.
- `wValue = (CS << 8) | canal` (canal 0-based: CH1 = 0 … CH24 = 23)
- `wLength = 4` en los registros de preamp/volumen; `wLength = 2 × canales` en medidores.

## Mapa de entidades

| Unidad   | Tipo              | Para qué                                                        |
| -------- | ----------------- | --------------------------------------------------------------- |
| `0x01` / `0x02` | Input Terminal  | terminales de entrada                                        |
| `0x0A`   | Feature Unit      | bloque de la línea de preamps                                   |
| `0x0B`   | Feature Unit      | (la doc vieja creía que el link vivía acá: **no**)              |
| `0x14` / `0x16` | Output Terminal | salidas                                                     |
| `0x28`   | Clock Selector    | **fuente de reloj** (CS=1)                                      |
| `0x29` / `0x2C` / `0x2D` | Clock Source | relojes internos / óptica 1 / óptica 2                      |
| `0x33`   | Routing Matrix    | ruteo (`state.xml`) + **loopback** (CS=6)                       |
| `0x36`   | Monitor Controller | **volumen del main** (CS=18), CUE (CS=19+), **store standalone** (CS=24) |
| `0x3A`   | Input Control (EU58) | **preamp**: phantom (CS=0), gain (CS=1), mute (CS=2), **link de par** (CS=3), **DI/instrumento** (CS=4), sync (CS=6) |
| `0x3C`   | Meters            | **medidores** de entradas y de salidas                           |

## Preamp — unidad `0x3A` (EU58)

| Registro             | CS | Datos              | Codificación                                                                 |
| -------------------- | -- | ------------------ | ---------------------------------------------------------------------------- |
| Phantom 48V          | 0  | `[p,0,0,0]`        | 0 = off · 1 = on                                                             |
| **Ganancia**         | 1  | `[0, byte, 0, 0]`  | `byte = dB_UI + 8` ⇒ **byte 0…58 = −8…+50 dB**; el MCU clampa en 58          |
| Mute                 | 2  | `[m,0,0,0]`        | 0 = sin mute · 1 = muteado                                                   |
| **Link de par**      | 3  | `[l,0,0,0]`        | prenderlo en el maestro basta; para apagarlo hay que escribirlo en **ambos** canales |
| **DI / instrumento** | 4  | `[b,0,0,0]`        | **bitmask, bit 1** (`2` = ON). Canales 1-2, 9-10, 17-18. **Read-modify-write obligatorio** |
| Sync                 | 6  | `[s,0,0,0]`        | estado de sincronía del canal                                                |

Con el par linkeado el **firmware espeja** gain y DI: el cliente no debe duplicar escrituras. Al crear
el link, el equipo **unifica el valor del par** (por eso los perfiles se aplican link → mute →
phantom/gain/DI → unmute).

## Reloj — unidad `0x28` (ClockSelector)

| CS | Datos | Valor |
| -- | ----- | ----- |
| 1  | `[v,0,0,0]` | **1 = Internal · 2 = Óptica 1 · 3 = Óptica 2** |

La clase de la app es `UacLib::UacClockSelector` (`setClockSource` / `getSelectedClockSource`).
Cambiarlo a óptica sin nada conectado deja al equipo sin reloj.

## Volumen del main — unidad `0x36` (MonitorController)

| Registro | CS | Datos | Codificación |
| -------- | -- | ----- | ------------ |
| **Volumen del main** | 18 | 2 bytes, entero con signo **Q8.8** | `dB = raw / 256` |
| CUE 1 | 19 | — | mismo formato (`setCue1Volume`); en este firmware los CS 19/20/22 hacen STALL y 21/23 responden 0 dB — **sin mapear** |
| **Store Standalone** | 24 | 4 bytes en cero | **trigger write-only**: guarda el estado completo en la memoria interna de la interfaz |

La pantalla del equipo usa escala **logarítmica**, no lineal:
**`pantalla = 100 × 10^(dB / 96)`** ⇔ **`dB = 96 × log10(pantalla / 100)`**
(comprobado contra el equipo: −96 dB muestra 10 · −61.4 dB muestra 22 · 0 dB muestra 100).
El piso del registro es −128 dB (Q8.8 con signo), que es el silencio real.
Confirmado girando la perilla física (CS=18 pasó de `[174,199]` = −56.3 dB a `[0,160]` = −96.0 dB).
La app oficial **no expone** este control.

## Medidores — unidad `0x3C`

Usan **`GET_MEM`**, no `GET_CUR`: `bmRequestType=0xA1`, **`bRequest=0x03`**, `wIndex = 0x3C00`,
`wLength = 2 × canales`. El **`wValue` elige el bloque**:

| wValue | Bloque                    | Formato                          |
| ------ | ------------------------- | -------------------------------- |
| 0      | niveles de **entrada** (24) | 2 bytes little-endian por canal |
| 1      | niveles de **salida** (16)  | ídem                            |
| 2      | clip de entradas          | 1 byte por canal                 |
| 3      | clip de salidas           | ídem                             |

Cada nivel es una **amplitud lineal de 16 bits**, con `65536 = full scale` ⇒
**`dB = 20·log10(raw / 65536)`** (lo que hace `DecibelConversions::meterIntToDB`).
Medido: un canal sin señal lee `1` = −96.3 dB; `0` significa silencio.
Costo: 4 transferencias ≈ **3 ms** ⇒ apto para medidores en tiempo real (`GET /api/meters`).

Sólo la unidad `0x3C` acepta este request (`0x34` devuelve un bloque parecido; `0x3D`, `0x38`, `0x32`
y `0x3A` hacen STALL).

## Loopback — unidad `0x33` (RoutingMatrix): mecanismo hallado, tabla pendiente

CS=6, 1 byte por canal, en los canales de host **22 y 23**. La app oficial **impone** su valor al
abrir (si se lo cambia por fuera, lo revierte), así que lo que se lee es el valor real del equipo.
Falta mapear las 10 opciones de la app (`DAW 1+2` … `CUE D`) a sus códigos: ver `docs/ROADMAP.md`.

## Correcciones a la documentación anterior (investigación EVO8)

| Decía | En realidad |
| ----- | ----------- |
| Gain 0…50 dB con `[0, dB, 0, 0]` | `byte = dB_UI + 8` ⇒ **−8…+50 dB**, byte 0…58 |
| «Ganancia negativa no escribible (error 58)» | Sí se escribe: era el offset +8 el que faltaba |
| Link en **FU11 (`0x0B`) CS=2** | Link en **EU58 (`0x3A`) CS=3**; el firmware espeja el par |
| No existía el volumen del main | **`0x36` CS=18**, Q8.8 con signo |
| No existían medidores | **`0x3C`**, 4 bloques según `wValue` |
| Sin reloj, sin standalone, sin DI | `0x28` CS=1 · `0x36` CS=24 · `0x3A` CS=4 |

## Método (para retomar la investigación)

1. Buscar en el binario el **modelo**, no lo que muestra la UI: ahí está el CS exacto y el formato
   (`MonitorControllerModel`, `MixerModel::updateInputMeterValues`, `UacLib::UacClockSelector`).
2. Provocar el cambio en la app oficial y comparar bytes.
3. Confirmar contra el hardware (perilla física, canal sin señal, ciclar energía).
4. En registros con bitmask, **read-modify-write** siempre (DI comparte byte en el mismo registro que
   phantom), y pasarle al helper el **número de unidad**, no el wIndex completo.
