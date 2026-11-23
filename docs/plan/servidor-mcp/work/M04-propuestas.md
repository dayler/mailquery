# M04 — Propuestas para el orquestador

## Marcas de `docs/tests/`

**Tabla: Casos de M04 que pasan a implementado**

| Caso | Método de test | Archivo |
|---|---|---|
| UT-CFG-05.01 | `test_ut_cfg_05_01_json_is_false_by_default_and_accepts_booleans` | `tests/test_config.py` |
| UT-CFG-05.02 | `test_ut_cfg_05_02_non_boolean_json_is_config_invalid_logged_in_text` | `tests/test_cli.py` |
| UT-CFG-05.03 | `test_ut_cfg_05_03_json_true_with_another_invalid_key_logs_in_text` | `tests/test_cli.py` |
| UT-CFG-06.01 | `test_ut_cfg_06_01_takes_logging_even_with_an_invalid_rest` | `tests/test_config.py` |
| UT-CFG-06.02 | `test_ut_cfg_06_02_defaults_without_raising` | `tests/test_config.py` |
| UT-LOG-05.01 | `test_ut_log_05_01_without_json_the_text_log_is_used_and_jsonl_is_untouched` | `tests/test_cli.py` |
| UT-LOG-05.02 | `test_ut_log_05_02_with_json_true_only_the_jsonl_changes` | `tests/test_cli.py` |
| UT-LOG-05.03 | `test_ut_log_05_03_lines_are_json_objects_with_the_shared_fields` | `tests/test_logging.py` |
| UT-LOG-05.04 | `test_ut_log_05_04_field_values_use_their_json_types` | `tests/test_logging.py` |
| UT-LOG-05.05 | `test_ut_log_05_05_error_message_is_always_text` | `tests/test_logging.py` |
| UT-LOG-05.06 | `test_ut_log_05_06_json_log_has_no_private_data_with_labels_unavailable` | `tests/test_logging.py` |
| UT-LOG-05.07 | `test_ut_log_05_07_internal_error_carries_its_traceback` | `tests/test_logging.py` |
| UT-LOG-05.08 | `test_ut_log_05_08_warning_level_keeps_info_out_of_the_json_log` | `tests/test_logging.py` |
| UT-LOG-05.09 | `test_ut_log_05_09_jsonl_and_its_rotated_files_are_0600` | `tests/test_logging.py` |
| UT-LOG-05.10 | `test_ut_log_05_10_jsonl_rotates_and_keeps_five_rotated_files` | `tests/test_logging.py` |
| UT-LOG-05.11 | `test_ut_log_05_11_both_formats_carry_the_same_events_in_the_same_order` | `tests/test_logging.py` |
| UT-LOG-05.12 | `test_ut_log_05_12_json_formatter_applies_only_to_the_mailquery_logger` | `tests/test_logging.py` |
| UT-LOG-06.01 | `test_ut_log_06_01_internal_error_hint_names_the_active_log_file` | `tests/test_cli.py` |
| UT-LOG-06.02 | `test_ut_log_06_02_outlook_hints_name_the_active_log_file` | `tests/test_outlook.py` |
| UT-LOG-06.03 | `test_ut_log_06_03_root_help_names_both_log_files` | `tests/test_cli.py` |
| DOC-18.01 | `test_doc_18_01_readmes_document_the_json_log` | `tests/test_packaging.py` |
| DOC-18.02 | `test_doc_18_02_example_documents_the_json_log` | `tests/test_integration.py` |

Quitar `[pendiente]` de las filas de UT-CFG-05.01–.03, UT-CFG-06.01–.02, UT-LOG-05.01–.12, UT-LOG-06.01–.03 y DOC-18.01–.02 en `docs/tests/cli-config.md` y `docs/tests/docs-packaging.md`.

No hace falta cambiar ningún texto de caso. `docs/tests/cli-config.md` queda pendiente de la marca `[por actualizar]` que M05 decida para su texto de la ayuda raíz.

## Unidad (`docs/changes/servidor-mcp.md`)

**Tabla: Filas de conciliación que propongo pasar a implementado**

| RC | Estado propuesto | Motivo |
|---|---|---|
| RC-07 | `implementado` | `[logging].json` en `config.py`, leído por `load_config` y por `load_logging_config`. |
| RC-12 | `implementado` | `setup_logging` escribe `mailquery.jsonl` con el mismo nivel, rotación y permisos. |
| RC-13 | `implementado` | Formateador JSON con `ts`, `level`, `logger`, `run`, `fields`, `text` y `traceback`. |
| RC-22 | `implementado` | Un solo archivo activo por ejecución; el del otro formato no se toca. |
| RC-27 | `implementado` | `[logging].json` es booleano; otro tipo da `E_CONFIG_INVALID` y se registra en texto. |
| RC-28 | `implementado` | `hint` de `E_INTERNAL` y de Outlook y ayuda raíz con el archivo o los archivos correctos. |

- RC-20 sigue para M06 (`docs/INTERFACES.md`).
- RC-24: la parte de logs queda para M05; la fila entera pasa con M05.

**Documentos consumidores**

- `docs/config.example.toml`: `actualizado`.
- `docs/tests/cli-config.md`: `actualizado` cuando se apliquen las marcas de arriba.

**Hallazgos para "Qué cambia"**

- El texto libre de un evento que ya tiene forma `clave=valor` (`event=start`, `event=end`, `event=error`, `event=internal_error`) entra como un campo más en `fields`, en su posición original (delante del resto), para que la línea JSON coincida con el ejemplo de RF-88 y no duplique `event` en `text`.
- Un registro del logger `mailquery` sin evento estructurado (biblioteca) lleva `fields` vacío y el mensaje formateado en `text`.
- `load_logging_config` devuelve `LoggingConfig()` ante cualquier problema del archivo, también `OSError`; no lanza.

## Desviaciones

Ninguna.

## Plan (decisiones dentro del margen, para registrar)

- Nombre de la función del archivo activo: `logging_setup.active_log_filename()`; devuelve `mailquery.log` antes de configurar y el nombre de la última configuración aplicada.
- Nombre del formateador JSON: `logging_setup.JsonFormatter`.
- Constantes de nombre de archivo: `TEXT_LOG_FILENAME` y `JSON_LOG_FILENAME`.
- En `logging_setup.setup_logging` el cuarto argumento se llama `json` (booleano, por defecto `False`); `cli.py` le pasa `config.logging.json` y `_best_effort_logger` recibe un cuarto argumento opcional para que `doctor` siga el formato activo solo con configuración válida.
- Texto del comentario de `config.example.toml`: `# json = false                   # true: JSON Lines in mailquery.jsonl`.
- Los README documentan la clave en la sección de configuración, los dos archivos y los campos en "Logs and privacy" / "Logs y privacidad", y la fila `E_INTERNAL` nombra los dos archivos, con el mismo contenido en inglés y en español.
- Los casos UT-LOG-05.08 y UT-LOG-05.11 usan `cli.main` (además de `setup_logging` directo) porque necesitan la configuración real; UT-LOG-06.01 y UT-LOG-06.03 están en `tests/test_cli.py` y UT-LOG-06.02 en `tests/test_outlook.py`, como permite el catálogo.
- UT-CLI-05.01 y el caso sin configuración de `LoggingConfigTests` se actualizaron para el cuarto argumento de `setup_logging`; su comportamiento no cambia.
