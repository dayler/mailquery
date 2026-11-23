# Propuestas de M04 para documentos compartidos

Cambio necesario en `docs/tests/` (solo lo aplica el orquestador). Según `docs/tests/TEST-CATALOG.md`, la marca `[pendiente]` se quita de la fila cuando el test existe y pasa; no se sustituye por otra marca.

## `docs/tests/cli-config.md`

Ancla: sección `#### UT-SNI-01 — --show-native-id en show`, tabla "Casos de UT-SNI-01" (filas .01 a .08). Quitar el prefijo `[pendiente] ` de las ocho filas, sin tocar el resto del texto.

**Tabla: Filas propuestas de UT-SNI-01**

| Caso | Tipo | Texto propuesto de `Verifica` |
|---|---|---|
| .01 | P | Con Apple Mail, `show <uid> --show-native-id` da la misma salida que sin la opción (salvo `generated_at`). |
| .02 | P | Con un plugin con `display_native_id`, `message.uid` es `<driver>:<forma nativa>`; las demás claves y valores, los textos de los warnings y `cached_path` son los mismos que sin la opción, y `cache.db` no cambia. |
| .03 | P | Con un plugin sin el gancho, la salida es la misma con la opción y sin ella. |
| .04 | N | Un plugin cuya forma nativa no cumple las reglas de un `<native_id>` ⇒ `E_PLUGIN_FAILED` (exit 3) y sin mensaje en la salida. |
| .05 | N | `search`, `new`, `attachment`, `mailboxes` y `doctor` con `--show-native-id` ⇒ `E_USAGE` (exit 2), sin crear el home. |
| .06 | N | Un `display_native_id` que supera el tope de 30 s (acortado en el test) ⇒ `E_CLIENT_TIMEOUT`. |
| .07 | P | `show --help` describe `--show-native-id` como opción de depuración. |
| .08 | B | Con `--fields subject`, el `uid` que siempre se entrega muestra la forma nativa. |

Los ocho casos están implementados en `tests/test_show_native_id.py` y pasan (véase la evidencia cruda de M04).

## Otros documentos

- No hay cambios necesarios en `docs/changes/id-corto-outlook.md`, el plan maestro, `README` ni la skill: la ayuda de `show` y el resto del milestone quedaron dentro de `src/` y `tests/`. La ayuda copiada en los README y la skill son de M07.
- Ningún test de ayuda existente falló en la suite completa, así que no hay archivos de M05/M07 que asignar.
