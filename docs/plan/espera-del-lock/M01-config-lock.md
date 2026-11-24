# M01 — Sección `[lock]` de la configuración

- **Unidad:** `docs/changes/espera-del-lock.md` (contribuye y no la completa sola).
- **Oleada / lote:** 1 / 1. **Rama del lote:** `feature/espera-del-lock-lote-1`. **Rama del milestone:** `feature/espera-del-lock-m01`, creada desde el tip de la rama del lote.
- **Commit base:** `044e8ae` (tip de `feature/espera-del-lock-lote-1`). **Línea base de la suite:** en `41fc5b2` (mismo código), 1654 tests, 10 fallos, 9 saltos. Fallos conocidos del entorno local, no del código: `test_ut_cnt_02_10`, `test_ut_cnt_03_01`, `test_ut_cnt_03_02`, `test_ut_cnt_03_10`, `test_ut_cw_07_01` (falta el backend de hojas de estilo), `test_tc_01_01`, `test_tc_02_07`, `test_tc_06_02`, `test_pkg_01_03`, `test_pkg_02_01` (metadatos del paquete instalado en 2.0.1).
- **Depende de:** nada. **Lo usan:** M02 (`LockConfig`), M03 (`config.lock`), M04 (valores por defecto).
- **ACs:** AC-80, la parte del esquema de `[lock]`.

## Objetivo

`load_config` acepta y valida la sección opcional `[lock]` y la expone como `Config.lock`.

## Alcance

- `LockConfig`, `Config.lock` y la lectura de `[lock]`, como fijan los rangos citados en "Especificación".
- `retries` e `initial_delay_ms` se leen con `_parse_int`, cuyos textos no cambian. `backoff_factor` necesita un lector nuevo de número entero o decimal que rechaza booleanos y cadenas (D-08).
- Los `hint` de sección y de clave de primer nivel desconocida nombran `[lock]` después de `[content]`.
- `load_logging_config` sigue devolviendo la configuración del log con un `[lock]` inválido.

## Fuera de alcance

- Reintentos de `RunLock` (M02). Uso de `config.lock` en los comandos, `doctor`, ayuda y MCP (M03). README, ejemplo de configuración y documento de interfaces (M04).

## Alcance de escritura

`src/mailquery/config.py`, `tests/test_config.py`, este archivo, `docs/plan/espera-del-lock/work/M01-handoff.md`, `docs/plan/espera-del-lock/work/M01-propuestas.md`, `docs/plan/espera-del-lock/work/M01-evidencia.md`.

## Especificación

Rangos de `docs/changes/espera-del-lock.md` en el commit `e3670c7` (encabezado y líneas):

- "Requerimientos", condiciones "Sección" a "Sección admitida": 77-84.
- "Configuración": 100-111.
- "Interfaz de los módulos": 113-117.
- "Criterios de aceptación", AC-80: 134.

## Puntos de entrada en el código

En `src/mailquery/config.py`, commit `a1e0977`; si la línea se movió, búscala por el nombre:

- `_TOP_LEVEL_KEYS` (82), `ContentConfig` (138), `Config` (166), `load_logging_config` (280), `_parse_config` (305), `_unknown_top_level` (329), `_unknown_key` (355), `_parse_int` (363), `_parse_content` (538).
- En `tests/test_config.py`: `ServerLoggingConfigTests` (692), `ContentConfigTests` (1354), como modelo de un grupo de sección.

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **D-06.** En los `hint` de sección o clave de primer nivel desconocida, `[lock]` va después de `[content]`.
- **D-08.** Forma de los `hint` de un valor inválido: fuera de rango, `valid range: <mín>..<máx>`; de otro tipo, `set <clave> to an integer between <mín> and <máx>` (para `backoff_factor`, `a number` en lugar de `an integer`). Las dos formas llevan el rango válido.

## Fases

**Tabla: Fases de M01**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Tests del grupo UT-CFG-07, en rojo | 🟢 |
| 2 | `LockConfig`, `Config.lock`, lectura y validación de `[lock]`, `hint` con `[lock]` | 🟢 |
| 3 | Gates, datos crudos de evidencia y propuestas | ⚪ |

## Tests

Grupo nuevo `UT-CFG-07 — [lock]` en `tests/test_config.py` (Requisitos: RF-89, AC-80); definición en `docs/tests/cli-config.md`, detrás de UT-CFG-06:

- **.01 P.** Sin `[lock]`: `retries = 5`, `initial_delay_ms = 150`, `backoff_factor = 2`. Con una sección que solo declara `retries`, las otras dos claves valen su valor por defecto.
- **.02 B.** Se aceptan `retries` 0 y 10; `initial_delay_ms` 10 y 5000; `backoff_factor` 1, 1.5 y 10.
- **.03 N.** `retries` igual a `-1`, `11`, `"5"`, `5.0` o `true` ⇒ `E_CONFIG_INVALID` (exit 2) con el rango 0 a 10 en el `hint`, en la forma de D-08.
- **.04 N.** `initial_delay_ms` igual a `9` o `5001` ⇒ `E_CONFIG_INVALID` con `valid range: 10..5000` en el `hint`.
- **.05 N.** `backoff_factor` igual a `0.5`, `11`, `"2"` o `true` ⇒ `E_CONFIG_INVALID` con el rango 1 a 10 en el `hint`, en la forma de D-08.
- **.06 N.** La clave `max_delay_ms` en `[lock]` ⇒ `E_CONFIG_INVALID` con `retries`, `initial_delay_ms` y `backoff_factor` en el `hint`.
- **.07 N.** Los `hint` de sección desconocida y de clave de primer nivel desconocida nombran `[lock]`.
- **.08 P.** `load_logging_config` con `[lock] retries = 11` devuelve la configuración del log sin fallar.

Tests que cambian: los que comparan literalmente los `hint` de sección o clave de primer nivel desconocida, si los hay (búscalos por `[content] and`).

Comando: `python -B -m unittest discover -s tests -t . -k ut_cfg_07`.

## Documentación

Ninguna.

## Actualizaciones de la unidad

Ninguna fila ni documento consumidor queda completo con este milestone. Propón quitar `[pendiente]` de UT-CFG-07 en `docs/tests/cli-config.md`.

## Gates

Los de `REGLAS.md`: suite completa, `-k ut_cfg_07`, `-k ut_cfg` (el prefijo entero), cobertura de `src/mailquery/config.py`, `git diff --check`.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de `REGLAS.md`, más: el texto exacto de los `hint` nuevos o cambiados.

## Definition of Done

- Los 8 casos de UT-CFG-07 existen y pasan solos y en la suite.
- La suite completa no tiene fallos nuevos frente a la línea base.
- `git diff --stat` solo muestra archivos del alcance de escritura.
- Ningún comentario de `src/` cita IDs ni documentos.
- Fases en 🟢; `work/M01-propuestas.md` y `work/M01-evidencia.md` confirmados en la rama.

## Registro de progreso

**Tabla: Registro de progreso de M01**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-24 | 1 | Ocho casos de UT-CFG-07 en `LockConfigTests`; en rojo por la falta de `LockConfig` (ImportError). |
| 2026-11-24 | 2 | `LockConfig`, `Config.lock`, `_parse_lock` y `_parse_number`; `hint` de primer nivel con `[lock]` tras `[content]`. Los 8 casos pasan solos al primer intento. |
