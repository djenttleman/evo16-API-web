# Migración a v2

La evidencia del EVO 16 del 15–16 de octubre de 2026 reemplaza los supuestos de mayo cuando difieren.
No se restauran DI CS=5, link FU11 ni la conversión lineal del main. La API pasa a versión 2 porque
corrige el significado de gain y requiere autenticación.

| v1 | v2 |
| --- | --- |
| `gain: 0…58`, byte sin offset | `gain: −8…50`, dB mostrados por EVO Control |
| `{"db": 28}` enviaba byte 28 | Para conservar byte 28, enviar `{"db":20}` |
| Peticiones sin credencial | `Authorization: Bearer …` desde `api-token` o Preferencias |
| `/docs` | `/api/openapi.json` autenticado; `/api/info` anuncia las rutas reales |
| Errores de lectura convertidos a 0/false | 503; no guardar ni aplicar valores inventados |
| Demo y escrituras `mock` implícitas | No hay simulación en producción |
| Import/export con `path` del servidor | Subida/descarga del contenido JSON |
| `comando.json` | URL scheme o API de ciclo de vida autenticada |
| Launcher Python y launchd en paralelo | App nativa dueña del proceso; CLI como adaptador |
| `POST :3000/api/service/stop` | URL `evo16remote://stop` o `POST :3100/api/stop` opcional |

Los perfiles originales sin versión conservan sus bytes: se resta ocho al leer gain y se devuelve
formato v2 (`formatVersion: 2`, `gainEncoding: db`). Leerlos no los reescribe. Al exportar o guardar,
el resultado ya expresa dB reales. Los perfiles v2 no se vuelven a convertir.

Los perfiles deben contener 24 canales, estados booleanos y pares coherentes. Se rechazan perfiles
incompletos o corruptos antes de escribir al hardware. Si un archivo v1 fue editado manualmente
para contener dB reales, marcarlo explícitamente como v2; no es posible adivinar su intención.

La primera apertura de la app descarga los agentes `com.david.evo16-web`, `com.david.evo16-remote`
y `com.david.evo16-launcher`, si están instalados, y conserva sus plists renombrados `.deprecated`.
Una instancia v1 iniciada manualmente debe cerrarse de forma normal antes de iniciar v2; la app
nueva no mata procesos por coincidencia de nombre ni al dueño de un puerto ocupado.

La compilación crea un artefacto de revisión en `build/`. `--release` incluye el runtime y los
recursos; `--install` es el paso explícito para reemplazar la instalación del usuario. No se cambia
la app instalada al cambiar de rama o ejecutar pruebas.
