# M03 — Núcleo: ganchos opcionales, aviso de impresos y contexto de plugin

- **Unidad:** `docs/changes/id-corto-outlook.md` (contribuye; no la completa sola).
- **Oleada / lote:** 2 / 1. **Rama del lote:** `feature/id-corto-outlook-lote-1`. **Rama del milestone:** `feature/id-corto-outlook-m03`, creada desde el tip de la rama del lote (con M01 y M02 integrados).
- **Commit base:** (te lo da el orquestador al lanzar; lo copias aquí en tu primer commit). **Línea base de la suite:** (te la da el orquestador al lanzar, con los fallos y saltos conocidos; la copias aquí).
- **Depende de:** M01 (`PluginNativeIds`, `short_id`). **Lo usan:** M04 (llamada a `display_native_id`), M05 (aviso de impresos, `bind_home`, `MessageNotFound`).
- **ACs:** AC-65 (aviso en el núcleo), AC-69 (sin crear la caché en `mailboxes`, `doctor` y `--version` con plugins), AC-70 (contexto de plugin, ganchos, tope de 30 s).

## Objetivo

Dar al núcleo los mecanismos genéricos que la unidad pide sin saber nada del id corto: el aviso de mensajes impresos, la llamada a los ganchos opcionales, la base abierta en el contexto de cada plugin, `short_id` en la superficie pública, el home para los drivers internos y el "no encontrado" con hint del driver.

## Alcance

- `plugins/api.py`: `PluginContext.native_ids` (D-08); `OPTIONAL_OPERATIONS` y la función que llama a un gancho opcional si existe, a través de `call_driver`, con la validación de `display_native_id` (D-10).
- `plugins/__init__.py`: reexporta `short_id` (y lo añade a `__all__`).
- `cli.py`: un `PluginContext` por plugin, con `PluginNativeIds(home, <driver>)`, que se cierra en el mismo `finally` que cierra los drivers; el contexto de los chequeos de `doctor` (`_plugin_checks`) lleva `native_ids = None`; llamada a `bind_home(home)` en los drivers internos que lo tengan (D-06); `_run_attachment` captura `MessageNotFound` (D-07).
- `backends/base.py`: `MessageNotFound` con `hint` (D-07). Refactor sin cambio de comportamiento: ningún driver la lanza todavía.
- `search.py`: aviso de impresos en `run_search` (sin agrupar y con `--group-by`) y en `run_new` (también con `--peek`), con las reglas de D-17; `run_show` captura `MessageNotFound`.
- El plugin de prueba gana los dos ganchos opcionales, configurables, y un modo que usa `context.native_ids`.

## Fuera de alcance

- La opción `--show-native-id` y su uso de `display_native_id` en `show` (M04).
- Cualquier cambio en el driver `outlook` (M05, M06).
- Documentación consumidora, incluida `docs/INTERFACES.md` (M07).

## Alcance de escritura

- `src/mailquery/plugins/api.py`, `src/mailquery/plugins/__init__.py`, `src/mailquery/search.py`, `src/mailquery/cli.py`, `src/mailquery/backends/base.py`.
- `tests/fakes/plugin.py`, `tests/test_plugins.py`, `tests/test_multidriver.py` (solo si un test existente necesita adaptarse al contexto por plugin), `tests/test_cli.py`.
- Este archivo (fases y registro), `docs/plan/id-corto-outlook/work/M03-handoff.md`, `docs/plan/id-corto-outlook/work/M03-propuestas.md`.

## Especificación

Rangos de `docs/changes/id-corto-outlook.md` en el commit `384e5a8`:

- "Por qué el núcleo avisa de lo que imprime": líneas 37–48.
- "Lo que no cambia" (`plugin_api = 1`, ganchos opcionales): líneas 94–101.
- RF-80, condiciones "Uso desde un plugin", "Acceso de un plugin", "Errores dentro de un plugin" y "Quién convierte": líneas 121–123 y 140–141.
- "RF-82. Aviso de mensajes impresos": líneas 167–181.
- RF-83, condiciones "Cómo lo obtiene el núcleo" y "Validación": líneas 193–194.
- "Requisitos existentes que cambian", RF-36 y sección 21.3: líneas 204 y 212.
- "Arquitectura" (módulos, diagrama y ganchos): líneas 225–268.
- AC-65: línea 366. AC-69: línea 374 (frase final sobre `mailboxes`, `doctor` y `--version`). AC-70: línea 376.

## Puntos de entrada en el código

- `src/mailquery/plugins/api.py`: `METADATA_OPERATIONS` (línea 83), `PluginContext` (161), `_RESULT_VALIDATORS` (648), `call_driver` (674), `_DriverCallProxy` (718), `wrap_driver` (770), `METADATA_TIMEOUT_SECONDS` (71).
- `src/mailquery/plugins/__init__.py`: lista de reexportación (líneas 15–75).
- `src/mailquery/cli.py`: `_bind_command` (851), `_open_drivers` (887, contexto en 916), `_run_attachment` (1404), `_attachment_not_found` (1369).
- `src/mailquery/search.py`: `run_search` (517; retornos de `--count`, agrupado y normal hacia 656, 669 y 713), `_grouped_search` (1937), `run_new` (723; escritura del estado hacia 870–885), `run_show` (901), `_message_not_found` (2962).
- `src/mailquery/backends/base.py`: `ExcludedStoreError` (línea 31) como modelo de `MessageNotFound`.
- `src/mailquery/uid.py`: `is_valid_native_id` (línea 59).
- `tests/fakes/plugin.py`: `FakePluginBackend` (112), `plugin_factory` (350).

## Refactorizaciones previas

- **`MessageNotFound` en `backends/base.py`** con su captura en `run_show` y `_run_attachment`. Justificación: el driver `outlook` necesita dar otro hint en un caso de "no encontrado" (RF-81) sin que el núcleo sepa por qué; hoy el hint de `show` es un atributo fijo del backend y el de `attachment` es fijo en la CLI. Alcance: una clase y dos `except`. Conserva el comportamiento: nadie la lanza hasta M05; un test sin ID la prueba con un backend inyectado.

## Decisiones aplicables

- **D-06.** `bind_home(home)` es un método interno opcional de los drivers internos; `_open_drivers` lo llama si existe, como `bind_command`.
- **D-07.** `MessageNotFound(LookupError)` con `hint`, solo para drivers internos; `run_show` y `_run_attachment` responden con su error de "no encontrado" actual (mismo código, mensaje y formato del uid) y ese hint. Si un plugin externo la lanzara, `call_driver` la convierte en `E_PLUGIN_FAILED`.
- **D-08.** `PluginContext.native_ids: PluginNativeIds | None = None`; un contexto por plugin; apertura perezosa; cierre en el `finally` de los drivers; `None` en los chequeos de `doctor`.
- **D-10.** `OPTIONAL_OPERATIONS` separado de `METADATA_OPERATIONS`; llamada solo si el driver tiene el gancho, por `call_driver`; el resultado de `printed_messages` se ignora; el de `display_native_id` de un plugin externo se valida con `is_valid_native_id` y, si no cumple, `E_PLUGIN_FAILED` (exit 3); el de un driver interno no se valida.
- **D-17.** Aviso en `run_search` justo antes de devolver (sin agrupar y agrupado) y en `run_new` antes de escribir el estado, también con `--peek`; uno por driver con filas; `row["uid"]` sin repetir, en el orden de la respuesta; `--count` no avisa; una respuesta sin mensajes no avisa.

## Fases

**Tabla: Fases de M03**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | `MessageNotFound` y sus capturas; test sin ID en `tests/test_cli.py` | ⚪ |
| 2 | `OPTIONAL_OPERATIONS`, llamada a ganchos opcionales y validación de la forma nativa; UT-PL-06.08 | ⚪ |
| 3 | `PluginContext.native_ids`, un contexto por plugin, `short_id` en `mailquery.plugins`, `bind_home`; UT-PL-05 | ⚪ |
| 4 | Aviso de impresos en `search` y `new`; plugin de prueba con ganchos; UT-PL-06.01–.07 | ⚪ |
| 5 | Suite completa, cobertura, diff, evidencia cruda | ⚪ |

## Tests

Grupos nuevos en `tests/test_plugins.py`, con el plugin de prueba y el store de prueba de Apple Mail como driver nativo. Las definiciones ya están `[pendiente]` en `docs/tests/plugins.md`.

#### UT-PL-05 — Contexto de plugin con la caché de ids nativos

Requisitos: RF-80, RF-36, AC-69, AC-70

**Tabla: Casos de UT-PL-05**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El plugin recibe en su `PluginContext` la base abierta para su driver; con ella asigna en `query`, registra en el aviso y resuelve en `find_message`: `show` de un uid impreso por `search` devuelve su mensaje. |
| .02 | N | El plugin no ve ni cambia las filas de otro driver ya presentes en `cache.db`; dos plugins declarados reciben accesos distintos, cada uno a su driver. |
| .03 | P | El registro funciona dentro del gancho de aviso, que corre vigilado por el tope de 30 s en un hilo trabajador; al terminar el comando, el acceso está cerrado y `cache.db` se puede borrar. |
| .04 | P | `from mailquery.plugins import short_id` funciona y es la función de la librería, importando primero `mailquery.plugins` o primero `mailquery.native_ids`; `PLUGIN_API` sigue siendo 1. |
| .05 | N | Con un plugin declarado, `mailboxes`, `doctor` y `--version` no crean `~/.mailquery/db/` ni `cache.db`. |
| .06 | N | Durante `search`, el `printed_messages` del plugin registra en una base bloqueada, sin permiso o inválida, sin capturar el error ⇒ `E_CLIENT_BUSY` (exit 5), `E_PERMISSION` (exit 3) o `E_PLUGIN_FAILED` (exit 3), sin mensajes en la salida. |

#### UT-PL-06 — Ganchos opcionales y aviso de mensajes impresos

Requisitos: RF-82, RF-83, RF-36, AC-65, AC-70

**Tabla: Casos de UT-PL-06**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `printed_messages` se llama una vez por driver con los `<native_id>` de sus filas impresas, sin repetir y en el orden de la respuesta, en `search`, `search --group-by from`, `new` y `new --peek`. |
| .02 | N | No se llama en `search --count`, en una respuesta sin mensajes de `search` o de `new`, ni en `show`, `attachment`, `mailboxes` y `doctor`. |
| .03 | N | Los mensajes leídos que no van en la respuesta (más allá de `--limit` o descartados por un filtro) no van en la lista, ni un uid que solo aparece en el texto de un warning (el plugin de prueba lo pone en el warning del cuerpo de un mensaje impreso). |
| .04 | P | Un plugin sin ganchos funciona igual y no recibe nada; lo que devuelve `printed_messages` no cambia la respuesta; `plugin_api` sigue en 1. |
| .05 | N | Un `printed_messages` que lanza `PluginError` con `reason` o una excepción cualquiera ⇒ el error mapeado de RF-50 (`E_CLIENT_BUSY`, `E_PLUGIN_FAILED`…); la salida no tiene mensajes y `new` no escribe `state.json`. |
| .06 | N | Un `printed_messages` que supera el tope de 30 s (acortado en el test) ⇒ `E_CLIENT_TIMEOUT`, sin mensajes y sin escribir estado. |
| .07 | P | Con dos plugins declarados, cada uno recibe solo los `<native_id>` de sus filas. |
| .08 | N | La llamada del núcleo a `display_native_id`: sin gancho no llama a nada; con gancho devuelve su valor; un valor que no cumple las reglas de un `<native_id>` (vacío, con `/`, con `..`, con espacio) ⇒ `E_PLUGIN_FAILED` (exit 3). |

Test sin ID en `tests/test_cli.py`: un backend inyectado como driver nativo (interno) cuyo `find_message` lanza `MessageNotFound("<hint>")` hace que `show` y `attachment` respondan con su error de "no encontrado" actual (código, mensaje y exit) y ese hint; sin la excepción, los textos no cambian.

Tests que cambian: los de `tests/test_plugins.py` que comparen la lista exacta de `mailquery.plugins.__all__` o la forma de `PluginContext`, si existen, se amplían con `short_id` y `native_ids`.

Comandos:

- `$PY -B -m unittest discover -s tests -t . -k ut_pl_05 > "$LOG/grupo-ut_pl_05.log" 2>&1` y lo mismo con `-k ut_pl_06`.
- Suite completa: la de `protocolo.md`.

## Documentación

Ninguna fuera del código (la documentación de plugins de `docs/INTERFACES.md` la hace M07). Docstrings en inglés que describen los ganchos opcionales y el campo nuevo del contexto.

## Actualizaciones de la unidad

Las aplica el orquestador al cerrar el milestone.

- **Conciliación:** según `trazabilidad.md`, aporta a RC-06, RC-09, RC-10, RC-18, RC-26, RC-28. Ninguna fila cambia de estado al cerrar este milestone: el orquestador las pasa todas a `implementado` en F4.
- **Hallazgo para RC-10:** el orquestador añade a su "Qué cambia" la excepción de "no encontrado" de `backends/base.py`, el home de los drivers internos y el contexto de plugin por driver (ver `trazabilidad.md`).
- **Documentos consumidores:** ninguno.
- **Checklist:** ninguno cambia.
- **Desviaciones:** ninguna prevista.

## Gates

- `-k ut_pl_05` y `-k ut_pl_06` verdes; el test sin ID de `MessageNotFound` verde.
- Suite completa sin fallos nuevos frente a la línea base.
- `git diff --check` limpio; `git diff --stat` dentro del alcance.
- Cobertura de `plugins/api.py`, `search.py` y `cli.py` informada (o "not run"); la puerta es el 85 % total de la CI.

## Datos crudos de evidencia

Los de `protocolo.md`, más la lista de puntos de `search.py` donde se avisa (función y línea).

## Definition of Done

- Los mecanismos de D-06, D-07, D-08, D-10 y D-17 existen y ningún comando cambia de salida sin plugins con ganchos.
- UT-PL-05 y UT-PL-06 pasan; el test de `MessageNotFound` pasa; suite sin fallos nuevos.
- Fases en 🟢, registro al día, evidencia cruda escrita.

## Registro de progreso

**Tabla: Registro de progreso de M03**

| Fecha | Fase | Nota |
|---|---|---|
