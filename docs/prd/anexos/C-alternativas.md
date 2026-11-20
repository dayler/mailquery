---
aliases: ["Anexo C", "Alternativas evaluadas por cliente"]
tags: [prd]
---

### Anexo C — Alternativas evaluadas por cliente

**Apple Mail (macOS)** — decisión: ADR-01.

**Tabla: Alternativas evaluadas para Apple Mail**

| Vía | Veredicto | Motivo |
|-----|-----------|--------|
| Leer el store en disco (`Envelope Index` + `.emlx`) | **Elegida** | Solo lectura estructural; sin credenciales ni red. |
| AppleScript | Descartada | El diccionario de Mail expone el estado de lectura como propiedad escribible: no hay garantía estructural de no mutar; exige Mail abierto y permiso de Automation. |
| IMAP | Descartada | Duplicaría credenciales, red y superficie de escritura (§2). |
| Spotlight | Descartada | `mdfind` no indexa el store (Anexo B). |

Herramientas existentes (p. ej. Fruitmail) confirman el camino técnico. `mailquery` se diferencia en que **no usa AppleScript en ningún caso** y **no ofrece ninguna operación de escritura**.

**Outlook clásico (Windows)** — decisión: ADR-11, ADR-13 y ADR-14.

**Tabla: Alternativas evaluadas para Outlook clásico**

| Vía | Veredicto | Motivo |
|-----|-----------|--------|
| **Outlook Object Model (OOM) vía COM** | **Elegida** | Única API local y soportada de lectura; funciona con stores en caché sin red. |
| Parsear `.ost`/`.pst` directamente | Descartada | Formato propietario; el `.ost` está bloqueado en exclusiva mientras Outlook corre. |
| Microsoft Graph / EWS | Descartada | Red, OAuth y credenciales; rompe I-1. |
| MAPI de terceros / Windows Search | Descartada | Dependencias nativas o índice parcial; no aportan frente al OOM. |

