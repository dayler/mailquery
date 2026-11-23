---
aliases: ["Protocolo de cambios"]
tags: [cambio, protocolo]
---

# Protocolo de cambios

Todo cambio del producto se define en una **unidad de cambio**: un archivo de `docs/changes/` que dice qué cambia en el producto, cómo se comprueba y qué secciones del PRD hay que poner al día. El PRD (`docs/prd/`) describe el producto tal como es y solo cambia al **conciliar** una unidad: con el cambio ya implementado, se redacta en esas secciones lo que el producto hace. Este documento dice cuándo hace falta una unidad, cómo se escribe y cómo se concilia.

- Una unidad está **abierta** mientras no está `conciliado`.
- Los **documentos consumidores** son los documentos fuera del PRD que repiten su contrato: `README.md` y `README.es.md`, `skills/mailquery/SKILL.md`, `docs/INTERFACES.md`, `docs/config.example.toml`, `docs/recipes/`, `docs/security/` y `docs/tests/`.

## Cuándo hace falta una unidad

Un cambio necesita una unidad si cambia lo que el producto hace o lo que el PRD dice. En caso de duda, se escribe.

**Tabla: Tratamiento de cada tipo de cambio**

| Cambio | ¿Concilia el PRD? | Tipo de unidad |
|---|---|---|
| Funcionalidad nueva | Sí | `funcionalidad` |
| Cambio de un comportamiento existente | Sí | `cambio` |
| Defecto cuyo arreglo cambia el código y el contrato | Sí | `defecto` |
| Defecto: el código se desvía del PRD y el PRD es correcto | No | `defecto` |
| Errata: el PRD no describe, o describe de forma ambigua, lo que el código hace, y el código es correcto | Sí | `errata` |
| Refactor que cambia lo que el PRD describe (decisiones de arquitectura, arquitectura, carpetas, modelo de datos) | Sí | `refactor` |
| Refactor interno | No | Sin unidad |
| Publicación de una versión del paquete, o subida de su número que ninguna otra unidad provoca | Sí | `versión` |
| Solo código de test o documentos consumidores | No | Sin unidad |

- Si el código y el PRD no coinciden, el dueño decide cuál es correcto.
- Un cambio sin unidad actualiza en su misma rama los documentos consumidores que le afecten.

## La unidad de cambio

- Una unidad es un cambio del producto de uno de los tipos de la tabla anterior.
- Cada unidad es un archivo `docs/changes/<nombre>.md`. El nombre, en minúsculas con dígitos y guiones, identifica la unidad fuera de su archivo.
- Se crea copiando [PLANTILLA.md](PLANTILLA.md) y sustituyendo su frontmatter por `aliases: ["<título de la unidad>"]` y `tags: [cambio]`.
- La unidad define lo que se implementa: el código, los tests y los documentos consumidores se comprueban contra su requerimiento y sus criterios de aceptación.
- La unidad no contiene el texto del PRD: dice qué secciones cambian y qué deben reflejar. El texto se redacta al conciliar.
- **Diseño sí, código no.** La unidad describe el diseño que el cambio necesita: estructuras de tablas y datos, contratos de interfaces con sus nombres y firmas, diagramas de clases, de secuencia o de componentes y ejemplos de invocación. No contiene código implementado: ni el cuerpo de funciones o métodos, ni sentencias de base de datos, ni pasos o tareas de implementación.
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
2. **Contexto:** el problema, el motivo, las alternativas descartadas y las preguntas abiertas. No pasa al PRD. Una unidad de tipo `defecto` cita aquí el ID de su entrada de `docs/KNOWN-DEFECTS.md`, si la tiene.
3. **Requerimiento:** lo que cambia en el producto, con la forma de "Forma del requerimiento".
4. **Criterios de aceptación:** cómo se comprueba que el cambio está hecho. Un criterio que debe quedar en el PRD es un párrafo que empieza por su ID (`**AC-<n>.** <texto>`); los demás son entradas de lista.
5. **IDs:** dos líneas. `- Crea:` lleva los IDs nuevos y `- Elimina:` los que desaparecen del PRD. Los IDs se separan con comas, un rango continuo se escribe `RF-80…RF-82` y una línea sin IDs lleva `—`. Un ID que otro reemplaza es una eliminación y una creación.
6. **Dependencias:** `Ninguna`, o una lista con una línea `- <nombre>` por cada unidad que debe estar conciliada antes.
7. **Decisiones:** `Ninguna`, o una entrada de lista por cada decisión del dueño que irá al Anexo D: `- **<pregunta>** (<AAAA-MM-DD>) <decisión>`.
8. **Glosario:** cada término nuevo o modificado con su definición final, los términos eliminados, o `Sin cambios`.
9. **Conciliación con el PRD:** la tabla de conciliación, con la forma de "Tabla de conciliación", o `Ninguna` en una unidad `defecto` cuyo arreglo no cambia el PRD.
10. **Documentos consumidores:** `Ninguno`, o una línea `- <documento>: <estado>` por cada documento consumidor que repite el contrato afectado, con el estado `pendiente`, `actualizado` o `sin cambio`. Se actualizan en la rama de la unidad.
11. **Checklist de conciliación:** la tabla del checklist, con la forma de "Checklist de conciliación".
12. **Desviaciones aprobadas:** `Ninguna`, o cada cambio del requerimiento o de los criterios hecho después de aprobarse la unidad, con quién lo aprobó y cuándo. La desviación ya está aplicada en la unidad; aquí solo se anota. Los commits y la evidencia de la implementación van en su plan o en su rama, no en la unidad.

### Forma del requerimiento

- **Qué dice.** El comportamiento del producto después del cambio: reglas, casos, límites, errores, datos y ejemplos. Describe comportamiento, no tareas: el reparto del trabajo va en el plan.
- **Cómo se ordena.** En subsecciones `###` libres, las que el cambio necesite: resumen, requerimientos, decisiones de arquitectura, arquitectura, modelo de datos, contrato de salida, configuración, cambios visibles, riesgos.
- **Prosa y listas.** El requerimiento se escribe en párrafos y listas. Una tabla solo se usa para datos que se leen comparando columnas, como una serie de medidas.
- **Requisitos nuevos.** Los requisitos funcionales y no funcionales nuevos van en la subsección `### Requerimientos`, cada uno con la forma de "Forma de un requisito nuevo".
- **Otros elementos nuevos con ID.** Un objetivo, caso de uso o decisión de arquitectura nuevo empieza con un párrafo cuyo principio es su ID y su título en negrita (`**ADR-<n>. <título>.**`). Debajo van su enunciado y sus reglas, en párrafos y listas; una decisión de arquitectura lleva su motivo y sus alternativas descartadas. Los criterios de aceptación con ID van en "Criterios de aceptación".
- **Elementos del PRD que cambian.** El requerimiento dice qué cambia en cada uno, citándolo por su ID o por su sección. No reescribe el texto del PRD.
- **Lo que se elimina.** El requerimiento nombra cada regla, opción o elemento que desaparece del producto.
- **Sin plan.** Ninguna línea de la unidad cita `docs/plan`.

### Forma de un requisito nuevo

Cada requisito nuevo tiene cuatro partes, en este orden:

1. **Título.** Un párrafo con su ID y su nombre en negrita. Un requisito funcional añade su prioridad, `M` (imprescindible) o `S` (deseable): `**RF-<n>. <nombre>.** Prioridad M.`
2. **Quién, qué y para qué.** Una frase: `**Como** <rol>, **quiero** <qué>, **para** <beneficio>.` El rol es quien recibe el beneficio: el harness de agentes, el usuario humano, el autor de un driver o de un plugin, o quien opera o depura la herramienta. El beneficio es un resultado para ese rol, no una tarea de implementación.
3. **Condiciones.** La línea `Condiciones:` y una lista con las reglas que el producto debe cumplir. Cada regla empieza por un nombre corto en negrita y dice una sola cosa.
4. **Comprobación.** La línea `Se comprueba con <criterios>.`, con los criterios de aceptación que cubren el requisito.

**Figura: Ejemplo de un requisito nuevo**

```markdown
**RF-x1. Límite de resultados por carpeta.** Prioridad S.

**Como** harness de agentes, **quiero** limitar los resultados de cada carpeta, **para** que una carpeta con mucho correo no oculte las demás.

Condiciones:

- **Opción.** `search --per-mailbox N` devuelve como mucho `N` mensajes de cada carpeta.
- **Rango.** `N` va de 1 a 50; fuera de rango ⇒ `E_USAGE`.

Se comprueba con AC-x1.
```

### Tabla de conciliación

Registra qué hay que poner al día en el PRD y en qué punto está cada cosa. Lleva el título `**Tabla: Conciliación con el PRD**` y estas columnas, en este orden:

- **`ID`:** `RC-01`, `RC-02`…, en orden y sin huecos.
- **`Contrato`:** el contrato, la regla o el elemento del producto que cambia.
- **`Archivo`:** el archivo del PRD donde ese contrato está escrito o donde irá, con su ruta desde `docs/prd/` entre comillas invertidas (`06-requisitos-funcionales.md`, `anexos/E-ejemplos-invocacion.md`). Un archivo que la unidad crea lleva `(nuevo)`.
- **`Ancla`:** el punto del archivo donde está lo que cambia, con la forma de "Anclas".
- **`Qué cambia`:** qué debe decir ese punto después del cambio, en una o dos frases y con los IDs del requerimiento. No es el texto del PRD.
- **`Estado`:** `pendiente`, `implementado` o `conciliado`.

Anclas:

- **Para qué sirven.** Quien concilia busca el ancla y lee solo su bloque, sin cargar el archivo entero. El ancla dice dónde mirar; no es texto del PRD.
- **ID.** Un ID (`RF-25`) señala la línea del archivo que lo define.
- **Texto.** Un texto entre comillas invertidas es el principio de una línea del archivo. En una fila de tabla es el principio de su primera celda, sin la barra. Solo una línea del archivo empieza así.
- **Contenido nuevo.** `después de <ancla>` marca tras qué bloque va.
- **Varias anclas.** Una celda puede llevar varias, separadas por punto y coma.
- **Si la primera celda no basta.** Se usa el título de su tabla o el encabezado de su sección, y "Qué cambia" nombra la fila.
- **Archivo nuevo.** La celda lleva `—`.

Reglas de la tabla:

- **Una fila por contrato y archivo.** Un contrato escrito en varios archivos tiene una fila por archivo; así ninguno queda sin revisar.
- **Qué filas hay.** Se usa la tabla "Sección dueña de cada tipo de cambio" para situar cada elemento del requerimiento y la tabla "Secciones que suelen cambiar a la vez" para no olvidar las que arrastra. Incluye, cuando corresponda, el bloque de la unidad en el resumen (sección 1) y en el problema (sección 2), los cambios visibles de su versión (sección 22) y los riesgos (sección 23).
- **Qué no va.** El glosario cambia con la sección "Glosario" de la unidad, el Anexo D con "Decisiones", y el historial y la portada con el procedimiento de conciliación.
- **Estado de una fila.** `pendiente`: lo que la fila describe no está en la rama de la unidad. `implementado`: está en la rama, con sus tests y sus documentos consumidores, o la fila no necesita código. `conciliado`: su archivo del PRD ya lo refleja.
- **Hallazgos.** Si la implementación descubre algo que el PRD debe reflejar, se añade a "Qué cambia" de su fila o como fila nueva. Si cambia el requerimiento, es una desviación.
- **Filas y estado de la unidad.** En una unidad `borrador`, todas las filas están `pendiente`. En una `aprobado`, `pendiente` o `implementado`. En una `implementado`, todas `implementado`. En una `conciliado`, todas `conciliado`.

### Checklist de conciliación

Es la puerta de la conciliación: la unidad no pasa a `conciliado` con un ítem `pendiente`. Lleva el título `**Tabla: Checklist de conciliación**` y las columnas `ID` (`CL-01`, `CL-02`…, en orden y sin huecos), `Ítem`, `Cómo se verifica` y `Estado` (`pendiente`, `cumplido` o `no aplica`).

Toda unidad empieza su checklist con los ítems comunes, en este orden. Después añade los suyos, si los tiene.

**Tabla: Ítems comunes del checklist de conciliación**

| Ítem | Cómo se verifica |
|---|---|
| Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila |
| El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial |
| Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` |
| Las decisiones están en el Anexo D y el glosario está aplicado | Revisión de "Decisiones" y "Glosario" |
| Los documentos consumidores están actualizados | Ninguno está `pendiente` |
| No quedan textos obsoletos en el PRD ni en los documentos consumidores | Búsqueda de cada texto |
| El defecto registrado está cerrado | Su entrada de `docs/KNOWN-DEFECTS.md` |
| La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` |
| La suite pasa | Suite completa, con `doc_14` y `doc_15` |

- El ítem de los textos obsoletos lista, después de dos puntos, las frases o reglas antiguas que deben desaparecer.
- Un ítem que no corresponde a la unidad lleva `no aplica`.

## Ciclo de vida

**Tabla: Estados de una unidad**

| Estado | Quién lo pone | Condición de entrada | Qué permite |
|---|---|---|---|
| `borrador` | Quien escribe la unidad | El archivo existe, creado desde la plantilla; sus IDs nuevos son marcadores | Revisarla y corregirla |
| `aprobado` | El dueño | El requerimiento y los criterios de aceptación están completos y sin preguntas abiertas, los IDs nuevos están reservados y la cabecera tiene la aprobación | Implementarla |
| `implementado` | Quien implementa | El código está en la rama de la unidad, la suite pasa, los criterios de aceptación se cumplen, ninguna fila de la tabla de conciliación ni documento consumidor está `pendiente` y las desviaciones están anotadas | Conciliarla |
| `conciliado (<AAAA-MM-DD>)` | Quien concilia | El procedimiento de conciliación está completo y ningún ítem del checklist está `pendiente` | Integrar la rama en `develop` |

- **Dónde vive.** Un borrador se escribe en su propia rama y llega a `develop` cuando el dueño lo aprueba, antes de implementarse: así las demás unidades ven sus IDs reservados y las secciones que va a cambiar.
- **El PRD va con el código.** La implementación de una unidad llega a `develop` en un solo merge, desde la rama de la unidad, y su commit de conciliación es el último de esa rama. Si la rama lleva varias unidades, sus commits de conciliación son los últimos, uno por unidad y en el orden de sus IDs. Una implementación que no cabe en un merge obliga a partir la unidad en unidades con dependencias.
- **Si `develop` avanza antes del merge.** Se integra otra vez en la rama y el commit de conciliación se rehace encima.
- **Errata.** Una errata no cambia código: pasa de `aprobado` a `conciliado` en una rama que solo lleva sus documentos consumidores y su conciliación.
- **Retiro.** Una unidad abierta que se abandona se elimina solo por orden del dueño. Sus IDs reservados se liberan y los posteriores de las demás unidades abiertas se renumeran para no dejar huecos. Las unidades que dependían de ella se retiran con ella o se reescriben sin esa dependencia en el mismo cambio.
- **Fin.** Una unidad `conciliado` se queda en `docs/changes/` hasta que el dueño ordena eliminarla, y no se elimina mientras una unidad abierta dependa de ella.

## IDs

- **Marcadores.** En `borrador`, los IDs nuevos son marcadores `<tipo>x<n>` (por ejemplo `RF-x1`, `AC-x2`, `Ox1`).
- **Dónde se definen.** Cada ID de la línea `- Crea:` se define una vez en la unidad: los criterios de aceptación en "Criterios de aceptación" y los demás en "Requerimiento".
- **Reserva al aprobar.** Al aprobarse la unidad, cada marcador se sustituye en todo el archivo por un ID real. Los IDs de cada tipo empiezan en el siguiente al mayor que reserve otra unidad abierta o, si ninguna reserva de ese tipo, en el de la tabla "Próximos IDs libres" de la portada. El PRD no se edita para reservarlos.
- **En orden.** Las unidades con IDs nuevos se concilian en el orden de esos IDs, para que los IDs del PRD no tengan huecos. Una unidad sin IDs nuevos se concilia en cualquier momento.
- **Intercambio.** Si una unidad está lista para conciliar antes que otra con IDs anteriores, toma los IDs más bajos y los de las demás unidades abiertas se renumeran.
- **Eliminación.** Si una unidad elimina un ID, los IDs posteriores del mismo tipo bajan para cerrar el hueco. La unidad usa la numeración anterior; la renumeración se hace al conciliar, después de redactar, e incluye los IDs que la unidad crea. Se aplica al PRD, a los tests, a los documentos consumidores y a las unidades abiertas. `HISTORIAL.md` y las unidades conciliadas conservan los IDs de su época.
- **Renumerar otra unidad no es una desviación.** Cuando un intercambio, una eliminación o un retiro renumeran IDs de otra unidad, se sustituyen en todo su archivo. La rama de esa unidad corrige sus tests y sus documentos al integrar `develop`.

## Versión del paquete

El campo "Paquete" lleva la versión que `develop` anuncia al conciliarse la unidad, sin sufijo de pre-release (por ejemplo `3.0.0`), y la clase del cambio.

**Tabla: Clases de cambio del paquete**

| Clase | Qué es | Tipos de unidad |
|---|---|---|
| `mayor` | Incompatible para un harness que consume la última versión publicada | `funcionalidad`, `cambio`, `defecto`, `versión` |
| `menor` | Añade o cambia algo visible de forma compatible | `funcionalidad`, `cambio`, `defecto`, `versión` |
| `parche` | Solo arreglos que no cambian el contrato | `defecto`, `versión` |
| `sin efecto` | Nada visible | `errata`, `refactor` |

- **Sumarse o subir.** Una unidad `mayor`, `menor` o `parche` se suma a la versión que `develop` anuncia si esa versión no está publicada y su salto respecto de la última publicada es de su clase o de una superior. Si no, la propia unidad sube el número: su requerimiento y su tabla de conciliación incluyen la sección 22.3, la línea "Versión del paquete" de la portada y la subsección de cambios visibles de la versión nueva.
- **`sin efecto`.** Nunca cambia el número.
- **Unidad `versión`.** Publica la versión que `develop` anuncia, o abre la siguiente versión de parche después de una publicación. Su clase es el salto de su versión respecto de la última publicada.
- **Nada bajo un número publicado.** Ningún cambio de código, con unidad o sin ella, llega a `develop` bajo un número ya publicado: el primer cambio de código después de publicar es una unidad que sube el número, o va precedido de una unidad `versión` que abre la siguiente versión de parche.
- **Publicar.** Una unidad `versión` que publica se concilia antes de publicar: el PRD describe la versión como publicada, y la publicación se hace desde el commit de merge de la unidad, sin commits intermedios. Si la publicación no llega a hacerse, ese merge se revierte.

## Reglas

- **Sin unidad no cambia el PRD.** Ningún texto del PRD cambia fuera de la conciliación de una unidad.
- **El PRD se escribe al conciliar.** El texto del PRD se redacta en la conciliación, a partir del requerimiento y de lo implementado. Cumple las reglas del PRD: describe el producto tal como es, no cita planes, tickets ni unidades, y cada tabla tiene título. Un elemento con ID pasa al PRD con su ID y su contenido.
- **Atómica.** Una unidad se concilia entera en un commit o no se concilia. Si una comprobación falla, no se aplica ninguna de sus filas.
- **Autocontenida.** Una unidad no usa contenido de otra unidad, salvo de las que declara en "Dependencias".
- **Sin cargar el PRD entero.** Ni escribir una unidad ni conciliarla exige leer el PRD completo. Al escribirla, lo que el cambio toca se localiza con la portada, las tablas de "Dónde va cada cambio" y una búsqueda de los términos y los IDs del cambio en `docs/prd/`; se leen solo los bloques encontrados. Al conciliar, se busca cada ancla y se lee solo su bloque.
- **Sin solapes.** Una misma regla del PRD la cambia o la elimina como mucho una unidad abierta. Si otra unidad necesita cambiarla, depende de la primera.
- **Eliminar borra.** Lo que una unidad elimina del PRD se borra: no se traslada ni se reescribe en otro sitio.

## Procedimiento de conciliación

1. Se integra `develop` en la rama de la unidad.
2. Se comprueba que la unidad está `implementado` (`aprobado` si es una errata), que sus dependencias están `conciliado` y que ninguna unidad abierta tiene IDs anteriores a los suyos; si alguna los tiene, se aplica el intercambio. Se comprueba también que el campo "Paquete" lleva la versión que `develop` anunciará con la unidad conciliada y, salvo en una errata, que esa versión no está publicada. Si está publicada y la unidad no sube el número, lo sube con una desviación aprobada o va precedida de una unidad `versión`.
3. Si la versión del PRD ya no es la base de la unidad, se comprueba que cada ancla sigue señalando su bloque y que cada fila sigue valiendo para el PRD actual, y se corrige la unidad antes de seguir.
4. Por cada fila de la tabla de conciliación, se busca su ancla, se lee su bloque y se redacta allí lo que la fila dice, según el requerimiento y lo implementado; la fila pasa a `conciliado`. Cada elemento nuevo con ID va a su sección dueña. Si la unidad elimina un ID, después se renumeran los posteriores.
5. Se revisan las demás unidades abiertas con filas sobre los mismos archivos. Si esta conciliación cambió una línea que otra unidad usa como ancla, esa ancla se corrige. Si cambió una regla que otra unidad da por vigente, esa unidad se corrige; si cambia su requerimiento, necesita una desviación aprobada antes de conciliarse.
6. Se añaden las decisiones al Anexo D y se aplica el glosario.
7. Versión e historial:
   - La versión del documento sube un número menor (por ejemplo, de 2.4 a 2.5). En la portada, "Versión del documento" toma el número nuevo y "Fecha" la fecha de la conciliación.
   - Al final de la tabla de `HISTORIAL.md` se añade la fila ``| **X.Y** | <título de la unidad> (`<nombre>`, aprobada por <quién> el <fecha> y conciliada el <fecha>): <archivos cambiados>. |``.
   - En la portada, la tabla "Próximos IDs libres" toma el máximo usado + 1 de cada tipo y la columna "IDs" de la tabla "Archivos del PRD" toma los rangos nuevos.
8. Si la unidad corrige un defecto registrado, se cierra su entrada del registro de defectos.
9. Se recorre el checklist: cada ítem se verifica y pasa a `cumplido` o a `no aplica`.
10. La unidad pasa a `conciliado (<AAAA-MM-DD>)`.
11. Pasan las comprobaciones de "Verificación".
12. El commit `docs(prd): reconcile <nombre>` incluye el PRD, la unidad, las demás unidades corregidas, el registro de defectos y las referencias renumeradas.

Una unidad cuya "Conciliación con el PRD" es `Ninguna` omite los pasos 3 a 7: el PRD, su versión y su historial no cambian.

## Dónde va cada cambio

1. Cada elemento del requerimiento va a su sección dueña:

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
3. Si el archivo dueño va a superar 300 líneas, la conciliación incluye su partición en un archivo nuevo con el mismo prefijo y su enlace en la tabla "Archivos del PRD". La partición mueve texto sin cambiarlo. Si el archivo define IDs, la unidad también adapta las comprobaciones de "Verificación" para que acepten como dueños los archivos con ese prefijo.

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
- **Qué implementa.** Un plan implementa el requerimiento de una o varias unidades `aprobado`. No hace falta un plan por unidad.
- **Qué contiene.** Milestones, dependencias, propiedad de archivos, briefs y evidencia, con la estructura que fija `CLAUDE.md`. No contiene el requerimiento, texto del PRD ni un registro de conciliación.
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

- Un defecto registrado se corrige con una unidad `defecto`, que cita su entrada. Si el PRD es correcto, su "Conciliación con el PRD" es `Ninguna` y su criterio de aceptación es un test de regresión registrado en `docs/tests/` que cita el requisito existente del PRD.
- Los criterios de aceptación que proponga una entrada del registro no son del PRD. Cada uno termina de una de dos formas: como AC con ID de la unidad, si debe quedar como contrato del producto, o como caso de test en `docs/tests/`, si solo comprueba que el código vuelve a cumplir el PRD.

## Verificación

- `python -B -m unittest discover -s tests -t . -k doc_14` verifica la estructura del PRD.
- `python -B -m unittest discover -s tests -t . -k doc_15` verifica cada unidad de `docs/changes/`, la plantilla y este protocolo: nombres y frontmatter, cabecera, secciones, estado y aprobación, IDs, dependencias, requerimiento y criterios de aceptación, tabla de conciliación y sus anclas, checklist, documentos consumidores y títulos de tabla.
