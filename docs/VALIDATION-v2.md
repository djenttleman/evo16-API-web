# Verificación v2

## Realizada sin interfaz física

La EVO 16 no está conectada a este Mac durante el desarrollo. Ninguna prueba de esta rama requiere
ni reclama una nueva verificación en hardware.

- Pruebas de API, autenticación, orígenes, traversal, límites y errores sin dispositivo.
- Serialización USB, caché compartida, cancelación de escrituras vencidas y recuperación tras fallo inicial.
- Codificación reciente: gain −8…50 ↔ byte 0…58; DI CS=4 preservando bits; link CS=3; piso del main.
- Perfiles completos v2 y migración v1 que preserva los bytes originales sin reescribir los archivos.
- Servicio real desde fuentes y desde el paquete congelado, usando `backend/fixtures/usb_helper.py`
  mediante `EVO16_HELPER_PATH` explícito. Credenciales, archivos y puertos de prueba aislados.
- Ausencia de dispositivo informada como `device_disconnected`, persistente durante la espera de reconexión; controles bloqueados.
- Helpers externos rotulados como prueba en API, web y app; nunca confundir un fixture con detección física.
- Segunda instancia rechazada sin terminar la primera; cierre por pérdida del proceso padre.
- Compilación de AppKit y paquete ARM64 con Python, web y helper incluidos; firma ad hoc verificada.
- Revisión visual de preferencias y web; control por teclado de ganancia negativa sobre el fixture.

Comandos:

```sh
python3 -m unittest backend.test_contract backend.test_presets backend.test_lifecycle
python3 backend/test_protocol_smoke.py
python3 backend/test_health_state.py
node --check web/app.js
bash -n menubar/build.sh menubar/install.command bin/evo16-remote
```

`backend/test_lifecycle.py` prueba también el paquete si está compilado en `build/`.
`EVO16_HELPER_PATH` es una sustitución local explícita para diagnósticos/pruebas; nunca viene de HTTP.
No habilitarla al verificar el equipo real. La producción no contiene un modo demo implícito.

## Pendiente al conectar la EVO 16

1. Abrir únicamente la app de esta rama y confirmar conexión; EVO Control oficial cerrada.
2. Comparar gain en la API y en la pantalla oficial, especialmente −8, 0 y +50 dB, manteniendo un
   entorno de audio apropiado para comprobar ganancias. Verificar retorno desde la perilla física.
3. Confirmar DI en los canales con hardware, preservación de flags y comportamiento con pares linkeados.
4. Verificar phantom y mute local/ADAT con la configuración de SP8 documentada. No inferir cambios
   de entidad a partir de la corrección de link.
5. Comparar el main con su pantalla logarítmica: silencio, 10 y 100; comprobar lectura física.
6. Desconectar y reconectar USB, abrir/cerrar la app oficial y verificar recuperación y estados 503.
7. Conectar RLM y la web simultáneamente; observar respuesta de controles y recursos del sistema.
8. Capturar un perfil válido, exportar/importar y aplicar; comparar el estado de los 24 canales.
9. Probar reloj y standalone solo cuando se quiera modificar esos estados; standalone se verifica
   tras ciclar energía. Siguen siendo acciones explícitas del usuario, no parte del arranque.

No hay programación automática de estas pruebas. Permanecen pendientes hasta que el equipo esté
conectado y se realice la comprobación física.
