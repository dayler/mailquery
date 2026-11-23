# M03 — Propuestas de cambio en documentos compartidos

Cambios necesarios fuera del alcance de escritura de M03. Los aplica el orquestador al integrar.

**Tabla: Propuestas de M03**

| Archivo | Ancla | Texto propuesto |
|---|---|---|
| `docs/tests/plugins.md` | Filas `.01`–`.06` de UT-PL-05, en `**Tabla: Casos de UT-PL-05**` | Quitar la marca `[pendiente]` de las seis filas: los tests existen en `tests/test_plugins.py` y pasan. |
| `docs/tests/plugins.md` | Filas `.01`–`.08` de UT-PL-06, en `**Tabla: Casos de UT-PL-06**` | Quitar la marca `[pendiente]` de las ocho filas: los tests existen en `tests/test_plugins.py` y pasan. |

Convención aplicada: `docs/tests/TEST-CATALOG.md` («un caso sin marca está implementado»); un caso con marca `[pendiente]` la pierde cuando el test existe y pasa.

No se propone ningún otro cambio en `docs/tests/`: los niveles de los casos no cambian, no hay goldens nuevos y `acceptance-matrix.md` no se modifica por este milestone.
