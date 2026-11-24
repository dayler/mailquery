---
aliases: ["PRD", "Índice del PRD"]
tags: [prd]
---

# PRD — mailquery

**Producto:** `mailquery` — CLI de solo lectura para leer y buscar el correo del cliente de escritorio local desde un harness de agentes (DeepSeek u otro similar): **Apple Mail en macOS** y **Outlook clásico en Windows**, ampliable con plugins de backend.
**Versión del documento:** 2.6 (un solo PRD para todas las plataformas, en un archivo por sección; incorpora plugins de backend, la recuperación local de adjuntos, el endurecimiento del contenido no confiable, la corrección de defectos de adjuntos, la salida a medida, el id corto de mensaje en Outlook, el servidor MCP por stdio y el log en JSON).
**Versión del paquete:** `3.0.0` (en `develop` se anuncia la pre-release `3.0.0a3`; sin publicar, §22.3).
**Fecha:** 2026-11-24.
**Repositorio:** <https://github.com/dayler/mailquery>.
**Estado:** describe el producto implementado en `develop`; el paquete sigue sin publicar (§22.3). Las aprobaciones y las conciliaciones de cada versión están en [HISTORIAL.md](HISTORIAL.md).

## Cómo se organiza

- El PRD es un conjunto de archivos. La sección N está en `NN-*.md`, la subsección 12.M en `12.MM-*.md` y el anexo X en `anexos/X-*.md`. Si una sección ocupa varios archivos, todos llevan su prefijo.
- Ningún archivo supera 300 líneas. Si un cambio hace que uno las supere, se parte en varios archivos con el mismo prefijo y se actualiza la tabla "Archivos del PRD".
- La numeración de secciones y los IDs (O, CU, RF, RNF, ADR, AC, `E_*`, `W_*`) son globales. Un ID solo cambia cuando una unidad de cambio elimina uno anterior de su tipo y renumera los posteriores. Una referencia a una sección se resuelve con la regla del primer punto.
- Cada regla tiene una sola sección dueña; las demás la referencian.
- En la sección 12.5, si un ejemplo contradice una regla del contrato, manda la regla y el ejemplo se corrige.
- Los términos se definen en [GLOSARIO.md](GLOSARIO.md). El historial de versiones del documento está en [HISTORIAL.md](HISTORIAL.md).
- Los enlaces son markdown relativos al archivo, sin anclas a encabezados, para que GitHub y Obsidian los resuelvan igual.
- La estructura se verifica con `python -B -m unittest discover -s tests -t . -k doc_14`, que toma de la tabla "Archivos del PRD" las secciones que deben existir.

## Índice

**Tabla: Archivos del PRD**

| Sección | Archivo | IDs |
|---|---|---|
| 1 Resumen ejecutivo | [01-resumen.md](01-resumen.md) | — |
| 2 Problema y contexto | [02-problema.md](02-problema.md) | — |
| 3 Objetivos | [03-objetivos.md](03-objetivos.md) | O1…O28 |
| 4 Garantía de solo lectura | [04-solo-lectura.md](04-solo-lectura.md) | — |
| 5 Usuarios y casos de uso | [05-usuarios.md](05-usuarios.md) | CU-01…CU-10 |
| 6 Requisitos funcionales | [06-requisitos-funcionales.md](06-requisitos-funcionales.md) | RF-01…RF-88 |
| 7 Requisitos no funcionales | [07-requisitos-no-funcionales.md](07-requisitos-no-funcionales.md) | RNF-01…RNF-22 |
| 8 Decisiones de arquitectura | [08-adr.md](08-adr.md) | ADR-01…ADR-51 |
| 9 Arquitectura | [09-arquitectura.md](09-arquitectura.md) | — |
| 10 Estructura de carpetas | [10-carpetas-y-cache.md](10-carpetas-y-cache.md) | — |
| 11 Modelo de datos | [11-modelo-de-datos.md](11-modelo-de-datos.md) | — |
| 12 CLI | [12-cli.md](12-cli.md) | — |
| 12.1 Opciones comunes | [12.01-opciones-comunes.md](12.01-opciones-comunes.md) | — |
| 12.2 `search` | [12.02-search.md](12.02-search.md) | — |
| 12.3 `new` | [12.03-new.md](12.03-new.md) | — |
| 12.4 `show` | [12.04-show.md](12.04-show.md) | — |
| 12.5 Contrato de salida (JSON) | [reglas](12.05-1-contrato-json.md) · [ejemplos A–H](12.05-2-ejemplos-show-attachment.md) · [ejemplos de contenido y salida](12.05-3-ejemplos-contenido-salida.md) | — |
| 12.6 Códigos de salida y errores | [12.06-errores.md](12.06-errores.md) | `E_*` |
| 12.7 Ayuda | [12.07-ayuda.md](12.07-ayuda.md) | — |
| 12.8 `doctor` | [12.08-doctor.md](12.08-doctor.md) | — |
| 12.9 `--version` | [12.09-version.md](12.09-version.md) | — |
| 12.10 Catálogo de warnings | [12.10-warnings.md](12.10-warnings.md) | `W_*` |
| 12.11 `attachment` | [12.11-attachment.md](12.11-attachment.md) | — |
| 12.12 Precedencia e interacciones | [12.12-precedencia.md](12.12-precedencia.md) | — |
| 13 Despliegue e instalación | [13-despliegue.md](13-despliegue.md) | — |
| 14 Logs | [14-logs.md](14-logs.md) | — |
| 15 Configuración | [15-configuracion.md](15-configuracion.md) | — |
| 16 Seguridad, privacidad y permisos | [16-seguridad.md](16-seguridad.md) | — |
| 17 Comportamiento ante errores | [17-comportamiento-errores.md](17-comportamiento-errores.md) | — |
| 18 Procesamiento único e idempotencia | [18-procesamiento-unico.md](18-procesamiento-unico.md) | — |
| 19 Rendimiento | [19-rendimiento.md](19-rendimiento.md) | — |
| 20 Criterios de aceptación | [20-criterios-aceptacion.md](20-criterios-aceptacion.md) | AC-01…AC-78 |
| 21 Operación con el harness | [21-harness.md](21-harness.md) | — |
| 22 Versiones | [22-versiones.md](22-versiones.md) | — |
| 23 Riesgos y mitigaciones | [23-riesgos.md](23-riesgos.md) | — |
| 24 Anexos | [24-anexos.md](24-anexos.md) | — |
| Anexo A Spike de Outlook | [anexos/A-spike-outlook.md](anexos/A-spike-outlook.md) | — |
| Anexo B Hechos verificados en macOS | [anexos/B-hechos-macos.md](anexos/B-hechos-macos.md) | — |
| Anexo C Alternativas evaluadas | [anexos/C-alternativas.md](anexos/C-alternativas.md) | — |
| Anexo D Registro de decisiones | [anexos/D-registro-decisiones.md](anexos/D-registro-decisiones.md) | — |
| Anexo E Ejemplos de invocación | [anexos/E-ejemplos-invocacion.md](anexos/E-ejemplos-invocacion.md) | — |
| Glosario | [GLOSARIO.md](GLOSARIO.md) | — |
| Historial del documento | [HISTORIAL.md](HISTORIAL.md) | — |

## Cómo se cambia el PRD

El PRD solo cambia al conciliar una unidad de cambio de `docs/changes/`. Cuándo hace falta una unidad, cómo se escribe y cómo se concilia está en el [protocolo de cambios](../changes/PROTOCOLO.md).

## Próximos IDs libres

**Tabla: Próximos IDs libres**

| O | CU | RF | RNF | ADR | AC |
|---|---|---|---|---|---|
| O29 | CU-11 | RF-89 | RNF-23 | ADR-52 | AC-79 |

Esta tabla se actualiza al conciliar una unidad de cambio.
