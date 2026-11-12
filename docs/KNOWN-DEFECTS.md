# Defectos conocidos

Estado: **abierto**. Seguimiento de defectos que el dueño reconoce en el producto actual. Este documento no cambia el PRD: [`PRD.md`](PRD.md) describe el comportamiento actual y enlaza cada defecto como "Pendiente conocido".

| ID | Título | Estado | Registrado |
|----|--------|--------|------------|
| BUG-01 | `attachment` no extrae adjuntos de plugins `attachments: "remote"` | Abierto | 2026-11-12 |

---

## BUG-01 — `attachment` no extrae adjuntos de plugins `attachments: "remote"`

**Registrado:** 2026-11-12, por decisión del dueño (D-2 de [`plan/PLAN-RECONCILIATION-FIX.md`](plan/PLAN-RECONCILIATION-FIX.md)).

**Comportamiento esperado** (delta [`PRD-v2.1.md`](PRD-v2.1.md): tabla §0.2 fila "No objetivos / clientes soportados", §4 punto 2, RF-43, RF-46, ADR-22):

- Un plugin externo con `network: true` y `attachments: "remote"` obtiene los bytes del adjunto desde su origen. Su uso de red es responsabilidad del plugin.
- El núcleo no abre red. Valida, sanea, aplica límites, calcula el SHA-256 y escribe en la caché exactamente igual que con un driver `"local"` (RF-47).
- Un adjunto no recuperable responde `E_ATTACHMENT_UNAVAILABLE` con el `reason` del plugin (`network`, `not_local`, …), no `unsupported`.

**Comportamiento actual:**

- `mailquery attachment <driver>:<native_id>` con un driver `attachments: "remote"` falla con `E_ATTACHMENT_UNAVAILABLE`, exit 3, mensaje `attachment recovery is unsupported by driver '<driver>'`, antes de abrir el store. Es el mismo tratamiento que `attachments: "none"`.
- `show` sí lista los nombres que da el plugin.

**Origen:**

- `src/mailquery/cli.py:1054-1067` (`_require_attachment_capabilities`: `mode not in ("none", "remote")`).
- `docs/INTERFACES.md:1020` ("el núcleo no puede materializar adjuntos remotos").
- `docs/plan/milestones/M08-attachment-command-and-show.md`, UT-ATC-10.03, y su test `tests/test_cli.py:2936`.

**Impacto:** hoy ninguno en uso real, porque no existen plugins remotos. Impide implementar `mailquery-graph` u otro conector remoto con recuperación de adjuntos sin cambiar el núcleo.

**Corrección (trabajo del implementador, fuera del plan de conciliación):**

1. Admitir `"remote"` en `_require_attachment_capabilities` (solo `"none"` se rechaza) y pasar el flujo de bytes del plugin por el motor de adjuntos sin cambios.
2. Sustituir UT-ATC-10.03 por casos positivos (`--index` y `--all` desde un plugin `"remote"` falso) y uno negativo (`reason: network` ⇒ `E_ATTACHMENT_UNAVAILABLE`).
3. Actualizar `INTERFACES.md` y el milestone M08.
4. En `PRD.md`: recuperar el texto del delta en RF-43, RF-46, §4 y la fila 5 de la precedencia de `attachment`, y retirar la nota "Pendiente conocido".
