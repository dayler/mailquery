# Registro de ejecución y evidencia

Lo rellena quien implementa, hito a hito. Los logs completos quedan en el directorio de logs (sección 6, X-03); aquí solo se copia lo que la evidencia necesita.

## 1. Estado

**Tabla: Estado de los hitos**

| Hito | Estado | Commit | Fecha |
|---|---|---|---|
| M1 Preparación | hecho | — (sin cambios en el repositorio) | 2026-11-20 |
| M2 Partición | hecho | ver `git log` de la rama (`docs(prd): split the PRD into one file per section`) | 2026-11-20 |
| M3 Prueba de estructura | pendiente | — | — |
| M4 Referencias | pendiente | — | — |
| M5 Verificación final | pendiente | — | — |

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

- `docs/prd/`: 47 archivos; el más largo, `15-configuracion.md`, 295 líneas.
- Tablas sin título en `docs/prd/`: 0. Archivos con BOM: 0.

## 4. Prueba de estructura (M3)

- DOC-14: not run
- Prueba negativa DOC-14.03 (fila RF duplicada en el árbol de trabajo y restaurada): not run
- Prueba negativa DOC-14.06 (archivo sin enlace desde la portada, borrado después): not run

## 5. Búsquedas y suite final (M4, M5)

**Tabla: Búsquedas de verificación**

| Búsqueda | Resultado |
|---|---|
| Enlaces a `PRD.md` fuera de las exclusiones | not run |
| Anclas `PRD.md#L` | not run |
| `docs/PRD.md` en `CLAUDE.md` y los README | not run |
| `v2.2` en los README | not run |
| Citas de planes en `docs/prd/` | not run |
| Cambios en `src`, `docs/PRD.md`, `docs/plan`, `docs/archive`, `docs/PRD-v2.2.md`, `docs/KNOWN-DEFECTS.md`, `docs/tmp` | not run |

- Suite completa: not run
- `git diff --stat 9a3080a...HEAD`: not run

## 6. Desviaciones y decisiones de ejecución

**Tabla: Desviaciones de ejecución**

| ID | Desviación | Motivo |
|---|---|---|
| X-01 | P-01 no se cumple: `develop` (`89f8441`) no incluye `feature/prd-v22-reconciliation`. La rama `feature/prd-chapters` sale de `9a3080a`, cuyo `docs/PRD.md` es el blob esperado. Las comparaciones contra `develop` de la sección 7.4 se hacen contra `9a3080a`. El cambio sin commitear de `docs/KNOWN-DEFECTS.md` se queda en el árbol de trabajo y no entra en ningún commit. | El dueño ordenó implementar el plan sin integrar antes esa rama |
| X-02 | `docs/PRD.md` no se sustituye ni se modifica; DOC-14 deja de comprobarlo (casos .05, .11 y .12 del plan revisado) y la sección 6 de `02-textos.md` se retira. | Orden del dueño del 2026-11-20 (D-06) |
| X-03 | Directorio de logs en el scratchpad de la sesión, fuera del checkout, en lugar de `../mailquery-plan2-logs/`. | Evitar escribir fuera del directorio de trabajo |
| X-04 | Los tres archivos de la 12.5 se llaman `12.05-1-contrato-json.md`, `12.05-2-ejemplos-show-attachment.md` y `12.05-3-ejemplos-contenido-salida.md`. | Con los nombres del plan, el orden alfabético invertía los dos archivos de ejemplos (D-01) |
| X-05 | Límite de caracteres R-09 añadido. | Orden del dueño del 2026-11-20 |
| X-06 | El script de la sección 7.2 mide también R-09. | R-09 |
