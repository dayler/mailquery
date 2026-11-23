# M06 — Propuestas de cambio en documentos compartidos

Cambios necesarios fuera del alcance de escritura de M06. Los aplica el orquestador al integrar.

**Tabla: Propuestas de M06**

| Archivo | Ancla | Texto propuesto |
|---|---|---|
| `docs/tests/outlook-runtime.md` | Fila `.01` de OL-30, en `**Tabla: Casos de OL-30**` | Retirar `[por actualizar]`: el barrido incluye `show --show-native-id` y sus cinco casos pasan. |
| `docs/tests/outlook-runtime.md` | Filas `.01`–`.04` de OL-34, en `**Tabla: Casos de OL-34**` | Retirar `[pendiente]`: los cuatro casos existen en `tests/test_outlook.py` y pasan. |
| `docs/tests/outlook-runtime.md` | Filas `.01`–`.15` de OL-35, en `**Tabla: Casos de OL-35**` | Retirar `[pendiente]`: los quince casos existen en `tests/test_outlook.py` y pasan (un caso por causa; el timeout en subproceso). |
| `docs/tests/outlook-runtime.md` | Filas `.01`–`.03` de OL-36, en `**Tabla: Casos de OL-36**` | Retirar `[pendiente]`: los tres casos existen en `tests/test_outlook.py` y pasan. |
| `docs/tests/smoke.md` | Fila `.11` de SMOKE-NEW, en `**Tabla: Casos de SMOKE-NEW.11**` | Retirar `[pendiente]`: el caso existe en `tests/test_smoke.py`; en macOS comprueba que `search` y `show` no crean `db/cache.db`, en Windows la forma del uid, `db/cache.db`, `--show-native-id` y los no leídos. |
| `docs/tests/outlook-data.md` | Fila `.03` de OL-23, en `**Tabla: Casos de OL-23**` | Retirar `[por actualizar]`: el caso se limita al `EntryID` que no coincide con ningún store, como dice su definición; el item inexistente en un store montado es ausencia confirmada y se cubre en OL-35.01. |
| `docs/tests/state-backends.md` | Fila `.03` de OL-23, en la lista de tests que cambian | Sin cambio de texto: la definición («no coincide con ningún store») ya coincide con el test. Solo se puede retirar la referencia a OL-23.03 como pendiente al conciliar. |

Convención aplicada: `docs/tests/TEST-CATALOG.md` («un caso sin marca está implementado»).

No se propone ningún otro cambio en `docs/tests/`: los niveles de los casos no cambian, no hay
goldens nuevos ni modificados, y `docs/plan/id-corto-outlook/trazabilidad.md` no cambia por este
milestone (el orquestador pasa las filas de RC a `implementado` en F4, como dice el archivo de M06).
