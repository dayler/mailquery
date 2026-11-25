# Registro de ejecución — espera-del-lock

Se completa al cerrar cada milestone y cada lote, y con cada relanzamiento.

**Tabla: Registro de ejecución**

| Fecha | Milestone o lote | Estado anterior → nuevo | Resultado de la suite | Evidencia | HITL / notas |
|---|---|---|---|---|---|
| 2026-11-24 | Plan | — → ⚪ | no ejecutada | — | Plan escrito; fase 0 en 🔴 por D-01 |
| 2026-11-24 | Validación del plan | sin validar → listo | no aplica | — | 1 revisión independiente: 0 bloqueantes, 9 no bloqueantes corregidos, 3 preguntas respondidas por el dueño (D-01, D-02, D-09); fase 0 a ⚪; plan sin aprobar |
| 2026-11-24 | Aprobación del plan | sin aprobar → aprobado | no aplica | — | Aprobado por Ariel Salazar Hinojosa |
| 2026-11-24 | Fase 0 | ⚪ → 🟢 | línea base en `41fc5b2`: 1654 tests, 10 fallos y 9 saltos | — | Unidad aprobada en `develop` (`e3670c7`, RF-89, AC-79, AC-80); definiciones `[pendiente]` en `docs/tests/`, `cli-config.md` partido en `log-output.md`; fallos conocidos del entorno local: UT-CNT-02.10, UT-CNT-03.01, .02, .10 y UT-CW-07.01 (sin hojas de estilo), TC-01.01, TC-02.07, TC-06.02, PKG-01.03 y PKG-02.01 (metadatos instalados 2.0.1) |
| 2026-11-24 | M01 | ⚪ → 🟡 | — | — | Lanzado en `../mailquery-wt/espera-del-lock-m01` desde `41fc5b2` |
| 2026-11-24 | M01 | 🟡 → 🟢 | `7a7a10d`: 1662 tests, sin fallos nuevos (10 conocidos del entorno con pyenv; OK con el `.venv`) | [evidence/M01.md](evidence/M01.md) | Integrado en el lote 1 (`4ce0dad`); `[pendiente]` quitado de UT-CFG-07; sin relanzamientos |
| 2026-11-24 | M02, M04 | ⚪ → 🟡 | — | — | Lanzados en paralelo en `../mailquery-wt/espera-del-lock-m02` y `-m04` desde el tip del lote |
| 2026-11-24 | M02 | 🟡 → 🟢 | `b1c558c`: 1671 tests, OK, 8 saltos (`.venv`) | [evidence/M02.md](evidence/M02.md) | Integrado en el lote 1 (`8948d6f`); `[pendiente]` quitado de UT-ST-08; sin relanzamientos |
| 2026-11-24 | M04 | 🟡 → 🟢 | `21d4de3`: 1665 tests, OK, 8 saltos (`.venv`) | [evidence/M04.md](evidence/M04.md) | Integrado en el lote 1 (`2765d59`); marcas de DOC-19 y DOC-06.02 quitadas; siete documentos consumidores a `actualizado`; sin relanzamientos |
| 2026-11-24 | M03 | ⚪ → 🟡 | — | — | Lanzado en `../mailquery-wt/espera-del-lock-m03` desde el tip del lote |
| 2026-11-24 | M03 | 🟡 → 🟢 | `c6b4fd0`: 1685 tests, OK, 8 saltos (`.venv`) | [evidence/M03.md](evidence/M03.md) | Integrado en el lote 1 (`b53234f`); HITL: dos desviaciones aprobadas por el dueño (D-12, D-13) y anotadas en la unidad; marcas de UT-CLI-15 y UT-MCP-13 quitadas; los once documentos consumidores, `actualizado`; sin relanzamientos |
| 2026-11-24 | Lote 1 | 🟡 → 🟡 | `513ed25`: 1685 tests, OK, 8 saltos (`.venv`) | — | Integrado en `feature/espera-del-lock` con `--no-ff`; rama empujada; PR único https://github.com/dayler/mailquery/pull/19; primera corrida de la matriz https://github.com/dayler/mailquery/actions/runs/45526401836 (macOS, Ubuntu e instaladores verdes; Windows en cola, cancelada por el push siguiente) |
| 2026-11-24 | Verificación de la implementación | sin verificar → verificado | 1685 tests, OK, 8 saltos | — | 1 revisión independiente: 15 partes de AC verificadas, 0 bloqueantes, 2 no bloqueantes: I-01 (registro sin el cierre del lote) corregido aquí; I-02 (`docs/tests/log-output.md` como documento consumidor) rechazado: solo recibió grupos de log y salida, no repite el contrato del lock |
| 2026-11-24 | Fase 3 | ⚪ → 🟡 | — | — | Unidad a `implementado`; filas RC-01 a RC-17 a `implementado`; pendientes: prueba manual del dueño (D-02, CL-11), conciliación y merge |
