# Defectos conocidos

Estado: **sin defectos abiertos**. Seguimiento de defectos que el dueño reconoce en el producto actual. Este documento no cambia el PRD: [`PRD.md`](PRD.md) describe el comportamiento actual y enlaza cada defecto como "Pendiente conocido".

| ID | Título | Estado | Registrado |
|----|--------|--------|------------|
| BUG-01 | `attachment` no extrae adjuntos de plugins `attachments: "remote"` | Cerrado el 2026-11-14 | 2026-11-12 |

---

## BUG-01 — `attachment` no extrae adjuntos de plugins `attachments: "remote"`

**Registrado:** 2026-11-12, por decisión del dueño. **Cerrado:** 2026-11-14,
corregido en `3.0.0` (en desarrollo).

**Comportamiento esperado** (RF-43, RF-46, ADR-22):

- Un plugin externo con `network: true` y `attachments: "remote"` obtiene los bytes del adjunto desde su origen. Su uso de red es responsabilidad del plugin.
- El núcleo no abre red. Valida, sanea, aplica límites, calcula el SHA-256 y escribe en la caché exactamente igual que con un driver `"local"` (RF-47).
- Un adjunto no recuperable responde `E_ATTACHMENT_UNAVAILABLE` con el `reason` del plugin (`network`, `not_local`, …), no `unsupported`.

**Comportamiento anterior (hasta la corrección):**

- `mailquery attachment <driver>:<native_id>` con un driver `attachments: "remote"` fallaba con `E_ATTACHMENT_UNAVAILABLE`, exit 3, mensaje `attachment recovery is unsupported by driver '<driver>'`, antes de abrir el store. Era el mismo tratamiento que `attachments: "none"`.
- `show` ya listaba los nombres que da el plugin.

**Origen:**

- `_require_attachment_capabilities` de `cli.py`, que rechazaba `mode not in ("none", "remote")`.
- `docs/INTERFACES.md`, sección de `cli.py` ("el núcleo no puede materializar adjuntos remotos").
- UT-ATC-10.03 ([`TEST-CATALOG.md`](TEST-CATALOG.md)), retirado; lo sustituyen `UT-RMT-01`–`UT-RMT-03`.

**Impacto:** ninguno en uso real mientras no existan plugins remotos, pero impedía implementar `mailquery-graph` u otro conector remoto con recuperación de adjuntos sin cambiar el núcleo.

**Corrección aplicada:** `_require_attachment_capabilities` rechaza solo `attachments: "none"` (con el hint que pide declarar un driver `"local"` o `"remote"`); un driver `"remote"` entrega sus bytes al mismo motor de adjuntos, con el mismo bloqueo, límites, SHA-256, staging, caché, manifiesto, `--force` y A7. Un fallo de origen del plugin se sigue reportando con su `reason` (`network`, `not_local`, …) como `E_ATTACHMENT_UNAVAILABLE`. UT-ATC-10.03 se retiró y lo sustituyen los casos `UT-RMT-01` a `UT-RMT-03`; `INTERFACES.md` y `TEST-CATALOG.md` se actualizan con la integración. En `PRD.md`, la conciliación debe admitir de nuevo los adjuntos remotos en RF-43, RF-46, §4 y la fila 5 de la precedencia de `attachment` (el texto anterior está en `docs/PRD-v2.1.md` del commit `3935ec5`) y retirar la nota "Pendiente conocido".
