# EVO 16 Remote — guía de la API para agentes

API HTTP para controlar una **Audient EVO 16** por USB. La misma URL sirve la interfaz web y la API.

- **Base**: `http://127.0.0.1:3000` (en LAN/Tailscale: `http://<ip>:3000`). `GET /api/health` devuelve las URLs.
- **Docs interactivas**: `http://127.0.0.1:3000/docs` (OpenAPI generado por FastAPI).
- **Código**: `~/dev/evo16-web` — la memoria del protocolo está en la skill `audient-usb-control`.

## Encender el servicio (desde una shell normal, NO desde dentro de Hermes)

```bash
evo16-remote start      # arranca (launchd, on-demand)
evo16-remote stop       # lo para y libera el USB
evo16-remote restart
evo16-remote status     # una línea: servicio + conexión del equipo + volumen del main
evo16-remote url        # imprime la URL de la interfaz
evo16-remote health     # JSON completo de /api/health
evo16-remote logs
```

Si el wrapper no está en `~/bin`:

```bash
cp ~/dev/evo16-web/bin/evo16-remote ~/bin/ && chmod +x ~/bin/evo16-remote
~/bin/evo16-remote install     # instala el agente launchd (una sola vez)
```

> Nota: desde dentro de un proceso del gateway de Hermes, `launchctl bootstrap/kickstart` está
> bloqueado por diseño. Esas acciones se hacen desde la Terminal del usuario.

## REQUISITO CRÍTICO

**La app oficial EVO Control debe estar CERRADA.** Es la dueña del USB: con la app abierta, el
helper no puede abrir el dispositivo y toda lectura/escritura falla. `GET /api/health` lo delata con
`audientAppRunning: true`.

Si el servicio estaba arrancado cuando el equipo no estaba disponible, no se reconecta solo:

```bash
curl -X POST http://127.0.0.1:3000/api/reconnect
```

## Estado

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/health` | Estado **en vivo** + **estado de alto nivel** (ver abajo) |
| GET | `/api/info` | Mapa de capacidades (lo que está en esta tabla) |
| GET | `/api/status` | Los 24 canales (`gain`, `phantom`, `mute`, `instrument`, `linked`, `linkPair`) + `mainVolume` |
| POST | `/api/reconnect` | Reabre el dispositivo (usar después de cerrar la app oficial). Devuelve `{"service": "ok", "device": {...}}` — el estado vive en `device`, no en la raíz |

### Estado de alto nivel (lo que debe mirar un cliente de terceros)

`GET /api/health` trae la verdad cruda **y** cuatro campos para que un cliente externo (RLM, una
extensión de REAPER) no tenga que interpretar nada:

```json
{
  "service": "ok", "version": "1.1.1", "uptimeSeconds": 58.7,
  "state": "connected", "ok": true,
  "stateDetail": "el equipo responde", "stateSeconds": 122.4,
  "audientAppRunning": false,
  "device": { "connected": true, "helper": true, "entity": "0x36", "mainVolume": -30.72 }
}
```

| `state` | Cuándo | Qué conviene hacer |
|---|---|---|
| `connected` | el equipo responde (`ok: true`) | usar la API normalmente |
| `usb_busy` | la app oficial EVO Control tiene el USB | cerrarla y `POST /api/reconnect` |
| `helper_down` | el helper USB murió | `POST /api/reconnect` |
| `device_unreachable` | el helper vive, el equipo no contesta | revisar cable / encendido |
| `reconnecting` | hay un `reconnect` en curso | esperar |
| `not_ready` | el servicio todavía no inicializó el dispositivo | esperar un segundo |
| `offline` | **sólo lo reporta el launcher del :3100** | `POST /api/start` |

`ok` es `true` **sólo** con `connected`. `stateSeconds` dice hace cuánto está así, para que un cliente
que consulta cada 2 s no muestre parpadeo en sus textos. `offline` no puede venir del propio servicio
(si está caído, no hay quién conteste): eso lo da el launcher, que vive fuera:

```bash
curl -s http://127.0.0.1:3100/api/status | jq '{state, ok, service, stateDetail}'
```

`/api/status` es la llamada de lectura habitual; la UI la marca cada 2 s. **No bajarlo:** cada
llamada son ~70 lecturas USB al equipo.

## Preamps (canales 1-24)

| Método | Ruta | Cuerpo | Notas |
|---|---|---|---|
| GET/POST | `/api/gain/{ch}` | `{"db": 28}` | 0…58 dB (el byte es `dB + 8`) |
| GET/POST | `/api/phantom/{ch}` | `{"on": true}` | 48 V |
| GET/POST | `/api/mute/{ch}` | `{"muted": false}` | |
| GET/POST | `/api/instrument/{ch}` | `{"on": true}` | **DI**, sólo canales **1, 2, 9, 10, 17, 18** |

```bash
curl -X POST http://127.0.0.1:3000/api/gain/1 -H 'Content-Type: application/json' -d '{"db":30}'
curl -X POST http://127.0.0.1:3000/api/instrument/2 -H 'Content-Type: application/json' -d '{"on":true}'
```

## Link de par

| Método | Ruta | Cuerpo |
|---|---|---|
| GET/POST | `/api/link/{ch}` | `{"on": true}` |

Los pares son `(impar, impar+1)`: 1-2, 3-4, 5-6, … Con el par linkeado **el firmware espeja gain y DI
solo**, así que el cliente **no** debe duplicar escrituras. El par es un estado del equipo (EU58
CS=3); al deslinkear el equipo **no** restaura los valores previos de cada canal.

## Volumen del main out

| Método | Ruta | Cuerpo | Notas |
|---|---|---|---|
| GET/POST | `/api/main-volume` | `{"db": -20}` | Control que **la app oficial no expone**. Escala de la pantalla del equipo: **logarítmica**, `pantalla = 100 × 10^(dB/96)` (= `dB = 96 × log10(v/100)`: −96 dB → 10, 0 dB → 100) |

## Encender y apagar el servicio

### La app de barra de menú: estado y comandos **sin abrir puertos**

`EVO 16 Remote.app` (código en `menubar/`) es el proceso que existe fuera del servicio, así que es el
único que puede decir `offline`. Y no necesita ningún puerto para eso: publica el estado en un
**archivo** y acepta **comandos por archivo** (o por esquema de URL). El servicio, además, se apaga
con la app.

| canal | cómo se usa | notas |
| --- | --- | --- |
| **`estado.json`** | leer el archivo | reescrito cada 2 s; `updatedAtEpoch` dice cuándo (si está viejo, la app no está corriendo) |
| **`comando.json`** | escribir `{"accion": "start", "id": 1}` | el resultado sale en `estado.json` como `commandResult` con el mismo `id` |
| **`evo16remote://`** | `open -g "evo16remote://start"` | fire-and-forget, sin archivos |

Ruta de los dos archivos: `~/Library/Application Support/EVO16Remote/`.
Acciones válidas: `start`, `stop`, `status`, `api-http-on`, `api-http-off`, `exponer-red-on`,
`exponer-red-off`, `salir`.

Desde un ReaScript:

```lua
-- leer el estado (sin HTTP, sin puertos)
local f = io.open(os.getenv("HOME") .. "/Library/Application Support/EVO16Remote/estado.json")
if f then local txt = f:read("*a"); f:close() end
-- pedirle algo
local g = io.open(os.getenv("HOME") .. "/Library/Application Support/EVO16Remote/comando.json", "w")
g:write('{"accion":"start","id":' .. os.time() .. '}'); g:close()
```

#### Opcionales (menú, apagadas por defecto)

- **API HTTP en `http://127.0.0.1:3100`** — misma forma de respuesta que el launcher:
  `GET /api/status` · `POST /api/start` · `POST /api/stop` · `GET /api/logs?n=80`.
- **Exponer la interfaz (`:3000`) en la red (LAN/Tailscale)** — por defecto sólo `127.0.0.1`. Se
  aplica al reiniciar el servicio. (El servicio lee esa preferencia de `prefs.json`, la misma que
  escribe la app, o `EVO16_HOST` para el agente de launchd.)

Compilar/instalar: `./menubar/build.sh --open` (Command Line Tools; queda en `~/Applications`).

#### Cierre y vigilancia

Al cerrarse la app, el servicio se apaga y libera el USB. Y por si la app muere de golpe, el servicio
la **vigila**: si el PID de `app.pid` ya no existe, se apaga solo en unos segundos. Sin app (servicio
lanzado a mano), no se apaga solo.

### Alternativa sin app: launcher HTTP en el puerto 3100

Si se prefiere HTTP, `launcher.py` expone `GET /api/status` · `POST /api/start` · `POST /api/stop` ·
`GET /api/logs?n=80` en **`http://127.0.0.1:3100`** (sólo stdlib, no toca el USB). Se instala una vez
con `~/bin/evo16-remote launcher-install`. El servicio, por su lado, expone su propio
`POST /api/service/stop`.

Es además el **único** que puede decir `state: "offline"`: vive fuera del servicio, así que sabe
cuándo no hay nadie escuchando. Un cliente externo puede tomar de ahí un estado único para todo
(`connected` / `usb_busy` / `helper_down` / `device_unreachable` / `not_ready` / **`offline`**).

> ⚠️ Misma forma de respuesta que la app y **mismo puerto**: usá uno u otro, no los dos. Si la app ya
> está sirviendo el `:3100`, el launcher no podrá abrir el puerto (y al revés).

## Medidores (niveles en tiempo real)

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/meters` | `inputs` (24) y `outputs` (16) **en dB**, más `inputClips`/`outputClips` |

Una llamada son **4 transferencias USB** (~3 ms medidos), así que se puede consultar varias veces
por segundo: es apta para medidores en vivo. `-120.0` = silencio.

Protocolo (del desensamblado de `MixerModel::updateInputMeterValues` / `updateOutputMeterValues`):
`GET_MEM` → `bmRequestType=0xA1`, `bRequest=0x03`, `wIndex = 0x3C00` (unidad `0x3C`),
`wLength = 2 × canales`; el **`wValue` es el selector**: `0` = niveles de entrada, `1` = niveles de
salida, `2` = clip de entradas (1 byte/canal), `3` = clip de salidas. Cada nivel son **2 bytes
little-endian = amplitud lineal**, con 65536 = full scale ⇒ `dB = 20·log10(raw / 65536)` (es lo que
hace `DecibelConversions::meterIntToDB`).

```bash
curl -s http://127.0.0.1:3000/api/meters | jq '{ch1: .inputs[0], mainL: .outputs[0]}'
```

## Fuente de reloj

| Método | Ruta | Cuerpo | Notas |
|---|---|---|---|
| GET | `/api/clock` | — | `{"value": 1, "name": "internal"}` |
| POST | `/api/clock` | `{"source": "internal"}` o `{"source": 2}` | Acepta nombre o número |

Valores: **1 = internal, 2 = optical1, 3 = optical2** (`ClockSelector` 0x28, `CS=1`, 1 byte).
Cambiar el reloj afecta la sincronización del equipo: si no hay nada conectado en la entrada óptica,
poner `optical1` deja al equipo sin reloj.

## Memoria interna del equipo (standalone)

| Método | Ruta | Notas |
|---|---|---|
| POST | `/api/store-standalone` | Guarda el estado **actual** en la memoria interna de la interfaz para que el equipo trabaje **solo, sin computadora**. Trigger en `MonitorController` (0x36) `CS=24`, 4 bytes en 0 |

**Es de UNA SOLA VÍA**: pisa el estado guardado antes y no se puede leer ni restaurar desde la API.
Para verificarlo hay que **ciclar la energía del equipo**: al volver debe cargar ese estado (incluye
ganancias, DI, 48V y el volumen del main).

```bash
# guardar cómo está ahora para uso standalone, y comprobar tras ciclar la energía
curl -X POST http://127.0.0.1:3000/api/store-standalone
```

## Perfiles de preamps (banco local en archivos)

| Método | Ruta | Cuerpo | Notas |
|---|---|---|---|
| GET | `/api/presets` | — | Lista + carpeta donde viven los archivos |
| GET | `/api/presets/{nombre}` | — | El JSON completo |
| POST | `/api/presets/{nombre}` | — | **Guarda el estado ACTUAL del equipo** con ese nombre |
| POST | `/api/presets/{nombre}/apply` | — | Inyecta el perfil (gain, 48V, DI, link y mute de los 24 canales) |
| POST | `/api/presets/{nombre}/export` | `{"path":"~/Documents/sala.json","overwrite":false}` | Copia a donde quieras |
| POST | `/api/presets/import` | `{"path":"…","name":"opcional"}` | Trae al banco local |
| DELETE | `/api/presets/{nombre}` | — | Borra el archivo |

Carpeta por defecto: `~/Library/Application Support/EVO16Remote/presets/` (cambiable con
`EVO16_PRESETS_DIR`). Nombres: letras, números, espacios, `-`, `_`, paréntesis; máx. 64.

## Receta típica (integración desde RLM)

```bash
# 1. ¿está el equipo disponible?
curl -s http://127.0.0.1:3000/api/health | jq '.device.connected, .audientAppRunning'

# 2. cambiar de escena: inyectar el perfil guardado y ajustar el main
curl -X POST http://127.0.0.1:3000/api/presets/Sala%20chica/apply
curl -X POST http://127.0.0.1:3000/api/main-volume -H 'Content-Type: application/json' -d '{"db":-20}'

# 3. guardar el estado que quedó (para volver a él después)
curl -X POST http://127.0.0.1:3000/api/presets/Fin%20de%20show
```

## Convenciones de error

- `400` → pedido inválido (canal fuera de rango, nombre de perfil inválido, archivo JSON que no es
  un perfil). El motivo viene en `{"detail": "…"}`.
- `503` → el servicio no tiene el dispositivo (la app oficial abierta, o el equipo desconectado):
  llamar `/api/reconnect` y reintentar.
- Si una lectura USB falla de forma rara y persiste: `/api/reconnect`. Como último recurso,
  reconectar el cable USB del equipo.

## Cosas que NO hacer

- No correr el servicio dos veces: al arrancar mata la instancia anterior a propósito (SIGTERM y
  espera, para que libere el USB). Es intencional, no un bug.
- No hacer barridos largos de registros USB **por fuera de la API** (decenas de lecturas de CS/canal
  seguidas pueden degradar el endpoint de control del firmware).
- No usar `/api/status` en bucle rápido: son ~70 lecturas USB por llamada.
- Si se escribe directo con la CLI `~/dev/evo-live/evotool.py`, recordar que sus funciones reciben el
  **unitID** (`0x3A`), no el wIndex (`0x3A00`).

## Tests

```bash
cd ~/dev/evo16-web/backend
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 test_protocol_smoke.py   # 48/48
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 test_presets.py          # 37/37
```
