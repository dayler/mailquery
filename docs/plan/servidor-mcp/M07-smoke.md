# M07 — SMOKE del servidor MCP con el cliente real

- **Unidad:** `docs/changes/servidor-mcp.md` (contribuye y no la completa sola).
- **Oleada / lote:** 4 / 2. **Rama del lote:** `feature/servidor-mcp-lote-2`. **Rama del milestone:** `feature/servidor-mcp-m07`, creada desde el tip de la rama del lote.
- **Commit base:** `ce19b37` (lote 2; el milestone solo toca `tests/test_smoke.py`). **Línea base de la suite:** la del lote; los fallos conocidos son los SMOKE del entorno local.
- **Depende de:** M05 (`mailquery mcp serve` instalable con `pipx`). **Lo usan:** F4 y F5 del plan.
- **ACs:** ninguno nuevo; verifica AC-72 y AC-74 contra el cliente real y cubre CL-10.

## Objetivo

Añadir a `tests/test_smoke.py` los casos SMOKE-MCP, que hablan con `mailquery mcp serve` instalado con `pipx` contra Apple Mail u Outlook reales, y dejar listo el procedimiento con el que el dueño los ejecuta en macOS y en Windows y hace la verificación manual con Claude Code. Esa ejecución del dueño es un gate de la fase F4 del plan, no de este milestone: M07 se cierra con sus fases 1 a 3 y no bloquea el cierre del lote 2.

## Alcance

- Clase nueva en `tests/test_smoke.py` con un cliente JSON-RPC mínimo de prueba (escribe una línea, lee una línea) sobre el `mailquery` instalado por la clase, con la instalación y la configuración de SMOKE-INSTALL.
- Casos SMOKE-MCP.01 a .07, con los saltos con motivo de la sección 6 de `docs/tests/infrastructure.md` (Linux, Windows sin Outlook clásico abierto, macOS sin `~/Library/Mail`, runners de CI) y los propios de cada caso.
- Ejecución en el equipo disponible para el subagente y entrega del procedimiento para el dueño.

## Fuera de alcance

- La verificación manual con Claude Code (registrar con `claude mcp add`, ver que lista las herramientas y que la skill las usa; sin registrar, que usa la CLI): la hace el dueño y el orquestador la anota en `evidence/M07.md`.
- Cambios en el código del producto: un fallo de producto se devuelve al orquestador, que reabre M05 (🟡).

## Alcance de escritura

- `tests/test_smoke.py`.
- `docs/plan/servidor-mcp/M07-smoke.md`, `docs/plan/servidor-mcp/work/M07-handoff.md`, `docs/plan/servidor-mcp/work/M07-propuestas.md`.

## Especificación

Rangos de `docs/changes/servidor-mcp.md` en el commit de la unidad aprobada (F0 anota aquí el commit; si las líneas se movieron, busca el encabezado):

- `**RF-84. Servidor MCP por stdio.**`, condiciones "Ciclo de vida", "Paridad", "Drivers y plugins" y "Permisos del sistema" (líneas 104–108).
- `**RF-86. Ejecución de una llamada.**`, condiciones "Proceso hijo" y "Entorno de los plugins" (líneas 142 y 150).
- `## Checklist de conciliación`, CL-10 (línea 428).

Casos de test: `#### SMOKE-MCP` de `docs/tests/smoke.md`.

## Puntos de entrada en el código

En el tip del lote 2 tras M05; si la línea se movió, búscala por el nombre:

- `tests/test_smoke.py`: `_skip_reason` (97), `SmokeTest.setUpClass` (145; instalación con `pipx`, `HOME` temporal y configuración), `_snapshot` (111) para los contadores de no leídos, `SmokeAttOutlook` (699) como modelo de clase con saltos por plataforma.
- Plugin para SMOKE-MCP.06: como en `tests/test_outlook.py` (1166–1180), un directorio temporal con el módulo de un plugin de prueba y su `dist-info` con el entry point `mailquery.backends`, puesto en el `PYTHONPATH` del servidor lanzado por el test (el servidor y sus hijos heredan el entorno y `-P` no quita `PYTHONPATH`). Una variante del plugin funciona y declara su cuenta en el `config.toml` temporal junto al driver nativo; otra falla al consultarse y da `E_PLUGIN_FAILED`. `tests/fakes/plugin.py` es la base del módulo; no se instala con `pipx inject`, porque no es una distribución.

## Refactorizaciones previas

Ninguna. Si el cliente JSON-RPC de prueba necesita compartir la instalación de `SmokeTest`, se reutiliza su `setUpClass` por herencia o por una función del módulo, sin cambiar los casos existentes.

## Decisiones aplicables

- **DP-01. Infraestructura de tests existente.** La línea base tiene tests unitarios con `unittest` (sin otros frameworks), una suite completa con un solo comando (`python -B -m unittest discover -s tests -t .`), dobles de Outlook y de plugins (`tests/fakes/`), lanzamiento de la CLI por subproceso con `PYTHONPATH=src` (`tests/test_cli.py`, `tests/test_plugins.py`), plugins falsos instalados con un `dist-info` en `PYTHONPATH` (`tests/test_outlook.py`), y SMOKE contra el cliente real que se salta con motivo donde no aplica (`tests/test_smoke.py`). Todos los AC se prueban con esa infraestructura: la rotación de AC-78 "en macOS y en Windows" corre en la matriz de CI, que incluye los dos sistemas; la parte de CL-10 que necesita el cliente real es SMOKE (M07). No hace falta un milestone de infraestructura ni una pregunta al dueño.
- **DA-03 (abierta).** Equipos y momento de la ejecución del dueño. No bloquea este milestone; el orquestador la pregunta al cerrarlo, para la fase F4.

## Fases

**Tabla: Fases de M07**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Cliente JSON-RPC de prueba y clase SMOKE-MCP con sus saltos; SMOKE-MCP.01 y .02 | 🟢 |
| 2 | SMOKE-MCP.03 a .07 | 🟢 |
| 3 | Ejecución en el equipo disponible (`-k smoke_mcp`), suite completa, procedimiento para el dueño, evidencia cruda y propuestas | 🟢 |

## Tests

- Grupo nuevo SMOKE-MCP en `tests/test_smoke.py`, métodos `test_smoke_mcp_<cc>_<descripción>`.
- Fuera de los equipos con cliente real, los casos se saltan con motivo y el número de tests es el mismo en los tres sistemas.
- Comando: `python -B -m unittest discover -s tests -t . -k smoke_mcp` y la suite completa.

## Documentación

Ninguna del producto. El procedimiento para el dueño (comandos, condiciones de cada caso, cómo preparar `E_PERMISSION` y `E_OUTLOOK_NOT_RUNNING`, cómo hacer la verificación manual con Claude Code) va en la evidencia cruda y el orquestador lo copia a `evidence/M07.md`.

## Actualizaciones de la unidad

Propones al orquestador, en `work/M07-propuestas.md`:

- Marcas de SMOKE-MCP en `docs/tests/smoke.md` (los casos ejecutados y verdes en algún equipo; los saltados, con el motivo).
- Documentos consumidores `docs/tests/smoke.md` y `docs/tests/infrastructure.md` (su viñeta de SMOKE-MCP, escrita en F0) a `actualizado` cuando estén aplicadas las marcas.
- CL-10: lo verifica el dueño en F4; tú entregas el procedimiento.

## Gates

- `-k smoke_mcp` verde o saltado con motivo en el equipo del subagente; suite completa sin fallos nuevos frente a la línea base.
- `git diff --check` limpio y `git diff --stat` solo con `tests/test_smoke.py` y tus archivos del plan.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md), más: plataforma, cliente y versión del sistema del equipo donde corriste los casos; resultado por caso (verde o saltado con motivo); y el procedimiento para el dueño.

## Definition of Done

- SMOKE-MCP.01 a .07 existen y pasan o se saltan con motivo en el equipo del subagente.
- El procedimiento para el dueño está en la evidencia cruda, completo para macOS y Windows.
- Suite completa sin fallos nuevos; `git diff --check` limpio; diff dentro del alcance; fases en 🟢, evidencia cruda y propuestas entregadas.

## Registro de progreso

**Tabla: Registro de progreso de M07**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | Cliente JSON-RPC de prueba y clase `SmokeMcpTest`; SMOKE-MCP.01 y .02. |
| 2026-11-23 | 2 | SMOKE-MCP.03 a .07, con los saltos por plataforma y por condición externa. |
| 2026-11-23 | 3 | Ejecución en macOS con Apple Mail real (`Ran 7 tests`, `OK (skipped=1)`), procedimiento para el dueño y evidencia. |
