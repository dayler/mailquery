---
aliases: ["Plantilla de unidad de cambio"]
tags: [cambio, plantilla]
---

# {Título de la unidad}

**Tipo:** {funcionalidad | cambio | defecto | errata | refactor | versión}
**Base:** PRD {versión}
**Fecha:** {AAAA-MM-DD de creación}
**Aprobación:** —
**Paquete:** {versión sin sufijo de pre-release} ({mayor | menor | parche | sin efecto})

## Estado

borrador

## Contexto

{Problema, motivo, alternativas descartadas y preguntas abiertas. No pasa al PRD. Una unidad de tipo defecto cita aquí el ID de su entrada del registro de defectos, si la tiene.}

## Requerimiento

{Lo que cambia en el producto: comportamiento, reglas, casos, límites, errores, datos y ejemplos, en las subsecciones que el cambio necesite. Se escribe en párrafos y listas; una tabla solo para datos que se leen comparando columnas. De cada elemento del PRD que cambia se dice qué cambia, citándolo por su ID o por su sección. Incluye el diseño que el cambio necesita (estructuras de tablas y datos, contratos de interfaces con nombres y firmas, diagramas), pero no código implementado ni pasos de implementación. No es el texto del PRD.}

### Requerimientos

{Un bloque como este por cada requisito nuevo. Un objetivo, caso de uso o decisión de arquitectura nuevo va en su propia subsección y empieza con un párrafo cuyo principio es su ID y su título en negrita.}

**RF-x1. {Nombre del requisito}.** Prioridad {M | S}.

**Como** {rol que recibe el beneficio}, **quiero** {qué}, **para** {beneficio}.

Condiciones:

- **{Nombre de la regla}.** {Una regla que el producto debe cumplir.}

Se comprueba con AC-x1.

## Criterios de aceptación

{Cómo se comprueba que el cambio está hecho. Un criterio que debe quedar en el PRD es un párrafo que empieza por su ID en negrita, como el de abajo; los demás son entradas de lista.}

**AC-x1.** {Resultado observable que comprueba el requisito.}

## IDs

- Crea: RF-x1, AC-x1 {marcadores en borrador, IDs reales desde la aprobación, o —}
- Elimina: {IDs o —}

## Dependencias

{Ninguna, o una línea "- nombre" por cada unidad que debe estar conciliada antes.}

## Decisiones

{Ninguna, o una entrada de lista por cada decisión del dueño que irá al Anexo D: la pregunta en negrita, la fecha entre paréntesis y la decisión.}

## Glosario

Sin cambios

## Conciliación con el PRD

{Una fila por contrato que cambia y por archivo del PRD donde está escrito. El ancla es un ID, o el principio de una línea del archivo entre comillas invertidas (en una fila de tabla, el de su primera celda); "después de" marca dónde va un contenido nuevo. Una unidad de tipo defecto cuyo arreglo no cambia el PRD lleva solo: Ninguna.}

**Tabla: Conciliación con el PRD**

| ID | Contrato | Archivo | Ancla | Qué cambia | Estado |
|---|---|---|---|---|---|
| RC-01 | {contrato, regla o elemento que cambia} | `{archivo del PRD}` | {ancla o anclas, separadas por punto y coma} | {qué debe decir ese punto después del cambio, con los IDs del requerimiento} | pendiente |

## Documentos consumidores

{Ninguno, o una línea "- documento: estado" por documento, con el estado pendiente, actualizado o sin cambio.}

## Checklist de conciliación

{Los ítems comunes, en este orden, y después los propios de la unidad. Estado: pendiente, cumplido o no aplica.}

**Tabla: Checklist de conciliación**

| ID | Ítem | Cómo se verifica | Estado |
|---|---|---|---|
| CL-01 | Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila | pendiente |
| CL-02 | El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial | pendiente |
| CL-03 | Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` | pendiente |
| CL-04 | Las decisiones están en el Anexo D y el glosario está aplicado | Revisión de "Decisiones" y "Glosario" | pendiente |
| CL-05 | Los documentos consumidores están actualizados | Ninguno está `pendiente` | pendiente |
| CL-06 | No quedan textos obsoletos en el PRD ni en los documentos consumidores: {frases o reglas que deben desaparecer} | Búsqueda de cada texto | pendiente |
| CL-07 | El defecto registrado está cerrado | Su entrada de `docs/KNOWN-DEFECTS.md` | pendiente |
| CL-08 | La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` | pendiente |
| CL-09 | La suite pasa | Suite completa, con `doc_14` y `doc_15` | pendiente |

## Desviaciones aprobadas

Ninguna
