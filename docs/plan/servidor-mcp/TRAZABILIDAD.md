# Trazabilidad del plan servidor-mcp

Leyenda de estados: la de [PLAN.md](PLAN.md). La columna "Tests" lista los grupos de [DEFINICIONES-TESTS.md](DEFINICIONES-TESTS.md); el orquestador la actualiza al cerrar cada milestone y la columna "CI" al cerrar cada lote.

## 1. Criterios de aceptación

**Tabla: Matriz AC → milestone → tests → estado**

| AC | Qué exige (resumen) | Milestone | Tests | Evidencia | CI | Estado |
|---|---|---|---|---|---|---|
| AC-71 | `initialize`, versiones, `ping`, `tools/list` con esquemas de RF-85, solo JSON-RPC en stdout, errores `-32601`/`-32700`/`-32600`, lotes, `\r\n` y `\n` en Windows | M02 (en proceso), M05 (`\n` del proceso real en Windows) | UT-MCP-01, UT-MCP-02, UT-MCP-03, UT-MCP-09.05 | — | — | ⚪ |
| AC-72 | argv equivalente con ejecutor sustituido; texto e `isError`; ejecutor real con `search --since bogus` igual que la CLI, también con `json.py` en el cwd | M02 (sustituido), M05 (real), M07 (cliente real) | UT-MCP-04, UT-MCP-05.01–.02, UT-MCP-05.07, UT-MCP-09.03, SMOKE-MCP | — | — | ⚪ |
| AC-73 | `E_USAGE` sin proceso hijo (parámetro desconocido, tipo, `uid`, `show_native_id`, NUL), formato de la CLI, `--subject=-…`, `-32602` | M02 | UT-MCP-06, UT-MCP-04.07 | — | — | ⚪ |
| AC-74 | Arranque sin config o con config inválida; `E_INTERNAL` y servidor vivo; `E_CONFIG_INVALID` que se corrige sin reiniciar; serie; cierre de stdin con llamada en curso; stderr vacío | M02 (en proceso), M05 (proceso real), M07 (cliente real) | UT-MCP-05.03–.05, UT-MCP-07, UT-MCP-09.01, .02, .04, SMOKE-MCP | — | — | ⚪ |
| AC-75 | Ayuda raíz con `mcp`; `E_USAGE` de `mcp` y `mcp serve extra`; ayudas con el registro; ayuda raíz con los dos logs; README y skill; log del servidor `start`/`call`/`end` sin valores | M04 (línea de logs de la ayuda), M05 | UT-LOG-06.03, UT-CLI-14, DOC-17, UT-MCP-11 | — | — | ⚪ |
| AC-76 | Dependencias sin cambios; `mcp_server.py` solo importa biblioteca estándar y `mailquery`; servidor responde con un plugin que no carga | M02, M05 | UT-MCP-08, UT-MCP-10 | — | — | ⚪ |
| AC-77 | Log JSON: archivo, campos, tipos, `message`, `traceback`, `hint` con `mailquery.jsonl`, nivel, permisos, rotación, `json = "yes"` y config inválida registrados en texto | M04 | UT-LOG-05, UT-LOG-06.01–.02, UT-CFG-05, DOC-18 | — | — | ⚪ |
| AC-78 | Rotación con el servidor en marcha, en macOS y Windows, en los dos formatos; `event=call` en el archivo activo nuevo | M05 | UT-MCP-12 (matriz de CI en macOS y Windows) | — | — | ⚪ |

## 2. Requisitos

**Tabla: Requisitos de la unidad → milestones**

| Requisito | Milestones | Grupos |
|---|---|---|
| RF-84 | M02, M04 (DP-05), M05 | UT-MCP-01, 02, 07, 08, 09 (incluidas .06 y .07), 10, 11, 12; UT-CFG-06; UT-CLI-14 |
| RF-85 | M02 | UT-MCP-03, UT-MCP-04 |
| RF-86 | M02, M05 | UT-MCP-04, 05, 06, 07, 09 |
| RF-87 | M05, M06 | UT-CLI-14, DOC-17 |
| RF-88 | M01 (preparación), M04, M05 (eventos del servidor en JSON) | UT-LOG-05 (incluida .12), UT-LOG-06, UT-CFG-05, DOC-18, UT-MCP-11.04, UT-MCP-12.02 |
| Versión `3.0.0a3` | M03 | DOC-16.03, TC-01.01, TC-02.07, PKG-01.03 |

## 3. Checklist de la unidad

**Tabla: Ítems del checklist que el plan prepara**

| Ítem | Quién lo deja listo | Cuándo | Estado |
|---|---|---|---|
| CL-05 Documentos consumidores | M03–M07 y el orquestador (`docs/tests/`) | Cierre de cada milestone; F5 | ⚪ |
| CL-06 Textos obsoletos en documentos consumidores | M05, M06; búsqueda del orquestador | F3 | ⚪ |
| CL-09 La suite pasa | Orquestador | Cierre de cada lote; F5 | ⚪ |
| CL-10 SMOKE y verificación manual | M07 (tests y procedimiento) y el dueño (ejecución, DA-03) | F4 | ⚪ |
| CL-11 `3.0.0a3` fuera del PRD | M03; búsqueda del orquestador | F3 | ⚪ |
| CL-12 Casos en el catálogo | Orquestador (F0 y cierre de cada milestone) | F0; F5 | ⚪ |
| CL-01–CL-04, CL-08, parte PRD de CL-06 y CL-11 | Quien concilie (DA-02) | Fuera del plan | ⚪ |
| CL-07 | No aplica | — | — |
