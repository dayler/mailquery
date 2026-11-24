# M02 — Evidencia cruda

Base del lote: `a283610`. Rama: `feature/espera-del-lock-m02`. Intérprete: `.venv\Scripts\python.exe` del checkout principal (Windows). Logs en `~/dev/mailquery-logs/espera-del-lock/M02/`.

## Suite completa

Commit `b1c558c`, bajo cobertura (una sola ejecución sirve de suite y de cobertura):

```
python -B -m coverage run -m unittest discover -s tests -t . > "$LOG/suite.log" 2>&1
Ran 1671 tests in 226.142s
OK (skipped=8)
```

Línea base: 1662 tests, OK, 8 saltos. Diferencia: +9 tests (UT-ST-08), ningún fallo nuevo, los mismos 8 saltos.

## Grupos del milestone, solos

```
python -B -m unittest discover -s tests -t . -k ut_st_08   ->  Ran 9 tests ... OK
python -B -m unittest discover -s tests -t . -k ut_st_01   ->  Ran 7 tests ... OK
```

Cada caso solo (`-k test_ut_st_08_0N`, N = 1..9): `Ran 1 test ... OK` los nueve, al primer intento. Fase 2 (rojo): `-k ut_st_08` dio 9 errores `TypeError: RunLock.__init__() got an unexpected keyword argument 'sleep'`. Tras la refactorización previa (fase 1), `-k ut_st_01`: 7 tests, OK, sin tocar los tests.

## Goldens

Ninguno.

## Tests nuevos

Clase `RunLockRetryTest` en `tests/test_state.py`; todos cubren AC-79 (RF-89):

- `test_ut_st_08_01_free_lock_is_taken_at_once`: lock libre, 1 intento, sin pausas.
- `test_ut_st_08_02_default_config_retries_five_times_then_e_locked`: 6 intentos, pausas y `E_LOCKED` con `message` y `hint` literales.
- `test_ut_st_08_03_pauses_are_capped_at_5000_ms`: tope por pausa.
- `test_ut_st_08_04_decimal_backoff_factor`: factor decimal.
- `test_ut_st_08_05_zero_retries_or_no_retry_make_a_single_attempt`: `retries = 0` y sin `retry`, `hint` de "Sin reintentos".
- `test_ut_st_08_06_lock_released_during_second_pause_is_taken_next`: lock liberado en la segunda pausa, 3 intentos.
- `test_ut_st_08_07_unopenable_lock_file_is_permission_error_without_pause`: la ruta del lock es un directorio; `E_PERMISSION` sin pausa.
- `test_ut_st_08_08_interrupted_pause_leaves_the_lock_free`: `KeyboardInterrupt` se propaga, el descriptor abierto queda cerrado (`os.fstat` falla) y otro `RunLock` toma el lock al liberarlo su dueño.
- `test_ut_st_08_09_pauses_are_truncated_to_whole_milliseconds`: truncado (D-09).

Ningún test duerme: todos pasan un `sleep` que registra la pausa en milisegundos enteros (`round(segundos * 1000)`), y el caso sin `retry` no llega a pausar. Los intentos se cuentan envolviendo `mailquery.state._lock_fd` con `mock.patch.object(..., wraps=...)`.

## Pausas observadas

- .02 (`LockConfig()` por defecto): `[150, 300, 600, 1200, 2400]`, 6 intentos.
- .03 (`retries = 3`, `initial_delay_ms = 1000`, `backoff_factor = 3`): `[1000, 3000, 5000]`, 4 intentos.
- .04 (`retries = 3`, `initial_delay_ms = 100`, `backoff_factor = 1.5`): `[100, 150, 225]`, 4 intentos.
- .09 (`retries = 3`, `initial_delay_ms = 10`, `backoff_factor = 1.25`): `[10, 12, 15]`, 4 intentos.

Comprobación adicional fuera de la suite: `backoff_factor = 1.1`, `initial_delay_ms = 100`, `retries = 4` da `[100, 110, 121, 133]` (121 exacto, sin bajar a 120).

## Texto exacto de los `hint` de `E_LOCKED`

- Reintentos agotados: `still held after <R> retries: <ruta>; retry later ([lock] in ~/.mailquery/config.toml sets the retries)`, con `<R>` = `retries` y `<ruta>` = `RunLock.path` (`<home>/locks/mailquery.lock`).
- Sin reintentos (`retries = 0` o sin `retry`): `wait for the running invocation to finish and retry (the harness should only retry exit code 5)`.
- `message` en ambos: `another mailquery run is already in progress`.

## `git diff --check a283610`

Sin salida (exit 0).

## `git diff --stat a283610` (antes de los archivos de `work/`)

```
 docs/plan/espera-del-lock/M02-reintento-runlock.md |  11 +-
 src/mailquery/state.py                             | 112 +++++++++++---
 tests/test_state.py                                | 166 +++++++++++++++++++++
 3 files changed, 268 insertions(+), 21 deletions(-)
```

Más `work/M02-evidencia.md` y `work/M02-propuestas.md` en el commit de cierre. Todo dentro del alcance de escritura.

## Cobertura

```
python -m coverage report --include="src/mailquery/state.py" -m
src\mailquery\state.py     366     16     92      6  95.2%   37, 188-189, 209-210, 256-258, 356, 364, 540, 607, 620, 744-749
```

`RunLock` (todas sus líneas) cubierto al 100 %. Las líneas 356 y 364 son las ramas POSIX de `_lock_fd` y `_unlock_fd`, no ejecutables en Windows; el resto de las no cubiertas queda fuera del código tocado.

## Decisiones aplicadas

- D-05: `sleep` recibe `pause_ms / 1000` segundos.
- D-09: la pausa se calcula como `int(initial_delay_ms * Fraction(str(backoff_factor)) ** (n - 1))`, exacta en racionales, truncada y topada a `LOCK_PAUSE_CAP_MS = 5000`.
- Interrupción: cualquier excepción de `sleep` (o de un intento) cierra el descriptor antes de propagarse; `_fd` sigue en `None`.
- Refactorización previa: `acquire` usa `_open_fd()` (apertura y `E_PERMISSION`) y `_try_lock(fd)` (un intento, devuelve el `OSError` o `None`); el `E_LOCKED` conserva su causa encadenada.

## Riesgos, deuda y pendientes

- Sin verificar en macOS/POSIX en este entorno: las ramas `fcntl` no se ejecutaron. El comportamiento del bucle no depende de la plataforma.
- `LockConfig` se importa solo bajo `TYPE_CHECKING`; `state` no depende de `config` en ejecución.
- Pendiente para M03: construir el lock de los comandos de datos con `config.lock` y el de `doctor` sin `retry`.
