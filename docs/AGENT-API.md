# EVO 16 Remote — guía de la API para agentes

API HTTP para controlar una **Audient EVO 16** por USB. La misma URL sirve la interfaz web y la API.

- **Base**: `http://127.0.0.1:3000` (en LAN/Tailscale: `http://<ip>:3000`). `GET /api/health` devuelve las URLs.
- **Docs interactivas**: `http://127.0.0.1:3000/docs` (OpenAPI generado por FastAPI).
- **Código**: `~/dev/evo16-web` — la memoria del protocolo está en la skill `audient-usb-control`.

## Encarecer el servicio (desde una shell normal, NO desde dentro de Hermes)

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
| GET | `/api/health` | Estado **en vivo**: `device.connected` (hace una lectura real al equipo), `device.helper`, `device.mainVolume`, `audientAppRunning`, `urls`, `uptimeSeconds` |
| GET | `/api/info` | Mapa de capacidades (lo que está en esta tabla) |
| GET | `/api/status` | Los 24 canales (`gain`, `phantom`, `mute`, `instrument`, `linked`, `linkPair`) + `mainVolume` |
| POST | `/api/reconnect` | Reabre el dispositivo (usar después de cerrar la app oficial) |

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
| GET/POST | `/api/main-volume` | `{"db": -20}` | Control que **la app oficial no expone**. Escala de la pantalla del equipo: **0 = −96 dB, 100 = 0 dB** ⇒ `dB = (v − 100) × 0.96` |

## Encender y apagar el servicio

### Recomendado para otras apps: la app de barra de menú (sin exponer nada por HTTP)

`EVO 16 Remote.app` (código en `menubar/`) vive en la barra de menú con tres acciones —**Encender
servicio**, **Apagar servicio**, **Salir**— y muestra el estado real en el propio ítem (ícono relleno
= equipo OK, hueco = servicio arriba sin equipo, apagado = servicio abajo).

Además acepta pedidos por **esquema de URL**, que es la puerta programática: **no hay ningún endpoint
HTTP de ciclo de vida**, sólo la app.

```bash
open -g "evo16remote://start"     # enciende el servicio (y la app si no estaba corriendo)
open -g "evo16remote://stop"      # lo apaga, liberando el USB
open -g "evo16remote://status"    # sólo refresca el estado
```

Después de `start` hay que esperar ~5-10 s a que el servicio abra el dispositivo; para saber cuándo
está listo se sondea `GET http://127.0.0.1:3000/api/health`. Desde un ReaScript:

```lua
os.execute('open -g "evo16remote://start"')
```

Compilar/instalar la app: `./menubar/build.sh --open` (requiere las Command Line Tools; queda en
`~/Applications`). Para que arranque con el sistema, agregala a «Iniciar sesión».

### Alternativa: launcher HTTP en el puerto 3100

Si preferís encender/apagar por HTTP en vez de por URL, está `launcher.py` (sólo stdlib, no toca el
USB), que escucha en **`http://127.0.0.1:3100`**:

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/status` | `{"service": "running"\|"stopped", "device": {...}, "agentInstalled": true}` |
| POST | `/api/start` | Arranca el servicio y **espera** a que responda |
| POST | `/api/stop` | Lo detiene ordenado (SIGTERM: libera el USB) |
| GET | `/api/logs?n=80` | Últimas líneas del log del servicio |

Se instala una sola vez desde la Terminal: `~/bin/evo16-remote launcher-install`.

### El servicio apagándose solo

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/service/stop` | Responde 200 **y después** baja (libera el USB) |

### Receta para una extensión externa (por ejemplo la de REAPER)

```bash
curl -s http://127.0.0.1:3000/api/health                # ¿está todo arriba?
open -g "evo16remote://start"                           # si no, encenderlo (URL, sin HTTP)
#   ... uso normal: http://127.0.0.1:3000/api/... (gain, phantom, link, meters, clock…)
curl -X POST http://127.0.0.1:3000/api/service/stop    # o: open -g "evo16remote://stop"
```

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
