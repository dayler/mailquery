# M03 — Propuestas para documentos compartidos

## Desviación para aprobar: la línea `Lock:` de la ayuda raíz ocupa dos líneas

La unidad (RF-89, condición "Ayuda") fija el texto `Lock: a busy run lock is retried 5 times, pausing 150 ms and doubling each time ([lock] in config.toml)` como una línea. Ese texto mide 103 columnas, y la ayuda ya tiene un ancho máximo de 100 (PRD §12.7, "ancho de 100 columnas"; lo comprueba UT-ATC-09.01 con `HELP_MAX_WIDTH = 100`). La ayuda raíz lo parte como las líneas `Output:` y `Exit codes:`, con la continuación sangrada hasta debajo del texto:

```text
Configuration: ~/.mailquery/config.toml (optional; see README.md)
Lock: a busy run lock is retried 5 times, pausing 150 ms and doubling each time
      ([lock] in config.toml)
```

Las palabras son las fijadas por la unidad, sin cambios. UT-CLI-15.07 comprueba que el bloque empieza en la línea siguiente a `Configuration:` y que, unidos sus espacios, es el texto fijado. Propuestas, si el dueño aprueba la desviación:

- `docs/changes/espera-del-lock.md`, sección "Desviaciones aprobadas": la línea `Lock:` se parte en dos para respetar el ancho de 100 columnas de la ayuda, con la continuación sangrada.
- `docs/tests/cli-config.md`, UT-CLI-15.07: "muestra, después de la línea `Configuration:`, la línea `Lock: …`, partida en dos líneas de 100 columnas como mucho".
- `docs/changes/espera-del-lock.md`, condición "Ayuda" y fila RC-09: decir que el texto puede ocupar dos líneas; al conciliar, el ejemplo de `docs/prd/12.07-ayuda.md` muestra la forma partida de arriba.

## Desviación menor: UT-CLI-15.01 y UT-MCP-13.01 comparan sin `scan.duration_ms`

"Su salida es la de una ejecución sin espera salvo `generated_at`": la salida de `search` lleva además `scan.duration_ms`, que cambia entre dos ejecuciones cualesquiera, con espera o sin ella. Los dos tests comparan sin `generated_at` ni `scan.duration_ms`. Propuesta para `docs/tests/cli-config.md` (UT-CLI-15.01), `docs/tests/mcp-server.md` (UT-MCP-13.01) y AC-79 en la unidad: "salvo `generated_at` y `scan.duration_ms`".

## `docs/tests/cli-config.md`

En "UT-CLI-15 — Reintento del lock en los comandos", **Tabla: Casos de UT-CLI-15**: quitar `[pendiente]` de .01 a .09. Implementados en `tests/test_cli.py` (`LockRetryCommandTests`, `test_ut_cli_15_01` a `test_ut_cli_15_09`); pasan solos, tres veces seguidas en grupo y en la suite completa. Con la desviación de la ayuda aprobada, .07 cambia como dice arriba.

## `docs/tests/mcp-server.md`

En "UT-MCP-13 — Lock ocupado en una llamada MCP", **Tabla: Casos de UT-MCP-13**: quitar `[pendiente]` de .01 y .02. Implementados en `tests/test_mcp_server.py` (`LockBusyCallTests.test_ut_mcp_13_01`, `LockConfigServerTests.test_ut_mcp_13_02`).

## `docs/changes/espera-del-lock.md`

- Documentos consumidores `docs/tests/cli-config.md` y `docs/tests/mcp-server.md`: de `pendiente` a `actualizado` al quitar sus marcas. `docs/tests/state-backends.md`, `docs/tests/acceptance-matrix.md` y `docs/tests/TEST-CATALOG.md`: de `pendiente` a `actualizado` cuando sus definiciones no tengan marcas (no son del alcance de M03; no se han revisado).
- Tabla de conciliación: las filas de RF-89, AC-79 y AC-80 (y RC-09, ayuda raíz) pasan de `pendiente` a `implementado` cuando la rama del lote tenga M01 a M04 integrados con sus tests y sus documentos consumidores.

## `src/mailquery/mcp_server.py`

Sin cambios: ningún test de UT-MCP-13 lo necesitó.

## Otros documentos compartidos

Ninguna propuesta para `MASTER-PLAN.md`, `INTEGRACION.md`, `REGLAS.md`, `TRAZABILIDAD.md`, `DECISIONES.md`, `REGISTRO.md`, `evidence/` ni `docs/prd/`.
