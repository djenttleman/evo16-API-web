# SmartGain del EVO 16 — trabajo completo del 16-oct-2026

Documento de cierre de la jornada. **Objetivo del día**: averiguar "el comando de SmartGain" para
aplicarlo a un canal o a todos. Resultado: **el comando no existe** (lo arranca el botón físico del
equipo), pero quedó **todo el mecanismo caracterizado**, el **protocolo verificado en hardware** y el
**camino claro** para clonar el algoritmo.

Nada de esto es teoría: cada afirmación tiene debajo la prueba (hardware real, captura a 0,5 s,
desensamblado del firmware del fabricante, o el código de la app oficial).

---

## 1. Conclusión principal

**El SmartGain vive en el firmware del equipo y lo arranca únicamente el botón físico.**

Flujo real (confirmado por David operando el equipo): **presionar el botón → elegir canal →
presionar otra vez → el equipo mide y ajusta la ganancia**. Si no hay señal suficiente muestra
*Issue Detected* y **restaura la ganancia original**.

**No hay comando de arranque por USB.** La app oficial **solo muestra** el estado (es un espejo):
por eso la app *pol*ea `CS=5` y no escribe otra cosa que `0`.

---

## 2. El protocolo verificado (unidad `0x3A`, InputControl)

| Registro | Qué es | Verificación |
|---|---|---|
| `CS=1` | **Ganancia** — 4 bytes `[0, código, 0, 0]`, `dB_UI = código − 8`, rango `−8…+50 dB` (código `0…58`) | Captura en vivo + app: `fcvtzs w8,d0 ; lsl w3,w8,#8` → `setParameter(1, chan, w3)` |
| `CS=5` | **Estado** del soundcheck: `1` Select Channels · `2/3` Smartgain Listening · `4` Issue Detected · `5/6` Successful · `255` inactivo | Escribirlo (cualquier valor, incluidos 4/5/6 y 255) **solo lo guarda**: el equipo no reacciona. La app lo *pol*ea (`InputControlModel::pollingTimerCallback`) |
| `CS=4` **bit 0** | **Canal elegido** para SmartGain (por canal) | Capturado en vivo con el botón físico. **El host lo escribe y el equipo lo respeta** (probado 1→0→1) |
| `CS=4` **bit 1** | Instrumento / DI | Coincide con el baseline del usuario (ch2 = `2`) |
| `CS=7` | **Qué canales pueden**: `7` = elegible + instrumento (locales 1-2), `3` = elegible (locales 3-8), `0` = no elegible (ADAT 9-24) | Solo lectura (escribir 3 en ch1 no cambia nada: sigue 7). Solo los **8 locales** |
| `CS=0` | 48V/phantom · `CS=2` mute · `CS=3` link (ya documentados) | — |

---

## 3. Pruebas realizadas (para que nadie las repita)

Todas sobre hardware real (firmware del equipo **1.30** = `firmware-img` v1.3.0), con señal real en
los canales 1 y 2, y con la app oficial y el servicio propios **cerrados** (USB libre):

| Prueba | Resultado |
|---|---|
| `CS=5` = `0/1/2/3/4/5/6/255` en canal 1 y canal 2 | Guarda el valor, **la ganancia no se mueve**, no hay estado |
| `CS=5` con payload de 4 **y** de 8 bytes, valor en byte 0/1/2 | Idem: nada |
| `CS=6`, `CS=7`, `CS=8` con 1 y con `0xFF` | Acepta y guarda; nada más ocurre |
| `CS=4` armado (bit0=1) + `CS=5=2` + `CS=5=1` (secuencia que usa la app) | Nada. El equipo no arranca |
| Captura a 0,5 s de **9 CS × 24 canales** durante el flujo físico real | **El arranque no deja huella en ningún registro** |
| Escritura del bit `CS=4` bit0 (que sí es del host) | El equipo lo respeta, pero **no** dispara la medición |

---

## 4. La captura que reveló el algoritmo (canal 8, sin señal)

Sondeo de `CS=1` (ganancia), `CS=4` (banderas) y `CS=5` cada 0,5 s mientras David ejecutaba el flujo
con el botón físico:

```
t~17s   ganancia 0    · flags 1     ← entró al modo (canal elegido)
t~19s   ganancia 5    · flags 1     ← arranca la rampa
t~20s   ganancia 10   · flags 1
t~20s   ganancia 20   · flags 1
t~21s   ganancia 30   · flags 1
t~21s   ganancia 40   · flags 1
t~22s   ganancia 50   · flags 1
t~22s   ganancia 58   · flags 1     ← techo (código 58 = +50 dB)
t~37s   ganancia 0    · flags 1     ← sin señal: RESTAURA el original
t~59s   ganancia 5    · flags 1     ← segundo ciclo
t~59s   ganancia 15   · flags 1
t~61s   ganancia 12   · flags 1     ← ¡baja! (ajuste fino)
t~62s   ganancia 6    · flags 1
t~62s   ganancia 1    · flags 1
t~63s   ganancia 0    · flags 1     ← restaura
```

**Modelo de comportamiento** (fiel a lo observado): búsqueda en **dos fases** —
1) **subida en pasos grandes** (`+5` y luego `+10` repetidos) hasta detectar señal o llegar al techo `58`;
2) **ajuste fino hacia abajo** con pasos decrecientes (`15→12→6→1`); si no hay señal, **restaura** el valor previo.

> Nota honesta: la *forma* del algoritmo es lo observado; **sus constantes internas no se pudieron
> extraer** (ver §5).

---

## 5. Firmware: qué se pudo y qué no

### De dónde sale el firmware (dato muy útil para el futuro)

La app oficial consulta **`https://update.audient.com/products.json`** (producto `evo16`, id 43;
componentes `firmware` id 50 y `firmware-img` id 54; el binario se pide con `&serial=` — con el
serial del equipo se obtiene el suyo). **Se descargaron los 11 firmwares** de la EVO 16 a
`~/dev/evo-osc/firmware/`. El equipo reporta **1.30** = `firmware-img` **v1.3.0**.

Y traen **símbolos C++**, que es lo que permitió entender la arquitectura.

### Estructura del `.img`

* Magic ASCII `AUDIENT_FIRMWARE` (16 bytes) + cabecera u32 LE desde `0x10` (incluye `0x000a2708` = el
  product id USB).
* Tres bloques: **A** `[0x38, 0x1b038)` (0x1b000) · **B** `[0x1b038, 0x6e73c)` (0x53d04) · **C**
  `[0x6ed3c, 0xc12e8)` (0x525ac). `0x6ed3c + 0x525ac = 791272` = tamaño exacto del archivo.
* **B** y **C** = ARM Cortex-M (dos builds/slots de la misma aplicación): Renesas RA + **FSP 3.6.0** +
  **UI LVGL**. Bases: `addr(B) = 0x90000000 + (offset − 0x1b038)`, `addr(C) = 0x00010000 + (offset − 0x6ed3c)`
  (probado: el literal en `C+0x3ff00` = `0x0004ff10` apunta exacto al typeinfo de `SmartGainScreen`).
* **A** = **XMOS xcore** (el chip USB/UAC2) y viene **con los nibbles intercambiados**:
  `byte_corregido = ((b << 4) | (b >> 4)) & 0xFF`. Sin esa corrección parece "no código" y no tiene
  strings. Con la corrección aparecen `Audient`, `EVO16`, `Clock Selector`, `Internal Clock`,
  `Optical1`, los descriptores UAC2 (IAD multiclass, AF v2.0) y strings del driver (`Failed to read
  ... Reg address: ... Data:`).

### Hallazgos del desensamblado

* **La máquina de estados del panel está probada**: renderer en `C+0x15044` con `subs r3,#1 ; cmp r3,#5
  ; bhi` y **tabla `tbb` en `C+0x1505e` = `03 33 27 1b 0f 03`** → mapa estado→cartel:
  `1` Select Channels · `2` sin cambio · `3` Smartgain Listening · `4` Issue Detected · `5` Smartgain
  Successful · `6` Select Channels. Los 4 textos están en `0x4feb0/0x4fec0/0x4fed4/0x4fee4`.
* **El ARM no tiene aritmética de ganancia**: un histograma de inmediatos sobre *todo* el código ARM no
  encuentra la escalera `{5,10,20,30,40,50,58}`, ni el tope `58`, ni umbrales → **la rampa corre en el
  XMOS** (bloque A). El ARM solo *pinta* y escribe el bit de selección (`CS=4`).
* `Application::Controller::updateSmartGainState` (`segC 0x0002166c`) es un **callback de suscripción a
  un parámetro del modelo** (`'SG State'`, string en `C+0x4d78c`, junto a `Clock Freq`, `Brightness`,
  `Power`, …), **no un manejador de USB**.
* Constantes de **2000 ms** (`0x7d0`) para el parpadeo de indicadores (`C+0x1155e`, `0x11594`, `0x115cc`,
  `0x11798`, `0x11914`) — **no** se pudo probar que sean la cadencia de la rampa.
* **Límite real**: el algoritmo **no se pudo localizar** en el bloque A (110 KB de xcore sin símbolos,
  ~10 % de instrucciones no decodificables, y **regiones de datos que se disfrazan de código**: varios
  "hallazgos" de constantes resultaron ser basura de esas zonas). Las búsquedas de la escalera y de
  umbrales (`Q1.31`/`Q8.23`/dBFS) **no dieron resultado**.

---

## 6. La app oficial (lado host)

* Clases XU que usa: `UacXUAudientInputControl` (`0x3A`), `BlendMixer`, `MonitorController` (`0x36`),
  `MonoMixController`, `OutputControl`, `RoutingMatrix` (`0x33`), `SystemControl`.
* `InputControlModel::setParameter(param, ch, valor)` pasa el `param` **directo como CS** → los IDs de
  parámetro de la app **son** los selectores CS (`0` phantom, `1` ganancia, `2` mute, `3` link,
  `4` flags, `5` soundcheck).
* `setInputBitState(ch, bit, on)` (`0x10001149c`) mantiene un array de u32 por canal y escribe `CS=4`;
  se usa con **bit 0** (canal elegido para SmartGain, desde `EvoSystemComponent`) y **bit 1** (DI).
* `EvoSystemComponent::setSmartGainArmVisibility` escribe `CS=5` con valor `0` al salir; los valores
  `1` (arrancar) y `2` (armado) aparecen en la máquina de la UI. **Ninguno arranca nada en el equipo**
  (verificado en hardware).

---

## 7. Lo que queda para "un algoritmo fiable"

Lo único que falta para clonarlo con fidelidad es **el nivel objetivo y la regla fina**, y eso **no está
en el código accesible** (está en el blob XMOS). Caminos de cierre, en orden de coste:

1. **Medirlo (1 minuto de trabajo)**: señal **estable** en un canal elegible + ejecutar el SmartGain del
   equipo con el botón + leer **el medidor del equipo** (`0x3C`) en el momento en que se asienta → **ese
   nivel es su objetivo**, sin ambigüedad de escalas internas. Repetir a 2-3 niveles de entrada para
   sacar la banda de tolerancia.
2. **Pico vs RMS**: la misma medición con (a) seno continuo, (b) tren de pulsos con crest factor alto,
   (c) ruido rosa. Si el pulso detiene la rampa mucho antes, el detector es de pico.
3. **Cadencia fina**: capturar `CS=1` a ≥1 kHz (no a 0,5 s) con señal justo por debajo del objetivo para
   ver la fase fina completa.
4. **Símbolos del XMOS**: conseguir un `.xe` con símbolos o acceso JTAG/xgdb (el firmware es un derivado
   del *XMOS USB Audio 2.0 reference design*: cruzarlo con ese código público ayudaría a ubicar el
   manejador del XU y, desde ahí, la tarea del SmartGain).

Mientras tanto, `POST /api/smartgain/{canal}` y `POST /api/smartgain` (rama `auri/smartgain`) hacen el
**mismo efecto** por vía directa: miden con los medidores del equipo, sacan el pico y dejan la ganancia
apuntando a −12 dBFS (parámetro `objetivoDb`), sin tocar canales sin señal — equivalente funcional del
"no hay señal → Issue Detected → restauro".

---

## 8. Herramientas y cómo reproducir

* **Helper USB**: `~/dev/evo16-web/mac-evo16/mac-evo16 0x2708 0x000a` — JSON por línea.
  * `{"type":"get_cur","wValue":(CS<<8)|(canal-1),"wIndex":0x3A00,"length":4}` / `set_cur` con `data`.
  * **`ctrl` genérico** (peticiones crudas): `{"type":"ctrl","bmReqType":…,"bReq":…,"wValue":…,"wIndex":…,"length":N}`
    (IN si `bmReqType & 0x80`; OUT con `"data":[…]`).
  * **Medidores**: `ctrl` con `bmReqType 0xA1`, `bReq 3`, `wValue 0`, `wIndex 0x3C00`, `length 48`
    (24 canales × 16 bits LE; `dB = 20·log10(raw/65536)`).
  * **Ojo**: el helper responde por **stderr** — al capturarlo desde Python hay que concatenar
    `stdout + stderr` (filtrar solo stdout da cero resultados y parece un fallo del equipo).
  * Si da `USB_BUSY`: otro proceso tiene el dispositivo (app de barra de menú, servicio `:3000` o la app
    oficial de Audient). Esperar unos segundos después de cerrarlos.
* **Desensamblado**: `/opt/homebrew/opt/llvm/bin/llvm-objdump --triple=xcore` para el bloque A (XMOS)
  y `--triple=thumbv7em` o **capstone** para B/C (ARM). El `llvm` de las Command Line Tools de macOS
  **no** trae el target xcore.
* **Memoria del proyecto**: `skill:audient-usb-control/references/smartgain.md` (protocolo + método).

---

## 9. Estado del repositorio al cierre

* Rama **`auri/smartgain`**: endpoints de SmartGain (`backend/main.py`, `backend/service.py`),
  documentación (`docs/AGENT-API.md`, `docs/PROTOCOLO-EVO16.md`) y este documento.
  Commits: `e942371` (endpoints) y `7d7331f` (protocolo verificado).
* Tests del repo con los cambios: **protocolo 48/48**, **contrato OK**, **presets OK**, **estados 20/20**.
* Este documento se incorpora a **`main`** por pedido explícito de David (16-oct-2026).

---

## 10. Cambios hechos en el equipo durante la jornada (y su restauración)

Se probaron escrituras en `CS=5`, `CS=6`, `CS=7`, `CS=8` y en `CS=4` bit0 (canales 1, 2 y 8). Todas
fueron **registros de estado/banderas** o valores dentro del rango propio del equipo (`−8…+50 dB`). Al
cierre se dejaron **`CS=4` y `CS=5` del canal 1 en 0**, la ganancia del canal 8 en 0 (como la dejó David)
y **ningún servicio corriendo**; la app de barra de menú quedó **abierta** (estado normal del usuario).
La única escritura con efecto audible real fue la ganancia, y David autorizó expresamente cambiar
ganancias durante la investigación.
