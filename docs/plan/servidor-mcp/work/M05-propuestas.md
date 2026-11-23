# M05 — propuestas

## Marcas de `docs/tests/`

- UT-MCP-09 a UT-MCP-12, UT-CLI-14 y DOC-17: implementados; quitar `[pendiente]` cuando el orquestador aplique las marcas.
- UT-ATC-09.01, .03 y .04: actualizados en los tests; quitar `[por actualizar]`.
- DOC-01.01, DOC-04.01, DOC-05.01, DOC-05.03 y TC-07.01: actualizados; quitar `[por actualizar]`.
- DOC-01.01 y DOC-05.01 pasan a hablar de siete comandos.

## Unidad

- Filas de conciliación a `implementado` (RC-02…RC-06, RC-08…RC-11, RC-14, RC-15, RC-17, RC-23, RC-24, RC-26, RC-29…RC-32, RC-34, RC-36) y hallazgos para su "Qué cambia": se proponen para la conciliación posterior, no se aplican en este trabajo.
- Documentos consumidores `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `skills/README.md` y `docs/tests/attachments-command.md` (cuando se aplique la marca de UT-ATC-09).

## Desviaciones

Ninguna.

## Plan

- El servidor instala su log con `setup_server_logging`, un manejador que abre, escribe, rota y cierra en cada evento; un fallo de escritura se ignora y no toca stdout ni stderr.
- `cli._run_mcp` resuelve `[logging]` con `load_logging_config`, aplica `--log-level` y arranca `serve` con el ejecutor real.
- Los flujos de la CLI se envuelven en UTF-8 sin traducción de fin de línea; el wrapper de stdin se detiene sin cerrar el buffer.
- La ayuda de `mcp serve` y la de `mcp` muestran el registro de Claude Code y la entrada `mcpServers`; los ejemplos que se analizan son solo `mailquery mcp serve`.
- El log JSON del servidor usa el mismo `JsonFormatter` y `mailquery.jsonl` que el resto del núcleo.
