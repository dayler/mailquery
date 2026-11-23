# M01 — Eventos de log estructurados (refactor)

- **Unidad:** `docs/changes/servidor-mcp.md` (contribuye y no la completa sola).
- **Oleada / lote:** 1 / 1. **Rama del lote:** `feature/servidor-mcp-lote-1`. **Rama del milestone:** `feature/servidor-mcp-m01`, creada desde el tip de la rama del lote.
- **Commit base:** `f866be8`. **Línea base de la suite:** `Ran 1562 tests`, `failures=3`, `skipped=7`. Los tres fallos son del entorno de este equipo (SMOKE contra Apple Mail real: cambia el `mtime` de `~/.mailquery/tmp`); el resto de la línea base está verde.
- **Depende de:** nada. **Lo usan:** M02 (`log_event` para los eventos del servidor), M04 (campos estructurados para el formateador JSON).
- **ACs:** ninguno directamente; prepara AC-77 (RF-88: "Los valores salen del evento, no de partir la línea de texto").

## Objetivo

Que cada evento del log del núcleo lleve sus campos `clave=valor`, su texto libre y su traceback como datos del registro, sin cambiar ni un byte del log de texto actual.

## Alcance

- Añadir `log_event` a `logging_setup.py` con la firma y el comportamiento de DP-02.
- Migrar a `log_event` todas las llamadas de log del núcleo: `cli.py` (eventos `start`, `end` de los comandos, de `attachment` y de `doctor`, `error`, `internal_error`, y la línea del store de `_log_backend_connection`), `logging_setup.py` (`logging initialized`), `store.py` (dos líneas), `accounts.py` (dos líneas) y `backends/outlook_com.py` (`event=watchdog_error`).
- En `_log_error`, el traceback de un `E_INTERNAL` viaja como `traceback=` de `log_event`; la línea de texto resultante es idéntica a la actual.
- Test de regresión sin ID que fija, para cada llamada migrada, la línea de texto que producía el código base.

## Fuera de alcance

- El formato JSON, la clave `[logging].json` y los `hint` con el archivo activo: M04.
- Cualquier cambio de nivel, de logger, de campos o de texto de un evento.
- Los logs propios de los plugins.

## Alcance de escritura

- `src/mailquery/logging_setup.py`, `src/mailquery/cli.py`, `src/mailquery/store.py`, `src/mailquery/accounts.py`, `src/mailquery/backends/outlook_com.py`, `tests/test_logging.py`.
- `docs/plan/servidor-mcp/M01-eventos-log.md`, `docs/plan/servidor-mcp/work/M01-handoff.md`, `docs/plan/servidor-mcp/work/M01-propuestas.md`.

## Especificación

Rangos de `docs/changes/servidor-mcp.md` en el commit de la unidad aprobada (F0 anota aquí el commit; si las líneas se movieron, busca el encabezado):

- `**RF-88. Log en formato JSON.**`, líneas 168–197: solo las condiciones "Campos" y "Tipos de los valores de `fields`", para saber qué datos debe llevar cada evento.
- `### Decisiones de diseño de la unidad`, líneas 60–72: la viñeta del log JSON (`fields`, `-`, `message`).

## Puntos de entrada en el código

En `f868036`; si la línea se movió, búscala por el nombre:

- `src/mailquery/logging_setup.py`: `LOG_FORMAT` (16), `setup_logging` (58, línea `logging initialized` en 90), `get_logger` (98).
- `src/mailquery/cli.py`: `_run_command` (990; `event=start` en 1071, `event=internal_error` en 1103, `event=end` en 1121 y 1133), `_log_backend_connection` (1564; línea del store en 1577), `_emit_doctor_report` (1770; `event=end command=doctor` en 1817), `_log_error` (2581).
- `src/mailquery/store.py`: `_log` (64) y sus usos (246, 849).
- `src/mailquery/accounts.py`: `_log` (62) y sus usos (258, 260).
- `src/mailquery/backends/outlook_com.py`: `event=watchdog_error` (445).
- `tests/test_logging.py`: `_LogHomeTestCase` (45), `FormatTests` (129), `ContentTests` (182).

## Refactorizaciones previas

Este milestone es la refactorización. **Por qué:** RF-88 exige que los valores de `fields` salgan del evento y no de partir la línea de texto; hoy los eventos son cadenas de formato con `%s`, de las que no se pueden recuperar los campos con seguridad (un `message` con espacios, `checks=%d/%d`, el traceback dentro del mensaje). **Alcance acotado:** solo las 14 llamadas de log del núcleo y una función nueva. **Comportamiento:** el log de texto queda idéntico byte a byte; lo comprueban UT-LOG-03, UT-LOG-04 y el test de regresión de la fase 1.

## Decisiones aplicables

- **DP-02. API de eventos de log estructurados (M01).** `logging_setup.log_event(logger, level: int, fields: Sequence[tuple[str, object]], *, text: str | None = None, traceback: str | None = None, exc_info: bool = False) -> None`. La línea de texto es `<text> <k1>=<v1> <k2>=<v2>…` (sin `<text> ` si no hay texto; cada valor con su representación de texto), seguida de un salto de línea y el traceback si lo hay, exactamente como las llamadas actuales. Los campos, el texto y el traceback viajan como datos del registro de log para el formateador JSON, junto con el `run` que hoy aporta el adaptador de `get_logger`; el adaptador de `get_logger` sustituye los datos extra del llamador por los suyos en todas las versiones soportadas (la opción `merge_extra` solo existe desde Python 3.13 y no se puede usar en 3.11 y 3.12), así que `log_event` debe conservar los dos (el `run` y los del evento) sin depender de ella. Todas las llamadas de log del núcleo pasan a `log_event`; las que hoy registran una excepción pasan a `exc_info=True`. El valor `checks=<pasados>/<total>` de `doctor` es un único campo de texto.

Margen tuyo: el nombre de las claves de `extra` (prefijadas, para no chocar con atributos de `LogRecord`) y si `log_event` acepta `Logger` y `LoggerAdapter`. Anótalo en `work/M01-propuestas.md`.

## Fases

**Tabla: Fases de M01**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Antes de tocar nada, escribir el test de regresión que captura, con el código base, la línea de texto de cada una de las 14 llamadas (todas las ramas: `attachment`, `doctor`, error con y sin traceback, `internal_error` con `exc_info`, store, cuentas, Outlook vigilado) y comprobar que pasa en el commit base | 🟢 |
| 2 | `log_event` en `logging_setup.py`; migrar `logging_setup.py`, `store.py`, `accounts.py` y `outlook_com.py`; test de regresión verde | 🟢 |
| 3 | Migrar `cli.py` (incluido `_log_error` con `traceback=`); test de regresión, UT-LOG-03 y UT-LOG-04 verdes; búsqueda de llamadas de log de la sección Tests sin resultados fuera de `log_event` | 🟢 |
| 4 | Suite completa, cobertura de los módulos tocados, evidencia cruda y propuestas | 🟢 |

## Tests

- Sin grupos nuevos con ID. Test de regresión nuevo en `tests/test_logging.py`, con nombre descriptivo (por ejemplo `test_log_event_keeps_the_text_line_of_every_core_event`), que compara cada línea con su texto esperado literal.
- Tests que deben seguir verdes sin cambiar: UT-LOG-01 a UT-LOG-04 (`tests/test_logging.py`, `tests/test_cli.py`), UT-MD-06, UT-ERR-02, UT-ATC-08 y UT-OL-ATT-04 (logs de drivers y adjuntos).
- Búsqueda de llamadas de log (fase 3), que no incluye `registry.info(driver)`, que no es de log:

  ```sh
  grep -rnE "(logger|_log\(\)|get_logger\([^)]*\))\.(info|warning|error|debug|exception)\(" src/mailquery
  ```

- Comandos: `python -B -m unittest discover -s tests -t . -k test_logging` y la suite completa de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md).

## Documentación

Ninguna: el log de texto no cambia. `docs/INTERFACES.md` documenta `log_event` en M06.

## Actualizaciones de la unidad

Ninguna fila de conciliación ni documento consumidor cambia de estado por este milestone. Las aplica el orquestador si las propones.

## Gates

- Suite completa sin fallos nuevos frente a la línea base.
- `python -B -m unittest discover -s tests -t . -k test_logging` verde.
- `git diff --check` limpio y `git diff --stat` solo con los archivos del alcance de escritura.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md), más: la lista de las llamadas migradas (archivo, función y evento) y la salida de la búsqueda de la fase 3.

## Definition of Done

- `log_event` existe con la firma de DP-02 y todas las llamadas de log del núcleo la usan.
- El test de regresión pasa en el commit base y en el tip del milestone con las mismas líneas esperadas.
- UT-LOG-01 a UT-LOG-04 verdes sin cambios en sus aserciones.
- Suite completa sin fallos nuevos; `git diff --check` limpio; diff dentro del alcance.
- Fases en 🟢, evidencia cruda y propuestas entregadas.

## Registro de progreso

**Tabla: Registro de progreso de M01**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | Test de regresión añadido antes del refactor; 13 casos verdes en `f866be8` (el evento de `setup_logging` a nivel `debug` no llegaba al archivo en la base por un `LogRecord` sin `run_id`; su caso queda en `StructuredSetupEventTests` y pasa tras el refactor). |
| 2026-11-23 | 2 | `log_event` con la firma de DP-02; migrados `logging_setup.py`, `store.py`, `accounts.py` y `outlook_com.py`; el adaptador conserva `run_id` y añade los datos del evento. |
| 2026-11-23 | 3 | Migrado `cli.py`; `_log_error` pasa el traceback como datos y la línea de texto no cambia; la búsqueda no encuentra llamadas directas. |
| 2026-11-23 | 4 | Suite completa y cobertura en la evidencia. |
