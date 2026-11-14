# M14 — SMOKE en equipos reales, auditoría documental y cierre

**Lote:** I4 · rama del lote `integration/i4-mailboxes-doctor-close` · **Oleada:** W9 (sola)
**Rama:** `feature/m14-smoke-closure`, creada desde la punta de `integration/i4-mailboxes-doctor-close` (con M12 y M13 integrados) · **Worktree:** `../mailquery-wt/m14`
**Estado:** 🟢 (fases F1–F6 cerradas; pendiente de integración) (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Cerrar la fase P4: ampliar SMOKE para los AC que dependen del cliente real (HITL-03), ejecutarlo en este Windows (Outlook clásico) y en el Mac del dueño, registrar las mediciones en `PERFORMANCE-BACKLOG.md`, auditar los documentos consumidores contra los textos obsoletos de CL-05 y dejar el registro de conciliación de `PRD-v2.2.md` en su estado final antes de la conciliación de `PRD.md` (tarea futura, fuera de este plan).

## 2. Alcance

**Dentro:**

1. **SMOKE (`tests/test_smoke.py`), solo lectura, `HOME`/`USERPROFILE` temporales, mismas reglas de salto que hoy:**
   - **SMOKE-NEW.07** (existente, se amplía): los presupuestos p95 de `PRD.md` sección 19 se miden con la salida por defecto de 3.0.0: `search` con la fila mínima, `search --fields snippet` (mismo presupuesto que `search`, RNF-23), `new`, `show`, `search --text` y `mailboxes` sin `--fields` (sin contadores). Solo `mailboxes --fields total,unread` es una medición informativa, sin aserción.
   - **SMOKE-NEW.08** (nuevo): contra el cliente real, `search`, `new`, `show` y `attachment` (si hay un adjunto local, como SMOKE-ATT) llevan `content_notice`; las filas de `search`/`new` tienen los seis campos; `search --count` y `search --group-by from --limit 1` terminan con exit 0.
   - **SMOKE-NEW.09** (nuevo): `show` de un mensaje con HTML devuelve `body_text` sin error (en Windows, `BodyFormat`/`HTMLBody` leídos por la lista blanca COM; en macOS, las partes HTML del `.emlx`); la lectura de cabeceras de A6 no abre ventanas ni cambia contadores de no leídos.
   - **SMOKE-NEW.10** (nuevo): `doctor --json --failures` con exit 0, `plugins: []` y, con la configuración de la prueba, `checks: []`.
   - Los contadores de no leídos del cliente real no cambian tras cada caso (como SMOKE-NEW hoy).
2. **Ejecución:**
   - **Windows (este equipo):** la ejecuta el subagente con Outlook clásico abierto: `python -B -m unittest tests.test_smoke -v`, sin otras corridas en marcha (sección 8.3 del plan maestro).
   - **macOS:** tras la fase F1, el orquestador empuja `feature/m14-smoke-closure` (`git push -u origin feature/m14-smoke-closure`; sin PR, así que no dispara CI; HITL-08). El dueño la ejecuta en su Mac (HITL-03) desde esa rama con `python3 -B -m unittest tests.test_smoke -v` (Terminal con Acceso total al disco, entorno con `css-inline`); el orquestador recoge el resultado según la regla de redacción del punto siguiente y el tamaño del store (número de mensajes y de carpetas) para A-02. La rama remota se borra al integrar M14. Si el Mac no está disponible, SMOKE de macOS queda "saltado con motivo" y A-01/A-02 pasan a pendiente (RK-10).
   - **Redacción (regla 6 del plan maestro):** de SMOKE solo se registran el nombre del test, el estado, la duración y el p95; direcciones, etiquetas de cuenta, nombres de carpeta, asuntos, uids reales y rutas de `HOME` se sustituyen por `<redacted>`/`<HOME>` antes de commitear la evidencia (el repositorio es público).
   - **CI:** la salida del paso "Check css-inline wheels" de la corrida verde del PR del lote I1 (AC-H15) ya está en el registro de ejecución desde el cierre de I1; la evidencia de M14 la referencia.
3. **`docs/PERFORMANCE-BACKLOG.md`:** nueva medición (fecha, equipo, versión `3.0.0a0`, commit) de los p95 de 3.0.0 en Windows y macOS, con `mailboxes` sin contadores y con `--fields total,unread`; el coste de las cabeceras de A6 en Outlook (RK-08); el pendiente de `mailboxes` limitado a los contadores (si M12 ya lo dejó, solo se actualizan las cifras). Si un presupuesto no se cumple, se registra como deuda abierta y se devuelve al orquestador (HITL) antes de cerrar.
4. **Auditoría documental (CL-04/CL-05, sin tocar `PRD.md`):** búsqueda de cada texto obsoleto de la lista CL-05 de `PRD-v2.2.md` sección 0.4 en `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `skills/README.md`, `docs/recipes/*`, `docs/config.example.toml`, `docs/security/threat-model.md`, `docs/KNOWN-DEFECTS.md`, `docs/PERFORMANCE-BACKLOG.md`, `docs/ROADMAP.md`, `scripts/install.sh`, `scripts/install.ps1` y en las ayudas del CLI; se corrige lo que quede (texto en presente sobre el producto implementado; el anexo de seguridad sigue citando `PRD-v2.2.md`, CL-07 es de la conciliación). La misma búsqueda en `docs/INTERFACES.md` y `docs/TEST-CATALOG.md` se entrega como lista de cambios para el orquestador. `docs/ROADMAP.md`: solo se tachan las ideas y decisiones que el incremento incorpora (`--fields` y BUG-01 ya están tachados; se verifica).
   - **Guardia automática:** `_STALE_TEXT_PATTERNS` de `tests/test_integration.py` (usado por DOC-01.04, DOC-02.02, DOC-05.04 y TC-07.03) añade `list accounts, folders, counters`, `standard library\s+only` y `solo biblioteca\s+estándar` (el texto español está partido en dos líneas) y `preflight`; antes de añadir cada patrón se comprueba con `grep` que, tras M01 y M13, ningún documento que recorre la guardia lo usa con un sentido vigente. `Counters are recalculated` no se añade: el epílogo de `mailboxes` puede seguir diciéndolo de los contadores pedidos con `--fields`.
5. **Comprobación final de trazabilidad:** cada AC de la matriz del plan maestro tiene grupos con evidencia; la lista de AC sin evidencia (si queda alguno) se devuelve al orquestador. Además:
   - Los barridos de solo lectura (TC-03.01 en `tests/test_readonly.py` y OL-30 en `tests/test_outlook.py`) recorren todas las opciones nuevas: `--strip-links`, `--fields` (en `search`, `new`, `show` y `mailboxes`), `--group-by`, `--count` y `doctor --failures`; si falta alguna, se devuelve al milestone que la introdujo (regla 9 del plan maestro).
   - Desviaciones: cada desviación de `PRD-v2.2.md` aprobada por el dueño durante la implementación está escrita en su texto normativo con su fila del historial (HITL-06) y su fila de la sección 0.5 está en `Implementado con desviación`; una desviación sin registrar bloquea el cierre de M14.
   - Destino de las decisiones del plan (sin citar el plan): bloque para `INTERFACES.md` con D-06, D-07, D-09, D-10 y D-25, redactados como contrato interno; D-03, D-04, D-05, D-17, D-19, D-20, D-22, D-23 y D-24 (comportamiento observable no literal en `PRD-v2.2.md`) figuran, reformulados, en la nota de su fila de la sección 0.5 (normalmente ya los copió cada commit de integración; M14 lo verifica y entrega lo que falte); los pendientes de A-01, A-02 y A-07 van a `docs/PERFORMANCE-BACKLOG.md`; A-08 va a la nota de "Responsabilidades de módulos".

**Fuera:** conciliar `PRD.md` (CL-01, CL-02, CL-03, CL-07, CL-08: tarea futura); cambiar código de producto (un defecto encontrado aquí devuelve su milestone a 🟡 según la regla 9 del plan maestro); borrar `docs/plan/` (lo decide el dueño al terminar todo el trabajo).

## 3. Dependencias y ACs

- **Entrada:** M01–M13 integrados en la rama del lote.
- **Salida:** cierre de P4 y del lote I4.
- **ACs:** AC-H15 (p95 y wheels), AC-O15 (p95 de `mailboxes`); verificación final de todos los AC.

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `tests/test_smoke.py`, `tests/test_integration.py` (solo `_STALE_TEXT_PATTERNS`) |
| Modifica | `docs/PERFORMANCE-BACKLOG.md` |
| Modifica si la auditoría lo exige | `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/recipes/*`, `docs/config.example.toml`, `docs/security/threat-model.md`, `docs/KNOWN-DEFECTS.md`, `docs/ROADMAP.md` |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 6, 7, 8 y auditoría), `docs/INTERFACES.md` (auditoría y decisiones D-06, D-07, D-09, D-10, D-25), registro de conciliación final y línea "Estado" de `PRD-v2.2.md` |

## 5. Refactorizaciones previas

Ninguna.

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — SMOKE | SMOKE-NEW.07 ampliado, SMOKE-NEW.08–10 | 🟢 |
| F2 — Windows | Corrida en este equipo | 🟢 (saltada con motivo: host macOS sin Outlook clásico) |
| F3 — macOS | Corrida en el Mac del dueño (HITL-03) | 🟢 |
| F4 — Rendimiento | `PERFORMANCE-BACKLOG.md` | 🟢 |
| F5 — Auditoría | CL-05 en documentos consumidores; guardia `_STALE_TEXT_PATTERNS`; listas para `INTERFACES.md` y `TEST-CATALOG.md` | 🟢 |
| F6 — Cierre | Suite completa, cobertura, trazabilidad, barridos de solo lectura, desviaciones, destino de las decisiones, evidencia cruda, bloques | 🟢 |

## 7. Tests

**SMOKE-NEW — Cliente real** (grupo existente) · `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .07 | B | p95 de `doctor`, `mailboxes` (sin contadores), `search` (fila mínima), `search --fields snippet`, `new`, `show` y `search --text` dentro de los presupuestos de `PRD.md` sección 19 de la plataforma; medición informativa de `mailboxes --fields total,unread`. |
| .08 | P | `content_notice` en `search`, `new`, `show` (y `attachment` si hay un adjunto local); filas de seis campos; `search --count` y `search --group-by from --limit 1` con exit 0. |
| .09 | P | `show` de un mensaje con HTML da `body_text` sin error y sin cambiar los contadores de no leídos. |
| .10 | P | `doctor --json --failures` con exit 0 y `plugins: []`. |

Se saltan con los mismos motivos de `TEST-CATALOG.md` sección 6 (Linux, Windows sin Outlook clásico abierto, macOS sin store, CI, sin `pipx`).

Comandos:

```bash
python -B -m unittest tests.test_smoke -v
python -B -m unittest discover -s tests -t . -k test_doc_01_
python -B -m unittest discover -s tests -t . -k test_doc_02_
python -B -m unittest discover -s tests -t . -k test_doc_05_
python -B -m unittest discover -s tests -t . -k test_tc_07_
python -B -m unittest discover -s tests -t . -v
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
```

## 8. Tests existentes afectados

- SMOKE-NEW.07 (se amplía).
- SMOKE-NEW.01 y .06 (los ajustó M12 a la salida agrupada) y SMOKE-NEW.02–.04 (los ajustó M10 a la fila por defecto): M14 entrega su texto final para `TEST-CATALOG.md` sección 8.
- DOC-01.04, DOC-02.02, DOC-05.04 y TC-07.03, por los patrones nuevos de `_STALE_TEXT_PATTERNS`.

## 9. Documentación

- `docs/PERFORMANCE-BACKLOG.md` (sección 2, punto 3).
- Documentos de la auditoría (sección 2, punto 4).
- Bloques para `TEST-CATALOG.md`: sección 6 (SMOKE de 3.0.0), sección 8 (textos finales de SMOKE-NEW.01–10 y de los casos DOC y TC que usan `_STALE_TEXT_PATTERNS`), sección 7 (filas finales de AC-H15 y AC-O15) y cambios de la auditoría.
- Bloques para `INTERFACES.md`: cambios de la auditoría y D-06, D-07, D-09, D-10 y D-25 redactados como contrato interno, sin citar el plan.
- `docs/PERFORMANCE-BACKLOG.md`: también los pendientes de A-01, A-02 y A-07.

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación final: cada una de las 32 filas de la sección 0.2 en `Implementado y documentado`, `Implementado con desviación` (con la desviación ya escrita en el texto normativo, HITL-06) o `Sin cambio de código` ("Contrato JSON único" (F1, F3) y "Cambios visibles en 3.0.0" (F1, F3): solo afectan al texto de `PRD.md`); "Rendimiento" (F3) con la referencia a la medición de `PERFORMANCE-BACKLOG.md`; "Responsabilidades de módulos" (F1, F2, F3) con la nota de A-08 (`load_headers`, `attachments/active_content.py`); las notas de comportamiento observable de la sección 2, punto 5, verificadas.
- Línea "Estado" de `PRD-v2.2.md` (HITL-06): de "No implementado." a "implementado en `develop`, pendiente de conciliación".
- Checklist: CL-04, CL-05 (documentos consumidores) y CL-06 en su estado final; CL-01, CL-02, CL-03, CL-07 y CL-08 quedan para la conciliación de `PRD.md`.
- Tabla de supersesión: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) resultado de `tests.test_smoke` en Windows y en macOS (o el motivo del salto) según la regla de redacción (nombre del test, estado, duración y p95), con el tamaño de los stores; referencia a la salida del paso de wheels de la CI de I1 en el registro de ejecución; (c) goldens: ninguno; (d) casos SMOKE nuevos y ampliados con AC; (e) `git diff --check` y `git diff --stat integration/i4-mailboxes-doctor-close...HEAD`; (f) resultado de la auditoría (texto, archivo, corrección), presupuestos incumplidos si los hay, AC sin evidencia, opciones que faltan en los barridos de solo lectura, desviaciones y su registro, riesgos, decisiones y pendientes; (g) cobertura: `coverage report` completo en el host de referencia (este Windows). Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] SMOKE-NEW.07 ampliado y SMOKE-NEW.08–10 escritos.
- [ ] SMOKE verde en este Windows; verde en el Mac del dueño o saltado con motivo registrado.
- [ ] `PERFORMANCE-BACKLOG.md` con las mediciones de 3.0.0.
- [ ] Ningún texto obsoleto de CL-05 en los documentos consumidores (salvo `PRD.md`).
- [ ] Todos los AC con evidencia (o la lista de faltantes devuelta al orquestador).
- [ ] TC-03.01 y OL-30 recorren todas las opciones nuevas.
- [ ] Ninguna desviación de `PRD-v2.2.md` sin registrar; decisiones del plan con destino permanente (sección 2, punto 5).
- [ ] Cobertura (D-21, HITL-07): total ≥ 85 % en el host de referencia y en los 12 jobs `test-suite` del PR del lote I4.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote; `tests/test_readonly.py` y OL-30 verdes.
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 — SMOKE | SMOKE-NEW.07 ampliado (`search --fields snippet` y medición informativa de `mailboxes --fields total,unread`) y SMOKE-NEW.08–.10 escritos; los 15 casos de `SmokeTest` verdes solos contra Apple Mail. |
| 2026-11-14 | F2 — Windows | Saltada con motivo: este host es macOS y no tiene Outlook clásico; la corrida de Windows y SMOKE-ATT-OL no aplican aquí. |
| 2026-11-14 | F3 — macOS | `tests.test_smoke` completa verde en el Mac: 19 casos (INSTALL, NEW y ATT-AM), 0 fallos; p95 de `mailboxes` 0,096–0,130 s y de `show` 0,045–0,053 s, dentro de presupuesto. |
| 2026-11-14 | F4 — Rendimiento | `PERFORMANCE-BACKLOG.md` con la medición de 3.0.0 (44 carpetas y 148.678 mensajes), la variante con contadores como deuda informativa y Windows pendiente de equipo. |
| 2026-11-14 | F5 — Auditoría | Textos de CL-05 revisados en los documentos consumidores; corregidos `docs/ROADMAP.md` y `docs/PERFORMANCE-BACKLOG.md`; guardia con cuatro patrones nuevos y DOC-01.04, DOC-02.02, DOC-05.04 y TC-07.03 verdes. |
| 2026-11-14 | F6 — Cierre | Suite completa `Ran 1428`, `OK (skipped=7)`; cobertura total 91,3 %; TC-03.01 y OL-30 verdes; informe con evidencia, auditoría, trazabilidad y bloques. |
