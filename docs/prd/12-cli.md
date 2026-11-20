---
aliases: ["Sección 12", "CLI"]
tags: [prd]
---

## 12. CLI

Invocación: `mailquery <comando> [opciones]`. Comandos, opciones y semántica son idénticos en ambas plataformas.

**Tabla: Comandos**

| Comando | Descripción | Salida |
|---------|-------------|--------|
| `doctor` | Diagnóstico del entorno y de la garantía read-only. | Informe de texto (JSON con `--json`; solo lo que falla con `--failures`) |
| `mailboxes` | Cuentas y sus carpetas, y si están incluidas; nombre, URL y contadores con `--fields` (RF-77, RF-78). | JSON con `accounts[]` (cada una con `mailboxes[]`) y `excluded_stores[]` |
| `search` | Búsqueda por metadatos y/o contenido. | JSON con `messages[]`; `groups[]` con `--group-by` (RF-70); solo el recuento con `--count` (RF-71) |
| `new` | Mensajes recibidos desde la última ejecución (cursor). | JSON con `messages[]`, `cursor` |
| `show <uid>` | Detalle de un mensaje. | JSON con `message` |
| `attachment <uid>` | Recupera adjuntos locales del mensaje (§12.11). | JSON con `uid`, `output_dir`, `count`, `attachments[]`, `warnings[]` |

