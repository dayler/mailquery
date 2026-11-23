# M05 — Propuestas de cambio en documentos compartidos

Cambios necesarios fuera del alcance de escritura de M05. Los aplica el orquestador al integrar.

**Tabla: Propuestas de M05**

| Archivo | Ancla | Texto propuesto |
|---|---|---|
| `docs/tests/outlook-runtime.md` | Filas `.01`–`.06` de OL-31, en `**Tabla: Casos de OL-31**` | Quitar la marca `[pendiente]`: los seis casos existen en `tests/test_outlook.py` y pasan. |
| `docs/tests/outlook-runtime.md` | Filas `.01`–`.07` de OL-32, en `**Tabla: Casos de OL-32**` | Quitar la marca `[pendiente]`: los siete casos existen en `tests/test_outlook.py` y pasan. |
| `docs/tests/outlook-runtime.md` | Filas `.01`–`.06` de OL-33, en `**Tabla: Casos de OL-33**` | Quitar la marca `[pendiente]`: los seis casos existen en `tests/test_outlook.py` y pasan. |
| `docs/tests/state-backends.md` | Fila `.01` de UT-UID-03, en `**Tabla: Casos de UT-UID-03**` | Quitar la marca `[pendiente]`: el caso existe en `tests/test_uid.py` y pasa. |

Los casos que el orquestador marcó `[por actualizar]` (OL-14.01, OL-23.01, OL-23.03, OL-25.01,
UT-UID-01.05, UT-UID-02.03, UT-ATC-01.04, TC-02.02–.06 y TC-09) pasan con su nueva expectativa;
la marca `[por actualizar]` se puede retirar en la misma pasada.

Convención aplicada: `docs/tests/TEST-CATALOG.md` («un caso sin marca está implementado»).

No se propone ningún otro cambio en `docs/tests/`: los niveles de los casos no cambian, no hay
goldens nuevos fuera de `tests/fixtures/expected/outlook/` y `acceptance-matrix.md` no cambia
por este milestone.
