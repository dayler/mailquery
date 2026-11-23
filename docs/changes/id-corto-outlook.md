---
aliases: ["Id corto de mensaje en Outlook y caché de ids nativos"]
tags: [cambio]
---

# Id corto de mensaje en Outlook y caché de ids nativos

**Tipo:** cambio
**Base:** PRD 2.4
**Fecha:** 2026-11-22
**Aprobación:** —
**Paquete:** 3.0.0 (mayor)

## Estado

borrador

## Contexto

### Problema

- El `uid` es `"<driver>:<native_id>"`. En Outlook mide 148 caracteres: `outlook:` más los 140 hexadecimales del `EntryID`. En Apple Mail mide unos 16 (`apple_mail:83143`).
- Dentro de un mismo store de Outlook, los primeros 137 caracteres del `uid` son iguales en todos los mensajes: solo cambian los 11 últimos.
- El `uid` se repite en cada fila, en cada warning de mensaje y en el `cursor` de `new`. En una fila mínima de `search` es cerca de un tercio de la fila.
- En Windows, el `EntryID` no cabe en el límite de ruta, y la caché de adjuntos lo sustituye por un identificador de 32 hexadecimales.
- El problema es solo de Outlook: el id nativo de Apple Mail ya es corto.

### Solución elegida

- **Alias y nada más.** Una tabla local traduce un id corto al `native_id` del mensaje. No guarda nada más y ninguna fila se actualiza.
- **Lo decide el driver.** El driver `outlook` emite el id corto como su parte del `uid` y lo traduce cuando el núcleo le pide un mensaje. El driver `apple_mail` no cambia.
- **El núcleo no se entera.** Ya trata la parte posterior al prefijo como texto opaco.
- **El núcleo pone las herramientas.** Una librería del núcleo da el cálculo del id corto, la conexión a la base y las operaciones sobre la tabla. La usan los drivers que lo deciden, también los plugins.

Con la unidad, el `uid` de Outlook pasa de 148 caracteres a 16 (`outlook:k3f9q2m7`), lo mismo que mide el de Apple Mail.

### Por qué el núcleo avisa de lo que imprime

El driver lee todas las filas del alcance y el núcleo decide después cuáles se imprimen. El driver no sabe cuáles son. Ejemplo con `mailquery search --from acme --since 2026-01-01 --limit 20`:

1. El driver lee las carpetas del alcance: 10.000 filas.
2. El núcleo filtra por `--from acme`: 37 filas.
3. El núcleo quita duplicados: 35 filas.
4. El núcleo recorta a `--limit 20` e imprime: 20 filas.

- Dentro de una ejecución no hace falta la base: el driver calcula en memoria el id corto de las 10.000 filas (13 ms, medido con ids sintéticos) y traduce desde memoria cuando el núcleo le devuelve esos ids.
- La base hace falta para la ejecución siguiente (`show`, `attachment`), y solo para las 20 filas impresas.
- Registro medido con ids sintéticos: 200 filas, de 4 a 6 ms y 96 KB; 10.000 filas, de 64 a 290 ms y 3,7 MB.

### Por qué 8 caracteres

**Tabla: Pares de mensajes con el mismo id corto esperados**

| Filas en la tabla | 8 caracteres | 10 caracteres |
|---|---|---|
| 100.000 | 0,0045 | 0,000004 |
| 1.000.000 | 0,45 | 0,0004 |

Una colisión no rompe nada, porque `seq` distingue los dos mensajes. Con 8 caracteres, el `uid` de Outlook mide lo mismo que el de Apple Mail.

### Alternativas descartadas

- **`uid` propio del núcleo, derivado de la cabecera `Message-ID`, con el estado de `new` en la misma base.** Cambia el contrato del `uid`, `state.json`, la ruta de adjuntos y varias decisiones de arquitectura para un problema que solo tiene Outlook.
- **Id corto también en Apple Mail.** Su `uid` pasaría de 16 a 19 caracteres, con una escritura en disco por búsqueda y sin nada a cambio.
- **Actualizar el `native_id` de una fila, o buscar el mensaje en otras carpetas cuando ya no existe.** El único propósito de la tabla es dar un alias al `native_id`; un mensaje movido es otro `native_id`.
- **Devolver todas las coincidencias de un id corto, con un warning nuevo.** `show` devuelve un solo mensaje y `attachment` necesita exactamente uno: obliga a cambiar el contrato JSON y el de plugins.
- **Registrar todas las filas que el driver lee.** La tabla se llena de mensajes que nadie pidió y crece hasta el tamaño del buzón.
- **Calcular el id corto de la cabecera `Message-ID`.** Cada copia del mismo mensaje en otra carpeta compartiría id corto.
- **Id corto de 10 caracteres.** Con `seq` en el `uid`, una colisión no rompe nada; 8 caracteres igualan el tamaño del `uid` de Apple Mail.
- **Contador `AUTOINCREMENT` de SQLite para `seq`.** Es un único contador por tabla: no puede empezar en 1 para cada par `driver` y `short_id`.
- **Conciliar el `state.json` anterior.** El dueño lo borra a mano y `new` lo regenera.
- **Aceptar el `EntryID` como `uid` en la entrada.** Solo se admite el id corto.
- **`--show-native-id` también en `search`, `new` y `attachment`.** Es una opción de depuración: solo aplica a `show`.
- **Caché del árbol de carpetas; tabla de adjuntos extraídos.** Dan falsos positivos o negativos, o no aportan nada sobre la caché de adjuntos actual.

### Preguntas abiertas

El requerimiento usa la respuesta provisional de cada pregunta. Una respuesta distinta del dueño cambia la parte indicada.

1. **¿Cómo se llama el archivo de la base?** Provisional: `~/.mailquery/cache.db`. Afecta a RF-x1, a "Caché de ids nativos" y a ADR-x1.
2. **¿Cómo se llaman el módulo de la librería y el aviso opcional del driver?** Provisional: módulo `native_ids.py`; el nombre del aviso se fija en `docs/INTERFACES.md`. Afecta a "Arquitectura" y a RF-x3.
3. **El aviso es un método nuevo del driver. ¿Cabe en `plugin_api = 1`?** Provisional: sí, porque es opcional y un plugin que no lo implementa funciona igual. Afecta a RF-x3.
4. **El driver calcula el `uid` al leer y registra al recibir el aviso. Si otro proceso ocupa entre tanto ese `short_id` y `seq`, ¿qué pasa?** Provisional: el comando falla con `E_IO` sin imprimir; al repetirlo, el mensaje recibe el `seq` siguiente. Solo puede ocurrir con una colisión y dos comandos a la vez. Afecta a RF-x3.
5. **¿`new --peek` registra los mensajes que imprime?** Provisional: sí; escribe en la caché de ids y no en el estado. Sin registro, sus uids no se podrían abrir. Afecta a RF-x3 y a AC-x3.
6. **¿Qué error da un fallo al leer o escribir la base, o una base dañada?** Provisional: `E_IO` (exit 3) con su hint actual; no se añade un código nuevo. Afecta a "Comando `show` y errores" y a "Caché de ids nativos".
7. **¿Cómo conviven dos comandos que escriben a la vez?** Provisional: con el bloqueo propio de SQLite y transacciones cortas; si la espera se agota, `E_IO`. Afecta a RF-x1.
8. **¿Qué texto lleva el error de formato del uid en Windows?** Provisional: `invalid uid part '<id>': expected a short id`. Afecta a "Comando `show` y errores".
9. **¿El id corto se acepta en mayúsculas?** Provisional: no, solo tal como se emite. Afecta a "Comando `show` y errores".
10. **Al borrarse la fila con el mayor `seq` de un par, un mensaje posterior puede recibir ese mismo `seq`. ¿Se acepta?** Provisional: sí; exige una colisión, un borrado y otra colisión con el mismo id corto. Afecta a RF-x1 y a "Riesgos".
11. **¿`doctor` informa de la caché de ids?** Provisional: no, sin chequeo nuevo.
12. **¿Qué pasa con las carpetas `attachments/outlook/<32 hexadecimales>/` ya extraídas?** Provisional: quedan sin uso y las borra el cron externo, como cualquier otra.
13. **El coste por comando con Outlook real no está medido. ¿Cambian los presupuestos de rendimiento?** Provisional: no.

## Requerimiento

### Resumen

1. **`uid` corto.** En Windows el `uid` es `outlook:` más un id corto de 8 caracteres, en lugar de los 140 del `EntryID`.
2. **Caché de ids nativos.** `~/.mailquery/cache.db` relaciona cada id corto impreso con su id nativo. El núcleo ofrece la librería y cada driver decide si la usa.
3. **`--show-native-id`.** Opción de depuración de `show`, que muestra el id nativo en lugar del id corto.

### Lo que no cambia

- El formato del `uid`, `"<driver>:<native_id>"`, y el contrato JSON. Ninguna salida tiene una propiedad `short_id` ni `seq`.
- El `uid` de Apple Mail y el driver `apple_mail`.
- `state.json`, su esquema y su migración. Los uids de Outlook de un `state.json` anterior no coinciden con ningún uid nuevo: el dueño lo borra a mano y `new` lo regenera.
- El cursor de `new` y el orden total. La clave de orden de Outlook sigue siendo el `EntryID`.
- La regla de la ruta de la caché de adjuntos. En Outlook el directorio pasa a ser `attachments/outlook/<id corto>/`; el identificador de 32 hexadecimales queda para los plugins con un `<native_id>` largo.
- `plugin_api = 1`.

### Requerimientos

**RF-x1. Librería de ids cortos y caché de ids nativos.** Prioridad M.

**Como** autor de un driver interno o de un plugin, **quiero** que el núcleo me dé una librería que asigne un id corto a un `<native_id>` largo y lo resuelva después, **para** acortar los uids de mi driver sin escribir mi propia caché y sin que el núcleo ni el contrato JSON cambien.

Condiciones:

- **Quién la usa.** Usarla es decisión de cada driver. Ningún comando del núcleo la usa, y el núcleo no distingue un id corto de cualquier otro `<native_id>`.
- **Cálculo del id corto.** Recibe un texto y una cantidad de caracteres. Devuelve el principio, con esa longitud, de la codificación en base32 del `SHA-256` del texto en UTF-8. El alfabeto es `0123456789abcdefghjkmnpqrstvwxyz`.
- **Conexión.** La librería da la conexión a la caché, `~/.mailquery/cache.db`.
- **Asignar.** Dado un `driver` y un `native_id`, devuelve su parte del `uid`: la de su fila si ya está registrado; si no, el id corto con el `seq` que le tocaría. No escribe.
- **Registrar.** Inserta, en una transacción, las filas de los `native_id` que aún no están. Si el `short_id` y el `seq` asignados a uno ya son de otro `native_id`, falla.
- **Resolver.** Dada la parte del `uid`, devuelve el `native_id` de su fila, o nada si no hay fila. No escribe.
- **Descartar.** Borra la fila de un `native_id`.
- **Filas.** Cada fila relaciona `driver`, `short_id` y `seq` con un `native_id`. Un `native_id` tiene como mucho una fila por driver. Una fila no se actualiza: se inserta y se borra.
- **`seq`.** Vale 1 para el primer `native_id` de un `driver` y `short_id`. Para cada uno siguiente, el mayor `seq` de ese par más uno.
- **Parte del `uid`.** Es `<short_id>` si `seq` es 1 y `<short_id>-<seq>` si es mayor. Así representa a un solo `native_id`.
- **Qué no guarda.** Ni `Message-ID`, asuntos, direcciones, cuerpos, cuentas, carpetas, fechas ni rutas.
- **Salida.** Ninguna salida JSON tiene una propiedad `short_id`, `seq` ni otra propia de la caché: el id corto solo aparece dentro del `uid`.
- **Concurrencia.** Dos comandos simultáneos escriben con transacciones cortas y el bloqueo de SQLite. Si la espera se agota ⇒ `E_IO`.

Se comprueba con AC-x2 y AC-x5.

**RF-x2. Id corto en Outlook.** Prioridad M.

**Como** harness de agentes que usa `mailquery` en Windows, **quiero** que el `uid` de un mensaje de Outlook mida 16 caracteres en lugar de 148, **para** que cada respuesta ocupe menos contexto y pueda volver a pedir el mensaje con ese mismo `uid`.

Condiciones:

- **Forma.** El `<native_id>` que el driver `outlook` emite y acepta es el id corto de 8 caracteres del `EntryID` permanente del mensaje, con el sufijo de RF-x1 cuando corresponde: `outlook:k3f9q2m7`, `outlook:k3f9q2m7-2`.
- **De qué se calcula.** Del `EntryID` como texto hexadecimal en mayúsculas. El mismo `EntryID` da siempre el mismo id corto, también después de borrar la caché. El sufijo depende del orden de registro.
- **El `EntryID` no es un uid.** Solo sale en el JSON con `--show-native-id` (RF-x4) y no se acepta como uid, con prefijo o sin él.
- **Resolución.** `show` y `attachment` resuelven el uid en la caché y abren el mensaje por su `EntryID`. Un uid que no está en la caché se trata como mensaje inexistente.
- **Resultado de la consulta al cliente.** *Encontrado*; *ausente confirmado*, cuando el store del mensaje está disponible y el mensaje no existe en él; o *indeterminado*, en cualquier otro caso: Outlook cerrado o que no responde, sin conexión, store no montado o ilegible, error o timeout.
- **Borrado a demanda.** Solo *ausente confirmado* borra la fila; el comando responde entonces como a un mensaje inexistente.
- **Garantía.** Con *indeterminado* la fila se conserva. El comando falla con el error de la causa o, si el store del mensaje no está montado, con `message uid … was not found`.
- **Sin actualizar ni buscar.** Nunca se cambia el `native_id` de una fila ni se busca el mensaje en otras carpetas. Un mensaje movido tiene otro `EntryID` y, por tanto, otro uid.
- **Sin otra purga.** No se borran filas por antigüedad ni al arrancar. Borrar una fila no cambia la caché de adjuntos (RF-51).
- **Apple Mail.** El driver `apple_mail` no usa la caché y su uid no cambia.

Se comprueba con AC-x1 y AC-x4.

**RF-x3. Aviso de mensajes impresos.** Prioridad M.

**Como** autor de un driver que usa ids cortos, **quiero** que el núcleo me diga qué mensajes míos va a imprimir, **para** registrar en la caché solo esos y no todos los que leí.

Condiciones:

- **Qué entrega.** Antes de escribir la respuesta, el núcleo entrega a cada driver que implementa el aviso la lista de los `<native_id>` de sus mensajes que la respuesta contiene.
- **Cuándo avisa.** En `search` y en `new`, también con `--group-by` y con `--peek`. `search --count`, `show`, `attachment`, `mailboxes` y `doctor` no avisan.
- **Opcional.** No cambia `plugin_api`: un driver que no lo implementa no recibe nada. El núcleo no interpreta lo que el driver hace con la lista.
- **Si falla.** El comando falla con el código del fallo y no imprime mensajes ni escribe estado.
- **Outlook.** El driver `outlook` registra en el aviso, en una sola transacción, los mensajes de la lista que aún no están en la caché. Un mensaje leído que no va en la respuesta no se registra.
- **Carrera.** Si el `short_id` y el `seq` con los que se calculó el uid de un mensaje ya pertenecen a otro `native_id` al registrarlo ⇒ `E_IO`, sin imprimir.

Se comprueba con AC-x3.

**RF-x4. `--show-native-id` en `show`.** Prioridad S.

**Como** persona que depura `mailquery`, **quiero** ver en la salida de `show` el id nativo de un mensaje en lugar de su id corto, **para** saber a qué `EntryID` de Outlook corresponde un `uid`.

Condiciones:

- **Qué muestra.** Con la opción, `message.uid` y cualquier otro uid de la respuesta de `show` muestran, después del prefijo del driver, el id nativo del mensaje: en `outlook`, `outlook:<EntryID>`.
- **Solo de presentación.** `show` valida y resuelve el uid, lee el mensaje y arma la respuesta igual que sin la opción. Solo cambia el texto del uid al escribirla.
- **Qué no toca.** La caché de ids nativos, `state.json`, la caché de adjuntos, `cached_path` ni las claves del JSON.
- **No sirve como entrada.** El id nativo mostrado no se acepta como entrada de ningún comando (RF-x2).
- **Cómo lo obtiene el núcleo.** Pide la forma nativa al driver con una operación opcional que no cambia `plugin_api`. Con un driver que no la implementa, la salida es la misma con la opción y sin ella: es el caso de `apple_mail`, cuyo uid ya es el id nativo.
- **Solo en `show`.** En `search`, `new`, `attachment`, `mailboxes` y `doctor`, la opción ⇒ `E_USAGE` (exit 2).

Se comprueba con AC-x6.

### Requisitos existentes que cambian

- **RF-25.** El uid legado sin prefijo de Windows es el id corto de RF-x2, no el `EntryID` hexadecimal.
- **RF-38.** El uid legado sin prefijo de Outlook es el id corto de RF-x2, no el `EntryID` hexadecimal.
- **RF-73.** `show --help` describe `--show-native-id` como opción de depuración (RF-x4). La skill no la menciona.
- **RNF-05.** La caché de ids nativos se suma a los archivos que mailquery crea con permisos 0600 en macOS.

### Decisión de arquitectura

**ADR-x1. Id corto de mensaje a cargo del driver, con una caché local de ids nativos en SQLite (`~/.mailquery/cache.db`).**

El driver `outlook` emite como `<native_id>` un id corto de 8 caracteres derivado del `EntryID`. El núcleo ofrece la librería y avisa a cada driver de los mensajes que imprime, sin saber que el id es corto.

- **Motivo.** El uid de Outlook pasa de 148 a 16 caracteres sin cambiar el formato `"<driver>:<native_id>"`, el contrato JSON, `state.json` ni la regla de la ruta de adjuntos. La caché solo traduce ids, registrar solo lo impreso la mantiene pequeña y cada uid apunta a un solo mensaje.
- **Alternativas descartadas.** `uid` propio del núcleo derivado de `Message-ID`, con el estado de `new` en la misma base; id corto también en Apple Mail; registrar todos los mensajes leídos; devolver todas las coincidencias de un id corto con un warning; cambiar el `native_id` de una fila o buscar el mensaje en otras carpetas; contador `AUTOINCREMENT` de SQLite para `seq`.

ADR-02 cambia: se añade que la caché de ids nativos guarda solo identificadores, ni mensajes ni estado de `new`.

### Arquitectura

- **`native_ids.py`** (nuevo, en `src/mailquery/`). La librería de RF-x1. La usan los drivers que lo deciden. No la llaman los comandos del núcleo y no guarda contenido de correos.
- **`backends/outlook.py`.** Emite el id corto de cada mensaje y lo resuelve en la caché de ids nativos (RF-x2). Registra en el aviso los mensajes impresos (RF-x3).
- **`search.py`.** Avisa a cada driver de los mensajes impresos (RF-x3).
- **`cli.py`.** Opción de depuración `--show-native-id` en `show` (RF-x4).
- **Home.** `cache.db` está en el primer nivel de `~/.mailquery`, junto a `state.json`.

### Caché de ids nativos

Base SQLite de la librería, en `~/.mailquery/cache.db`. La escriben solo los drivers que usan la librería; de los internos, solo `outlook`.

**Figura: Tabla de la caché de ids nativos**

```sql
CREATE TABLE cache_native_ids (
  driver     TEXT    NOT NULL,
  short_id   TEXT    NOT NULL,
  seq        INTEGER NOT NULL,
  native_id  TEXT    NOT NULL,
  PRIMARY KEY (driver, short_id, seq),
  UNIQUE (driver, native_id)
);
```

- **`driver`.** Driver dueño de la fila.
- **`short_id`.** Id corto del `native_id`, sin sufijo.
- **`seq`.** Se calcula al insertar, en la misma transacción, con la regla de RF-x1. No es un contador de SQLite.
- **`native_id`.** Id del mensaje en su driver; en `outlook`, el `EntryID`.

Reglas del archivo:

- La librería crea el archivo y la tabla en su primer uso. Con solo el driver `apple_mail`, el archivo no se crea.
- Solo se insertan y se borran filas: ninguna se actualiza.
- Si el archivo se borra, los uids ya impresos dejan de resolverse hasta que `search` o `new` vuelven a imprimir el mensaje, con el mismo id corto. `new` y su estado no dependen de este archivo.
- Si el archivo no se puede abrir, leer o escribir, o no es una base válida, el comando que lo necesita falla con `E_IO` (exit 3).
- En macOS el archivo tiene permisos 0600.

### Modelo de datos

- **`uid` de Outlook.** `"outlook:<id corto>"`: el id corto de 8 caracteres del `EntryID` permanente del item, con el prefijo del driver. Cambia si el mensaje se mueve de carpeta.
- **Orden total.** `native_order_key` de Outlook sigue siendo el `EntryID` como texto hexadecimal en mayúsculas, no el id corto.
- **Mensaje movido a otra carpeta del alcance dentro de la ventana de lookback.** Su `EntryID` cambia y, con él, su `uid`; puede re-emitirse una vez, como hoy.

### Comando `show` y errores

**Figura: Formas del uid de Outlook en la entrada**

```bash
mailquery show outlook:k3f9q2m7         # Windows: uid prefijado, con el id corto
mailquery show k3f9q2m7                 # Windows: uid legado sin prefijo (driver nativo)
mailquery show outlook:k3f9q2m7-2       # segundo mensaje con el mismo id corto
mailquery show outlook:k3f9q2m7 --show-native-id   # depuración: la salida muestra outlook:<EntryID>
```

Validación del uid en Windows, en `show` y en `attachment`:

- **Forma válida.** 8 caracteres de `0123456789abcdefghjkmnpqrstvwxyz`, seguidos o no de `-` y un entero ≥ 2.
- **Forma inválida** ⇒ `E_USAGE` (exit 2), mensaje `invalid uid part '<id>': expected a short id`. Incluye un `EntryID`, con prefijo o sin él, y un id corto en mayúsculas.
- **Id corto que no está en la caché de ids nativos** ⇒ `E_USAGE` (exit 2), mensaje `message uid … was not found`.
- **Id corto cuyo mensaje ya no existe en un store disponible** ⇒ el mismo `message uid … was not found`, y su fila se borra.
- **Fallo al abrir, leer o escribir `cache.db`** ⇒ `E_IO` (exit 3). `E_IO` pasa a cubrir la caché de ids nativos, además de la caché de adjuntos y el staging.

Los ejemplos del PRD con un uid de Outlook usan el id corto.

### Cambios visibles en 3.0.0

- **`uid` en Windows.** Antes, string `EntryID` hexadecimal. Después, string `"outlook:<id corto>"`, de 16 caracteres; el `EntryID` no se acepta como uid.
- **Opciones de `show`, en macOS y en Windows.** Nueva opción de depuración `--show-native-id`.
- **Archivos de `~/.mailquery` en Windows.** Nuevo `cache.db`, la caché de ids nativos.

### Riesgos

- **Borrado o pérdida de `cache.db`.** Probabilidad baja, impacto bajo. Los uids de Outlook ya impresos dejan de resolverse hasta que una búsqueda vuelve a imprimir el mensaje, con el mismo id corto; `new` no depende de ella.
- **`cache.db` crece con filas de mensajes borrados que nadie vuelve a pedir.** Probabilidad media, impacto bajo. Solo se registran los mensajes impresos y cada fila guarda dos identificadores; borrado a demanda (RF-x2). Riesgo aceptado.
- **Dos mensajes con el mismo id corto.** Probabilidad baja, impacto bajo. Cada uno tiene su `seq` y su uid (RF-x1). El sufijo depende del orden de registro: si se borra `cache.db`, los dos uids pueden intercambiarse, y el `seq` de una fila borrada puede pasar a otro mensaje. Riesgo aceptado.
- **`cache.db` guarda el `EntryID` de los mensajes impresos.** Probabilidad media, impacto bajo. Es un archivo privado del usuario (RNF-05), sin `Message-ID`, asuntos, direcciones ni cuerpos.
- **Un uid de Outlook guardado por el harness deja de resolverse** (mensaje movido, `cache.db` borrada). Probabilidad media, impacto bajo. Se vuelve a buscar el mensaje.
- **Riesgo actual que cambia.** "Rutas largas en Windows (EntryID largo)" deja de ser de Outlook: queda para un plugin con un `<native_id>` largo.

### Documentación

- `docs/INTERFACES.md` documenta la librería del núcleo: el cálculo del id corto con su parámetro de longitud, la conexión a la base y las operaciones de asignar, registrar, resolver y descartar, con sus firmas y un ejemplo de uso desde un plugin.
- `docs/INTERFACES.md` documenta el aviso opcional de mensajes impresos: cuándo lo llama el núcleo, qué recibe y qué pasa si falla.
- `docs/INTERFACES.md` documenta la operación opcional con la que el núcleo pide a un driver la forma nativa de sus ids para `--show-native-id`.
- `README.md`, `README.es.md` y `skills/mailquery/SKILL.md` documentan la forma del `uid` de Outlook y el archivo `cache.db`. Los README documentan además `show --show-native-id` como opción de depuración.
- `docs/security/` recoge que `cache.db` guarda el `EntryID` de los mensajes impresos.
- `docs/tests/` registra los casos de AC-x1…AC-x6.

## Criterios de aceptación

**AC-x1.** En Windows, todo `uid` emitido es `outlook:` más un id corto de 8 caracteres; el mismo mensaje da el mismo `uid` en corridas sucesivas y después de borrar `cache.db`; `show` y `attachment` lo resuelven; un `EntryID` como uid, con prefijo o sin él ⇒ `E_USAGE`. En macOS el `uid` no cambia y, con solo el driver `apple_mail`, `cache.db` no se crea.

**AC-x2.** Dos `native_id` del mismo driver con el mismo id corto reciben `seq` 1 y 2 y los uids `<driver>:<short_id>` y `<driver>:<short_id>-2`; cada uid resuelve a su mensaje.

**AC-x3.** `search` y `new` (también con `--group-by` y con `--peek`) registran en la caché de ids nativos solo los mensajes que imprimen; `search --count` no escribe en ella; si el registro falla, el comando falla sin imprimir mensajes ni escribir estado.

**AC-x4.** Un `uid` cuyo mensaje ya no existe en un store disponible ⇒ `message uid … was not found` y su fila desaparece de la caché. Con Outlook cerrado, sin conexión o con el PST del mensaje desmontado, la fila sigue en la caché: hay un caso de prueba por cada causa. Ninguna fila cambia de `native_id`.

**AC-x5.** Ninguna salida JSON tiene una propiedad `short_id` ni `seq`: las claves de las respuestas de `search`, `new`, `show`, `attachment`, `mailboxes` y `doctor` son las mismas con la caché de ids nativos y sin ella.

**AC-x6.** `show --show-native-id` muestra en Windows `outlook:<EntryID>` en `message.uid`; las claves del JSON, los demás valores, la caché de ids nativos y `cached_path` son los mismos que sin la opción; ese id nativo como entrada de `show` o de `attachment` ⇒ `E_USAGE`; `search`, `new` y `attachment` rechazan la opción con `E_USAGE`. En macOS la salida de `show` es la misma con la opción y sin ella.

## IDs

- Crea: RF-x1…RF-x4, ADR-x1, AC-x1…AC-x6
- Elimina: —

## Dependencias

Ninguna

## Decisiones

- **¿Cómo se acorta el `uid` de Outlook?** (2026-11-22) Con un id corto de 8 caracteres derivado del `EntryID`, a cargo del driver, sin cambiar el formato del `uid` ni el contrato JSON; Apple Mail no cambia (ADR-x1, RF-x2).
- **¿Quién ofrece las herramientas del id corto?** (2026-11-22) Una librería del núcleo, con el cálculo (recibe la cantidad de caracteres), la conexión y las operaciones de la tabla; cada driver decide si la usa (RF-x1).
- **¿Qué guarda la caché de ids nativos?** (2026-11-22) `driver`, `short_id`, `seq` y `native_id` en la tabla `cache_native_ids`, y nada más; ninguna salida JSON tiene una propiedad `short_id` (RF-x1).
- **¿Qué pasa si dos mensajes tienen el mismo id corto?** (2026-11-22) `seq` los distingue y va en el `uid` a partir de 2; cada `uid` apunta a un solo mensaje y no hay warning nuevo (RF-x1).
- **¿Qué mensajes se registran en la caché de ids nativos?** (2026-11-22) Solo los que el comando imprime: el núcleo avisa de ellos a cada driver antes de imprimir (RF-x3).
- **¿Qué pasa si el `native_id` de una fila ya no existe?** (2026-11-22) La fila se borra solo con la ausencia confirmada; con Outlook cerrado, sin conexión o con un PST desmontado no se borra nada; no se actualiza la fila ni se busca el mensaje en otras carpetas (RF-x2).
- **¿Se concilia el `state.json` anterior con el id corto?** (2026-11-22) No: el dueño lo borra a mano y `new` lo regenera.
- **¿Se puede ver el id nativo en la salida?** (2026-11-22) Sí, solo para depurar: con `--show-native-id` en `show` y en ningún otro comando; es solo de presentación y el id nativo no se acepta como entrada (RF-x4).

## Glosario

- **Id corto** (nuevo): Alias de un `native_id` largo: el principio de la codificación en base32 de su `SHA-256`, con el sufijo `-<seq>` cuando otro `native_id` del mismo driver tiene el mismo principio. En Outlook tiene 8 caracteres y es la parte del `uid` posterior al prefijo (RF-x1, RF-x2).
- **Caché de ids nativos (`cache.db`)** (nuevo): Base SQLite de `~/.mailquery` que relaciona cada id corto impreso con su `native_id`.

## Conciliación con el PRD

**Tabla: Conciliación con el PRD**

| ID | Contrato | Archivo | Ancla | Qué cambia | Estado |
|---|---|---|---|---|---|
| RC-01 | Resumen del producto | `01-resumen.md` | después de `` `new` y `search --unread` se mantienen `` | Bloque nuevo "Id corto de mensaje en Outlook" con los tres puntos del resumen del requerimiento. | pendiente |
| RC-02 | uid legado de Windows | `06-requisitos-funcionales.md` | RF-25; RF-38 | El uid legado sin prefijo de Windows es el id corto (RF-x2). | pendiente |
| RC-03 | Forma del `uid` de Outlook | `11-modelo-de-datos.md` | `` `uid` `` | `"outlook:<id corto>"`: el id corto del `EntryID`; cambia si el mensaje se mueve de carpeta. | pendiente |
| RC-04 | Ejemplos de `show` con uid de Outlook | `12.04-show.md` | `mailquery show apple_mail:83143` | Los ejemplos de Windows usan el id corto, con prefijo y sin él. | pendiente |
| RC-05 | Ejemplo de invocación con uid de Outlook | `anexos/E-ejemplos-invocacion.md` | `mailquery show outlook:00000000A1B2C3D4…` | El ejemplo usa el id corto. | pendiente |
| RC-06 | Requisitos nuevos | `06-requisitos-funcionales.md` | después de RF-79 | Subsección nueva 6.10 con RF-x1…RF-x4. | pendiente |
| RC-07 | Ayuda de `show` | `06-requisitos-funcionales.md` | RF-73 | `show --help` describe `--show-native-id` como opción de depuración. | pendiente |
| RC-08 | Privacidad y permisos | `07-requisitos-no-funcionales.md` | RNF-05 | La caché de ids nativos entre los archivos con permisos 0600. | pendiente |
| RC-09 | Decisiones de arquitectura | `08-adr.md` | ADR-02; después de ADR-49 | ADR-02 añade que la caché de ids nativos guarda solo identificadores. ADR-x1 nueva. | pendiente |
| RC-10 | Módulos | `09-arquitectura.md` | `` `cli.py` ``; `` `search.py` ``; `` `backends/outlook.py` ``; después de `` `uid.py` `` | `cli.py`: opción de depuración de `show`. `search.py`: aviso de mensajes impresos. `backends/outlook.py`: id corto y su resolución. Fila nueva de `native_ids.py`. | pendiente |
| RC-11 | Árbol de fuentes y home | `10-carpetas-y-cache.md` | `│   ├── cli.py, config.py`; `├── state.json` | `native_ids.py` en el árbol de fuentes. `cache.db` en el del home. | pendiente |
| RC-12 | Orden total | `11-modelo-de-datos.md` | `- **Orden total:**` | Aclara que `native_order_key` de Outlook es el `EntryID`, no el id corto. | pendiente |
| RC-13 | Caché de ids nativos | `11-modelo-de-datos.md` | después de `- **Composición JSON multi-driver:**` | Subsección nueva 11.4 con la tabla `cache_native_ids`, sus columnas y sus reglas. | pendiente |
| RC-14 | Opciones de `show` | `12.04-show.md` | `` Opciones: `--fields LISTA` `` | Añade `--show-native-id`, opción de depuración (RF-x4). | pendiente |
| RC-15 | Validación del uid | `12.04-show.md` | `` `uid` con formato inválido ``; `` `uid` que no existe, está borrado `` | Formato inválido en Windows: no es un id corto, con el mensaje `expected a short id`. No encontrado: también un uid que no está en la caché de ids nativos. | pendiente |
| RC-16 | Error `E_IO` | `12.06-errores.md` | `` `E_IO` `` | Cubre también la caché de ids nativos. | pendiente |
| RC-17 | Mensaje movido de carpeta | `18-procesamiento-unico.md` | `Mensaje movido a otra carpeta del alcance` | Cambia su `EntryID` y, con él, su `uid`. | pendiente |
| RC-18 | Criterios de aceptación | `20-criterios-aceptacion.md` | después de AC-62 | AC-x1…AC-x6. | pendiente |
| RC-19 | Cambios visibles: opciones | `22-versiones.md` | `` Opciones de `search`, `new` y `show` `` | Añade `--show-native-id` en `show`. | pendiente |
| RC-20 | Cambios visibles en Windows | `22-versiones.md` | `**Tabla: Cambios visibles de 3.0.0 solo en Windows**` | Fila `uid`: `"outlook:<id corto>"`, de 16 caracteres; el `EntryID` no se acepta como uid. Fila nueva: `cache.db` en `~/.mailquery`. | pendiente |
| RC-21 | Riesgos | `23-riesgos.md` | después de `Los chequeos de un plugin son tan fiables como el plugin`; `Rutas largas en Windows (EntryID largo)` | Los cinco riesgos nuevos del requerimiento. "Rutas largas en Windows (EntryID largo)" pasa a ser de los plugins con un `<native_id>` largo. | pendiente |

Secciones revisadas que no cambian:

- Sección 10.3.3 y fila "Directorio de adjuntos" de la sección 15: la regla de la ruta no cambia.
- Sección 11.2 y AC-06: `state.json` no cambia.
- Sección 12.5: sus ejemplos no tienen ningún `uid` de Outlook, y `--show-native-id` no cambia las claves ni la forma del JSON.
- Secciones 12.2, 12.3, 12.7 y 12.11: `search`, `new` y `attachment` no tienen la opción.
- Sección 12.8: `doctor` no cambia.
- Sección 22.3: el cambio de forma del `uid` ya justifica la versión mayor.
- ADR-12: ya estaba superado; queda como registro.
- Anexo A: es el registro del spike y no se cambia.

## Documentos consumidores

- README.md: pendiente
- README.es.md: pendiente
- skills/mailquery/SKILL.md: pendiente
- docs/INTERFACES.md: pendiente
- docs/config.example.toml: sin cambio
- docs/recipes/: pendiente
- docs/security/: pendiente
- docs/tests/: pendiente

## Checklist de conciliación

**Tabla: Checklist de conciliación**

| ID | Ítem | Cómo se verifica | Estado |
|---|---|---|---|
| CL-01 | Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila, de RC-01 a RC-21 | pendiente |
| CL-02 | El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial | pendiente |
| CL-03 | Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` | pendiente |
| CL-04 | Las decisiones están en el Anexo D y el glosario está aplicado | Ocho filas en el Anexo D y dos términos en el glosario | pendiente |
| CL-05 | Los documentos consumidores están actualizados | Ninguno está `pendiente` | pendiente |
| CL-06 | No quedan textos obsoletos en el PRD ni en los documentos consumidores: "`EntryID` hexadecimal" como uid legado de Windows; `"outlook:<EntryID>"` como `uid`; `expected an uppercase hexadecimal EntryID`; `mailquery show outlook:00000000A1B2C3D4…`; "Rutas largas en Windows (EntryID largo)" | Búsqueda de cada texto | pendiente |
| CL-07 | El defecto registrado está cerrado | Su entrada de `docs/KNOWN-DEFECTS.md` | no aplica |
| CL-08 | La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` | pendiente |
| CL-09 | La suite pasa | Suite completa, con `doc_14` y `doc_15` | pendiente |
| CL-10 | La garantía de no borrar filas con Outlook cerrado, sin conexión o con un PST desmontado está probada | Un caso de prueba por cada causa (AC-x4) | pendiente |

## Desviaciones aprobadas

Ninguna
