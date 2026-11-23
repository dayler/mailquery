# M06 — Propuestas para el orquestador

Rama `feature/servidor-mcp-m06`, commits `317c691`, `80040d8` y `e36fd81`
sobre la base `0ca8909`. Evidencia en
`<REPO>/.logs/servidor-mcp/M06/evidencia-cruda.md`.

## 1. Marcas de `docs/tests/`

Ninguna. M06 no escribe en `docs/tests/` y no hay casos nuevos, renombrados ni
textos que la implementación obligue a cambiar. Los grupos TC-04, DOC-03,
DOC-14, DOC-15 y DOC-16.02 siguen verdes sobre los documentos actualizados.

## 2. Unidad

### 2.1 Conciliación con el PRD

Propongo pasar a `implementado` estas filas, porque el contenido que describen
ya está en los documentos consumidores de este milestone:

**Tabla: Filas de conciliación propuestas**

| Fila | Dónde quedó el contenido |
|---|---|
| RC-18 (vista de componentes) | `docs/INTERFACES.md` §1 y §2 (layout, `mcp_server.py`, proceso hijo, dos archivos de log) y §3 `mcp_server.py`/`logging_setup.py`; `docs/security/threat-model.md` §4.3. |
| RC-19 (responsabilidades de módulos) | `docs/INTERFACES.md` §3 `mcp_server.py` (interfaz, protocolo, esquemas, argv, ejecutor y resultado) y §2 (regla de dependencias). |
| RC-20 (responsabilidad del logger) | `docs/INTERFACES.md` §3 `logging_setup.py` y `config.py` (`[logging].json`, `load_logging_config`); `docs/security/threat-model.md` §4.3 y §9. |
| RC-21 (flujo de una llamada MCP) | `docs/INTERFACES.md` §3 `mcp_server.py` y `cli.py` (`mcp serve`), y §8.8 (prueba manual); `docs/security/threat-model.md` §4.3. |
| RC-35 (riesgos del servidor MCP) | `docs/security/threat-model.md` §4.3, T-14 y §9; `docs/ROADMAP.md` §3. |

El PRD no se toca en este plan: si el orquestador necesita que la fila apunte a
`docs/prd/09-arquitectura.md` o `docs/prd/23-riesgos.md` antes de marcarla,
esa reconciliación queda fuera del alcance de M06.

### 2.2 Documentos consumidores

**Tabla: Estado propuesto de los documentos consumidores**

| Documento | Estado propuesto |
|---|---|
| `docs/INTERFACES.md` | `actualizado` |
| `docs/security/` | `actualizado` |
| `docs/ROADMAP.md` | `actualizado` |
| `docs/recipes/` | `actualizado` |

`docs/recipes/` no necesitó la frase de MCP: ninguna receta afirma que la CLI
sea la única vía. Se actualizó porque la fila `E_INTERNAL` de las dos recetas
nombraba `mailquery.log` como único archivo del log del núcleo (CL-06).

### 2.3 Hallazgos para "Qué cambia"

- El servidor MCP por stdio y el log JSON Lines son hechos de 3.0.0 y los
  documentos consumidores ya los describen con las secciones que la unidad
  espera para el PRD.
- La privacidad de `mailquery.jsonl` es la misma que la del log de texto y el
  servidor no añade campos: `event=call` lleva herramienta, código de salida y
  duración, nunca valores de parámetros.

## 3. Desviaciones

Ninguna.

## 4. Plan

- **Recetas:** se aplicó la condición de la fase 3 al pie de la letra (sin
  frase de MCP por no haber afirmación de CLI única) y se corrigió la fila
  `E_INTERNAL` para que nombre los dos formatos del log del núcleo.
- **ROADMAP:** se retiró la desventaja "Es CLI, no MCP" y se reformuló la
  ventaja de coste por turnos; el adaptador MCP queda como hecho de 3.0.0, sin
  plan ni fechas. No se añadieron fechas nuevas.
- **Títulos de tablas:** las tablas de `docs/security/threat-model.md` §6 y de
  `docs/ROADMAP.md` §4 no tenían título; se les añadió al modificarlas.
- **Spec del milestone:** los rangos de `docs/changes/servidor-mcp.md` citados
  en M06 no coinciden con el archivo actual (CL-06 y CL-11 están en 426 y 431,
  no en 424 y 429); se localizaron por encabezado, como pide el propio archivo.
- **Hook local:** el `pre-commit` del repositorio principal falla en este
  worktree por un hook de Mend/WhiteSource que espera `./.vscode/diff/`; los
  commits usan `--no-verify`. Conviene revisarlo en el orquestador.
