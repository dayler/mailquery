# Registro de ejecución

Lo completa solo el orquestador, al cerrar cada milestone y cada lote, y en cada relanzamiento, bloqueo o defecto posterior al cierre. Una fila por evento.

**Tabla: Registro de ejecución**

| Fecha | Milestone o lote | Estado anterior → nuevo | Suite | Evidencia | HITL / notas |
|---|---|---|---|---|---|
| 2026-11-23 | Plan | — → ⚪ | Línea base al planificar: 1451 tests, 10 fallos del entorno, 7 saltos | [decisiones.md](decisiones.md) | Plan escrito; todos los semáforos en ⚪ |
| 2026-11-23 | Plan | ⚪ → ⚪ | — | — | Revisión independiente: 7 hallazgos mayores y 17 menores, corregidos en el plan; H-03 (item que no se puede abrir) respondido por el dueño: se mantiene el comportamiento actual como desviación aprobada |
| 2026-11-23 | F0 | ⚪ → 🟢 | Línea base con el venv: 1452 tests, `OK (skipped=8)` en `4361e96` | [decisiones.md](decisiones.md) | Rama de la unidad `feature/id-corto-outlook` y worktree `.worktrees/unit`; H-03 aplicada a la unidad; venv con `css-inline~=0.23.1` y `coverage~=7.17`; ubicaciones en D-21 |
| 2026-11-23 | F0 | 🟢 → 🟢 | `-k doc_15` verde | — | Definiciones `[pendiente]` y `[por actualizar]` en `docs/tests/`; prefijos UT-NID y UT-SNI; AC-63…AC-70 en la matriz |
