# EVO 16 Remote

App nativa para macOS con interfaz web y API local para controlar una Audient EVO 16 por USB.
La app administra un único servicio; al salir libera el USB. Sin interfaz USB, el estado es `device_disconnected` y los controles se bloquean. La app oficial EVO Control debe
estar cerrada para que el equipo esté disponible.

**App 2.0.1 / contrato API 2.0.0 — contrato actualizado a los hallazgos de hardware del 15–16 de octubre de 2026.**
La [referencia de protocolo](docs/PROTOCOLO-EVO16.md) prevalece sobre las observaciones anteriores.
La investigación de mayo y la documentación v1 están [archivadas y deprecadas](docs/history/README-v1.md);
no deben utilizarse para implementar controles nuevos.

## Controles actuales

- UI de ganancia **0…50**, canales 1–24. Las ganancias negativas quedan pendientes de investigación.
  La corrección 2.0.1 conserva la codificación de API/perfiles v2 mediante un adaptador de presentación.
- Phantom 48 V y mute, canales 1–24.
- DI en canales **1, 2, 9, 10, 17 y 18**: EU58 CS=4, bit 1, lectura-modificación-escritura.
- Link de pares en EU58 CS=3; el firmware espeja gain y DI. El cliente no duplica escrituras.
- Main out: unidad 0x36 CS=18, Q8.8 con signo. Pantalla logarítmica: `100 × 10^(dB/96)`.
- Medidores, fuente de reloj, perfiles locales y guardado standalone en la memoria de la interfaz.
- Loopback y volúmenes CUE siguen pendientes de completar; no se anuncian como controles soportados.

## Compilar y revisar

Requiere macOS 13 o posterior y Command Line Tools. Desarrollo con Python 3.13:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
EVO16_PYTHON="$PWD/.venv/bin/python" ./menubar/build.sh
open "build/EVO 16 Remote.app"
```

La compilación normal crea una app de desarrollo en `build/`, vinculada al checkout y al Python
seleccionado. **No reemplaza la app instalada.** El menú ofrece estado, abrir interfaz,
encender/apagar, preferencias (`⌘,`) y salir.

Para generar una app con Python, dependencias, helper USB e interfaz web incluidos:

```sh
EVO16_PYTHON="$PWD/.venv/bin/python" ./menubar/build.sh --release
```

La app resultante no necesita el repositorio ni un Python instalado en el Mac de destino. La
arquitectura de la app y del helper debe coincidir con ese Mac. El helper incluido se puede
recompilar con `make -C mac-evo16`. La firma de desarrollo es ad hoc; una distribución pública
con confianza de Gatekeeper requiere Developer ID y notarización con las credenciales del editor.

Instalación explícita: `./menubar/build.sh --release --install`, o `./menubar/install.command`.
El instalador coloca la app en `~/Applications` y la CLI en `~/bin` cuando está disponible.

## Conexión e integración

- API y web: `http://127.0.0.1:3000`, accesible solo desde este Mac por defecto.
- Todas las rutas `/api/*` requieren credencial Bearer. La web local usa una cookie HttpOnly
  SameSite=Strict; las escrituras con cookie requieren el mismo origen.
- La credencial se copia desde Preferencias. También está en
  `~/Library/Application Support/EVO16Remote/api-token` (permisos 0600, carpeta 0700).
- Preferencias permite acceso por red y una API de ciclo de vida opcional en `127.0.0.1:3100`.
  El acceso remoto necesita credencial; HTTP no cifra la red local, por lo que se recomienda
  Tailscale o un transporte HTTPS administrado por el usuario. No abrir puertos a Internet.
- La app publica `estado.json` para descubrir estado y rutas sin otra consulta USB. Un estado
  de más de ocho segundos debe considerarse vencido.
- URL scheme: `evo16remote://start`, `stop`, `status`, `preferences`.
- Guía para ReaLiveMixer y otros clientes: [docs/AGENT-API.md](docs/AGENT-API.md).

CLI: `evo16-remote start|stop|restart|status|health|info|url|logs|preferences`. Los comandos de ciclo
de vida se envían a la app; la CLI no maneja procesos ni crea un segundo servicio.

## Disponibilidad y consumo

Un trabajador USB serializa operaciones completas, incluidas las secuencias de DI y perfiles.
La cola admite 32 solicitudes pendientes. Cada transferencia y operación tiene un plazo total;
una escritura vencida antes de empezar no se ejecuta después.

Los clientes comparten una captura de estado de hasta dos segundos y una captura de medidores de
hasta 150 ms. El sondeo completo se suspende cuando deja de haber consultas de estado; la sonda
ligera de conexión continúa. Los fallos nunca se sustituyen por ganancias cero o booleanos falsos.

El servicio reintenta conectar con espera progresiva de 2 a 30 segundos. `/api/reconnect` permite
forzar el intento, incluso si la inicialización original falló. Las lecturas fallidas invalidan la
conexión. La app puede reiniciar su propio servicio tras un cierre inesperado.

## Migración desde v1

Este cambio es incompatible a propósito: consultar [docs/MIGRATION-v2.md](docs/MIGRATION-v2.md)
antes de actualizar un cliente. Los archivos originales de perfiles no se reescriben al leerlos.

Los agentes launchd antiguos y `launcher.py` están deprecados. La primera apertura de la app v2
descarga únicamente los tres agentes con los identificadores del proyecto y renombra sus plists
como `.deprecated`. No termina procesos por nombre ni libera un puerto matando a su dueño.
`comando.json` se reemplaza por el URL scheme o la API de ciclo de vida.

## Verificación sin hardware

```sh
python3 -m unittest backend.test_contract backend.test_presets backend.test_lifecycle
python3 backend/test_protocol_smoke.py
python3 backend/test_health_state.py
node --check web/app.js
```

Las pruebas cubren seguridad HTTP, el contrato, recuperación, cola, caché compartida, tiempos
límite del helper, validación/migración de perfiles y codificación USB reciente. No equivalen a una
nueva verificación física: el protocolo conserva la evidencia registrada en octubre.

Detalle de pruebas realizadas y comprobaciones físicas pendientes: [docs/VALIDATION-v2.md](docs/VALIDATION-v2.md).
