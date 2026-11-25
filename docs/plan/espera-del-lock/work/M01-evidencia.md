# M01 — Evidencia cruda

- **Base del lote:** `044e8ae`. **Commits de código y tests:** `72131f9` (tests en rojo), `7a7a10d` (implementación).
- **Intérprete de los gates:** Python 3.14.7 de pyenv-win (`python`). **Cobertura:** el mismo commit con el intérprete del `.venv` del checkout del orquestador (solo lectura), porque `coverage` no está instalado en el de pyenv; `tests/__init__.py` pone el `src/` del worktree primero en `sys.path`, así que se mide el código del worktree.

## Suite completa

Commit `7a7a10d`:

```
python -B -m unittest discover -s tests -t . > "$LOG/suite.log" 2>&1
Ran 1662 tests in 207.468s
FAILED (failures=10, skipped=9)
```

Los 10 fallos son exactamente los conocidos de la línea base: `test_ut_cnt_02_10`, `test_ut_cnt_03_01`, `test_ut_cnt_03_02`, `test_ut_cnt_03_10`, `test_ut_cw_07_01`, `test_tc_01_01`, `test_tc_02_07`, `test_tc_06_02`, `test_pkg_01_03`, `test_pkg_02_01`. 1662 = 1654 de la línea base + 8 casos nuevos. Ningún fallo nuevo.

Con el intérprete del `.venv` (corrida de cobertura), mismo commit: `Ran 1662 tests in 210.309s` / `OK (skipped=8)`.

## Grupos del milestone

```
python -B -m unittest discover -s tests -t . -k ut_cfg_07
Ran 8 tests in 0.055s
OK

python -B -m unittest discover -s tests -t . -k ut_cfg
Ran 22 tests in 0.815s
OK
```

Cada caso solo (`-k test_ut_cfg_07_0N`, N = 1..8): `Ran 1 test` / `OK`, los ocho al primer intento.

## Goldens

Ninguno.

## Tests nuevos

Clase `LockConfigTests` en `tests/test_config.py`; todos cubren RF-89 y AC-80 (esquema de `[lock]`):

- `test_ut_cfg_07_01_absent_section_and_missing_keys_use_the_defaults` — UT-CFG-07.01.
- `test_ut_cfg_07_02_range_bounds_are_accepted` — UT-CFG-07.02.
- `test_ut_cfg_07_03_invalid_retries_is_config_invalid_with_the_range` — UT-CFG-07.03.
- `test_ut_cfg_07_04_out_of_range_initial_delay_is_config_invalid_with_the_range` — UT-CFG-07.04.
- `test_ut_cfg_07_05_invalid_backoff_factor_is_config_invalid_with_the_range` — UT-CFG-07.05.
- `test_ut_cfg_07_06_unknown_key_in_lock_lists_the_allowed_keys` — UT-CFG-07.06.
- `test_ut_cfg_07_07_unknown_section_and_key_hints_name_lock_after_content` — UT-CFG-07.07.
- `test_ut_cfg_07_08_logging_config_ignores_an_invalid_lock_section` — UT-CFG-07.08.

Tests existentes cambiados: ninguno (ningún test comparaba literalmente los `hint` de sección o clave de primer nivel desconocida).

## Texto exacto de los `hint` nuevos o cambiados

Cambiados:

- Sección de primer nivel desconocida: `account blocks must be declared as [scope."<account-id>"], not as top-level tables; only [logging], [search], [new], [attachments], [content], [lock] and [scope.*] are allowed`.
- Clave de primer nivel desconocida: `only the [logging], [search], [new], [attachments], [content], [lock] and [scope.*] sections are allowed; see docs/config.example.toml`.

Nuevos (mensaje → `hint`):

- `[lock].retries must be an integer` → `set retries to an integer between 0 and 10`.
- `[lock].retries out of range: <v>` → `valid range: 0..10`.
- `[lock].initial_delay_ms must be an integer` → `set initial_delay_ms to an integer between 10 and 5000`.
- `[lock].initial_delay_ms out of range: <v>` → `valid range: 10..5000`.
- `[lock].backoff_factor must be a number` → `set backoff_factor to a number between 1 and 10`.
- `[lock].backoff_factor out of range: <v>` → `valid range: 1..10`.
- `unknown key [lock].<clave>` → `remove it; allowed keys in this table: retries, initial_delay_ms, backoff_factor`.
- `lock must be a TOML table` → `write it as a table, e.g. [lock] with its keys indented below`.

## `git diff --check` y `git diff --stat` contra `044e8ae`

`git diff --check 044e8ae`: sin salida, exit 0.

```
 docs/plan/espera-del-lock/M01-config-lock.md |   8 ++-
 src/mailquery/config.py                      | 102 +++++++++++++++++++++++++--
 tests/test_config.py                         | 100 ++++++++++++++++++++++++++
 3 files changed, 203 insertions(+), 7 deletions(-)
```

(Antes del commit de evidencia; este añade `work/M01-evidencia.md` y `work/M01-propuestas.md`.)

## Cobertura

```
coverage report --include=src/mailquery/config.py
Name                      Stmts   Miss Branch BrPart  Cover   Missing
src\mailquery\config.py     521     12    208      9  97.1%   296-297, 663, 679, 802->804, 814, 837->836, 905-906, 939-940, 1075, 1078, 1087
```

Todas las líneas sin cubrir son anteriores a M01; `_parse_number`, `_parse_lock`, `LockConfig` y las ramas nuevas están cubiertas.

## Riesgos, deuda, decisiones

- **D-06** aplicada: `[lock]` va después de `[content]` en los dos `hint` de primer nivel.
- **D-08** aplicada: `retries` e `initial_delay_ms` con `_parse_int` sin cambios de texto; `backoff_factor` con el lector nuevo `_parse_number` (entero o decimal, rechaza booleanos y cadenas), mismos textos con `a number`. `LockConfig.backoff_factor` es siempre `float` (`2` en TOML ⇒ `2.0`).
- Constantes nuevas públicas en `config.py`: `DEFAULT_/MIN_/MAX_LOCK_RETRIES`, `DEFAULT_/MIN_/MAX_LOCK_INITIAL_DELAY_MS`, `DEFAULT_/MIN_/MAX_LOCK_BACKOFF_FACTOR` y `LOCK_KEYS`, disponibles para M03 (ayuda) y M04.
- `load_logging_config` no cambia: solo lee `[logging]`, así que un `[lock]` inválido no la afecta (UT-CFG-07.08).
- Pendiente: nada de este milestone. Propuesta en `work/M01-propuestas.md`.
