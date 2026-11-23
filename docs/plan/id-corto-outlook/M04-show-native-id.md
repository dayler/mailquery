# M04 — `show --show-native-id` en el núcleo

- **Unidad:** `docs/changes/id-corto-outlook.md` (contribuye; no la completa sola).
- **Oleada / lote:** 3 / 2. **Rama del lote:** `feature/id-corto-outlook-lote-2`. **Rama del milestone:** `feature/id-corto-outlook-m04`, creada desde el tip de la rama del lote (con el lote 1 integrado).
- **Commit base:** (te lo da el orquestador al lanzar; lo copias aquí en tu primer commit). **Línea base de la suite:** (te la da el orquestador al lanzar, con los fallos y saltos conocidos; la copias aquí).
- **Depende de:** M03 (llamada a `display_native_id` con validación). **Lo usan:** M06 (prueba de la opción con Outlook), M07 (ayuda copiada en los README).
- **ACs:** AC-68 (opción, presentación, rechazo en otros comandos, forma nativa inválida de un plugin, macOS sin cambios), AC-70 (plugin sin el gancho).

## Objetivo

Añadir a `show` la opción de depuración `--show-native-id`, que solo cambia el texto de `message.uid` cuando el driver tiene el gancho `display_native_id`.

## Alcance

- Opción `--show-native-id` en el parser de `show`, con su ayuda de depuración (RF-73); ningún otro subcomando la acepta (con el parser actual, una opción desconocida ya es `E_USAGE`, exit 2, antes de crear el home).
- `run_show` recibe la opción y, al final, sustituye `message.uid` por `<driver>:<forma nativa>` con la llamada de M03 (D-16). Si el driver no tiene el gancho, la salida no cambia.
- `_execute` pasa la opción a `run_show` en sus dos llamadas.
- El docstring de `run_show` deja de decir que `show` nunca escribe: `show` puede escribir en la caché de ids nativos a través de un driver que la usa.

## Fuera de alcance

- El gancho `display_native_id` del driver `outlook` (M05) y su prueba de punta a punta (M06).
- README y skill (M07).

## Alcance de escritura

- `src/mailquery/cli.py`, `src/mailquery/search.py`.
- `tests/test_show_native_id.py` (nuevo).
- Este archivo (fases y registro), `docs/plan/id-corto-outlook/work/M04-handoff.md`, `docs/plan/id-corto-outlook/work/M04-propuestas.md`.

## Especificación

Rangos de `docs/changes/id-corto-outlook.md` en el commit `384e5a8`:

- "RF-83. `--show-native-id` en `show`": líneas 183–198.
- "Requisitos existentes que cambian", RF-73: línea 209.
- "Comando `show` y errores", figura de formas del uid: líneas 319–326.
- "Cambios visibles en 3.0.0", opciones de `show`: líneas 341–346.
- AC-68: línea 372. AC-70: línea 376.
- "Decisiones", entrada "¿Se puede ver el id nativo en la salida?": línea 408.

## Puntos de entrada en el código

- `src/mailquery/cli.py`: `_SHOW_EPILOG` (línea 254), parser de `show` en `build_parser` (líneas 584–606), `_execute` (1109; llamadas a `run_show` hacia 1172 y 1183), `_ArgumentParser.error` (326).
- `src/mailquery/search.py`: `run_show` (901), `_message_metadata` (2356; formato del uid en 2372).
- `src/mailquery/plugins/api.py`: la función de M03 que llama a un gancho opcional (búscala por `OPTIONAL_OPERATIONS`).
- `tests/fakes/plugin.py`: el gancho `display_native_id` configurable que añadió M03.

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **D-10.** La forma nativa se pide con la función de M03; un valor que no cumple las reglas de un `<native_id>` ⇒ `E_PLUGIN_FAILED` (exit 3).
- **D-16.** `run_show` arma el mensaje igual que sin la opción y al final solo sustituye `message.uid`; warnings, errores, `cached_path` y la caché no cambian.
- Texto de la ayuda (inglés): `debugging option: show the driver's native id in message.uid instead of the short uid; the native id is not accepted as input`.

## Fases

**Tabla: Fases de M04**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Opción en el parser y su ayuda; paso a `run_show` | ⚪ |
| 2 | Sustitución de `message.uid` con el gancho | ⚪ |
| 3 | UT-SNI-01 completo | ⚪ |
| 4 | Suite completa, cobertura, diff, evidencia cruda | ⚪ |

## Tests

Archivo nuevo `tests/test_show_native_id.py`, con el store de prueba de Apple Mail (`tests/fixtures/make_fixtures.py`) y el plugin de prueba, sin el doble de Outlook. Las definiciones ya están `[pendiente]` en `docs/tests/cli-config.md`.

#### UT-SNI-01 — `--show-native-id` en `show`

Requisitos: RF-83, RF-73, AC-68, AC-70

**Tabla: Casos de UT-SNI-01**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con Apple Mail, `show <uid> --show-native-id` da la misma salida que sin la opción (salvo `generated_at`). |
| .02 | P | Con un plugin con `display_native_id`, `message.uid` es `<driver>:<forma nativa>`; las demás claves y valores, los textos de los warnings y `cached_path` son los mismos que sin la opción, y `cache.db` no cambia. |
| .03 | P | Con un plugin sin el gancho, la salida es la misma con la opción y sin ella. |
| .04 | N | Un plugin cuya forma nativa no cumple las reglas de un `<native_id>` ⇒ `E_PLUGIN_FAILED` (exit 3) y sin mensaje en la salida. |
| .05 | N | `search`, `new`, `attachment`, `mailboxes` y `doctor` con `--show-native-id` ⇒ `E_USAGE` (exit 2), sin crear el home. |
| .06 | N | Un `display_native_id` que supera el tope de 30 s (acortado en el test) ⇒ `E_CLIENT_TIMEOUT`. |
| .07 | P | `show --help` describe `--show-native-id` como opción de depuración. |
| .08 | B | Con `--fields subject`, el `uid` que siempre se entrega muestra la forma nativa. |

Tests que cambian: los tests de ayuda existentes que comparen la ayuda de `show` completa, si fallan por la opción nueva, están en archivos de M05 o M07; no los tocas: los nombras en tu mensaje final y el orquestador los asigna (fuera de alcance).

Comandos:

- `$PY -B -m unittest tests.test_show_native_id > "$LOG/grupo-ut_sni.log" 2>&1`.
- Suite completa: la de `protocolo.md`.

## Documentación

- Ayuda de `show` (`cli.py`): la opción con el texto de "Decisiones aplicables"; si `_SHOW_EPILOG` tiene una lista de opciones o ejemplos de uid, se añade la opción ahí con el mismo sentido.
- README y skill: los hace M07.

## Actualizaciones de la unidad

Las aplica el orquestador al cerrar el milestone.

- **Conciliación:** según `trazabilidad.md`, aporta a RC-06, RC-07, RC-10, RC-14, RC-18, RC-19, RC-26. Ninguna fila cambia de estado al cerrar este milestone: el orquestador las pasa todas a `implementado` en F4.
- **Documentos consumidores:** ninguno.
- **Checklist:** ninguno cambia.
- **Desviaciones:** ninguna prevista.

## Gates

- `tests.test_show_native_id` verde.
- Suite completa sin fallos nuevos frente a la línea base.
- `git diff --check` limpio; `git diff --stat` dentro del alcance.

## Datos crudos de evidencia

Los de `protocolo.md`, más la ayuda de `show --help` resultante (texto completo de la opción).

## Definition of Done

- `--show-native-id` existe solo en `show`, cumple D-16 y su ayuda la describe como opción de depuración.
- UT-SNI-01 pasa entero; suite sin fallos nuevos.
- Fases en 🟢, registro al día, evidencia cruda escrita.

## Registro de progreso

**Tabla: Registro de progreso de M04**

| Fecha | Fase | Nota |
|---|---|---|
