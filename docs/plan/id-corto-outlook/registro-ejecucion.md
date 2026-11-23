# Registro de ejecución

Lo completa solo el orquestador, al cerrar cada milestone y cada lote, y en cada relanzamiento, bloqueo o defecto posterior al cierre. Una fila por evento.

**Tabla: Registro de ejecución**

| Fecha | Milestone o lote | Estado anterior → nuevo | Suite | Evidencia | HITL / notas |
|---|---|---|---|---|---|
| 2026-11-23 | Plan | — → ⚪ | Línea base al planificar: 1451 tests, 10 fallos del entorno, 7 saltos | [decisiones.md](decisiones.md) | Plan escrito; todos los semáforos en ⚪ |
| 2026-11-23 | Plan | ⚪ → ⚪ | — | — | Revisión independiente: 7 hallazgos mayores y 17 menores, corregidos en el plan; H-03 (item que no se puede abrir) respondido por el dueño: se mantiene el comportamiento actual como desviación aprobada |
| 2026-11-23 | F0 | ⚪ → 🟢 | Línea base con el venv: 1452 tests, `OK (skipped=8)` en `4361e96` | [decisiones.md](decisiones.md) | Rama de la unidad `feature/id-corto-outlook` y worktree `.worktrees/unit`; H-03 aplicada a la unidad; venv con `css-inline~=0.23.1` y `coverage~=7.17`; ubicaciones en D-21 |
| 2026-11-23 | F0 | 🟢 → 🟢 | `-k doc_15` verde | — | Definiciones `[pendiente]` y `[por actualizar]` en `docs/tests/`; prefijos UT-NID y UT-SNI; AC-63…AC-70 en la matriz |
| 2026-11-23 | M02 | 🟡 → 🟢 | 1453 tests, `OK (skipped=8)` en `e3a90d3`; `tests.test_outlook` 225, `OK (skipped=1)` | [evidence/M02.md](evidence/M02.md) | Integrado con `--no-ff` en `b4e9e1f`; sin relanzamientos |
| 2026-11-23 | M01 | 🟡 → 🟢 | 1481 tests, `OK (skipped=7)` en `a48184e`; `-k ut_nid` 29, `OK` | [evidence/M01.md](evidence/M01.md) | Integrado con `--no-ff`; cobertura de `native_ids.py` 90.7 %; marcas `[pendiente]` retiradas; sin relanzamientos |
| 2026-11-23 | M03 | 🟡 → 🟢 | 1497 tests, `OK (skipped=8)` en `778fa7a`; UT-PL-05 6 `OK`, UT-PL-06 8 `OK` | [evidence/M03.md](evidence/M03.md) | Integrado con `--no-ff`; cobertura de los módulos tocados 93.6 %; marcas retiradas; sin relanzamientos |
| 2026-11-23 | M04 | 🟡 → 🟢 | 1505 tests, `OK (skipped=8)` en `39ddb8d`; `tests.test_show_native_id` 8, `OK` | [evidence/M04.md](evidence/M04.md) | Integrado con `--no-ff`; marcas de UT-SNI-01 retiradas; sin relanzamientos |
| 2026-11-23 | Lote 1 | 🟡 → 🟢 | Suite en la rama de la unidad: 1497 tests, `OK (skipped=7)` | [evidence/M01.md](evidence/M01.md), [evidence/M02.md](evidence/M02.md), [evidence/M03.md](evidence/M03.md) | Integrado en `feature/id-corto-outlook` con `--no-ff` y empujado; PR https://github.com/dayler/mailquery/pull/11 con la matriz completa verde (12 jobs de `test suite` y 3 de `install scripts`), run https://github.com/dayler/mailquery/actions/runs/45124436682 |
