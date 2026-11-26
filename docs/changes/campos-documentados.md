---
aliases: ["Campos de --fields documentados en la ayuda, el servidor MCP y la skill"]
tags: [cambio]
---

# Campos de --fields documentados en la ayuda, el servidor MCP y la skill

**Tipo:** defecto
**Base:** PRD 2.8
**Fecha:** 2026-11-26
**Aprobación:** Ariel Salazar Hinojosa, 2026-11-26
**Paquete:** 3.0.0 (menor)

## Estado

aprobado

## Contexto

### Problema

Un agente que usaba `mailquery` por el servidor MCP pidió `show` con `fields: ["body"]` y recibió `E_USAGE` (`unknown field 'body' in --fields`). En `show`, el texto del cuerpo se llama `body_text`; `body` solo existe en la fila de `search` y `new`, donde es el estado del cuerpo (`{available, readable, partial, truncated}`) y no lleva texto.

El agente no tenía forma de saberlo antes de fallar:

- **Ayuda.** `search --help`, `new --help` y `show --help` imprimen la lista de campos válidos en un bloque `Valid fields:` al final de sus `Notes`. La línea de la opción `--fields` no la lleva.
- **Servidor MCP.** La descripción de cada parámetro es el `help` de su opción (RF-85, punto 2). El bloque de `Notes` no llega al esquema, así que el parámetro `fields` de `search`, `new` y `show` no dice qué valores acepta. `mailboxes` no tiene el problema: su línea de `--fields` ya lista sus campos.
- **Skill.** `skills/mailquery/SKILL.md` explica la fila por defecto y `--fields`, pero no lista los campos de cada comando, no explica la diferencia entre `body` y `body_text` y su único ejemplo de `show` con `--fields` es `--fields attachments`.

En la misma tarea, una respuesta de `search` ocupó 193 KB. Parte de ese tamaño venía de pedir `mailbox` en cada fila para resumir el correo por carpeta, cuando `--group-by mailbox` da ese resumen sin repetir `mailbox` en las filas (RF-70). La skill no lo explica.

El registro de defectos tiene dos entradas sobre la misma causa: BUG-02 (la skill no enseña `show UID --fields body_text` ni la diferencia entre `body` y `body_text`) y BUG-03, síntoma 2 (la skill no reproduce las listas de campos de cada comando). Esta unidad corrige BUG-02 y el síntoma 2 de BUG-03:

- **BUG-02.** Se cierra cuando se cumplen AC-03.3 y AC-03.4 de BUG-03, como dice su entrada.
- **AC-03.2, AC-03.3 y AC-03.4 de BUG-03.** No pasan al PRD: terminan como casos de test nuevos del grupo DOC-10 de `docs/tests/docs-packaging.md`, que comprueban los criterios sin ID de esta unidad sobre la skill.
- **Síntoma 4 y AC-03.6 de BUG-03.** El síntoma 4 (la skill no se verifica contra la CLI) se corrige solo para los campos: un test comprueba que cada campo que la skill atribuye a un comando está en la lista de ese comando. Los casos de DOC-10 existentes no cambian; los de esta unidad son casos nuevos, así que AC-03.6 se cumple.
- **Síntomas 1 y 3 de BUG-03 (AC-03.1, AC-03.5).** Quedan fuera; BUG-03 sigue abierto por ellos.

### Solución elegida

La lista de campos válidos de cada comando pasa a la línea de ayuda de su opción `--fields`. Por RF-85, esa línea es la descripción del parámetro `fields` del servidor MCP, así que el esquema de `tools/list` lleva la lista sin cambiar la forma en que se genera. La skill y los README reproducen las listas, explican la diferencia entre `body` y `body_text` y, en la skill, que `--group-by` quita de las filas el campo de su clave.

### Alternativas descartadas

- **`enum` en los elementos del `array` `fields` del esquema MCP.** Cada elemento puede ser una lista separada por comas (`"to,cc"`), que un `enum` rechazaría. Además, añadiría un caso especial a la generación del esquema, que hoy solo tiene las excepciones del punto 3 de RF-85.
- **Mantener también el bloque `Valid fields:` en `Notes`.** La lista saldría dos veces en la misma ayuda.
- **Renombrar `body` o `body_text` para que coincidan.** Cambia el contrato de salida de `search`, `new` y `show`; se documenta la diferencia en su lugar.
- **Generar el bloque de campos de la skill desde las constantes del código.** La skill es Markdown escrito a mano; un test comprueba que cada campo que cita existe en la lista de su comando.

### Fuera de alcance

- La forma verbal de las líneas de ayuda de `--fields`, `--group-by` y `--count` (BUG-36): el texto actual se conserva y solo se le añade lo que esta unidad pide.
- El tamaño de las respuestas (`mailbox` compacto, que corresponde a BUG-04; JSON sin sangría en el servidor MCP; tope de bytes): son otras unidades.

### Preguntas abiertas

Ninguna.

## Requerimiento

### Lo que no cambia

- Las listas de campos de `search`, `new`, `show` y `mailboxes`, su orden y su validación.
- El error de un campo desconocido o vacío: `E_USAGE` (exit 2) con el mensaje `unknown field '<campo>' in --fields` y el hint `valid fields: <lista>`.
- La salida JSON de todos los comandos.
- La generación del esquema MCP (RF-85): la descripción de cada parámetro sigue siendo el `help` de su opción y `fields` sigue siendo un `array` de `string` sin `enum`.
- La línea de ayuda de `mailboxes --fields`, que ya lista sus campos.

### Ayuda de `--fields`

Cada bloque de esta sección es el `help` de la opción, un solo texto sin saltos de línea: aquí se parte solo para leerlo, y `argparse` lo ajusta al ancho de la terminal.

- **`search` y `new`.** La línea de ayuda de `--fields` conserva su texto actual y añade, en este orden, la diferencia entre `body` y `body_text` y la lista de campos válidos:

  ```text
  adds fields to the default row (uid, subject, from, date_received, is_read,
  has_attachments); comma-separated or repeatable; all adds the full row; body is
  the body state, its text is body_text in show; valid fields: uid, message_id,
  duplicate_count, subject, from, to, cc, date_sent, date_received, mailbox,
  is_read, is_flagged, has_attachments, size_bytes, snippet, body, all
  ```

- **`show`.** La línea de ayuda de `--fields` conserva su texto actual y añade la lista de campos válidos:

  ```text
  selects the fields of message (uid is always included); comma-separated or
  repeatable; all selects every field; valid fields: uid, message_id, subject,
  from, to, cc, date_sent, date_received, mailbox, is_read, is_flagged,
  has_attachments, size_bytes, headers, body_text, body_truncated, attachments,
  partial, readable, source, all
  ```

- **Misma lista que el error.** La lista de cada línea de ayuda es la del hint `valid fields: <lista>` del mismo comando, con los mismos campos y en el mismo orden.
- **Una sola vez.** El bloque `Valid fields:` al final de las `Notes` de `search --help`, `new --help` y `show --help` se elimina: la lista sale solo en la línea de la opción. El párrafo de `Notes` que explica `--fields` no cambia.

### Servidor MCP

- Por RF-85, la descripción del parámetro `fields` de las herramientas `search`, `new` y `show` es el texto de la sección anterior, y la de `mailboxes`, la línea de ayuda de `mailboxes --fields`. Un harness que solo lee `tools/list` ve los campos válidos de cada herramienta sin llamar a `--help` ni provocar un error.

**Figura: Parámetro `fields` de la herramienta `show` en `tools/list`**

```json
"fields": {
  "type": "array",
  "description": "selects the fields of message (uid is always included); comma-separated or repeatable; all selects every field; valid fields: uid, message_id, subject, from, to, cc, date_sent, date_received, mailbox, is_read, is_flagged, has_attachments, size_bytes, headers, body_text, body_truncated, attachments, partial, readable, source, all",
  "items": {"type": "string"}
}
```

### Skill

`skills/mailquery/SKILL.md` añade a lo que RF-73 ya pide:

- **Listas de campos.** En "Default row and `--fields`", la frase `The field lists differ per command` y la lista de campos válidos de `search` y `new` y la de `show`, cada una escrita como en el hint `valid fields: <lista>` de su comando: los mismos campos, en el mismo orden, separados por `, ` y terminados en `all`. La de `mailboxes` ya está en "Folders and counters".
- **Dónde leerlas.** La frase `the description of the fields parameter of each MCP tool and the --fields line of <command> --help carry them`, o una equivalente que nombre los dos sitios.
- **`body` y `body_text`.** La frase `` In `search` and `new`, `body` is the body state and carries no text; the body text is `body_text`, only in `show` `` y el ejemplo `show UID --fields body_text`, que devuelve solo `uid` y el cuerpo, sin cabeceras ni adjuntos, como forma de leer el cuerpo de un mensaje elegido.
- **Campo de la clave en `--group-by`.** En "Grouping and counting", la frase `the rows of a group omit the key field`, con los dos casos: `from` con `--group-by from` y `mailbox` con `--group-by mailbox`. Para resumir o contar el correo por carpeta se usa `--group-by mailbox` en lugar de `--fields mailbox`, que repite la carpeta entera en cada fila; con `--group-by`, `--limit` es el número de mensajes por grupo (5 por defecto, como mucho 50) y salen como mucho 50 grupos, así que para recorrer todos los mensajes de una carpeta se usa `--include-mailbox` y no `--group-by`.
- **Campos citados.** Un campo citado es cada nombre de una lista `--fields <lista>` que sigue a `search`, `new`, `show` o `mailboxes` en una línea de comandos o en código de la skill, y cada nombre de las listas de campos que la skill escribe. Cada campo citado está en la lista del comando al que sigue o al que pertenece la lista.

### README

`README.md` y `README.es.md`, con el mismo contenido:

- **`show`.** La sección de `show` lista los campos válidos de `--fields`, escritos como en el hint de `show` y terminados en `all`, y explica la diferencia entre `body` y `body_text` con la frase `` `body` is the body state `` (en `README.es.md`, `` `body` es el estado del cuerpo ``) y el ejemplo `show <uid> --fields body_text`.
- **Servidor MCP.** La sección del servidor MCP dice que la descripción de cada parámetro es la línea de ayuda de su opción, así que la de `fields` lista los campos válidos de su comando, con la frase `the description of each parameter is the help line of its option` (en `README.es.md`, `la descripción de cada parámetro es la línea de ayuda de su opción`).
- La lista de la fila completa de `search` y la frase sobre el campo de la clave de `--group-by` ya están y no cambian.

### Elementos del PRD que cambian

- **RF-73.** La línea de ayuda de `--fields` de `search`, `new` y `show` lista los campos válidos de su comando, con `all`, y la de `search` y `new` dice que `body` es el estado del cuerpo y su texto es `body_text` de `show`. La skill lista los campos de cada comando, explica la diferencia entre `body` y `body_text` con `show UID --fields body_text` y dice que con `--group-by` las filas no llevan el campo de la clave. Los README listan los campos de `show`, explican la diferencia entre `body` y `body_text`, y su sección del servidor MCP dice que la descripción de `fields` lista los campos válidos.
- **RF-85.** El punto 2 dice que, por salir del `help` de su opción, la descripción del parámetro `fields` de `search`, `new`, `show` y `mailboxes` lista los campos válidos de su comando, y que el esquema no lleva `enum` en sus elementos porque cada uno puede ser una lista separada por comas. El requisito se comprueba también con AC-81.
- **§20.** El punto 3 incluye AC-81 en su rango, y AC-81 va después de AC-80.
- **§23.** La mitigación del riesgo "`--fields` añade en `search`/`new` y elige en `show`, y el agente lo confunde" nombra la línea de ayuda de `--fields`, la descripción del parámetro `fields` del servidor MCP y las listas de la skill.

### Cambios visibles

Ninguna fila nueva en §22.4: `--fields` y `mcp serve` son nuevos en `3.0.0`, y la fila "Opciones de `search`, `new` y `show`" no cambia.

## Criterios de aceptación

**AC-81.** En `tools/list`, la descripción del parámetro `fields` de `search` y de `new` contiene los campos de RF-68 seguidos de `all`, la de `show`, los de RF-69 seguidos de `all`, y la de `mailboxes`, los de RF-78; en cada herramienta, la lista coincide, en campos y orden, con la del hint `valid fields: <lista>` de un campo desconocido en el mismo comando.

- `search --help`, `new --help` y `show --help` muestran la lista de campos de su comando una sola vez, en la línea de `--fields`, y no tienen el bloque `Valid fields:`.
- La línea de `--fields` de `search --help` y `new --help` contiene `body is the body state, its text is body_text in show`.
- La skill contiene `The field lists differ per command`, la lista de `search` y `new` y la de `show` con el texto exacto del hint de su comando, una frase que nombra la descripción del parámetro `fields` de las herramientas MCP y la línea de `--fields` de `--help` como sitios donde leerlas, la frase sobre `body` y `body_text` de la sección "Skill", `show UID --fields body_text`, la frase `the rows of a group omit the key field` con `--group-by from` y `--group-by mailbox`, y la frase que dice que `--limit` es por grupo con `--group-by`.
- Cada campo citado de la skill, con la definición de la sección "Skill", está en la lista del comando al que sigue o al que pertenece la lista.
- `README.md` y `README.es.md` contienen la lista de `show` con el texto exacto de su hint, `--fields body_text`, la frase sobre `body` de la sección "README" en su idioma y la frase sobre la descripción de cada parámetro en su idioma.
- La suite completa pasa.

## IDs

- Crea: AC-81
- Elimina: —

## Dependencias

Ninguna

## Decisiones

- **¿Dónde se documentan los campos válidos de `--fields` para un harness que usa el servidor MCP?** (2026-11-26) En la línea de ayuda de `--fields` de cada comando, que el servidor usa como descripción del parámetro `fields`, y en la skill y los README. `body` y `body_text` no se renombran: la diferencia se documenta.

## Glosario

Sin cambios

## Conciliación con el PRD

**Tabla: Conciliación con el PRD**

| ID | Contrato | Archivo | Ancla | Qué cambia | Estado |
|---|---|---|---|---|---|
| RC-01 | Ayuda, skill y README de `--fields` | `06-requisitos-funcionales.md` | RF-73 | La línea de ayuda de `--fields` de `search`, `new` y `show` lista los campos válidos de su comando con `all`, y la de `search` y `new` dice que `body` es el estado del cuerpo y su texto `body_text` de `show`; la skill lista los campos de cada comando, explica `body` y `body_text` con `show UID --fields body_text` y dice que con `--group-by` las filas no llevan el campo de la clave; los README listan los campos de `show`, explican `body` y `body_text`, y su sección del servidor MCP dice que la descripción de `fields` lista los campos válidos. | pendiente |
| RC-02 | Descripción de los parámetros del servidor MCP | `06-requisitos-funcionales.md` | RF-85 | El punto 2 dice que la descripción del parámetro `fields` de `search`, `new`, `show` y `mailboxes` lista los campos válidos de su comando y que el esquema no lleva `enum` en sus elementos; el requisito se comprueba también con AC-81. | pendiente |
| RC-03 | Alcance de los criterios | `20-criterios-aceptacion.md` | `3. **Plugins, adjuntos` | El rango del punto incluye AC-81. | pendiente |
| RC-04 | Criterios de aceptación | `20-criterios-aceptacion.md` | después de AC-80 | AC-81. | pendiente |
| RC-05 | Riesgo de confundir `--fields` | `23-riesgos.md` | `` `--fields` añade en `search`/`new` y elige en `show` `` | La mitigación nombra la línea de ayuda de `--fields`, la descripción del parámetro `fields` del servidor MCP y las listas de la skill, además del error con la lista válida (RF-73, RF-85). | pendiente |

## Documentos consumidores

- README.md: pendiente
- README.es.md: pendiente
- skills/mailquery/SKILL.md: pendiente
- docs/INTERFACES.md: sin cambio
- docs/recipes/: sin cambio
- docs/tests/docs-packaging.md: pendiente
- docs/tests/mcp-server.md: pendiente
- docs/tests/acceptance-matrix.md: pendiente

## Checklist de conciliación

**Tabla: Checklist de conciliación**

| ID | Ítem | Cómo se verifica | Estado |
|---|---|---|---|
| CL-01 | Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila | pendiente |
| CL-02 | El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial | pendiente |
| CL-03 | Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` | pendiente |
| CL-04 | Las decisiones están en el Anexo D y el glosario está aplicado | Revisión de "Decisiones" y "Glosario" | pendiente |
| CL-05 | Los documentos consumidores están actualizados | Ninguno está `pendiente` | pendiente |
| CL-06 | No quedan textos obsoletos en el PRD ni en los documentos consumidores: `La ayuda, la skill y el error con la lista válida lo explican`; en la ayuda de `search`, `new` y `show`, `Valid fields:` | Búsqueda de cada texto | pendiente |
| CL-07 | El defecto registrado está cerrado | En `docs/KNOWN-DEFECTS.md`, BUG-02 cerrado; BUG-03 sigue abierto por los síntomas 1 y 3, con AC-03.2, AC-03.3, AC-03.4 y AC-03.6 marcados como cumplidos | pendiente |
| CL-08 | La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` | pendiente |
| CL-09 | La suite pasa | Suite completa, con `doc_14` y `doc_15` | pendiente |
| CL-10 | Las listas de `tools/list` coinciden con las del PRD | La descripción de `fields` de cada herramienta contra RF-68, RF-69 y RF-78 | pendiente |

## Desviaciones aprobadas

Ninguna
