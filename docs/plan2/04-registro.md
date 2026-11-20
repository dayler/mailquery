# Registro de ejecución y evidencia

Lo rellena quien implementa, hito a hito. Los logs completos quedan en el directorio de logs (sección 6, X-03); aquí solo se copia lo que la evidencia necesita.

## 1. Estado

**Tabla: Estado de los hitos**

| Hito | Estado | Commit | Fecha |
|---|---|---|---|
| M1 Preparación | hecho | — (sin cambios en el repositorio) | 2026-11-20 |
| M2 Partición | hecho | `29d7cbf` `docs(prd): split the PRD into one file per section` | 2026-11-20 |
| M3 Prueba de estructura | hecho | `05c0016` `test(docs): check the structure of the split PRD` | 2026-11-20 |
| M4 Referencias | hecho | `23d112b` `docs: point the references to the split PRD` | 2026-11-20 |
| M5 Verificación final | hecho; estado propuesto: listo para revisión del dueño | commit de este registro | 2026-11-20 |

## 2. Línea base (M1)

**Tabla: Línea base**

| Medida | Esperado | Obtenido |
|---|---|---|
| Blob de `docs/PRD.md` (P-02) | `ca24a3576fce0b6abd0c4f251aea5ebb313ad52a` | `ca24a3576fce0b6abd0c4f251aea5ebb313ad52a` (en `9a3080a`; ver X-01) |
| PRD base guardado | sí | sí: `PRD-base.md` en el directorio de logs, LF, 2991 líneas, 354.783 caracteres |
| Suite completa: resumen | — | `Ran 1427 tests`, `FAILED (failures=10, skipped=7)` |
| Fallos conocidos | — | `test_ut_cnt_02_10`, `test_ut_cnt_03_01`, `test_ut_cnt_03_02`, `test_ut_cnt_03_10`, `test_ut_cw_07_01`, `test_tc_01_01`, `test_tc_02_07`, `test_tc_06_02`, `test_pkg_01_03`, `test_pkg_02_01` |
| Tablas sin título | 14 | 14 |
| Referencias de sección sin encabezado | 0 | 0 (418 referencias) |
| IDs: máximos y huecos | O28, CU-09, RF-79, RNF-22, ADR-49, AC-62; sin huecos | igual |

## 3. Partición (M2)

**Tabla: Medición de R-01 y R-09**

| Medida | Obtenido | Límite |
|---|---|---|
| Líneas añadidas + eliminadas (R-01) | 123 + 33 = 156 | 299 |
| Caracteres de `docs/prd/` (R-09) | 375.780 (+5,92 %) | 390.261 (+10 %) |

**Tabla: Bloques del diff de reconstrucción**

| Bloque (líneas base) | Cambio E-n |
|---|---|
| 4, 6, 8 | E-01 (versión, fecha, estado) |
| 8–10 (+2 líneas) y 33–35 | E-01 (corte de la cabecera) y E-02 (título del historial, fila 2.3) |
| 39, 387, 780, 927, 1065, 1601, 1703, 1710, 1878, 2291, 2377, 2661, 2872, 2883 (+2 cada uno) | E-05 (14 títulos de tabla) |
| 70, 72, 87, 133, 505, 2339, 2408 | E-04 (7 enlaces relativos) |
| 704 | E-03 (árbol de carpetas) |
| 2800 (+9) | E-06 (lista de anexos) |
| 2973–2991 | E-07 (glosario) |

- `docs/prd/`: 47 archivos; el más largo, `15-configuracion.md`, 296 líneas.
- Tablas sin título en `docs/prd/`: 0. Archivos con BOM: 0.

## 4. Prueba de estructura (M3)

- DOC-14: `Ran 11 tests`, `OK`.
- Prueba negativa DOC-14.03 (fila RF-01 duplicada en el árbol de trabajo y restaurada con `git checkout`): falla con `RF: duplicated ['RF-01']`.
- Prueba negativa DOC-14.06 (archivo vacío `99-vacio.md`, borrado después): falla con `['99-vacio.md']`.
- Lo que DOC-14 inspecciona: 43 capítulos, 86 encabezados numerados, 5 de anexo, 406 referencias de sección, 62 enlaces y 44 filas del Índice.

## 5. Búsquedas y suite final (M4, M5)

**Tabla: Búsquedas de verificación**

| Búsqueda | Resultado |
|---|---|
| Enlaces a `PRD.md` fuera de las exclusiones | 1: `docs/KNOWN-DEFECTS.md:3` (X-07) |
| Anclas `PRD.md#L` | ninguno |
| `docs/PRD.md` en `CLAUDE.md` y los README | ninguno |
| `v2.2` en los README | ninguno |
| Citas de planes en `docs/prd/` | ninguno |
| Cambios en `src`, `docs/PRD.md`, `docs/plan`, `docs/archive`, `docs/PRD-v2.2.md`, `docs/KNOWN-DEFECTS.md`, `docs/tmp` | vacío |

- Suite completa: `Ran 1438 tests`, `FAILED (failures=10, skipped=7)`: los mismos 10 fallos de la línea base; los 11 tests nuevos son DOC-14.
- `git diff --stat 9a3080a...HEAD`: 62 archivos; fuera de `docs/prd/` solo los de la sección 5 del plan y `docs/plan2/`.
- R-01 y R-09 sobre el último commit: 156 líneas (límite 299); 375.780 caracteres, +5,92 % (límite 390.261).
- `docs/PRD.md`: blob `ca24a3576fce0b6abd0c4f251aea5ebb313ad52a`, sin cambios. `docs/KNOWN-DEFECTS.md`: sin tocar, su cambio pendiente sigue fuera de los commits.

## 6. Desviaciones y decisiones de ejecución

**Tabla: Desviaciones de ejecución**

| ID | Desviación | Motivo |
|---|---|---|
| X-01 | P-01 no se cumple: `develop` (`89f8441`) no incluye `feature/prd-v22-reconciliation`. La rama `feature/prd-chapters` sale de `9a3080a`, cuyo `docs/PRD.md` es el blob esperado. Las comparaciones contra `develop` de la sección 7.4 se hacen contra `9a3080a`. El cambio sin commitear de `docs/KNOWN-DEFECTS.md` se queda en el árbol de trabajo y no entra en ningún commit. | El dueño ordenó implementar el plan sin integrar antes esa rama |
| X-02 | `docs/PRD.md` no se sustituye ni se modifica, y DOC-14 no lo comprueba: sus casos son .01 a .11 de `03-prueba-estructura.md`. Se retiró de `02-textos.md` la sección que daba el texto de sustitución de `docs/PRD.md`; las secciones 6 y 7 actuales son las ediciones de README, `CLAUDE.md` y enlaces, y se aplicaron. | Orden del dueño del 2026-11-20 (D-06) |
| X-03 | Directorio de logs en el scratchpad de la sesión, fuera del checkout, en lugar de `../mailquery-plan2-logs/`. | Evitar escribir fuera del directorio de trabajo |
| X-04 | Los tres archivos de la 12.5 se llaman `12.05-1-contrato-json.md`, `12.05-2-ejemplos-show-attachment.md` y `12.05-3-ejemplos-contenido-salida.md`. | Con los nombres del plan, el orden alfabético invertía los dos archivos de ejemplos (D-01) |
| X-05 | Límite de caracteres R-09 añadido. | Orden del dueño del 2026-11-20 |
| X-06 | El script de la sección 7.2 mide también R-09. | R-09 |
| X-07 | `docs/KNOWN-DEFECTS.md:3` tiene un enlace markdown a `PRD.md` (la sección 7 de `02-textos.md` decía que no). No se cambia: R-04 y orden del dueño de no tocar ese archivo. El enlace sigue funcionando porque `docs/PRD.md` existe (D-06). | R-04 |
| X-08 | En `00-plan.md`, el límite del script de la sección 7.2 se calcula como base + base // 10, y la tabla de riesgos cita DOC-14.11 en lugar de DOC-14.12. | Expresar el límite como incremento máximo; corregir la referencia al caso de BOM |
| X-09 | Contra D-12, las menciones de texto `PRD.md` que nombran el PRD vigente pasan a "PRD" (o "el PRD"/"del PRD" según la frase) en `docs/INTERFACES.md`, `docs/security/threat-model.md`, `docs/PERFORMANCE-BACKLOG.md`, `docs/ROADMAP.md`, nueve archivos de `docs/tests/`, `tests/test_state.py` y `tests/test_multidriver.py` (83 cambios en 17 archivos). No cambian `docs/KNOWN-DEFECTS.md` (R-04), los documentos históricos (`docs/archive/`, `docs/PRD-v2.2.md`) ni la ADR-26 de `docs/prd/08-adr.md`, que es un registro de decisión. | Orden del dueño del 2026-11-20 de actualizar los documentos que referencian el PRD |
