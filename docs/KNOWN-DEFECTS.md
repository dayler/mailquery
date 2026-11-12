# Defectos conocidos

Estado: **abierto**. Seguimiento de defectos que el dueño reconoce en el producto actual. Este documento no cambia el PRD: [`PRD.md`](PRD.md) describe el comportamiento actual y enlaza cada defecto como "Pendiente conocido".

| ID | Título | Estado | Registrado |
|----|--------|--------|------------|
| BUG-01 | `attachment` no extrae adjuntos de plugins `attachments: "remote"` | Abierto | 2026-11-12 |

---

## BUG-01 — `attachment` no extrae adjuntos de plugins `attachments: "remote"`

**Registrado:** 2026-11-12, por decisión del dueño.

**Comportamiento esperado** (RF-43, RF-46, ADR-22):

- Un plugin externo con `network: true` y `attachments: "remote"` obtiene los bytes del adjunto desde su origen. Su uso de red es responsabilidad del plugin.
- El núcleo no abre red. Valida, sanea, aplica límites, calcula el SHA-256 y escribe en la caché exactamente igual que con un driver `"local"` (RF-47).
- Un adjunto no recuperable responde `E_ATTACHMENT_UNAVAILABLE` con el `reason` del plugin (`network`, `not_local`, …), no `unsupported`.

**Comportamiento actual:**

- `mailquery attachment <driver>:<native_id>` con un driver `attachments: "remote"` falla con `E_ATTACHMENT_UNAVAILABLE`, exit 3, mensaje `attachment recovery is unsupported by driver '<driver>'`, antes de abrir el store. Es el mismo tratamiento que `attachments: "none"`.
- `show` sí lista los nombres que da el plugin.

**Origen:**

- `src/mailquery/cli.py:1055-1067` (`_require_attachment_capabilities`: `mode not in ("none", "remote")`).
- `docs/INTERFACES.md:1019-1021` ("el núcleo no puede materializar adjuntos remotos").
- UT-ATC-10.03 ([`TEST-CATALOG.md`](TEST-CATALOG.md)) y su test `tests/test_cli.py:2935`.

**Impacto:** hoy ninguno en uso real, porque no existen plugins remotos. Impide implementar `mailquery-graph` u otro conector remoto con recuperación de adjuntos sin cambiar el núcleo.

**Corrección:**

1. Admitir `"remote"` en `_require_attachment_capabilities` (solo `"none"` se rechaza) y pasar el flujo de bytes del plugin por el motor de adjuntos sin cambios.
2. Sustituir UT-ATC-10.03 por casos positivos (`--index` y `--all` desde un plugin `"remote"` falso) y uno negativo (`reason: network` ⇒ `E_ATTACHMENT_UNAVAILABLE`).
3. Actualizar `INTERFACES.md` y `TEST-CATALOG.md`.
4. En `PRD.md`: admitir de nuevo los adjuntos remotos en RF-43, RF-46, §4 y la fila 5 de la precedencia de `attachment` (el texto anterior está en `docs/PRD-v2.1.md` del commit `3935ec5`), y retirar la nota "Pendiente conocido".
