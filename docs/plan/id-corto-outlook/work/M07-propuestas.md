# M07 — Propuestas de cambio en documentos compartidos

Cambios necesarios fuera del alcance de escritura de M07. Los aplica el orquestador al integrar.

**Tabla: Propuestas de M07**

| Archivo | Ancla | Texto propuesto |
|---|---|---|
| `docs/ROADMAP.md` | Sección `## 10. Para publicar 3.0.0`, primera frase | Sustituir `con la versión \`3.0.0a1\`` por `con la versión \`3.0.0a2\``. |
| `docs/ROADMAP.md` | Sección `## 10. Para publicar 3.0.0`, punto 1 | Sustituir `Subir la versión de \`3.0.0a1\` a \`3.0.0\`` por `Subir la versión de \`3.0.0a2\` a \`3.0.0\``. |
| `docs/tests/docs-packaging.md` | Filas `.01`–`.04` de DOC-16, en `**Tabla: Casos de DOC-16**` | Quitar la marca `[pendiente]`: los cuatro casos existen en `tests/test_packaging.py` y pasan. |
| `docs/tests/end-to-end.md` | Filas `.01` y `.07` de TC-01 y TC-02 | Quitar la marca `[por actualizar]`: los goldens `doctor` y `outlook/doctor` ya llevan `pkg 3.0.0a2` y ambos casos pasan. |

Justificación de las dos filas de `docs/ROADMAP.md`: son el único texto vigente fuera de
`docs/prd/`, `docs/changes/` y los documentos consumidores que conserva `3.0.0a1`; las
apariciones en `docs/KNOWN-DEFECTS.md` (observaciones fechadas 2026-11-17 y 2026-11-18) y en
`docs/PERFORMANCE-BACKLOG.md` (medición del 2026-11-14) son registros históricos y no cambian.

Observación fuera de alcance, sin propuesta de texto: el comentario de `tests/test_smoke.py:977`
dice «show never writes: the cache directory must not exist yet»; el caso sigue siendo correcto
(comprueba que no existe la caché de adjuntos), y `show` ahora solo escribe en la caché de ids
nativos. No se toca porque `tests/test_smoke.py` no está en el alcance de escritura de M07.
