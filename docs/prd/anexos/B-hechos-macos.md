---
aliases: ["Anexo B", "Hechos verificados en macOS"]
tags: [prd]
---

### Anexo B — Hechos verificados en macOS (2026-11-01/02)

Tomados el 2026-11-01/02 (macOS 27.0.1 arm64, Apple Mail 16.0, store `V10`),
los que fijaron decisiones:

- La resolución de rutas por fórmula alcanza el 100 % (66.028/66.028).
- Gmail guarda todo en `[Gmail]/All Mail`; INBOX sale de las etiquetas, y los
  contadores de Mail en carpetas virtuales no son fiables (INBOX 36 vs 0
  reales) ⇒ membresía por etiqueta y contadores recalculados.
- Hay 86 grupos de duplicados por identificador global ⇒ dedupe (RF-06).
- Abrir la base viva en solo lectura no cambia inode, tamaño ni `mtime`, y las
  escrituras se rechazan; el modo `immutable` ignora el WAL ⇒ prohibido.
- `mdfind` no indexa el store ⇒ Spotlight descartado.
- La app del harness tiene FDA y `Terminal` no ⇒ el permiso es por app.

En el equipo de referencia (store vivo, ~66.000 mensajes, 2,5 GB): consulta de
metadatos de 500 filas en 0,1–1 ms, resolución `uid → ruta` en < 1 ms y
parseo de un `.emlx` medio en ~3,7 ms. Un escaneo de contenido sin acotar
costaría ~4 minutos: por eso RF-15 exige filtros y un máximo de candidatos
(`[search].max_scan`, §15.1). Los presupuestos p95 están en §19.

