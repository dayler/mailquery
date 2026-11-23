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
| 2026-11-23 | Plan | ⚪ → ⚪ | — | — | Dos revisiones independientes del plan: 27 hallazgos en la primera y 10 en la segunda (DP-10 roto, llamadas de los procesos hijo en las pruebas reales, entre otros); todos corregidos en el plan. |
