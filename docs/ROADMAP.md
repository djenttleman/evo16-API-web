# Roadmap / pendientes

Lo que sabemos que falta, con lo ya investigado para retomarlo rápido.

## 1. Tabla de códigos del loopback (pendiente, prioridad baja)

El loopback **ya está resuelto a nivel mecanismo** y verificado; falta el **mapa de las 10 opciones**
a sus códigos de cable.

- Registro: `RoutingMatrix` (unidad `0x33`), **`CS=6`**, 1 byte por canal, en los canales de host
  **22 y 23** (los que devuelve `EvoRackProductDefinition::getLoopbackToHostOutput()` = 22).
- Verificado: escribiendo valores falsos ahí, al abrir la app oficial los **revierte** a los suyos ⇒
  ese registro *es* el loopback y la app lo empuja desde su modelo.
- Hoy, en el equipo de David: **18 y 19**, con su `state.xml` en `loop-back type="3" index="3"`
  (hipótesis sin confirmar: `DAW 7+8`, patrón `código = 12 + 2·index`).
- **Cómo completarlo**: abrir la app, elegir cada opción en el selector de loopback y leer
  `0x33 CS=6` en los canales 22-23 con el servicio parado. Opciones a mapear (las 10 que expone la
  app): `DAW 1+2`, `DAW 3+4`, `DAW 5+6`, `DAW 7+8`, `DAW 9+10`, `MASTER MIX`, `CUE A`, `CUE B`,
  `CUE C`, `CUE D`.
- Nota: la app **adopta el estado del equipo** al arrancar, así que inyectar el valor en `state.xml`
  no sirve para fijarlo; hay que seleccionarlo en la UI.

## 2. Medidores en la UI del remote (opcional)

La API ya los expone (`GET /api/meters`, ~3 ms por llamada, apta para tiempo real). Falta dibujarlos
en la interfaz si se quiere (barras por canal + salidas). Consideración: cada cliente que pollee
suma lecturas USB, así que conviene un intervalo propio (p. ej. 150-250 ms) distinto del poll de
estado, que va cada 2 s.

## 3. Confirmar el número de canales de salida

`GET /api/meters` devuelve **16** salidas (32 bytes). El bloque se lee bien con ese largo, pero
conviene confirmarlo contra el descriptor del equipo (`bNrChannels` del streaming de salida) para no
sobrar ni faltar canales. Ídem el número exacto de canales del bloque de clip.

## 4. Volúmenes de CUE

El desensamblado muestra `setCue1Volume` en **`CS=19`** de la unidad `0x36` (y siguientes), con el
mismo formato Q8.8 que el volumen del main (`CS=18`). En este firmware los CS 19/20/22 **hacen
STALL**, pero `CS=21` y `CS=23` responden con 0 dB — sin mapear todavía qué son. Retomar si David
quiere controlar los CUE desde el remote.

## 5. Loopback como *fuente* del bloque de medidores

`MixerModel::updateOutputMeterValues` lee su bloque del **mismo** destino que las entradas
(unidad `0x3C`, selector `1`). Si en el futuro se agregan buses (MIX/BUS/VCA del lado de la app),
probablemente aparezcan más selectores: el `wValue` es la clave a barrer (ya probados 0, 1, 2 y 3).

## Descartado (no retomar sin motivo)

- **Camino 2 (protocolo de nodos/OSC de la app)**: mutuamente excluyente con el control por USB y
  no aporta para ReaLiveMixer. No hay servidor OSC público; es el protocolo interno de nodos.
- **`0x3B` (OutputControl)**: la entidad no existe en este firmware (todo STALL). El volumen del main
  está en `0x36 CS=18` (ver README).
- **Optimización de `state.db` de Hermes**: decidido por David que no compensa.
