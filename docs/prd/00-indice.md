---
aliases: ["PRD", "Índice del PRD"]
tags: [prd]
---

# PRD — mailquery

**Producto:** `mailquery` — CLI de solo lectura para leer y buscar el correo del cliente de escritorio local desde un harness de agentes (DeepSeek u otro similar): **Apple Mail en macOS** y **Outlook clásico en Windows**, ampliable con plugins de backend.
**Versión del documento:** 2.3 (un solo PRD para todas las plataformas, en un archivo por sección; incorpora plugins de backend, la recuperación local de adjuntos, el endurecimiento del contenido no confiable, la corrección de defectos de adjuntos y la salida a medida).
**Versión del paquete:** `3.0.0` (en `develop` se anuncia la pre-release `3.0.0a1`; sin publicar, §22.3).
**Fecha:** 2026-11-20.
**Repositorio:** <https://github.com/dayler/mailquery>.
**Estado:** v0.13 aprobado e implementado (macOS + Apple Mail). v1.0 **aprobado** por el dueño del producto el 2026-11-03. v1.3 es un solo documento según el estándar de un PRD, con la arquitectura como única excepción porque no hay TRD. v2.1: plugins de backend y adjuntos aprobados por el dueño el 2026-11-11, implementados en `develop` y conciliados en este documento el 2026-11-12. v2.2: endurecimiento del contenido no confiable (F1), corrección de defectos de adjuntos (F2) y salida a medida (F3), aprobados por el dueño el 2026-11-13, implementados en `develop` y conciliados en este documento el 2026-11-18; sin publicar. v2.3: el documento se parte en un archivo por sección, sin cambiar el producto.

## Cómo se organiza

- El PRD es un conjunto de archivos. La sección N está en `NN-*.md`, la subsección 12.M en `12.MM-*.md` y el anexo X en `anexos/X-*.md`. Si una sección ocupa varios archivos, todos llevan su prefijo.
- Ningún archivo supera 300 líneas. Si un cambio hace que uno las supere, se parte en varios archivos con el mismo prefijo y se actualiza la tabla del Índice.
- La numeración de secciones y los IDs (O, CU, RF, RNF, ADR, AC, `E_*`, `W_*`) son globales y estables. Una referencia a una sección se resuelve con la regla del primer punto.
- Cada regla tiene una sola sección dueña; las demás la referencian.
- En la sección 12.5, si un ejemplo contradice una regla del contrato, manda la regla y el ejemplo se corrige.
- Los términos se definen en [GLOSARIO.md](GLOSARIO.md). El historial de versiones del documento está en [HISTORIAL.md](HISTORIAL.md).
- Los enlaces son markdown relativos al archivo, sin anclas a encabezados, para que GitHub y Obsidian los resuelvan igual.
- La estructura se verifica con `python -B -m unittest discover -s tests -t . -k doc_14`, que toma de la tabla del Índice las secciones que deben existir.

## Índice

**Tabla: Archivos del PRD**

| Sección | Archivo | IDs |
|---|---|---|
| 1 Resumen ejecutivo | [01-resumen.md](01-resumen.md) | — |
| 2 Problema y contexto | [02-problema.md](02-problema.md) | — |
| 3 Objetivos | [03-objetivos.md](03-objetivos.md) | O1…O28 |
| 4 Garantía de solo lectura | [04-solo-lectura.md](04-solo-lectura.md) | — |
| 5 Usuarios y casos de uso | [05-usuarios.md](05-usuarios.md) | CU-01…CU-09 |
| 6 Requisitos funcionales | [06-requisitos-funcionales.md](06-requisitos-funcionales.md) | RF-01…RF-79 |
| 7 Requisitos no funcionales | [07-requisitos-no-funcionales.md](07-requisitos-no-funcionales.md) | RNF-01…RNF-22 |
| 8 Decisiones de arquitectura | [08-adr.md](08-adr.md) | ADR-01…ADR-49 |
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
| 20 Criterios de aceptación | [20-criterios-aceptacion.md](20-criterios-aceptacion.md) | AC-01…AC-62 |
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
| Plantilla de documento de cambio | [PLANTILLA-CAMBIO.md](PLANTILLA-CAMBIO.md) | — |

## Cómo se concilia un cambio

Conciliar es llevar al PRD un cambio de comportamiento aprobado, para que el PRD describa el producto tal como es. Solo se concilia un **documento de cambio** con la estructura de esta parte.

Los documentos de cambio viven en `docs/changes/`, uno por archivo. Se crean copiando [PLANTILLA-CAMBIO.md](PLANTILLA-CAMBIO.md) y sustituyendo su frontmatter por `aliases: ["<título del documento>"]` y `tags: [cambio]`. El nombre del archivo sin `.md` es el **nombre** del documento.

La **unidad de conciliación** es una funcionalidad o un defecto. Cada unidad se concilia completa, de forma independiente y en un solo commit. Fuera de su documento, una unidad se identifica como `<nombre>/<ID>`.

### Cabecera del documento de cambio

- **Título.**
- **Base:** versión del PRD contra la que se escribió.
- **Fecha.**
- **Numeración:** el rango reservado de cada tipo de ID que crea el documento (por ejemplo `RF-80…RF-84`), o `—`. Cada rango empieza en el próximo ID libre del PRD o después del último rango que reserve otro documento de `docs/changes/`. El PRD no se edita para reservarlos.
- **Fuente de verdad:** hasta que una unidad está `conciliado`, para lo que cambia manda el documento de cambio.
- **Tabla de unidades:** una fila por unidad, con su ID, título, estado, IDs reservados y las unidades de las que depende.

### Estructura de cada unidad

Cada unidad es una sección `## <ID> — <título>`. El ID lo asigna el documento de cambio y es único dentro de él. La sección tiene estas subsecciones `###`, en este orden y con estos nombres:

1. **Estado:** `borrador`, `aprobado (<quién>, <fecha>)`, `implementado` o `conciliado (<fecha>)`.
2. **Contexto:** el problema, el motivo y las alternativas descartadas. No se copia al PRD.
3. **IDs:** los que la unidad crea (dentro de los rangos del documento), sustituye y elimina, y la renumeración que provoca una eliminación.
4. **Dependencias:** las unidades que deben estar conciliadas antes, o `Ninguna`.
5. **Cambios en el PRD:** una subsección `#### <archivo> — sección <N.M>` por cada archivo que cambia, en el orden del PRD. Incluye, cuando corresponda, el bloque de la unidad en el resumen (sección 1) y en el problema (sección 2), los cambios visibles (sección 22.4) y los riesgos (sección 23). Cada cambio indica:
   - **Operación:** `añadir`, `modificar`, `sustituir` o `eliminar`.
   - **Ubicación:** el ID, el encabezado o la primera frase actual del texto afectado; en `añadir`, el texto después del cual va.
   - **Texto final:** el texto literal que queda en el PRD, con su formato y su título de tabla. En `eliminar`, se omite.
6. **Decisiones:** las filas finales para el Anexo D, o `Ninguna`.
7. **Glosario:** cada término nuevo o modificado con su definición final, los términos eliminados, o `Sin cambios`.
8. **Secciones relacionadas y textos obsoletos:** cada fila de la tabla "Secciones que suelen cambiar a la vez", marcada `cambia` (con su cambio en "Cambios en el PRD") o `sin cambio`, y las frases o reglas antiguas que deben desaparecer del PRD y de los documentos consumidores.
9. **Documentos consumidores:** cada documento fuera del PRD que repite el contrato afectado (por ejemplo `README.md` y `README.es.md`, `skills/mailquery/SKILL.md`, `docs/INTERFACES.md`, `docs/config.example.toml`, `docs/recipes/`, `docs/tests/`) con su estado. Se actualizan al implementar y se verifican al conciliar.
10. **Desviaciones aprobadas:** cada cambio del texto final aprobado durante la implementación, con quién lo aprobó y cuándo. La desviación ya está aplicada en "Cambios en el PRD"; aquí solo se anota. Los commits y la evidencia de la implementación van en su plan, no en el documento de cambio.

Una unidad que no cambia el PRD tiene la línea `Sin cambios en el PRD.` en "Cambios en el PRD" y omite "Decisiones", "Glosario" y "Secciones relacionadas y textos obsoletos".

### Reglas

- **Atómica.** Una unidad se concilia entera en un commit o no se concilia. Si una comprobación falla, no se aplica ninguno de sus cambios.
- **Autocontenida.** Una unidad no usa texto de otra unidad, salvo de las que declara en "Dependencias".
- **Copiar es conciliar.** El texto final ya cumple las reglas del PRD: describe comportamiento, no cita planes, tickets ni documentos, y cada tabla tiene título. Al conciliar se copia; no se reescribe.
- **Sin solapes.** Un mismo párrafo, fila o entrada del PRD lo cambia como mucho una unidad abierta. Si otra unidad necesita cambiarlo, depende de la primera.
- **En orden de IDs.** Las unidades que crean IDs se concilian en el orden de esos IDs, también entre documentos, para que los IDs del PRD no tengan huecos. Una unidad sin IDs nuevos se concilia en cualquier momento.
- **Sin documento no hay conciliación.** Un cambio de código sin documento de cambio necesita antes una unidad escrita y aprobada.
- **`eliminar` borra.** El texto eliminado no se traslada ni se reescribe en otro sitio. Si se elimina un ID, los IDs posteriores del mismo tipo se renumeran sin huecos, se corrigen todas sus referencias en el PRD, los tests y los documentos, y los rangos de los documentos de cambio abiertos se desplazan igual.
- **Fin del documento de cambio.** Cuando todas sus unidades están `conciliado`, el documento de cambio se elimina solo por orden del dueño.

### Procedimiento (por unidad)

1. Se comprueba que la unidad está `implementado`, que sus dependencias están `conciliado`, que sus documentos consumidores están verificados y que las unidades con IDs anteriores a los suyos ya están conciliadas.
2. Si la versión actual del PRD no es la base del documento ni la versión que el propio documento introdujo, se revisa la Ubicación de cada cambio contra `git log -- docs/prd/` y se corrige la unidad antes de seguir.
3. Los cambios de "Cambios en el PRD" se aplican en orden, copiando el texto final.
4. Se añaden las decisiones al Anexo D, se aplica el glosario y se comprueba que los textos obsoletos ya no aparecen.
5. Versión e historial:
   - En la primera unidad conciliada del documento, la versión del documento sube un número menor (por ejemplo, de 2.3 a 2.4). En la cabecera de esta portada, "Versión del documento" toma el número nuevo y su paréntesis añade al final `; <título del documento de cambio>`; "Fecha" toma la fecha de la conciliación; "Estado" añade al final ` vX.Y: <título del documento de cambio>, en conciliación.` Al final de la tabla de `HISTORIAL.md` se añade la fila `| **X.Y** | <título del documento de cambio>: <nombre>/<ID> (<archivos cambiados>). |`.
   - En cada unidad siguiente del mismo documento, "Fecha" toma la fecha de la conciliación y la celda de su fila en `HISTORIAL.md` añade `; <nombre>/<ID> (<archivos cambiados>)`.
   - En la última unidad del documento, en "Estado", `en conciliación` pasa a `conciliado el <fecha>`.
   - La tabla "Próximos IDs libres" toma el máximo usado + 1 de cada tipo.
6. `python -B -m unittest discover -s tests -t . -k doc_14` pasa.
7. La unidad pasa a `conciliado (<fecha>)` y su fila de la tabla de unidades se actualiza.
8. Un solo commit, con el mensaje `docs(prd): reconcile <nombre>/<ID>`, incluye el PRD, el documento de cambio y las referencias renumeradas.

### Secciones que suelen cambiar a la vez

**Tabla: Secciones que suelen cambiar a la vez**

| Si cambia | Revisar también |
|---|---|
| Un objetivo (3) o un caso de uso (5) | Los RF que lo cubren (6) |
| Un RF o RNF (6, 7) | Su AC (20), cambios visibles (22.4) |
| La salida JSON (12.5) | Los ejemplos de `12.05-2-ejemplos-show-attachment.md` y `12.05-3-ejemplos-contenido-salida.md`, la ayuda (12.7) |
| Un error o código de salida (12.6) | Comportamiento ante errores (17), ejemplos (12.5) |
| Un warning (12.10) | Ejemplos (12.5), `doctor` (12.8) si lo informa |
| Una opción de configuración (15) | Tabla 15.1, archivo completo 15.5, `docs/config.example.toml` |
| Una decisión de arquitectura (8) | Arquitectura (9), riesgos (23) |
| Un comportamiento visible para el usuario | Cambios visibles (22.4) |

## Cómo se añade una funcionalidad

1. Se escribe un documento de cambio en `docs/changes/` (o se añade una unidad a uno abierto); la funcionalidad es una unidad.
2. Cada cambio va a su sección dueña:

**Tabla: Sección dueña de cada tipo de cambio**

| Cambio | Archivo |
|---|---|
| Objetivo / caso de uso | `03-objetivos.md` / `05-usuarios.md` |
| Requisito funcional / no funcional | `06-requisitos-funcionales.md` / `07-requisitos-no-funcionales.md` |
| Decisión de arquitectura | `08-adr.md` |
| Campo o forma de la salida JSON | `12.05-1-contrato-json.md` y un ejemplo en `12.05-2-ejemplos-show-attachment.md` o `12.05-3-ejemplos-contenido-salida.md`, según corresponda |
| Error o código de salida / warning | `12.06-errores.md` / `12.10-warnings.md` |
| Opción de configuración | `15-configuracion.md` |
| Criterio de aceptación | `20-criterios-aceptacion.md` |
| Cambio visible para el usuario | `22-versiones.md` (22.4) |
| Riesgo aceptado | `23-riesgos.md` |
| Decisión del dueño | `anexos/D-registro-decisiones.md` |

3. El contenido nuevo es una subsección dentro de su sección dueña. Una sección de primer nivel nueva solo se crea si ninguna sección es dueña: obliga a renumerar, renombrar archivos y corregir todas las referencias, añade su fila a la tabla del Índice y es una unidad propia.
4. Si el archivo dueño va a superar 300 líneas, la unidad incluye su partición en un archivo nuevo con el mismo prefijo y su enlace en la tabla del Índice.

## Próximos IDs libres

**Tabla: Próximos IDs libres**

| O | CU | RF | RNF | ADR | AC |
|---|---|---|---|---|---|
| O29 | CU-10 | RF-80 | RNF-23 | ADR-50 | AC-63 |

Los documentos de cambio reservan sus rangos en su cabecera. Esta tabla se actualiza al conciliar.
