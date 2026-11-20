---
aliases: ["Sección 19", "Rendimiento"]
tags: [prd]
---

## 19. Rendimiento

**Tabla: Presupuestos p95 por backend**

| Operación | Apple Mail (macOS) | Outlook (Windows) |
|-----------|--------------------|--------------------------------|
| `doctor` (sin las llamadas a los plugins, RF-79) | < 2 s | < 3 s |
| `mailboxes` (sin `--fields total` ni `unread`, RF-78) | < 150 ms | < 1 s |
| `search` metadatos (página de 20, sin `--fields` o con `--fields snippet`, RNF-22) | < 500 ms | < 1 s |
| `new` (típico ≤ 50 mensajes nuevos) | < 500 ms | < 1 s |
| `show` | < 150 ms | < 500 ms |
| `search --text` acotado (≤ 500 candidatos) | < 3 s | < 10 s |

**Pendiente conocido (abierto):** el acierto de caché de `attachment` en Outlook supera su
presupuesto, y `mailboxes --fields total` o `unread` tiene el coste del recuento real, sin
presupuesto (RNF-22). El análisis, la medición reproducible y los criterios de cierre están en
[`docs/PERFORMANCE-BACKLOG.md`](../PERFORMANCE-BACKLOG.md).

**Tabla: Presupuesto p95 de `attachment`**

| Operación | Apple Mail | Outlook | Plugin local | Plugin remoto |
|-----------|------------|---------|--------------|---------------|
| `attachment` acierto de caché (archivo local) | < 50 ms | < 50 ms | < 50 ms | < 50 ms |
| `attachment` 1 adjunto ≤ 5 MB | < 200 ms | < 600 ms | sin objetivo fijo | sin presupuesto (red) |
| `attachment --all` de N adjuntos | presupuesto × N (lineal) | presupuesto × N (lineal) | sin objetivo fijo | sin presupuesto (red) |

Apple Mail y Outlook tienen presupuesto; fuera del acierto de caché, un plugin local solo está acotado por RNF-21 y un plugin remoto no tiene objetivo de latencia. El timeout de §7/RNF-21 acota el peor caso.

---

