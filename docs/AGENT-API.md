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
