# Plugin VST3 — Diseño

> **Fecha:** 2026-07-15
> **Estado:** 📐 DISEÑO — nada implementado.
> **Autor:** djenttleman + Claude (Opus 4.8)
> **Dispositivo:** Audient EVO 16 (VID 0x2708, PID 0x000A)
> **Formato:** VST3 únicamente. **Sin AU.**
> **Hosts objetivo:** Studio One, Reaper (macOS)

---

## Resumen

Plugin VST3 que permite controlar la ganancia de un preamp de la EVO 16 desde el
DAW. Cada instancia se asigna a un canal (1–24) y controla su ganancia. La ganancia
queda guardada en el proyecto y se recupera al cargarlo.

Las instancias del plugin **no hablan USB**. Son clientes ligeros de un daemon
singleton que es el único dueño del dispositivo. Esa no es una preferencia de
diseño: es una restricción física del USB en macOS (ver abajo).

---

## La restricción que define la arquitectura

`USBDeviceOpen()` ([mac-evo16.c:80](../mac-evo16/mac-evo16.c)) es un **open exclusivo**.
Un solo proceso en todo el sistema puede tener el dispositivo abierto. El segundo
que lo intente recibe `kIOReturnExclusiveAccess` y falla.

El repo ya documentaba esta restricción sin nombrarla:

| Evidencia | Ubicación |
|---|---|
| `pkill -9 -f mac-evo16` antes de arrancar el server | [main.py:40](../backend/main.py) |
| *"Is the official EVO Control app closed?"* | [main.py:77](../backend/main.py) |

**Consecuencia:** N instancias del plugin abriendo el dispositivo directamente =
1 gana, N−1 fallan. Y además romperían el web service y la app oficial de Audient.
Los VST3 se cargan dentro del proceso del DAW, así que el conflicto se agrava con
dos DAWs abiertos, o durante un rescan de plugins.

La independencia que se busca no está en el transporte, está en el **estado**: cada
instancia controla su canal sin pisarse con las demás. Eso se logra con un proceso
único dueño del USB y N clientes.

---

## Arquitectura

```
[VST3 inst 1 → CH3 ] ─┐
[VST3 inst 2 → CH7 ] ─┼─► IPC ─► daemon (singleton) ─► IOKit ─► EVO 16
[VST3 inst N → CH14] ─┘              ▲   (dueño único del USB
[Web UI / tablet ] ──── HTTP ────────┘    + caché de estado)
```

El daemon es, funcionalmente, lo que ya son `backend/main.py` + `mac-evo16`.
El protocolo USB no se reimplementa: las constantes `VERIFIED_*` de
[service.py](../backend/service.py) siguen siendo la única fuente de verdad.

| Fase | Transporte | Objetivo |
|---|---|---|
| **1** | HTTP contra el FastAPI existente (`localhost:3000`) | Validar la arquitectura sin escribir USB nuevo |
| **2** | Daemon nativo (C++ + IOKit) sobre Unix socket, lanzado por launchd | Producto: sin dependencia de Python |

---

## Modelo de parámetros

Los parámetros se exponen al DAW pero **no son automatizables**
(`automatable = false`; en JUCE `withAutomatable(false)`).

En VST3, "exponer un parámetro" y "hacerlo automatizable" son cosas separadas. Con
`automatable = false` el host sigue guardando el valor con el proyecto, sigue
restaurándolo al cargar y sigue exponiéndolo a superficies de control remoto. Lo
único que desaparece es la lane de automatización.

**Justificación (criterio de diseño de sonido, no técnico):** la ganancia de un
preamp y el phantom no se automatizan nunca. Son valores deterministas que el
ingeniero fija al obtener niveles según la fuente. Una vez seteados, son estáticos
para el proyecto. Marcarlos no-automatizables impone esa semántica en código en vez
de dejarla a la disciplina del usuario.

### Qué guarda el proyecto

| Parámetro | Rango | Automatizable | Guardado | Recall |
|---|---|:---:|:---:|:---:|
| **Gain** | 0–50 dB, 51 pasos | ❌ | ✅ | ✅ |
| **Channel** | 1–24 | ❌ | ✅ | n/a |
| **Phantom 48V** | bool | ❌ | ❌ | ❌ |
| **Mute** | bool | ❌ | ❌ | ❌ |
| **Instrument** | — | — | ❌ | ❌ |

**El proyecto guarda exactamente dos cosas por instancia: el canal y su ganancia.**
Phantom y mute son controles vivos de la UI: reflejan el hardware y se pueden tocar,
pero no viajan en el proyecto.

**Channel no debe ser automatizable.** Es tentador exponerlo porque necesita
persistir, pero un parámetro automatizable es un parámetro que el host puede barrer:
la instancia saltaría de canal a mitad de la canción, reasignando qué preamp
controla.

**Gain como parámetro escalonado** (`stepCount = 50`): el rango verificado es
0–50 dB entero ([service.py](../backend/service.py), `VERIFIED_GAIN_MIN_DB` /
`VERIFIED_GAIN_MAX_DB`). Con 51 pasos discretos el host cuantiza antes de llegar al
plugin, y la mayoría de los cambios se detectan como no-ops con una comparación de
enteros.

**Instrument** queda fuera: hoy no funciona por USB
(ver [instrument-mode-research.md](instrument-mode-research.md)).

---

## Recall

**Al cargar un proyecto se aplica solo el delta de ganancia. Nada más.**

Sobreescribir las ganancias físicas al cargar es intencional y es el modelo de las
consolas digitales de directo: el proyecto es dueño de la ganancia. El usuario debe
saber que cargar un proyecto con plugins insertados pisa lo que haya en la interfaz.

El daemon ya conoce `actual` (tiene caché), así que compara contra `desired` y
escribe únicamente lo que cambió. En el caso común —reabrir el proyecto en el que
estabas trabajando— **el delta es cero y no se escribe nada.** El peor caso son ~16
escrituras.

### Phantom: nunca se recala

El phantom **no se aplica nunca de forma automática**. Solo se conmuta por acción
manual explícita, desde el plugin o desde el web UI.

**Motivo — la asimetría:** una ganancia mal recalada suena mal y se corrige. 48V
sobre un micro de cinta lo destruye, y no hay deshacer. Y el software no puede saber
qué hay enchufado: el canal 3 tenía un condensador hace tres meses, hoy tiene una
cinta, y la EVO no tiene forma de enterarse.

Como el proyecto tampoco guarda el phantom (opción A), no hay nada contra lo que
divergir: el plugin simplemente refleja el estado del hardware.

### Sin pantalla de carga

Con este alcance no hace falta. El peor caso son ~16 escrituras de ganancia y el
caso típico no escribe nada. No hay nada que cargar.

---

## El daemon

### Estado

```python
desired[(channel, control)] = value   # lo que se quiere; último valor gana
actual[(channel, control)]  = value   # lo que el hardware confirmó
```

Un hilo drena la diferencia a ritmo limitado. Propiedades que salen solas:

- Si dos instancias apuntan al mismo canal, la última gana — determinista, sin
  condición de carrera.
- El web UI lee `actual` desde memoria, sin tocar el bus.

### El caché no es opcional

`get_all_status()` hace 24 canales × 3 lecturas = **72 control transfers**, y el web
UI lo llama cada 2 s ([app.js:269](../web/app.js)). Con N instancias haciendo lo
mismo, el bus se satura. El daemon mantiene shadow state, sirve lecturas desde
memoria y **empuja** los cambios a los clientes en vez de que cada uno haga polling.

### Rate limit

Seguro barato, no necesidad demostrada. El quirk #2 de [DESIGN.md](DESIGN.md)
(ráfagas → STALL) se observó **en EVO4/Linux abriendo y cerrando el fd por comando**;
el helper de macOS mantiene un handle persistente, así que puede no reproducirse.
Empezar en ~50 transfers/s y medir. Ver riesgos abiertos.

---

## Reglas de threading

**Nada de USB en el hilo de audio.** Un control transfer tarda 1–5 ms y es
bloqueante. En `processBlock` = dropouts garantizados.

El parámetro se escribe en un atomic; un hilo worker (o timer de UI) drena los
cambios y habla con el daemon.

**Nada de red bloqueante en el constructor.** Studio One instancia los plugins en su
`Plug-In Scanner.app` durante el escaneo, no solo al usarlos (verificado 2026-07-16).
Si el constructor hace un GET bloqueante y el daemon no está corriendo, **el escaneo
se cuelga el timeout de conexión entero en cada arranque de Studio One.**

Conexión perezosa y asíncrona. El plugin arranca en estado desconectado sin quejarse
y sin tocar la red hasta que hace falta.

### Supresión de eco

El daemon empuja estado → el plugin actualiza su parámetro → el parámetro notifica
al host → el host reenvía el valor → vuelta al daemon.

**Regla:** cuando el valor viene del daemon, se actualiza el parámetro **sin**
reenviarlo (flag de supresión durante la escritura). Solo los cambios originados en
la GUI del plugin viajan hacia el hardware.

Como los parámetros no son automatizables, el conflicto clásico de knob físico vs.
modo Read **no existe**.

---

## Decisiones descartadas y por qué

| Descartado | Motivo |
|---|---|
| Cada instancia abre el USB directamente | Imposible: `USBDeviceOpen()` es exclusivo |
| Versión AU | Su único argumento era Logic, que no carga VST3. Studio One y Reaper cargan VST3 nativamente. AU = superficie extra de testeo a cambio de cero. Además AUv3 es sandboxeado por diseño, que era el origen del riesgo #1 |
| Parámetros automatizables | Ni por diseño de sonido ni por caso de uso. Un preamp no se automatiza |
| Batch/paquete de escrituras | **No existe en el protocolo.** Cada `SET_CUR` codifica un solo canal en `wValue = (CS << 8) \| channel_index`. En el cable siempre es uno por uno |
| Recall de phantom | 48V sobre una cinta es daño irreversible y el software no sabe qué hay enchufado |
| Recall de mute | El mute de un preamp es transitorio (el guitarrista se fue a fumar), no una propiedad del proyecto. El mute de pista del DAW cubre lo que sí lo es |
| Apply ordenado (mute → phantom → asentar → gain → unmute) | Importado del recall de escena de consola, donde el contexto es **PA vivo durante el show**. Cargar un proyecto en un DAW no es eso. Sin phantom ni mute en el recall, no queda orden que decidir |
| Bracket de mute en la ganancia | 3× escrituras, deja canales mudos si el daemon muere a mitad, y si el mute de la EVO no es suave cambia un clic por dos. La ganancia es recuperable — ese fue el criterio para separarla del phantom |
| Ventana de asentamiento al cargar | Solo existía para poder recoger todo y ordenarlo. Sin orden, no hace falta esperar a nadie |
| Cola de comandos | Reproduciría todos los valores intermedios con retraso creciente. El mapa `desired` coalesce por naturaleza |

---

## Riesgos abiertos

### ✅ #1 — Sandboxing del host — PASA

> Verificado 2026-07-16 con `codesign -d --entitlements` sobre los binarios
> instalados. **Degradado de 🔴 a 🟡 al descartar AU** (el riesgo venía de AUv3, que
> es una App Extension sandboxeada por diseño), y cerrado aquí.

Los cuatro binarios que pueden hospedar el plugin, **sin
`com.apple.security.app-sandbox`**:

| Binario | App Sandbox | Hardened Runtime |
|---|---|---|
| `REAPER.app` | ✅ ausente | sí |
| `REAPER.app/Contents/Plugins/reaper_host_arm64.app` (bridge) | ✅ ausente | sí |
| `Studio One 7.app` | ✅ ausente | sí |
| `Studio One 7.app/Contents/PlugIns/Plug-In Scanner.app` | ✅ ausente | sí |

El App Sandbox es **opt-in vía entitlement**: sin esa clave no hay sandbox, no existe
forma de activarlo sin declararlo. El Hardened Runtime que sí tienen los cuatro
restringe inyección de código, JIT y validación de librerías — **no la red**.

Ambos hosts declaran `com.apple.security.cs.disable-library-validation`, necesario
para cargar plugins de terceros.

**Naturaleza de la evidencia:** inferencia, no observación. No se ha compilado un
plugin ni se le ha visto hacer el GET; se ha probado que *no existe el mecanismo que
podría bloquearlo* en ninguno de los cuatro procesos. La confirmación empírica se
pliega al primer paso de la fase 1 (que el plugin arranque haciendo el GET) en vez de
construir un dummy de usar y tirar.

Un Unix domain socket esquiva además el prompt de "Red local" de macOS. (Localhost
por TCP tampoco lo dispara — el loopback está exento. Solo el web UI sirviendo en
`0.0.0.0` para la tablet toca red de verdad, y eso ya funciona hoy.)

### 🟡 #2 — Ráfaga de escrituras (sin medir)

¿Aguanta la EVO ~16 escrituras seguidas con handle persistente? El quirk #2 de
DESIGN.md predice STALL, pero se observó en otro contexto (EVO4/Linux, open/close
por comando). Medir dónde empieza a fallar y fijar el rate limit ahí.

### ✅ #3 — Licencia — RESUELTO

> Verificado 2026-07-16 en fuente primaria. Nota: información previa en esta
> conversación ("JUCE es GPL3 o de pago", "el VST3 SDK es GPL3 o licencia
> Steinberg") era **incorrecta y está desactualizada**. Ambas cosas cambiaron.

**El formato no tiene decisión de licencia.** El
[VST3 SDK es MIT](https://steinbergmedia.github.io/vst3_dev_portal/pages/FAQ/Licensing.html)
desde finales de 2025: sin registro, sin acuerdo que firmar, distribución de
binarios sin abrir código, compatible con este repo MIT.

**Framework — decisión: JUCE Starter.**

| | Licencia | Coste | Techo | Papeleo |
|---|---|---|---|---|
| **JUCE Starter** ← elegido | Propietaria, perpetua | Gratis | $20k/año | Cuenta + EULA |
| VST3 SDK directo | MIT | Gratis | Ninguno | Ninguno |

[JUCE Starter](https://juce.com/get-juce/) permite uso comercial y closed-source
dentro del techo. **No hace falta GPL3.** Se elige por velocidad: knob, selector de
canal y parámetros salen en decenas de líneas.

⚠️ **Cable trampa:** el techo de $20k de Starter cuenta *"donations, sponsorship,
advertising"*, no solo ventas ([EULA JUCE 8](https://juce.com/legal/juce-8-licence/)).
Relevante para un repo público con GitHub Sponsors. Si se cruza: Indie, $40/mes.

**Cuándo reconsiderar el SDK directo:** si importa que cualquiera pueda forkear y
compilar sin sacarse su propia licencia de JUCE. Con JUCE, el código propio puede ser
MIT pero quien compile necesita cuenta. Con el SDK directo el árbol es MIT de punta a
punta. Coste: escribir el widget del knob a mano.

### ⚪ #4 — Plataforma (fuera de alcance inicial)

Todo el código IOKit es solo macOS. En Windows el driver de Audient reclama el
dispositivo (mismo problema que DESIGN.md describe en Linux); un port implicaría
WinUSB o el truco de la interfaz DFU.

---

## Plan por fases

| Fase | Qué | Sale bien si |
|---|---|---|
| ~~**0**~~ | ~~Check de sandboxing~~ | ✅ Pasa: ningún host ni helper tiene App Sandbox |
| ~~**0b**~~ | ~~Decidir licencia~~ | ✅ Resuelto: VST3 SDK (MIT) + JUCE Starter (gratis) |
| **0c** | Levantar el daemon: venv + `pip install -r requirements.txt` | `curl localhost:3000/api/status` responde (modo demo vale) |
| **1** | Plugin cliente HTTP: gain + channel, no-automatable, recall por delta.<br>**Primer commit = el GET, antes de la GUI** (confirma el riesgo #1 gratis) | Dos instancias en canales distintos, sin pisarse; recall al reabrir |
| **2** | Daemon con caché + push; el web UI migra a él | N instancias + web UI sin saturar el bus |
| **3** | Daemon nativo (C++/IOKit/launchd), sin Python | Se instala junto al plugin |
| **4** | Phantom/mute como controles vivos en la UI del plugin | — |
