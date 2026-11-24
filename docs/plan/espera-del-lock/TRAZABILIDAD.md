# Trazabilidad — espera-del-lock

**Tabla: AC → milestone → tests → estado**

| AC | Parte | Milestone | Tests | Estado |
|---|---|---|---|---|
| AC-79 | Lock retenido 2 s sin `[lock]`: `search` exit 0 con la salida de una ejecución sin espera | M03 | UT-CLI-15.01 | ⚪ |
| AC-79 | La misma llamada por MCP: `isError: false`, una sola ejecución | M03 | UT-MCP-13.01 | ⚪ |
| AC-79 | `retries = 2`, 100 ms, lock 3 s: `E_LOCKED` entre 300 ms y 2 s, con `message` y `hint` | M03 | UT-CLI-15.02 | ⚪ |
| AC-79 | `retries = 0`: `E_LOCKED` sin esperar, `hint` de "Sin reintentos" | M02, M03 | UT-ST-08.05, UT-CLI-15.03 | ⚪ |
| AC-79 | Pausas simuladas: por defecto, factor 3 con tope y factor 1.5 | M02 | UT-ST-08.02, .03, .04 | ⚪ |
| AC-79 | Archivo del lock que no se abre: `E_PERMISSION` sin esperar | M02, M03 | UT-ST-08.07, UT-CLI-15.09 | ⚪ |
| AC-79 | `doctor` con el lock retenido responde sin esperar | M03 | UT-CLI-15.06 | ⚪ |
| AC-79 | Dos `new` a la vez: los dos exit 0, cada mensaje en uno solo | M03 | UT-CLI-15.08 | ⚪ |
| AC-80 | Valores límite aceptados | M01 | UT-CFG-07.02 | 🟢 |
| AC-80 | Valores inválidos de las tres claves: `E_CONFIG_INVALID` con el rango | M01, M03 | UT-CFG-07.03, .04, .05, UT-CLI-15.05 | 🟡 |
| AC-80 | Clave desconocida (`max_delay_ms`) y `hint` de sección desconocida con `[lock]` | M01 | UT-CFG-07.06, .07 | 🟢 |
| AC-80 | `[lock]` que solo declara `retries` | M01 | UT-CFG-07.01 | 🟢 |
| AC-80 | `retries = 11`: chequeos `config` y `lock` de `doctor` | M03 | UT-CLI-15.06 | ⚪ |
| AC-80 | `retries = 11`: `mcp serve` arranca y `search` devuelve `E_CONFIG_INVALID` | M01, M03 | UT-CFG-07.08, UT-MCP-13.02 | 🟡 |
| AC-80 | `--help` muestra la línea `Lock:` | M03 | UT-CLI-15.07 | ⚪ |

Fuera de los AC: UT-ST-08.01, .06, .08 y .09 (primer intento, lock conseguido, interrupción y pausas sin decimales), UT-CLI-15.04 (los cinco comandos de datos) y DOC-19 (documentos consumidores), todos de RF-89.
