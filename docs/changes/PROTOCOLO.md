---
aliases: ["Protocolo de cambios"]
tags: [cambio, protocolo]
---

# Protocolo de cambios del PRD

El PRD (`docs/prd/`) describe el producto tal como es. Solo cambia al **conciliar** una **unidad de cambio**: un archivo de `docs/changes/` con el texto final que el PRD debe tener. Este documento dice cuándo hace falta una unidad, cómo se escribe y cómo se concilia.

- Una unidad está **abierta** mientras no está `conciliado`.
- Los **documentos consumidores** son los documentos fuera del PRD que repiten su contrato: `README.md` y `README.es.md`, `skills/mailquery/SKILL.md`, `docs/INTERFACES.md`, `docs/config.example.toml`, `docs/recipes/`, `docs/security/` y `docs/tests/`.

## Cuándo hace falta una unidad

Un cambio necesita una unidad si altera algún texto del PRD. Si no altera ninguno, no se escribe unidad. En caso de duda, se escribe.

**Tabla: Tratamiento de cada tipo de cambio**

| Cambio | ¿Altera el PRD? | Tipo de unidad |
|---|---|---|
| Funcionalidad nueva | Sí | `funcionalidad` |
| Cambio de un comportamiento existente | Sí | `cambio` |
| Defecto cuyo arreglo cambia el código y el contrato | Sí | `defecto` |
| Defecto: el código se desvía del PRD y el PRD es correcto | No | Sin unidad |
| Errata: el PRD no describe, o describe de forma ambigua, lo que el código hace, y el código es correcto | Sí | `errata` |
| Refactor que cambia lo que el PRD describe (decisiones de arquitectura, arquitectura, carpetas, modelo de datos) | Sí | `refactor` |
| Refactor interno | No | Sin unidad |
| Publicación de una versión del paquete, o subida de su número que ninguna otra unidad provoca | Sí | `versión` |
| Solo código de test o documentos consumidores | No | Sin unidad |

- Si el código y el PRD no coinciden, el dueño decide cuál es correcto.
- Un cambio sin unidad actualiza en su misma rama los documentos consumidores que le afecten.

## La unidad de cambio

- Una unidad es un cambio de uno de los tipos de la tabla anterior.
- Cada unidad es un archivo `docs/changes/<nombre>.md`. El nombre, en minúsculas con dígitos y guiones, identifica la unidad fuera de su archivo.
- Se crea copiando [PLANTILLA.md](PLANTILLA.md) y sustituyendo su frontmatter por `aliases: ["<título de la unidad>"]` y `tags: [cambio]`.
- Desde que una unidad está `aprobado` y hasta que está `conciliado`, para lo que cambia manda la unidad.

### Cabecera

- **Título** (`# <título>`).
- **Tipo:** uno de los tipos de unidad de la tabla anterior.
- **Base:** versión del PRD contra la que se escribió.
- **Fecha:** la de creación de la unidad.
- **Aprobación:** `—` mientras la unidad está en `borrador`; desde la aprobación, quién la aprobó y cuándo (`<quién>, <AAAA-MM-DD>`). No se borra al avanzar de estado.
- **Paquete:** `<versión> (<clase>)`, según "Versión del paquete".

### Secciones

La unidad tiene estas secciones `##`, en este orden y con estos nombres:

1. **Estado:** `borrador`, `aprobado`, `implementado` o `conciliado (<AAAA-MM-DD>)`.
2. **Contexto:** el problema, el motivo y las alternativas descartadas. No se copia al PRD. Una unidad de tipo `defecto` cita aquí el ID de su entrada de `docs/KNOWN-DEFECTS.md`, si la tiene.
3. **IDs:** dos líneas. `- Crea:` lleva los IDs nuevos y `- Elimina:` los que desaparecen del PRD. Los IDs se separan con comas, un rango continuo se escribe `RF-80…RF-82` y una línea sin IDs lleva `—`. Un ID que otro reemplaza es una eliminación y una creación.
4. **Dependencias:** `Ninguna`, o una lista con una línea `- <nombre>` por cada unidad que debe estar conciliada antes.
5. **Cambios en el PRD:** los cambios, con la forma de "Forma de un cambio", o `Ninguno` si la unidad solo cambia el glosario o el Anexo D.
6. **Decisiones:** `Ninguna`, o una tabla con el título `**Tabla: Filas para el Anexo D**` y las columnas del Anexo D (`Pregunta original`, `Decisión`), con las filas finales.
7. **Glosario:** cada término nuevo o modificado con su definición final, los términos eliminados, o `Sin cambios`.
8. **Secciones relacionadas y textos obsoletos:** una línea `- <fila>: cambia` o `- <fila>: sin cambio` por cada fila de la tabla "Secciones que suelen cambiar a la vez" (una fila `cambia` tiene su cambio en "Cambios en el PRD"), y una línea `- Textos obsoletos:` con las frases o reglas antiguas que deben desaparecer del PRD y de los documentos consumidores, o `Ninguno`.
9. **Documentos consumidores:** `Ninguno`, o una línea `- <documento>: <estado>` por cada documento consumidor que repite el contrato afectado, con el estado `pendiente`, `actualizado` o `sin cambio`. Se actualizan en la rama de la unidad.
10. **Desviaciones aprobadas:** `Ninguna`, o cada cambio del texto final hecho después de aprobarse la unidad, con quién lo aprobó y cuándo. La desviación ya está aplicada en "Cambios en el PRD"; aquí solo se anota. Los commits y la evidencia de la implementación van en su plan o en su rama, no en la unidad.

### Forma de un cambio

"Cambios en el PRD" tiene una subsección `### <archivo> — <sección>` por cada archivo que cambia: primero `00-indice.md` y después los demás, en el orden de la tabla "Archivos del PRD" de la [portada](../prd/00-indice.md). `<sección>` es `Portada` para `00-indice.md` y, para los demás, la sección que esa tabla da al archivo: `sección <N>`, `sección 12.<M>` o `Anexo <X>`. `GLOSARIO.md` e `HISTORIAL.md` no van aquí: el glosario cambia con la sección "Glosario" de la unidad y el historial con el procedimiento de conciliación. Incluye, cuando corresponda, el bloque de la unidad en el resumen (sección 1) y en el problema (sección 2), los cambios visibles de su versión (sección 22) y los riesgos (sección 23).

Bajo el encabezado de un archivo van todos sus cambios, en el orden del archivo. Cada cambio repite estas tres entradas:

- **Operación:** `añadir` (el texto final va después del bloque de la Ubicación), `modificar` (el texto final reemplaza el bloque; una fila o un criterio con ID conserva su ID: reemplazarlo por otro es un `eliminar` y un `añadir`) o `eliminar` (el bloque desaparece).
- **Ubicación:** un bloque de código con una sola línea: el principio de una línea del archivo, tal como está escrita; exactamente una línea del archivo empieza así. Esa línea identifica el bloque afectado. En un archivo nuevo es `archivo nuevo`, la operación es `añadir` y el texto final es el archivo completo.
- **Texto final:** un bloque de código con el texto literal que queda en el PRD, con su formato y su título de tabla. Si el texto contiene un bloque de código, el bloque que lo envuelve usa una valla más larga. En `eliminar` no se escribe.

**Tabla: Bloque que identifica una Ubicación**

| La línea de la Ubicación es | El bloque es |
|---|---|
| Una fila de tabla | Esa fila |
| Una línea de campo (`**<campo>:** …`) | Esa línea y sus líneas de continuación, hasta la siguiente línea de campo o línea en blanco |
| El título de una tabla (`**Tabla: …**`) | El título y la tabla entera |
| Un encabezado | La sección entera, hasta el siguiente encabezado del mismo nivel o de uno superior |
| Una entrada de lista | La entrada, con sus líneas de continuación y sus subentradas |
| Una línea dentro de un bloque de código | El bloque de código entero |
| Cualquier otra línea | El párrafo, hasta la siguiente línea en blanco |

## Ciclo de vida

**Tabla: Estados de una unidad**

| Estado | Quién lo pone | Condición de entrada | Qué permite |
|---|---|---|---|
| `borrador` | Quien escribe la unidad | El archivo existe, creado desde la plantilla; sus IDs nuevos son marcadores | Revisarla y corregirla |
| `aprobado` | El dueño | El texto final está completo, los IDs nuevos están reservados y la cabecera tiene la aprobación | Implementarla |
| `implementado` | Quien implementa | El código está en la rama de la unidad, la suite pasa, ningún documento consumidor está `pendiente` y las desviaciones están anotadas | Conciliarla |
| `conciliado (<AAAA-MM-DD>)` | Quien concilia | Los pasos 1 a 8 del procedimiento de conciliación están completos | Integrar la rama en `develop` |

- **Dónde vive.** Un borrador se escribe en su propia rama y llega a `develop` cuando el dueño lo aprueba, antes de implementarse: así las demás unidades ven sus IDs reservados y sus ubicaciones.
- **El PRD va con el código.** La implementación de una unidad llega a `develop` en un solo merge, desde la rama de la unidad, y su commit de conciliación es el último de esa rama. Si la rama lleva varias unidades, sus commits de conciliación son los últimos, uno por unidad y en el orden de sus IDs. Una implementación que no cabe en un merge obliga a partir la unidad en unidades con dependencias.
- **Si `develop` avanza antes del merge.** Se integra otra vez en la rama y el commit de conciliación se rehace encima.
- **Errata.** Una errata no cambia código: pasa de `aprobado` a `conciliado` en una rama que solo lleva sus documentos consumidores y su conciliación.
- **Retiro.** Una unidad abierta que se abandona se elimina solo por orden del dueño. Sus IDs reservados se liberan y los posteriores de las demás unidades abiertas se renumeran para no dejar huecos. Las unidades que dependían de ella se retiran con ella o se reescriben sin esa dependencia en el mismo cambio.
- **Fin.** Una unidad `conciliado` se queda en `docs/changes/` hasta que el dueño ordena eliminarla, y no se elimina mientras una unidad abierta dependa de ella.

## IDs

- **Marcadores.** En `borrador`, los IDs nuevos son marcadores `<tipo>x<n>` (por ejemplo `RF-x1`, `AC-x2`, `Ox1`).
- **Reserva al aprobar.** Al aprobarse la unidad, cada marcador se sustituye en todo el archivo por un ID real. Los IDs de cada tipo empiezan en el siguiente al mayor que reserve otra unidad abierta o, si ninguna reserva de ese tipo, en el de la tabla "Próximos IDs libres" de la portada. El PRD no se edita para reservarlos.
- **En orden.** Las unidades con IDs nuevos se concilian en el orden de esos IDs, para que los IDs del PRD no tengan huecos. Una unidad sin IDs nuevos se concilia en cualquier momento.
- **Intercambio.** Si una unidad está lista para conciliar antes que otra con IDs anteriores, toma los IDs más bajos y los de las demás unidades abiertas se renumeran.
- **Eliminación.** Si una unidad elimina un ID, los IDs posteriores del mismo tipo bajan para cerrar el hueco. El texto final de la unidad usa la numeración anterior; la renumeración se hace al conciliar, después de copiar, e incluye los IDs que la unidad crea. Se aplica al PRD, a los tests, a los documentos consumidores y a las unidades abiertas. `HISTORIAL.md` y las unidades conciliadas conservan los IDs de su época.
- **Renumerar otra unidad no es una desviación.** Cuando un intercambio, una eliminación o un retiro renumeran IDs de otra unidad, se sustituyen en todo su archivo, texto final incluido. La rama de esa unidad corrige sus tests y sus documentos al integrar `develop`.

## Versión del paquete

El campo "Paquete" lleva la versión que `develop` anuncia al conciliarse la unidad, sin sufijo de pre-release (por ejemplo `3.0.0`), y la clase del cambio.

**Tabla: Clases de cambio del paquete**

| Clase | Qué es | Tipos de unidad |
|---|---|---|
| `mayor` | Incompatible para un harness que consume la última versión publicada | `funcionalidad`, `cambio`, `defecto`, `versión` |
| `menor` | Añade o cambia algo visible de forma compatible | `funcionalidad`, `cambio`, `defecto`, `versión` |
| `parche` | Solo arreglos que no cambian el contrato | `versión` |
| `sin efecto` | Nada visible | `errata`, `refactor` |

- **Sumarse o subir.** Una unidad `mayor` o `menor` se suma a la versión que `develop` anuncia si esa versión no está publicada y su salto respecto de la última publicada es de su clase o de una superior. Si no, la propia unidad sube el número: sus cambios incluyen la sección 22.3, la línea "Versión del paquete" de la portada y la subsección de cambios visibles de la versión nueva.
- **`sin efecto`.** Nunca cambia el número.
- **Unidad `versión`.** Publica la versión que `develop` anuncia, o abre la siguiente versión de parche después de una publicación. Su clase es el salto de su versión respecto de la última publicada.
- **Nada bajo un número publicado.** Ningún cambio de código, con unidad o sin ella, llega a `develop` bajo un número ya publicado: el primer cambio de código después de publicar es una unidad que sube el número, o va precedido de una unidad `versión` que abre la siguiente versión de parche.
- **Publicar.** Una unidad `versión` que publica se concilia antes de publicar: su texto final describe la versión como publicada, y la publicación se hace desde el commit de merge de la unidad, sin commits intermedios. Si la publicación no llega a hacerse, ese merge se revierte.

## Reglas

- **Sin unidad no cambia el PRD.** Ningún texto del PRD cambia fuera de la conciliación de una unidad.
- **Atómica.** Una unidad se concilia entera en un commit o no se concilia. Si una comprobación falla, no se aplica ninguno de sus cambios.
- **Autocontenida.** Una unidad no usa texto de otra unidad, salvo de las que declara en "Dependencias".
- **Copiar es conciliar.** El texto final ya cumple las reglas del PRD: describe comportamiento, no cita planes, tickets ni documentos, y cada tabla tiene título. Al conciliar se copia; no se reescribe. La única excepción es la renumeración de IDs.
- **Sin solapes.** Un mismo bloque del PRD lo modifica o elimina como mucho una unidad abierta. Si otra unidad necesita cambiarlo, depende de la primera.
- **`eliminar` borra.** El texto eliminado no se traslada ni se reescribe en otro sitio. La única excepción es la partición de un archivo que va a superar 300 líneas: mueve texto sin cambiarlo, como un `eliminar` en el archivo de origen y un `añadir` con el mismo texto en el archivo nuevo.

## Procedimiento de conciliación

1. Se integra `develop` en la rama de la unidad.
2. Se comprueba que la unidad está `implementado` (`aprobado` si es una errata), que sus dependencias están `conciliado` y que ninguna unidad abierta tiene IDs anteriores a los suyos; si alguna los tiene, se aplica el intercambio. Se comprueba también que el campo "Paquete" lleva la versión que `develop` anunciará con la unidad conciliada y, salvo en una errata, que esa versión no está publicada. Si está publicada y la unidad no sube el número, lo sube con una desviación aprobada o va precedida de una unidad `versión`.
3. Si la versión del PRD ya no es la base de la unidad, se revisa la Ubicación de cada cambio y se corrige la unidad antes de seguir.
4. Los cambios de "Cambios en el PRD" se aplican en orden, copiando el texto final. Si la unidad elimina un ID, después se renumeran los posteriores.
5. Se corrigen las ubicaciones de las demás unidades abiertas que esta conciliación afecta: si cambió la línea que otra unidad usa como Ubicación, esa Ubicación pasa a la línea nueva o, si la línea desapareció, al bloque anterior; si esta unidad añadió texto en el punto donde otra unidad añade, la Ubicación de la otra pasa al último bloque añadido. Salvo los IDs renumerados, el texto final de la otra unidad no se toca: si ya no encaja, esa unidad necesita una desviación aprobada antes de conciliarse.
6. Se añaden las decisiones al Anexo D, se aplica el glosario y se comprueba que los textos obsoletos ya no aparecen en el PRD ni en los documentos consumidores.
7. Versión e historial:
   - La versión del documento sube un número menor (por ejemplo, de 2.4 a 2.5). En la portada, "Versión del documento" toma el número nuevo y "Fecha" la fecha de la conciliación.
   - Al final de la tabla de `HISTORIAL.md` se añade la fila ``| **X.Y** | <título de la unidad> (`<nombre>`, aprobada por <quién> el <fecha> y conciliada el <fecha>): <archivos cambiados>. |``.
   - En la portada, la tabla "Próximos IDs libres" toma el máximo usado + 1 de cada tipo y la columna "IDs" de la tabla "Archivos del PRD" toma los rangos nuevos.
8. Si la unidad corrige un defecto registrado, se cierra su entrada del registro de defectos.
9. La unidad pasa a `conciliado (<AAAA-MM-DD>)`.
10. Pasan las comprobaciones de "Verificación".
11. El commit `docs(prd): reconcile <nombre>` incluye el PRD, la unidad, las demás unidades corregidas, el registro de defectos y las referencias renumeradas.

## Dónde va cada cambio

1. Cada cambio va a su sección dueña:

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
| Cambio visible para el usuario | `22-versiones.md` (subsección de cambios visibles de la versión de la unidad) |
| Riesgo aceptado | `23-riesgos.md` |
| Decisión del dueño | `anexos/D-registro-decisiones.md` |

2. El contenido nuevo es una subsección dentro de su sección dueña. Una sección de primer nivel nueva solo se crea si ninguna sección es dueña: obliga a renumerar, renombrar archivos y corregir todas las referencias, añade su fila a la tabla "Archivos del PRD" y es una unidad propia.
3. Si el archivo dueño va a superar 300 líneas, la unidad incluye su partición en un archivo nuevo con el mismo prefijo y su enlace en la tabla "Archivos del PRD". Si el archivo define IDs, la unidad también adapta las comprobaciones de "Verificación" para que acepten como dueños los archivos con ese prefijo.

**Tabla: Secciones que suelen cambiar a la vez**

| Si cambia | Revisar también |
|---|---|
| Un objetivo (3) o un caso de uso (5) | Los RF que lo cubren (6) |
| Un RF o RNF (6, 7) | Su AC (20), cambios visibles (22) |
| La salida JSON (12.5) | Los ejemplos de `12.05-2-ejemplos-show-attachment.md` y `12.05-3-ejemplos-contenido-salida.md`, la ayuda (12.7) |
| Un error o código de salida (12.6) | Comportamiento ante errores (17), ejemplos (12.5) |
| Un warning (12.10) | Ejemplos (12.5), `doctor` (12.8) si lo informa |
| Una opción de configuración (15) | Tabla 15.1, archivo completo 15.5, `docs/config.example.toml` |
| Una decisión de arquitectura (8) | Arquitectura (9), riesgos (23) |
| Un comportamiento visible para el usuario | Cambios visibles (22) |

## Planes

- **Cuándo hay plan.** Un plan hace falta cuando la implementación se delega a subagentes o se reparte en varios milestones. Una unidad que se implementa sin plan tiene como evidencia los commits y los tests de su rama.
- **Qué implementa.** Un plan implementa una o varias unidades `aprobado`. No hace falta un plan por unidad.
- **Qué contiene.** Milestones, dependencias, propiedad de archivos, briefs y evidencia, con la estructura que fija `CLAUDE.md`. No contiene texto del PRD ni un registro de conciliación.
- **Milestones y unidades.** Cada milestone dice qué unidad completa, si completa alguna. Todos los milestones de una unidad se integran en la rama de la unidad; solo esa rama llega a `develop`.
- **La unidad no cita el plan.** El plan nombra sus unidades; la unidad no nombra el plan.
- **Fin del plan.** Un plan se elimina entero, solo por orden del dueño, cuando todas sus unidades están `conciliado`.

## Organización de carpetas

**Figura: Carpetas de las unidades y de los planes**

```
docs/
  changes/
    PROTOCOLO.md
    PLANTILLA.md
    <nombre>.md              una unidad por archivo, en cualquier estado
  plan/
    <nombre-del-plan>/       un plan por carpeta
```

- **`docs/changes/` es plana.** Todas las unidades están en su primer nivel, sin subcarpetas. Una unidad no cambia de nombre ni de carpeta al cambiar de estado.
- **Un plan por carpeta.** Cada plan vive en `docs/plan/<nombre-del-plan>/`, con su plan maestro, su archivo de reglas para subagentes, sus briefs y su evidencia. Varios planes abiertos no comparten archivos.
- **Unidades sin plan.** No dejan nada en `docs/plan/`.
- **Ramas.** Una unidad sin plan se implementa en su propia rama; las unidades de un plan, en las ramas que el plan define. Las ramas que avanzan a la vez usan un worktree cada una, fuera del repositorio.

## Defectos registrados

- Un defecto sin unidad se cierra en la rama de su arreglo, con un test de regresión registrado en `docs/tests/` que cita el requisito existente del PRD.
- Los criterios de aceptación que proponga una entrada del registro no son del PRD. Cada uno termina de una de dos formas: como AC de una unidad, si debe quedar como contrato del producto, o como caso de test en `docs/tests/`, si solo comprueba que el código vuelve a cumplir el PRD.

## Verificación

- `python -B -m unittest discover -s tests -t . -k doc_14` verifica la estructura del PRD.
- `python -B -m unittest discover -s tests -t . -k doc_15` verifica cada unidad de `docs/changes/`, la plantilla y este protocolo: nombres y frontmatter, cabecera, secciones, estado y aprobación, IDs, dependencias, forma de los cambios y ubicaciones, texto final, solapes, secciones relacionadas, documentos consumidores y títulos de tabla.
