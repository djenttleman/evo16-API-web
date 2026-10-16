# EVO 16 Remote — macOS Web Controller

Control remoto de una **Audient EVO 16** por USB: preamps (ganancia, 48V, DI, mute), link de par,
**volumen del main out**, perfiles de preamps guardables/exportables, y una **API HTTP pensada para
que la consuma un agente** → [`docs/AGENT-API.md`](docs/AGENT-API.md).

Servicio on-demand: `evo16-remote start|stop|status|url|health` (ver `bin/evo16-remote`).
Pendientes y lo ya investigado para retomarlos: [`docs/ROADMAP.md`](docs/ROADMAP.md).

> **English** | [Español](#español)

---

## English

Control your Audient EVO 16 preamps and ADAT channels from any device on your local network (tablet, phone, laptop).

### Quick Start (Standalone Binary)

```bash
# Download and run — no Python required
./EVO16-Remote.app/Contents/MacOS/EVO16-Remote
# → http://localhost:3000
```

### Controls

| Section    | Channels | Type                               |
| ---------- | -------- | ---------------------------------- |
| **ANALOG** | CH 1–8   | EVO 16 built-in preamps            |
| **ADAT 1** | CH 9–16  | Optical input 1 (e.g. Audient SP8) |
| **ADAT 2** | CH 17–24 | Optical input 2                    |

Per channel: **gain 0–50 dB** (knob), **mute**, and **48V phantom**.

### Verified Setup

> Tested with Audient SP8 on both ADAT 1 and ADAT 2. All preamp controls
> (gain 0–50 dB and 48V phantom) work bidirectionally over ADAT.

| Device | Setting | Value |
|--------|---------|-------|
| **macOS** | Sample Rate | 48 kHz |
| **EVO 16** | Clock Source | Internal |
| **SP8** | Sample Rate | AUTO |
| **SP8** | Clock Source | Digital |
| **SP8** | World Clock Termination | OFF |

*Connect the SP8 via ADAT optical cable to the EVO 16. Set the EVO 16 as
clock master (Internal), and the SP8 as clock slave (Digital). The SP8's
World Clock Termination must be OFF for bidirectional control to work.*

### Architecture

```
Tablet  ──HTTP──►  FastAPI  ──JSON stdin──►  mac-evo16 (C)  ──IOKit USB──►  EVO 16
:3000               :3000                      stdio                        USB
```

### Components

| Layer          | Technology                  | Role                                                        |
| -------------- | --------------------------- | ----------------------------------------------------------- |
| **USB driver** | `mac-evo16` (C, IOKit)      | Direct USB control transfers. No root, no kernel extension. |
| **API server** | FastAPI (Python, port 3000) | REST endpoints, serves web UI                               |
| **Frontend**   | Vanilla HTML/CSS/JS         | Responsive knobs (0–50 dB), mute, 48V, 24 channels          |
| **IPC**        | JSON over stdin/stdout      | Backend ↔ C helper communication                            |

---

## USB Protocol — Full Reference

> 📌 **Referencia verificada del EVO 16** (gain real −8…+50 dB, link en `0x3A` CS=3, volumen del main,
> medidores, reloj, standalone): **[`docs/PROTOCOLO-EVO16.md`](docs/PROTOCOLO-EVO16.md)**.
> Lo que sigue es la investigación **original del EVO8** (mayo 2026): sirve como historia, pero sus
> supuestos de gain, link (FU11) y alcance de entidades están corregidos en ese documento.

### Device Identification

| Property   | Value                      |
| ---------- | -------------------------- |
| Vendor ID  | `0x2708`                   |
| Product ID | `0x000A`                   |
| Class      | USB Audio Class 2.0 (UAC2) |

### Entity Map

| Entity   | Type           | wIndex (hex)     | Controls                                  |
| -------- | -------------- | ---------------- | ----------------------------------------- |
| **EU58** | Extension Unit | `0x3A00` (14848) | Gain, Mute, Phantom — **all 24 channels** |
| **FU11** | Feature Unit   | `0x0B00` (2816)  | Digital trim, stereo linking (CS=2)       |

### Control Transfers

All commands use 4-byte USB control transfers:

| Direction | bmRequestType | Description             |
| --------- | ------------- | ----------------------- |
| **Write** | `0x21`        | Host → Device (SET_CUR) |
| **Read**  | `0xA1`        | Device → Host (GET_CUR) |

**wValue** = `(CS << 8) | channel_index`

- CS = Control Selector
- channel_index = 0-based (CH1=0, CH2=1, …, CH24=23)

**wIndex** = Entity ID (see table above)

### EU58 — Extension Unit 58 (Primary Control)

wIndex = `0x3A00` (14848)

| Control     | CS  | Data Bytes [0..3] | Mapping                         |
| ----------- | --- | ----------------- | ------------------------------- |
| **Gain**    | 1   | `[0, byte, 0, 0]` | ⚠️ `byte = dB_UI + 8` ⇒ **−8…+50 dB** (byte 0…58). Ver `docs/PROTOCOLO-EVO16.md` |
| **Mute**    | 2   | `[m, 0, 0, 0]`    | m=0 unmute, m=1 mute            |
| **Phantom** | 0   | `[p, 0, 0, 0]`    | p=0 off, p=1 on (48V)           |

#### Gain Details

- **Write range**: 0–50 (integer dB). Values >50 or <0 are clamped by MCU.
- **Read format**: byte[1] = current dB value.
- **Negative gain**: -8 to -1 dB NOT writable via SET_CUR. MCU returns error code 58.
  - Hardware *can* display negative gain via physical knob.
  - Reverse-engineering pending: capture EVO Control app USB traffic.

### FU11 — Feature Unit 11 (Digital Trim / Stereo Link)

> ❌ **Corregido**: el link de par **no** vive acá. Vive en **EU58 (`0x3A`) CS=3** (ver
> `docs/PROTOCOLO-EVO16.md`). Esta tabla es de la investigación original del EVO8 y no debe usarse
> para implementar el link.

| Control  | CS  | Data Bytes         | Observación histórica                    |
| -------- | --- | ------------------ | ---------------------------------------- |
| **Mute** | ?   | `[136, 0, 0, 0]`   | Toggles mute in some contexts            |
| **CS=2** | 2   | `[0, value, 0, 0]` | Supuesto linkeo estéreo (**descartado**) |

### Channel Map

| Range     | Section | Type             | Gain | Mute | Phantom           |
| --------- | ------- | ---------------- |:----:|:----:|:-----------------:|
| CH1–CH8   | ANALOG  | Built-in preamps | ✅    | ✅    | ✅ real            |
| CH9–CH16  | ADAT 1  | Optical input 1  | ✅    | ✅    | ✅ write accepted* |
| CH17–CH24 | ADAT 2  | Optical input 2  | ✅    | ✅    | ✅ write accepted* |

*\* Phantom writes to ADAT channels are accepted by the protocol but may be no-ops without Audient SP8 or compatible ADAT preamps.*

### JSON IPC Protocol (Backend ↔ Helper)

```
→ {"type":"get_cur","wValue":256,"wIndex":14848,"length":4}
← {"data":[0,12,0,0]}

→ {"type":"set_cur","wValue":257,"wIndex":14848,"data":[0,25,0,0]}
← {"status":"ok"}
```

Commands: `get_cur`, `set_cur`, `quit`.

---

## REST API

Base URL: `http://localhost:3000`

| Method | Endpoint            | Body              | Response                        | Description              |
| ------ | ------------------- | ----------------- | ------------------------------- | ------------------------ |
| GET    | `/api/status`       | —                 | `{device, inputs[], outputs[]}` | Full state (24 channels) |
| POST   | `/api/gain/{ch}`    | `{"db": 35}`      | `{channel, gain, status}`       | Set gain 0–50 dB         |
| POST   | `/api/mute/{ch}`    | `{"muted": true}` | `{channel, muted, status}`      | Mute toggle              |
| POST   | `/api/phantom/{ch}` | `{"on": true}`    | `{channel, phantom, status}`    | 48V toggle               |
| GET    | `/api/instrument/{ch}` | —              | `{channel, instrument, status}` | DI: `true`/`false`/`null` (canales sin hardware de DI) |
| POST   | `/api/instrument/{ch}` | `{"on": true}` | `{channel, instrument, status}` | Modo instrumento (DI). Sólo canales **1-2, 9-10, 17-18** (el resto: 400) |
| GET    | `/api/link/{ch}`    | —                 | `{channel, linked, pair, status}` | Link del par al que pertenece el canal |
| POST   | `/api/link/{ch}`    | `{"on": true}`    | `{channel, linked, pair, status}` | Linkea/deslinkea el par (escribe CS=3 en ambos canales) |

**Link de par estéreo**: los pares son `(1,2)`, `(3,4)`, `(5,6)`, … El estado vive en el equipo
(EU58 CS=3) y con el par linkeado el **firmware espeja el preamp** (gain y DI comprobados): el
cliente no debe duplicar escrituras. Al crear el link el equipo unifica el valor del par; si se
quiere un valor concreto, escribirlo después de linkear. Verificado en hardware (firmware 1.30).

En `/api/status` cada canal trae `instrument` (sólo donde hay hardware de DI), `linked` y
`linkPair`. El poll lee CS=3 una vez por par (12 lecturas extra, no 24).

## Perfiles de preamps (save state por escena)

Un perfil guarda el estado de los **24 canales** (gain, 48V, DI, link de par y mute) para poder
reinyectarlo cuando haga falta — por ejemplo al cambiar de escena.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/presets` | Perfiles guardados + la carpeta donde viven los archivos |
| GET | `/api/presets/{nombre}` | Contenido completo del perfil (JSON) |
| POST | `/api/presets/{nombre}` | **Guarda el estado ACTUAL del equipo** como ese perfil (sobrescribe) |
| POST | `/api/presets/{nombre}/apply` | **Inyecta** el perfil en el equipo |
| POST | `/api/presets/{nombre}/export` | Copia el perfil a un archivo en la ubicación que se indique (`{"path": "~/Documents/sala.json", "overwrite": false}`) |
| POST | `/api/presets/import` | Trae al banco local un perfil desde cualquier archivo (`{"path": "…", "name": "opcional"}`) |
| DELETE | `/api/presets/{nombre}` | Borra el archivo del perfil |

**Almacenamiento en archivos** (JSON, uno por perfil, editables a mano):

```
~/Library/Application Support/EVO16Remote/presets/<nombre>.json
```

Se puede cambiar de carpeta con la variable de entorno `EVO16_PRESETS_DIR` (por ejemplo para
versionarlos dentro del proyecto):

```bash
EVO16_PRESETS_DIR="$HOME/dev/evo16-web/presets" \
  python3 backend/main.py
```

Los nombres se validan (letras, números, espacios, `-`, `_`, paréntesis; máx. 64) para que un
nombre no pueda escribir fuera de la carpeta. La escritura es atómica (archivo temporal + rename).

**Orden de aplicación** (importa): primero el link de cada par, después el mute de los que van a
quedar muteados, luego phantom/gain/DI, y al final el unmute. Escribir el link primero es
necesario porque al linkear el equipo unifica el valor del par: los valores finales tienen que
escribirse después para que queden los del perfil.

**UI**: la barra «PERFIL DE PREAMPS» sobre el rack permite elegir, `APLICAR`, `GUARDAR ESTADO`
(captura el estado actual y lo guarda con el nombre que se escriba), `EXPORTAR` (a la ruta que se
indique; nunca pisa un archivo existente salvo que se pida), `IMPORTAR` y `BORRAR`.

## Volumen del main out (control que la app oficial NO expone)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/main-volume` | Volumen del main mix en dB |
| POST | `/api/main-volume` | `{"db": -20}` → fija el volumen |

**Protocolo**: `MonitorController` (unidad `0x36`), **`CS=18`**, payload de **2 bytes**, entero
**con signo** little-endian en **Q8.8** (`dB = raw / 256`). Lo reveló el desensamblado de
`UacXUAudientMonitorController::setMainVolume` (`mov w2, #0x12` = 18, `fcvtzs w8, d0, #8` = ×256) y
lo confirmó la **perilla física** del equipo: al bajarla el registro pasó de `[174,199]` (−56.3 dB) a
`[0,160]` (−96.0 dB). Los volúmenes de CUE usan el mismo esquema en `CS=19` y siguientes.

**Escala de la pantalla del equipo** (0–100, comprobada en hardware con dos mediciones): es
logarítmica, **`pantalla = 100 × 10^(dB / 96)`** ⇔ `dB = 96 × log10(v / 100)` (−96 dB = 10 · −61.4 dB = 22 · 0 dB = 100). El slider de la UI usa esa misma escala y **manda el valor
mientras se desliza** (throttle ~90 ms, siempre el último), así el equipo avanza en conjunto con el
slider como si fuera la perilla.

En `/api/status` el campo `mainVolume` trae el valor actual (una lectura extra por poll).

## Memoria interna del equipo (standalone)

`POST /api/store-standalone` guarda el estado **actual** en la memoria interna de la interfaz, para
que el equipo funcione **solo, sin computadora** (incluye ganancias, DI, 48V y el volumen del main).

Trigger descubierto en el binario (`UacXUAudientMonitorController::setStandAloneState`): `SET_CUR` a
`MonitorController` (unidad `0x36`), **`CS=24`**, índice 0, **4 bytes en cero** — no lleva valor, es
un comando. Es de **una sola vía**: pisa el estado guardado antes y no se puede leer ni restaurar
desde la API; se verifica **ciclando la energía** del equipo (al volver debe cargar ese estado).
En la UI es el botón «GUARDAR EN LA INTERFAZ».

## App de barra de menú (el único proceso que vive siempre)

`EVO 16 Remote.app` (código en `menubar/`) vive junto al reloj, sin ícono en el Dock. Es el único
punto de control del ciclo de vida: muestra el estado en vivo, enciende/apaga el servicio y —por
pedido— **al cerrarse la app se cierra el servicio y se libera el USB**.

### Canales para otras apps: por defecto **ninguno abre un puerto**

| canal | cómo se usa | para qué |
| --- | --- | --- |
| **`estado.json`** | leer `~/Library/Application Support/EVO16Remote/estado.json` | el estado completo, reescrito cada 2 s |
| **`comando.json`** | escribirle `{"accion": "start", "id": 1}` | pedirle encender/apagar/consultar/… |
| **`evo16remote://`** | `open -g "evo16remote://start"` | lo mismo, sin archivos (fire-and-forget) |

`comando.json` acepta: `start`, `stop`, `status`, `api-http-on`, `api-http-off`, `exponer-red-on`,
`exponer-red-off`, `salir`. El resultado queda en `estado.json` como
`commandResult: {accion, id, ok}` con el mismo `id` que mandaste.

### Opciones del menú (las dos **apagadas** por defecto)

- **Abrir la API HTTP en `:3100`** — misma forma de respuesta que `launcher.py`, para curl/HTTP.
- **Exponer la interfaz (`:3000`) en la red (LAN/Tailscale)** — por defecto el servicio escucha sólo
  en `127.0.0.1`. Se aplica **al reiniciar** el servicio (Apagar y Encender desde el menú).

### Vigilante

El servicio vigila a la app: si desaparece (incluso si la matan de golpe), se apaga solo en unos
segundos y libera el USB. Si no hay app (servicio lanzado a mano), no se apaga solo.

## Encender y apagar por API (alternativa sin app)

Si se prefiere HTTP, `launcher.py` expone `GET /api/status` · `POST /api/start` · `POST /api/stop` ·
`GET /api/logs?n=80` en **`http://127.0.0.1:3100`** (sólo stdlib, no toca el USB). Se instala una vez
con `~/bin/evo16-remote launcher-install`. El servicio, por su lado, expone su propio
`POST /api/service/stop`.

> ⚠️ La app y el launcher usan el **mismo puerto y la misma forma de respuesta**: usá uno u otro.

## Medidores en tiempo real

`GET /api/meters` devuelve los niveles **en dB** de los 24 canales de entrada y de las salidas
(16), más el estado de clip de cada uno. Una llamada son 4 transferencias USB (~3 ms medidos), así
que sirve para medidores en vivo.

Protocolo (del desensamblado de `MixerModel::updateInputMeterValues` / `updateOutputMeterValues`):
`GET_MEM` con `bmRequestType=0xA1`, `bRequest=0x03`, `wIndex = 0x3C00` (unidad `0x3C`) y
`wLength = 2 × canales`; el **`wValue` elige el bloque**: `0` = niveles de entrada, `1` = niveles de
salida, `2` = clip de entradas (1 byte/canal), `3` = clip de salidas. Cada nivel son **2 bytes
little-endian = amplitud lineal** con 65536 = full scale ⇒ **`dB = 20·log10(raw / 65536)`** (lo que
hace `DecibelConversions::meterIntToDB`). Verificado en hardware: un canal sin señal lee 1
(−96.3 dB) y 0 significa silencio.

## Fuente de reloj

`GET /api/clock` · `POST /api/clock {"source": "internal" | "optical1" | "optical2"}` (o 1/2/3).

`ClockSelector` (unidad `0x28`), **`CS=1`**, 1 byte: `1` = Internal, `2` = Óptica 1, `3` = Óptica 2
(la clase de la app es `UacLib::UacClockSelector`). Ojo: cambiar el reloj a óptica sin nada
conectado deja al equipo sin sincronía.

Channel range: 1–24.

---

## Web UI

### Features

- **24 knobs** — 0–50 dB, 300° sweep (7 o'clock to 5 o'clock), real-time commit every 1 dB step
- **Mute buttons** — white heartbeat glow
- **48V buttons** — red glow, persisted on ADAT (for SP8 compatibility)
- **Responsive** — 5→4→3→2 columns, tablet-friendly
- **Dark theme** — Audient hardware style, green knob fill
- **Polling** — 2s auto-sync from hardware

### Visual Design

| Element    | Color             | Notes                       |
| ---------- | ----------------- | --------------------------- |
| Knob fill  | `#22c55e` (green) | 300° sweep, dasharray-based |
| Knob track | `#333840` (gray)  | Visible against dark bg     |
| Dot        | `#ffffff` (white) | Position indicator          |
| 48V ON     | `#dc2626` (red)   | Amber-red glow pulse        |
| Mute ON    | `#e4e8f0` (white) | Glow-only heartbeat         |
| Background | `#080a0f`         | Dark, green radial gradient |

### Accessibility

- Full **VoiceOver** support — `role="slider"`, `role="switch"`, `aria-valuenow`, `aria-valuetext`
- Keyboard navigation — Tab, arrow keys (knobs), Space/Enter (buttons)
- Focus visible `#f59e0b` outline

---

## Project Structure

```
evo16-web/
├── EVO16-Remote.spec       # PyInstaller build spec
├── README.md               # This file
├── backend/
│   ├── main.py             # FastAPI web server
│   ├── service.py          # EVO 16 USB protocol service
│   ├── evo16-web.sh        # Build + launch script
│   └── com.david.evo16-web.plist  # launchd auto-start
├── mac-evo16/
│   ├── mac-evo16.c         # IOKit USB helper source
│   ├── mac-evo16           # Compiled binary (requires Xcode/make)
│   └── Makefile
├── web/
│   ├── index.html          # SPA entry point
│   ├── app.js              # Knob logic, API client, polling
│   └── style.css           # Dark theme, responsive layout
└── dev/                    # Reverse-engineering probe tools
    ├── probe-evo16.py      # Initial USB scanner
    ├── diag-entities.py    # Entity discovery
    ├── diag-fu11.py        # FU11 exploration
    └── ...                 # Other diagnostic scripts
```

---

## Known Limitations & Pending Work

### Negative Gain (-8 to -1 dB)

- **Status**: NOT supported via USB SET_CUR
- **Cause**: MCU rejects signed byte values. Byte[0] signed encoding persists in register but doesn't affect hardware.
- **Workaround**: Use physical knob on EVO 16 for negative values.
- **Pending**: Capture EVO Control app USB traffic to discover the proprietary encoding.

### FU11 Digital Trim

- **Status**: Partially mapped
- **CS=2**: Controls stereo linking, not individual gain trim.
- **Pending**: Full FU11 CS mapping for digital attenuation on ADAT channels.

### ADAT Phantom (48V)

- **Status**: Verified with Audient SP8 on ADAT 1 and ADAT 2.
- 48V writes to ADAT channels (9–24) are forwarded correctly to SP8 preamps.
- Requires proper clock configuration (see [Verified Setup](#verified-setup) above).

### Instrument Mode (DI / High-Z) — ❌ PENDING

- **Status**: NOT supported via USB GET_CUR/SET_CUR
- **Cause**: Instrument mode uses a vendor-specific control transfer (bmRequestType 0x40) not visible in the UAC2 entity space. EU58 CS=5 accepts writes but does not toggle the hardware.
- **Workaround**: Press the physical INSTR button on the EVO 16 front panel for CH1/CH2.
- **Full research**: [instrument-mode-research.md](dev/instrument-mode-research.md)

### Core Audio / Aggregate Devices

- The EVO 16 appears as a 24-in/24-out audio interface in macOS.
- No aggregate device support implemented — use Audio MIDI Setup manually.

---

## Building from Source

### Prerequisites

- macOS 14+ with Xcode Command Line Tools
- Python 3.13+ (for standalone binary: none required)

### Build & Run

```bash
# 1. Build USB helper
cd mac-evo16 && make

# 2. Start server
cd .. && python3 backend/main.py
# → http://localhost:3000

# 3. (Optional) Build standalone binary
pip3 install pyinstaller
pyinstaller EVO16-Remote.spec
```

---

## Credits

- **Reverse engineering**: @david (djenttleman) + Hermes Agent
- **USB protocol**: Discovered via brute-force scanning of 256 entities × 256 selectors
- **IOKit driver**: Apple IOKit framework, no third-party USB libraries
- **EVO 16 hardware**: Audient — all trademark rights reserved

---

---

## Español {#español}

Control remoto web para la interfaz de audio **Audient EVO 16**. Controla los 8 preamplificadores analógicos y los 16 canales ADAT desde cualquier dispositivo en tu red local (tablet, teléfono, laptop).

### Inicio rápido

```bash
# Descarga y ejecuta — no necesita Python instalado
./EVO16-Remote.app/Contents/MacOS/EVO16-Remote
# → Abre http://localhost:3000 en tu navegador
```

### ¿Qué controla?

| Sección    | Canales  | Tipo                                  |
| ---------- | -------- | ------------------------------------- |
| **ANALOG** | CH 1–8   | Preamplificadores internos del EVO 16 |
| **ADAT 1** | CH 9–16  | Entrada óptica 1 (ej. Audient SP8)    |
| **ADAT 2** | CH 17–24 | Entrada óptica 2                      |

Cada canal: **ganancia 0–50 dB** (knob), **mute**, y **48V phantom**.

### Configuración verificada

> Probado con Audient SP8 en ADAT 1 y ADAT 2. Todos los controles de
> preamplificador (ganancia 0–50 dB y 48V phantom) funcionan bidireccionalmente.

| Dispositivo | Ajuste | Valor |
|-------------|--------|-------|
| **macOS** | Frecuencia de muestreo | 48 kHz |
| **EVO 16** | Fuente de reloj | Internal |
| **SP8** | Frecuencia de muestreo | AUTO |
| **SP8** | Fuente de reloj | Digital |
| **SP8** | World Clock Termination | OFF |

*Conecta el SP8 vía cable óptico ADAT al EVO 16. Configura el EVO 16 como
maestro de reloj (Internal) y el SP8 como esclavo (Digital). La terminación
World Clock del SP8 debe estar en OFF para que el control bidireccional funcione.*

### Cómo funciona

```
Tablet ──HTTP──► FastAPI ──stdin──► mac-evo16 (C) ──IOKit USB──► EVO 16
```

- El binario incluye todo: servidor web, helper USB, y frontend
- No requiere root, kexts, ni drivers
- Compatible con macOS 14+

### Lo que falta (pendiente)

- **Ganancia negativa (-8 a -1 dB)**: el microcontrolador del EVO 16 rechaza valores negativos por USB. Solo se puede desde la perilla física.
- **FU11 (digital trim)**: mapeo incompleto. CS=2 controla stereo linking, no atenuación digital.
- **Modo Instrumento (DI / alta impedancia)**: ❌ PENDIENTE. El EVO 16 usa un comando USB propietario (vendor-specific) que no es visible en el espacio UAC2 estándar. Solo funciona desde el botón físico del panel frontal. Ver [investigación completa](dev/instrument-mode-research.md).

### Construir desde fuente

```bash
cd mac-evo16 && make      # helper USB (requiere Xcode CLT)
cd .. && python3 backend/main.py  # servidor de desarrollo
```

---

*Document version: 1.0 — May 2026*
