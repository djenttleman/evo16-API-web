# API v2 — EVO 16 Remote / ReaLiveMixer

Fuente de verdad del control: [PROTOCOLO-EVO16.md](PROTOCOLO-EVO16.md), hallazgos del 15–16 de octubre
2026. La investigación de mayo y el contrato v1 están deprecados cuando contradicen esa referencia.

## Descubrimiento y autenticación

La app debe estar abierta. Base de control: `http://127.0.0.1:3000`.

La carpeta `~/Library/Application Support/EVO16Remote/` contiene:

- `api-token`: credencial del usuario, solo lectura para el cliente. No registrarla ni enviarla en URLs.
- `estado.json`: estado de la app y del servicio, con `updatedAtEpoch`, versión y rutas. Si tiene
  más de ocho segundos, la app no está disponible; no tratarlo como un estado actual del hardware.
- `prefs.json`: preferencias administradas por la app. No modificarlas desde una integración.

Todas las peticiones HTTP de la API requieren `Authorization: Bearer <credencial>`, incluidas
salud, información y esquema OpenAPI. Clientes nativos como RLM no necesitan CORS. La API rechaza
orígenes web diferentes; un WebView de otro origen debe delegar las peticiones a su capa nativa.

```sh
TOKEN="$(cat "$HOME/Library/Application Support/EVO16Remote/api-token")"
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3000/api/health
curl -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"db":-8}' http://127.0.0.1:3000/api/gain/1
```

`GET /api/info` anuncia rangos y capacidades; `GET /api/openapi.json` entrega el esquema generado
por las rutas reales. Versión API: `2.0.0`; revisión de protocolo: `evo16-2026-10-16`.

## Estado y disponibilidad

| Ruta | Resultado |
| --- | --- |
| `GET /api/health` | Sonda compartida: `service`, `version`, `protocolRevision`, `state`, `ok`, `stateDetail`, `stateSeconds`, `device`, `sampleAgeSeconds` |
| `GET /api/status` | Estado completo válido: `inputs` (24), `mainVolume`, `outputs` vacío, `status: ok`, `sampledAtEpoch`, `sampleAgeSeconds` |
| `POST /api/reconnect` | Intenta reconectar: `service`, `device`, `state`, `ok` y frescura de la sonda |

Estados de salud: `connected`, `usb_busy`, `helper_down`, `device_unreachable`, `reconnecting`,
`not_ready`, `device_disconnected`. `device_disconnected` identifica ausencia de la EVO 16 en USB,
diferente de un fallo del helper. `ok` es verdadero únicamente con una sonda reciente y conexión real. Un `200` de salud
indica que el servicio responde; mirar `ok` para saber si responde el equipo.

`offline` lo publica la app cuando el servicio está apagado. Si tampoco está abierta la app, el
archivo de estado vence o la conexión HTTP falla. La reconexión automática usa espera progresiva.

`/api/status` nunca simula controles: sin captura válida devuelve 503. Fallar una lectura invalida
la captura completa. `outputs: []` significa que no se ofrece estado de mute de salidas. Los campos
de DI de canales sin hardware son `null`, no un control inactivo que se pueda activar.

Sondear estado cada dos segundos. Varias apps comparten la misma captura; no provocan una ronda
USB por cliente. Los medidores comparten capturas durante 150 ms. Una escritura invalida la captura.
`testMode: true` indica un helper externo de prueba/diagnóstico; no tomar sus respuestas como
verificación física. La web y la app lo rotulan explícitamente como prueba.
No hay garantía de simultaneidad física entre los registros de una captura.

## Ganancia: corrección de presentación 2.0.1

El usuario comprobó que −8 en la UI anterior mostraba 0 en el equipo. Los valores físicos negativos
no están descubiertos. La UI actual usa **0…50** y adapta el contrato v2 existente:
`apiGain = uiGain - 8`, `uiGain = clamp(apiGain + 8, 0, 50)`. Así UI 0 envía byte 0 y UI 50 envía
byte 50. Los valores por encima del límite confirmado no se ofrecen en la UI.

No cambia el protocolo ni se reescriben los perfiles por este ajuste visual. Un cliente que use
el contrato v2 debe conservar su codificación; su campo `db` es una convención heredada cuya
interpretación como ganancia física no está verificada. La API y los perfiles se revisarán por
separado si la investigación confirma otro mapeo. No enviar valores negativos suponiendo atenuación.

## Controles

| Método / ruta | Cuerpo POST | Unidad y significado |
| --- | --- | --- |
| `GET / POST /api/gain/{channel}` | `{"db":-8}` | Contrato legado v2: entero −8…50; en el cable `db + 8`. **No equivale a dB físicos verificados** |
| `GET / POST /api/phantom/{channel}` | `{"on":true}` | Phantom 48 V |
| `GET / POST /api/mute/{channel}` | `{"muted":true}` | Mute de entrada |
| `GET / POST /api/instrument/{channel}` | `{"on":true}` | DI solo en 1, 2, 9, 10, 17, 18; CS=4, bit 1, RMW |
| `GET / POST /api/link/{channel}` | `{"on":true}` | Pares 1–2, 3–4…; EU58 CS=3 |
| `GET / POST /api/main-volume` | `{"db":-20}` | Q8.8 firmado, rango permitido −128…0 dB |
| `GET /api/meters` | — | `inputs` (24), `outputs` (16), clips, en dB; cantidad de salidas pendiente de confirmación adicional |
| `POST /api/smartgain/{channel}` | `{segundos?, objetivoDb?}` | Acomoda la ganancia de un canal midiendo su nivel real (ver **SmartGain**) |
| `POST /api/smartgain` | `{segundos?, objetivoDb?}` | Lo mismo para los 24 canales en una sola pasada; los canales sin señal no se tocan |
| `GET / POST /api/clock` | `{"source":"internal"}` | 1/internal, 2/optical1, 3/optical2 |
| `POST /api/store-standalone` | — | Guarda el estado actual en la memoria del equipo; sobrescribe el anterior |

Canales: 1–24. Los GET individuales devuelven `channel`, el campo leído y `status: ok`. Mute usa
`muted` en el GET individual y `mute` en la captura completa. Link incluye `pair: [impar, par]`.

El firmware espeja gain y DI al linkear; el cliente no duplica escrituras. Una secuencia completa
se serializa para evitar que otra petición intercale un cambio entre lectura y escritura de DI.
La API no agrega nuevos controles ni cambia CS, entidades o payloads sin evidencia de hardware.

Pantalla del main: `v = floor(100 × 10^(db/96))`, con el piso de silencio de la UI en 0.
Para escribir: `db = max(-128, 96 × log10(v/100))`; `v = 0` se envía como −128 dB.
Conservar la ley logarítmica: −96 dB corresponde a 10 y 0 dB a 100.

Cambiar el reloj a óptico sin una fuente presente puede perder la sincronización. Standalone es
una operación de una sola vía; la comprobación física requiere ciclar la energía del equipo.

## SmartGain — `POST /api/smartgain/{channel}` y `POST /api/smartgain`

Acomoda la ganancia midiendo el nivel real de entrada. **No existe un comando de SmartGain en el
equipo**: el firmware no lo dispara ni lo ejecuta por USB (ver `PROTOCOLO-EVO16.md`, CS=5). Lo hace
el software, que ya tiene los medidores del equipo (4 transferencias, ~3 ms).

- `POST /api/smartgain/2` → **un canal**. `POST /api/smartgain` → **los 24 en una sola pasada** (una
  lectura de medidores trae todos, así que "todos" cuesta lo mismo que uno).
- Cuerpo opcional: `{"segundos": 10, "objetivoDb": -12}`. Por defecto mide **10 s** y apunta a
  **−12 dBFS** (el objetivo de Audient).
- Los canales **sin señal no se tocan**: vuelven con `ok: false` y el motivo en `detail`.
- La ganancia se recorta al rango real (**−8…+50 dB**). Si la señal entra demasiado caliente, el
  ajuste queda en el piso y se ve en `deltaDb`.

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"segundos":10}' http://127.0.0.1:3000/api/smartgain/2
# {"status":"ok","ok":true,"channel":2,"peakDb":-0.1,"gainAntesDb":-5.0,"gainDb":-8,
#  "deltaDb":-3.0,"objetivoDb":-12.0,"segundos":6.1,"muestras":24,
#  "resumen":"canal 2: pico -0.1 dB → ganancia -8 dB"}
```

## Perfiles

| Ruta | Comportamiento |
| --- | --- |
| `GET /api/presets` | Lista del banco local |
| `GET /api/presets/{name}` | Contenido validado, migrado a v2 si era v1 |
| `POST /api/presets/{name}` | Captura y guarda los 24 canales actuales |
| `POST /api/presets/{name}/apply` | Aplica un perfil validado; devuelve `status`, `applied`, `errors` |
| `POST /api/presets/{name}/export` | Devuelve el JSON como descarga; el cliente elige dónde guardarlo |
| `POST /api/presets/import` | `{"preset": {…}, "name":"opcional"}`; sube contenido, nunca una ruta del Mac |
| `DELETE /api/presets/{name}` | Borra el perfil del banco |

Formato: `formatVersion: 2`, `gainEncoding: "db"`, `name`, `savedAt`, `device`, `channels`.
Deben estar los 24 canales, sin duplicados, con ganancias válidas y booleanos reales. Un par linkeado
debe tener estados compatibles de gain y DI. Se valida todo antes de la primera escritura USB.

Los perfiles sin versión son v1: su campo gain era el byte 0…58. Al leerlos se resta ocho, conservando
exactamente lo que se enviaba al equipo. El original no se modifica hasta un guardado explícito.
Un perfil incompleto o inconsistente se rechaza; no se aplican valores por defecto.

Aplicación: link → mute de los que terminarán muteados → phantom/gain/DI → unmute final. El resultado
puede ser `partial` si una escritura falla; no existe rollback físico. Consultar errores y estado
antes de reintentar. Los perfiles no incluyen main, reloj ni memoria standalone.

## Encendido y apagado

La app es el único dueño del servicio; al salir lo termina y libera el helper. Si la app muere,
el servicio detecta la desaparición de su padre y se cierra. No hay otro launcher en paralelo.

Desde RLM se puede abrir la app mediante LaunchServices y el esquema:

```sh
open -g -a "$HOME/Applications/EVO 16 Remote.app" 'evo16remote://start'
open -g -a "$HOME/Applications/EVO 16 Remote.app" 'evo16remote://stop'
```

La alternativa HTTP se activa en Preferencias y escucha **solo loopback**, con la misma credencial:

- `GET http://127.0.0.1:3100/api/status`: estado de la app y del servicio.
- `POST /api/start` o `POST /api/stop`: **202 Accepted**; consultar estado hasta que termine.

El 3100 es para clientes nativos; rechaza solicitudes de navegador y orígenes web. El antiguo buzón
`comando.json`, los agentes launchd separados, `launcher.py`, `/api/service/stop` y `/api/logs`
están deprecados/eliminados. Los logs se consultan en Preferencias o con `evo16-remote logs`.

## Errores y reintentos

- `400`: canal, perfil o valor semántico inválido; `detail` describe el problema.
- `401`: credencial ausente o incorrecta.
- `403`: origen web no permitido.
- `408`: se agotó el plazo para recibir el cuerpo.
- `413`: solicitud mayor a 256 KiB.
- `422`: estructura/tipo/rango del cuerpo inválido.
- `503`: dispositivo no disponible, cola llena o tiempo agotado; `Retry-After: 2`.

Nunca hay un éxito `mock`. Un timeout después de empezar una escritura puede dejar un resultado
incierto: leer el estado antes de reintentar, especialmente standalone. Las solicitudes que vencen
mientras esperan en la cola se descartan. Preferir escritura absoluta de estado a comandos toggle.
