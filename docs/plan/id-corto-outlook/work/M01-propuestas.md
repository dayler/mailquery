# M01 — Propuestas de cambio en documentos compartidos

Cambios necesarios fuera del alcance de escritura de M01. Los aplica el orquestador al integrar.

**Tabla: Propuestas de M01**

| Archivo | Ancla | Texto propuesto |
|---|---|---|
| `docs/tests/native-ids.md` | Filas `.01`–`.04` de UT-NID-01, en `**Tabla: Casos de UT-NID-01**` | Quitar la marca `[pendiente]` de las cuatro filas: los tests existen en `tests/test_native_ids.py` y pasan. |
| `docs/tests/native-ids.md` | Filas `.01`–`.09` de UT-NID-02, en `**Tabla: Casos de UT-NID-02**` | Quitar la marca `[pendiente]` de las nueve filas: los tests existen en `tests/test_native_ids.py` y pasan. |
| `docs/tests/native-ids.md` | Filas `.01`–`.11` de UT-NID-03, en `**Tabla: Casos de UT-NID-03**` | Quitar la marca `[pendiente]` de las once filas: los tests existen en `tests/test_native_ids.py` y pasan. |
| `docs/tests/native-ids.md` | Filas `.01`–`.05` de UT-NID-04, en `**Tabla: Casos de UT-NID-04**` | Quitar la marca `[pendiente]` de las cinco filas: los tests existen en `tests/test_native_ids.py` y pasan. |

Convención aplicada: `docs/tests/TEST-CATALOG.md` («un caso sin marca está implementado»); un caso con marca `[pendiente]` la pierde cuando el test existe y pasa.

No se propone ningún otro cambio en `docs/tests/`: los niveles de los casos no cambian, no hay goldens nuevos y `acceptance-matrix.md` no se modifica por este milestone.
