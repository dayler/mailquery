# M03 — Evidencia cruda

Base del lote: `93fa726`. Rama: `feature/espera-del-lock-m03`. Intérprete: `.venv\Scripts\python.exe` del checkout principal (Windows). Logs en `~/dev/mailquery-logs/espera-del-lock/M03/`.

## Suite completa

Commit `c6b4fd0` (código y tests; los commits posteriores solo tocan `docs/plan/`):

```
python -B -m unittest discover -s tests -t . > "$LOG/suite.log" 2>&1
Ran 1685 tests in 228.251s
OK (skipped=8)
```

Línea base: 1674 tests, OK, 8 saltos. Diferencia: +11 tests (UT-CLI-15 ×9, UT-MCP-13 ×2), ningún fallo nuevo, los mismos 8 saltos. La ejecución bajo cobertura dio el mismo resultado (`Ran 1685 tests in 229.279s`, `OK (skipped=8)`).

## Grupos del milestone, solos

Cada caso solo (`-k test_ut_cli_15_0N`, N = 1..9; `-k test_ut_mcp_13_0N`, N = 1..2): `Ran 1 test ... OK`. Todos al primer intento salvo UT-CLI-15.06, que falló una vez por una aserción del test (esperaba el rango `0..10` en el detalle del chequeo `config` de `doctor`, que solo lleva el `message`); corregida la aserción, OK al segundo intento.

Tres corridas seguidas de cada grupo, sin fallos intermitentes:

```
python -B -m unittest discover -s tests -t . -k ut_cli_15   ->  Ran 9 tests in 7.739s / 7.800s / 7.750s, OK ×3
python -B -m unittest discover -s tests -t . -k ut_mcp_13   ->  Ran 2 tests in 3.678s / 3.707s / 3.738s, OK ×3
```

Gates por subconjunto:

```
-k ut_cli    ->  Ran 33 tests in 20.380s, OK
-k ut_mcp    ->  Ran 69 tests in 19.480s, OK
-k test_tc_  ->  Ran 46 tests in 14.167s, OK
```

Fase 2 (rojo): con `src/mailquery/cli.py` en la base, `-k ut_cli_15 -k ut_mcp_13` dio 10 fallos: .01, .02, .04 (los cinco comandos), .07, .08 y UT-MCP-13.01. Pasaban ya .03, .05, .06, .09 y UT-MCP-13.02, que verifican comportamiento que el cambio conserva. En .08 sin el cambio uno de los dos `new` dio `E_LOCKED`: los dos procesos sí coinciden.

## Tiempos medidos

Reloj `time.monotonic` (QueryPerformanceCounter, resolución 1e-07 s), desde la confirmación del proceso que retiene (o justo antes del comando):

- UT-CLI-15.01 (CLI en subproceso, lock retenido 2 s): 3.094 s hasta terminar con exit 0 (incluye el arranque del intérprete del subproceso).
- UT-CLI-15.02 (`retries = 2`, `initial_delay_ms = 100`, lock retenido 3 s): `E_LOCKED` a los 0.308 s (límites 0.3 y 2.0 s).
- UT-CLI-15.03 (`retries = 0`): `E_LOCKED` a los 0.005 s, sin ninguna pausa registrada.
- UT-CLI-15.06 (`doctor` con el lock retenido): 0.063, 0.054 y 0.035 s para sin `[lock]`, pausas máximas y `retries = 11`; ninguna pausa registrada y el lock construido sin `retry`.
- UT-CLI-15.08 (dos `new` a la vez): 1.032 y 0.815 s por proceso.
- UT-CLI-15.09 (archivo del lock no abrible): `E_PERMISSION` a los 0.004 s, sin pausas.
- UT-MCP-13.01 (servidor en proceso, lock retenido 2 s): 2.305 s hasta la respuesta.

## Ayuda raíz

`python -m mailquery --help`, desde `Configuration:` hasta `Lock:`:

```text
Configuration: ~/.mailquery/config.toml (optional; see README.md)
Lock: a busy run lock is retried 5 times, pausing 150 ms and doubling each time
      ([lock] in config.toml)
```

El texto fijado mide 103 columnas y la ayuda tiene un tope de 100; se parte en dos líneas. Desviación propuesta en `work/M03-propuestas.md`.

## Goldens

Ninguno.

## Tests nuevos

En `tests/test_cli.py`, clase `LockRetryCommandTests`:

- `test_ut_cli_15_01`: AC-79 (`search` espera 2 s y su salida es la de una ejecución sin espera, salvo `generated_at` y `scan.duration_ms`).
- `test_ut_cli_15_02`: AC-79 (reintentos agotados, `message` y `hint` literales con la ruta del lock, entre 0.3 y 2 s).
- `test_ut_cli_15_03`: AC-79 (`retries = 0`, hint de "Sin reintentos", sin pausas).
- `test_ut_cli_15_04`: AC-79 (los cinco comandos de datos construyen el lock con `config.lock`).
- `test_ut_cli_15_05`: AC-80 (`retries = 11` en cada comando de datos: `E_CONFIG_INVALID`, `0..10` en el `hint`, sin construir el lock).
- `test_ut_cli_15_06`: AC-79 y AC-80 (`doctor` con el lock retenido, sin pausa y sin `retry`, con tres configuraciones; con `retries = 11` el chequeo `config` informa el error).
- `test_ut_cli_15_07`: AC-80 (línea `Lock:` tras `Configuration:`).
- `test_ut_cli_15_08`: AC-79 (dos `new` a la vez: exit 0 y mensajes repartidos sin repetición).
- `test_ut_cli_15_09`: AC-79 (`E_PERMISSION` sin pausas cuando el archivo del lock es un directorio).

En `tests/test_mcp_server.py`:

- `LockBusyCallTests.test_ut_mcp_13_01`: AC-79 (llamada con el lock retenido 2 s: resultado de la CLI, `isError: false`, una sola ejecución).
- `LockConfigServerTests.test_ut_mcp_13_02`: AC-80 (`mcp serve` arranca con `retries = 11` y `search` devuelve `E_CONFIG_INVALID` con `isError: true`).

Tests cambiados: `_FakeLock` (y con él `_BusyLock`) acepta `retry` y `sleep`; `test_lock_busy_against_a_real_flock_exits_5` declara `[lock] retries = 0`. Ningún test comparaba la ayuda raíz entera.

## `git diff --check` y `git diff --stat` contra `93fa726`

`git diff --check 93fa726`: sin salida (exit 0).

```
 docs/plan/espera-del-lock/M03-cli-mcp.md         |  14 +-
 docs/plan/espera-del-lock/work/M03-evidencia.md  | nuevo
 docs/plan/espera-del-lock/work/M03-propuestas.md | nuevo
 src/mailquery/cli.py                             |   4 +-
 tests/test_cli.py                                | 309 +++++-
 tests/test_mcp_server.py                         | 150 ++++-
```

`src/mailquery/mcp_server.py` no cambia.

## Cobertura

```
python -B -m coverage run -m unittest discover -s tests -t .
python -m coverage report --include=src/mailquery/cli.py
src\mailquery\cli.py    1093     79    342     25  92.2%
```

La línea cambiada de `_run_command` (`with RunLock(home_path, config.lock):`) queda cubierta.

## Riesgos, deuda y decisiones

- D-07 aplicada: el lock lo retiene un subproceso de Python con `RunLock` que duerme; las pruebas sin espera envuelven el `RunLock` real con un `sleep` que registra cada pausa.
- D-10 aplicada: UT-CLI-15.01 y .08 lanzan la CLI en subprocesos con `_LAUNCHER`; UT-MCP-13.01 usa `serve` en proceso con un runner que cuenta las llamadas y ejecuta `cli.main` sobre el fixture.
- R-01 aplicada: medida con reloj monótono desde la confirmación del proceso que retiene. Margen ajustado en .02 (0.308 s frente al mínimo de 0.3 s): las pausas reales suman 300 ms y `time.sleep` no vuelve antes de tiempo, así que el mínimo no puede bajar de 0.3 s.
- UT-CLI-15.08 no puede forzar que los dos `new` coincidan; sin el cambio de `cli.py` coincidieron en la corrida de fase 2.
- Desviaciones propuestas al dueño: línea `Lock:` partida en dos y comparación sin `scan.duration_ms` (ver `work/M03-propuestas.md`).
- El chequeo `lock` de `doctor` ya construía `RunLock(home_path)` sin `retry`: no cambió.
