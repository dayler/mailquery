# M02 — propuestas

## Marcas de `docs/tests/`

- UT-MCP-01 a UT-MCP-08: implementados en `tests/test_mcp_server.py`; quitar `[pendiente]` en `docs/tests/mcp-server.md` cuando el orquestador aplique las marcas.

## Unidad

- RC-19 y RC-21: sin hallazgos que cambien su contrato; la responsabilidad y el flujo son los de la unidad. Las filas pasan a `implementado` en M05, cuando el comando existe.

## Desviaciones

Ninguna.

## Plan

- El ejecutor real se llama `SubprocessToolRunner`; `serve` recibe un `ToolRunner` con `run(argv)`.
- `build_argv` devuelve el comando como primer elemento (`["search", ...]`), para que `serve` solo anteponga el intérprete y `-P -m mailquery`.
- El límite del argv se comprueba al final de `build_argv` (con el intérprete y el entorno) y otra vez no se repite en `serve`.
- Una línea que no se puede decodificar como UTF-8 se responde con `-32700` y el servidor sigue leyendo.
- El evento `event=call` solo se registra cuando el ejecutor devuelve un resultado; un fallo de lanzamiento devuelve `E_INTERNAL` sin evento.
