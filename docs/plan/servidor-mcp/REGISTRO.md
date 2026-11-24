# Registro de ejecución del plan servidor-mcp

Lo escribe el orquestador al lanzar, cerrar, bloquear o relanzar un milestone y al cerrar cada lote. Cada relanzamiento cuenta para los límites de `CLAUDE.md`.

## 1. Línea base

Medida al planificar, en `f868036`, en el equipo del dueño (Windows, Python 3.14.7), con `python -B -m unittest discover -s tests -t .`: `Ran 1561 tests in 246.047s`, `FAILED (failures=10, skipped=7)`. Los 10 fallos son del entorno de ese equipo, no del código:

- 5 por metadatos de una instalación editable antigua (`mailquery 2.0.1`): TC-01.01, TC-02.07, TC-06.02, PKG-01.03 y PKG-02.01.
- 5 por `css-inline` sin instalar: UT-CNT-02.10, UT-CNT-03.01, UT-CNT-03.02, UT-CNT-03.10 y UT-CW-07.01.

F0 prepara en cada worktree un entorno virtual `.venv` con `css-inline~=0.23.1`, `coverage~=7.17` y, en Windows, `pywin32`, sin instalar `mailquery`, como la matriz de CI, y vuelve a medir la línea base en el commit de partida; esa medición es la que reciben los subagentes.

## 2. Registro

**Tabla: Registro de ejecución**

| Fecha | Milestone o lote | Estado anterior → nuevo | Resultado de la suite | Evidencia | HITL / notas |
|---|---|---|---|---|---|
| 2026-11-23 | Plan | — → ⚪ | 1561 tests, 10 fallos de entorno, 7 saltos (sección 1) | — | Plan creado. F0 en 🔴 por DA-01 (unidad en `borrador`). |
| 2026-11-23 | F0 | 🔴 → ⚪ | — | — | DA-01 respondida: unidad aprobada; IDs reservados (CU-10, RF-84…RF-88, ADR-51, AC-71…AC-78) y sustituidos en la unidad y en el plan. Falta commitear la unidad aprobada en `develop` (orden del dueño). |
| 2026-11-23 | Plan | ⚪ → ⚪ | — | — | Dos revisiones independientes del plan: 27 hallazgos en la primera y 10 en la segunda; todos corregidos. |
| 2026-11-23 | F0 | ⚪ → 🟢 | Línea base en `f866be8`: `Ran 1562`, `failures=3` (SMOKE del entorno), `skipped=7` | — | Definiciones de test en `docs/tests/`; consumidores añadidos a la unidad (DP-14); rama `feature/servidor-mcp`; worktrees `.worktrees/servidor-mcp-*` con `.venv`. |
| 2026-11-23 | M01 | ⚪ → 🟢 | `Ran 1576`, 3 fallos de entorno | `evidence/M01.md` | `log_event` en las 14 llamadas; test de regresión; sin llamadas directas. |
| 2026-11-23 | M03 | ⚪ → 🟢 | `Ran 1562`, `OK (skipped=7)` | `evidence/M03.md` | `3.0.0a3` en paquete, `--version`, `doctor` y documentos; búsqueda de CL-11 limpia. |
| 2026-11-23 | Lote 1 (M01+M03) | ⚪ → 🟢 | — | — | Integración `--no-ff` en `feature/servidor-mcp-lote-1`. |
| 2026-11-23 | M02 | ⚪ → 🟢 | `-k ut_mcp` 52 tests, OK; cobertura 92.6 % | `evidence/M02.md` | Núcleo del servidor, esquemas y ejecutor real. |
| 2026-11-23 | M04 | ⚪ → 🟢 | `Ran 1598`, 2 fallos SMOKE de entorno | `evidence/M04.md` | `[logging].json`, `JsonFormatter`, archivo activo, hints y README. |
| 2026-11-23 | M05 | ⚪ → 🟢 | `-k ut_mcp` 67 tests, `-k smoke_mcp` 7 OK (1 skip) | `evidence/M05.md` | `mcp serve`, log del servidor, ayudas, README, skill y pruebas con procesos reales. |
| 2026-11-23 | Lote 2 (M06+M07) | ⚪ → 🟢 | grupos verdes | `evidence/M06.md`, `evidence/M07.md` | M06 documentos técnicos; M07 SMOKE-MCP en macOS con Apple Mail real. |
| 2026-11-23 | PR #17 | abierto → mergeado | Matriz del PR: 15/15 jobs verdes (12 de suite, 3 de instaladores) | https://github.com/dayler/mailquery/pull/17 | Único PR de `feature/servidor-mcp` a `develop`, mergeado en `dd79daf`; la conciliación PRD/unidad se difiere por orden del dueño. |
| 2026-11-23 | `develop` | — → 🟢 | Matriz de `develop`: 15/15 jobs verdes sobre `dd79daf` | https://github.com/dayler/mailquery/actions/runs/45294624259 | CI de `develop` tras el merge, sin fallos; `main` sin tocar. |
