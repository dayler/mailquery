# M03 — Comandos, `doctor`, ayuda y MCP

- **Unidad:** `docs/changes/espera-del-lock.md` (la completa).
- **Oleada / lote:** 3 / 1. **Rama del lote:** `feature/espera-del-lock-lote-1`. **Rama del milestone:** `feature/espera-del-lock-m03`, creada desde el tip de la rama del lote.
- **Commit base:** (te lo da el orquestador al lanzar; lo copias aquí en tu primer commit). **Línea base de la suite:** (te la da el orquestador al lanzar, con los fallos y saltos conocidos; la copias aquí).
- **Depende de:** M01 (`config.lock`) y M02 (`RunLock(home, retry)`), ya integrados en la rama del lote. **Lo usan:** nadie.
- **ACs:** AC-x1 y AC-x2, las partes de comando, `doctor`, ayuda y MCP.

## Objetivo

Los comandos de datos toman el lock con los reintentos de `config.lock`; `doctor` hace un solo intento; la ayuda raíz nombra el reintento; las llamadas MCP heredan el comportamiento de su comando.

## Alcance

- `_run_command` construye `RunLock(home_path, config.lock)` para `search`, `new`, `show`, `attachment` y `mailboxes`.
- El chequeo `lock` de `doctor` construye el lock sin `retry`.
- La ayuda raíz añade, después de la línea `Configuration:`, la línea `Lock:` fijada por la unidad.
- Los dobles de `RunLock` de `tests/test_cli.py` aceptan el constructor nuevo.
- Tests de comando y de MCP de los dos AC. El servidor MCP no cambia de código: si un test muestra que hace falta, es una contradicción que vuelve al orquestador.

## Fuera de alcance

- Esquema de `[lock]` (M01), bucle de reintentos (M02), README y demás documentos (M04).
- `src/mailquery/mcp_server.py`.

## Alcance de escritura

`src/mailquery/cli.py`, `tests/test_cli.py`, `tests/test_mcp_server.py`, este archivo, `docs/plan/espera-del-lock/work/M03-handoff.md`, `docs/plan/espera-del-lock/work/M03-propuestas.md`, `docs/plan/espera-del-lock/work/M03-evidencia.md`.

## Especificación

Rangos de `docs/changes/espera-del-lock.md` en el commit `<commit de referencia>` (encabezado y líneas):

- "Lo que no cambia": 51-58.
- "Requerimientos", condiciones "Quién reintenta" (76), "Valor inválido" (82), "Errores previos" (85) y "Lock conseguido" a "MCP" (89-96).
- "Interfaz de los módulos": 113-117.
- "Criterios de aceptación": 130-134.

## Puntos de entrada en el código

Commit `a1e0977`; si la línea se movió, búscala por el nombre:

- `src/mailquery/cli.py`: texto de la ayuda raíz, línea `Configuration:` (138); `_run_command` (1093) y su `with RunLock(home_path)` (1147); chequeo `lock` de `doctor`, comentario `# lock` (2289).
- `tests/test_cli.py`: definición de `_FakeLock` y `_BusyLock` (116-141) y sus usos (799-953); lock retenido con `RunLock` real (819-827, 1664); `_LAUNCHER` y `PipeEncodingTests` (1959-2001), que lanzan la CLI en un subproceso sobre el fixture.
- `tests/test_mcp_server.py`: runners de prueba (52-77) y grupo UT-MCP-09 con el servidor real (823-927).

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **D-07.** Las pruebas con otro proceso reteniendo el lock usan un subproceso de Python que toma `RunLock` y duerme; las de pausas simuladas sustituyen `sleep`.
- **R-01 (mitigación).** Se mide con reloj monótono solo alrededor del comando y la medida arranca cuando el proceso que retiene confirma que tiene el lock.
- **D-10.** UT-CLI-15.01 y .08 lanzan la CLI en subprocesos sobre el fixture, con el mecanismo de `_LAUNCHER`. UT-MCP-13.01 usa el servidor en proceso con un runner que cuenta las ejecuciones y llama a `cli.main` sobre el fixture mientras un subproceso retiene el lock: el proceso hijo del servidor real no tiene acceso al fixture.

## Fases

**Tabla: Fases de M03**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Dobles de `RunLock` adaptados; suite verde sin cambios de `src/` | ⚪ |
| 2 | Tests de UT-CLI-15 y UT-MCP-13, en rojo los que dependen de `cli.py` | ⚪ |
| 3 | `_run_command`, chequeo `lock` de `doctor` y línea `Lock:` de la ayuda | ⚪ |
| 4 | Gates, datos crudos de evidencia y propuestas | ⚪ |

## Tests

Grupo nuevo `UT-CLI-15 — Reintento del lock en los comandos` en `tests/test_cli.py` (Requisitos: RF-x1, AC-x1, AC-x2); definición en `docs/tests/cli-config.md`, detrás de UT-CLI-14:

- **.01 P.** Lock retenido 2 s por otro proceso, sin `[lock]`: `search` termina con exit 0 tras liberarse y su salida es la de una ejecución sin espera salvo `generated_at`.
- **.02 N.** `retries = 2`, `initial_delay_ms = 100` y lock retenido 3 s: `E_LOCKED` (exit 5), no antes de 300 ms ni después de 2 s, con el `message` y el `hint` de reintentos agotados que fija la unidad, comparados literalmente con `2` y la ruta del lock.
- **.03 N.** `retries = 0` y lock retenido: `E_LOCKED` sin esperar, con el `hint` de "Sin reintentos", comparado literalmente.
- **.04 P.** `search`, `new`, `show`, `attachment` y `mailboxes` construyen el lock con `config.lock`.
- **.05 N.** Cada comando de datos con `retries = 11`: `E_CONFIG_INVALID` (exit 2) con el rango en el `hint`, sin tomar el lock.
- **.06 P.** `doctor` con el lock retenido: `held by another mailquery process` sin ninguna pausa, con cualquier `[lock]`; con `retries = 11`, el chequeo `config` informa el error y el chequeo `lock` responde sin esperar.
- **.07 P.** `mailquery --help` muestra, después de la línea `Configuration:`, la línea `Lock: a busy run lock is retried 5 times, pausing 150 ms and doubling each time ([lock] in config.toml)`.
- **.08 P.** Dos `new` lanzados a la vez, cada uno de menos de 2 s: los dos terminan con exit 0 y cada mensaje nuevo sale en uno solo.
- **.09 N.** El archivo del lock no se puede abrir: el comando da `E_PERMISSION` sin esperar.

Grupo nuevo `UT-MCP-13 — Lock ocupado en una llamada MCP` en `tests/test_mcp_server.py` (Requisitos: RF-x1, AC-x1, AC-x2); definición en `docs/tests/mcp-server.md`, detrás de UT-MCP-12:

- **.01 P.** Lock retenido 2 s por otro proceso, sin `[lock]`: `tools/call` de `search` devuelve el resultado de la CLI con `isError: false` y una sola ejecución del comando.
- **.02 N.** `[lock] retries = 11`: `mailquery mcp serve` arranca, y una llamada a `search` devuelve `E_CONFIG_INVALID` con `isError: true`.

Tests que cambian: los dobles `_FakeLock` y `_BusyLock`; `test_lock_busy_against_a_real_flock_exits_5`, que declara `[lock] retries = 0` para seguir fallando sin espera; y cualquier test que compare la ayuda raíz entera.

Comando: `python -B -m unittest discover -s tests -t . -k ut_cli_15` y `-k ut_mcp_13`.

## Documentación

La ayuda raíz de `mailquery --help` (en `cli.py`). Ninguna otra.

## Actualizaciones de la unidad

Propón al orquestador:

- Quitar `[pendiente]` de UT-CLI-15 y UT-MCP-13 en `docs/tests/cli-config.md` y `docs/tests/mcp-server.md`.
- Documentos consumidores `docs/tests/cli-config.md`, `docs/tests/mcp-server.md`, `docs/tests/state-backends.md`, `docs/tests/acceptance-matrix.md` y `docs/tests/TEST-CATALOG.md`: de `pendiente` a `actualizado` cuando sus definiciones no tengan marcas.
- Las filas de la tabla de conciliación de la unidad: de `pendiente` a `implementado`, al quedar el requerimiento completo en la rama del lote con sus tests y sus documentos consumidores.
- Cualquier desviación respecto de los textos fijados por la unidad, para que el dueño la apruebe.

## Gates

Los de `REGLAS.md`: suite completa, `-k ut_cli_15`, `-k ut_mcp_13`, `-k ut_cli`, `-k ut_mcp`, `-k test_tc_` (incluye los gates de solo lectura), cobertura de `src/mailquery/cli.py`, `git diff --check`.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de `REGLAS.md`, más: los tiempos medidos en UT-CLI-15.01, .02 y .03 y en UT-MCP-13.01, y la salida de `mailquery --help` desde `Configuration:` hasta `Lock:`.

## Definition of Done

- Los 9 casos de UT-CLI-15 y los 2 de UT-MCP-13 pasan solos y en la suite, tres corridas seguidas sin fallo intermitente.
- La suite completa no tiene fallos nuevos frente a la línea base.
- `src/mailquery/mcp_server.py` no cambia.
- `git diff --stat` solo muestra archivos del alcance de escritura.
- Ningún comentario de `src/` cita IDs ni documentos.
- Fases en 🟢; `work/M03-propuestas.md` y `work/M03-evidencia.md` confirmados en la rama.

## Registro de progreso

**Tabla: Registro de progreso de M03**

| Fecha | Fase | Nota |
|---|---|---|
