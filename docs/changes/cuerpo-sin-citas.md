---
aliases: ["Cuerpo sin texto citado en show, search y new"]
tags: [cambio]
---

# Cuerpo sin texto citado en show, search y new

**Tipo:** cambio
**Base:** PRD 2.9
**Fecha:** 2026-11-26
**Aprobación:** Ariel Salazar Hinojosa, 2026-11-28
**Paquete:** 3.0.0 (mayor)

## Estado

aprobado

## Contexto

### Problema

Un agente que resumía los pendientes de dos semanas de correo leyó unos 35 cuerpos con `show`. Cada respuesta de un hilo trae todo el historial citado: un mensaje de unos 10 KB solo decía "Yes." y el resto era la conversación anterior, que el agente ya había leído en otros mensajes. Para saber si un hilo está cerrado basta casi siempre la parte nueva de la última respuesta.

El `snippet` de `search` y `new` tiene el mismo problema cuando la parte nueva va debajo de la cita o intercalada: los 200 caracteres son texto citado y no sirven para el triage.

La cita no se puede quitar después de la conversión: con un cuerpo HTML, la conversión a texto (A3) junta todo el espacio en blanco en un solo espacio, y `body_text` llega como una sola línea en la que ya no se reconocen las marcas de cita.

### Solución elegida

- `show`, `search` y `new` entregan por defecto el cuerpo sin el texto citado: `body_text` en `show` y el `snippet` en `search` y `new`. Cada cita quitada deja el marcador `[quoted text omitted: N chars]`.
- `--keep-quoted` entrega el cuerpo completo. En el servidor MCP es el parámetro `keep_quoted` de las tres herramientas.
- El campo `quoted_chars` dice cuántos caracteres se quitaron: en `show`, junto a `body_text`; en `search` y `new`, dentro de `body`.
- En los drivers nativos, la conversión compartida del cuerpo marca qué partes del texto son citas; en un plugin, el núcleo las marca sobre el `body_text` que entrega. El núcleo decide qué se quita (ADR-52). Las reglas de reconocimiento son del núcleo y valen para todos los drivers.
- Solo se quita lo que tiene una marca reconocida. Los separadores y las marcas de texto plano solo cuentan en una respuesta, un reenvío no se corta nunca y un cuerpo que se quedaría sin texto propio sale completo.

### Alternativas descartadas

- **Corte opcional con `--strip-quoted`.** El agente tendría que acordarse de pedirlo en cada llamada para ahorrar tokens, y lo barato tiene que ser lo que sale por defecto, como la fila mínima de F3. Se elige cortar por defecto y entregar la cita con `--keep-quoted`.
- **Clave `[content].quoted_display` en `config.toml`.** El indicador basta; una clave más haría que la misma llamada diera cuerpos distintos según la configuración de cada equipo. Descartada por el dueño.
- **Quitar la cita de `body_text` ya convertido en los drivers nativos.** Las marcas de un cuerpo HTML no sobreviven a la conversión (ver "Problema").
- **Que cada driver corte.** El indicador tendría que llegar al driver y cada driver repetiría las reglas, con el riesgo de que Apple Mail y Outlook corten distinto (ADR-52).
- **Segmentos de cita entregados por los plugins.** El plugin definiría qué es una cita y `plugin_api = 1` tendría que cambiar. El núcleo aplica las reglas de texto plano al `body_text` del plugin.
- **Dos campos, `quoted_omitted` y `quoted_chars`.** `quoted_omitted` sería siempre `quoted_chars > 0`. Se deja solo `quoted_chars`.
- **Conservar la línea de atribución ("On …, X wrote:").** Una respuesta cuya parte nueva está vacía nunca se quedaría sin texto propio y la regla "Sin texto propio" no se aplicaría. Gmail y Thunderbird ya la meten en su marca; la atribución se quita con su cita y el marcador avisa del corte.
- **Quitar `<blockquote>` sin atributos.** Mucha gente lo usa para citar texto que no es una respuesta; el riesgo de quitar contenido propio es alto.
- **Cortar en el primer separador o en líneas `>` sin comprobar que el mensaje es una respuesta.** Newsletters, notificaciones y plantillas usan `<hr>` y bloques de "From:", y un texto plano puede llevar líneas `>` de markdown o de un log pegado. Un falso positivo afectaría a todas las llamadas, porque el corte es el comportamiento por defecto.
- **Cortar los reenvíos.** En un reenvío con una nota ("FYI") la parte útil es justo el mensaje reenviado.

### Verificación de los formatos

Los nombres de clase, `id` y estilo de "Formatos de cita" vienen de cómo esos clientes generan el HTML. Los tests de la implementación usan fixtures sacados de correos reales de cada cliente y de cada idioma del conjunto, anonimizados; las capturas originales no entran en el repositorio.

### Fuera de alcance

- Firmas, avisos legales y líneas como "Sent from my iPhone": son otra heurística, con otros riesgos, y serían otra unidad con su propia opción.
- Idiomas fuera del conjunto inicial (inglés, español, francés, alemán, italiano y portugués).
- `attachment`: no entrega el cuerpo.
- Los filtros de `search`: `--text` sigue buscando en el cuerpo completo.

### Preguntas abiertas

Ninguna.

## Requerimiento

### Lo que no cambia

- Qué cuerpo se elige y cómo se convierte (RF-53, A3), incluida la omisión de elementos ocultos.
- Los modos de URL A4 (RF-54).
- `W_HIDDEN_CONTENT` (RF-56): cuenta los caracteres ocultos de todo el cuerpo, con la cita incluida, con `--keep-quoted` o sin él.
- `--text` (RF-09, §12.12 punto 5): compara con el cuerpo completo convertido con A3, con la cita incluida.
- Qué se lee de cada mensaje (RNF-22): el cuerpo solo se lee en los casos de RF-68 y RF-69, a cuya lista de campos que leen el cuerpo se añade `quoted_chars`. Las pruebas de respuesta se leen en la misma lectura del cuerpo.
- El tope de 200 caracteres del `snippet`, el de 20.000 caracteres de cada cuerpo de `show` (§15.6) y el de 60.000 caracteres de cuerpo por respuesta de `show` que añade `show-varios-uid`.
- El cursor de `new`: avanza igual con `--keep-quoted` o sin él.
- `--count` y `--group-by` sin `snippet` ni `body` no leen cuerpos.
- `plugin_api = 1` y lo que un plugin entrega en el cuerpo (RF-53); el núcleo hace el corte sobre su `body_text`.

### Requerimientos

**RF-93. Cuerpo sin texto citado.** Prioridad S.

**Como** harness de agentes, **quiero** recibir por defecto solo la parte nueva de cada mensaje, sin el historial que cita, **para** leer un hilo sin pagar en tokens la misma conversación en cada respuesta.

Condiciones:

- **`show` por defecto.** `body_text` se entrega sin el texto citado.
- **`search` y `new` por defecto.** El `snippet` se calcula sobre el cuerpo sin el texto citado.
- **Opción `--keep-quoted`.** `show`, `search` y `new` aceptan `--keep-quoted`, sin argumento; los demás comandos no la aceptan (`E_USAGE`).
- **Alcance de `--keep-quoted`.** La opción vale para todos los mensajes de la llamada.
- **Salida con `--keep-quoted`.** `body_text` y `snippet` salen con el texto citado y sin marcadores.
- **Solo texto marcado.** Solo se quita texto que tiene una marca de "Formatos de cita".
- **Marca envolvente.** Una marca envolvente se quita con su contenido.
- **Separador.** Un separador quita desde la marca hasta el final del cuerpo, con las marcas envolventes y el texto que van detrás.
- **Todas las envolventes.** Se quitan todas las marcas envolventes del cuerpo.
- **Primer separador.** Si cuentan varios separadores, manda el primero según el orden del documento.
- **Marcas anidadas.** Una marca dentro de una marca envolvente no cuenta: la exterior se quita una vez, con todo su contenido.
- **Solo texto visible.** Un elemento que A3 omite no es una marca, y su texto no cuenta para un bloque de cabeceras ni para una línea de atribución.
- **Envolventes HTML sin prueba.** Las marcas envolventes de un cuerpo HTML cuentan aunque el mensaje no tenga prueba de respuesta.
- **Separadores solo en respuestas.** Un separador, en HTML o en texto plano, solo cuenta si el mensaje tiene una prueba de "Pruebas de respuesta".
- **Líneas citadas solo en respuestas.** Las líneas citadas de un cuerpo de texto plano solo cuentan si el mensaje tiene una prueba de respuesta.
- **Marca sin prueba.** Un separador o unas líneas citadas que no cuentan por falta de prueba de respuesta son texto propio; las marcas envolventes HTML que van detrás de ese separador se quitan igual.
- **Texto propio.** Es el texto del cuerpo que queda fuera de las marcas que cuentan.
- **Reenvío por el asunto.** Un mensaje cuyo primer prefijo del asunto es de reenvío no se corta.
- **Reenvío por el cuerpo.** Un mensaje con una marca de reenvío en su texto propio no se corta.
- **Reenvío dentro de una envolvente.** Un mensaje no se corta si el primer texto de una de sus marcas envolventes que no va detrás de un separador que cuenta, sin contar el espacio en blanco, es una marca de reenvío. Gmail y Apple Mail ponen ahí el mensaje reenviado.
- **Reenvío citado.** Una marca de reenvío que está dentro de una cita (también en una marca envolvente que va detrás de un separador que cuenta), y no al principio de una marca envolvente del mensaje, no impide el corte.
- **Sin texto propio.** Si no queda texto propio, o solo queda espacio en blanco, el cuerpo no se corta.
- **Cuerpo sin cortar.** Un cuerpo que no se corta sale como con `--keep-quoted`.
- **Marcador.** Cada cita quitada (con `N` ≥ 1) se sustituye por `[quoted text omitted: N chars]`, con esa forma también para `N` igual a 1.
- **Límites de una cita.** Una cita empieza en su primer carácter que no es espacio en blanco y termina en el último, también tras aplicar A2; el espacio en blanco que la rodea antes de A2 es del texto vecino, y el que queda en los bordes de la cita al aplicar A2 se descarta sin duplicarlo en el texto vecino. Si tras A2 una cita queda vacía o solo con espacio en blanco, se omite sin marcador, no suma a `quoted_chars` y, en HTML, se quita el espacio separador sobrante junto a ella para no dejar espacios al principio, al final ni duplicados.
- **Citas seguidas.** Dos citas quitadas separadas solo por espacio en blanco son una sola cita, con un solo marcador, y ese espacio cuenta en su `N`.
- **Espacio junto al marcador.** Si el carácter de antes o el de después del marcador no es espacio en blanco, entre los dos se pone un espacio, que no cuenta en `N`. En texto plano las citas son líneas enteras, así que el marcador queda en una línea propia.
- **Marcador sin saneado.** El marcador es texto del producto: no pasa por A2 ni por A4.
- **Longitud `N`.** `N` es el número de caracteres de la cita quitada, después de A2.
- **Valor de `quoted_chars`.** Es la suma de los `N` de todas las citas quitadas del mensaje, también de las que un tope deja fuera del texto entregado.
- **`quoted_chars` a cero.** `quoted_chars` vale `0` cuando no se quitó nada: sin marcas que cuenten, con `--keep-quoted`, en un cuerpo que no se corta y cuando el cuerpo no está disponible o no es legible.
- **Tope de cada cuerpo.** El tope de 20.000 caracteres de cada cuerpo de `show` y `body_truncated` se calculan sobre el texto cortado, con sus marcadores.
- **Tope por respuesta.** El tope de 60.000 caracteres de cuerpo por respuesta de `show` suma los `body_text` ya cortados.
- **Tope del `snippet`.** El tope de 200 caracteres del `snippet` y `body.truncated` se calculan sobre el texto cortado, con sus marcadores.
- **Marcador entero.** El truncado no parte un marcador: si el límite cae dentro de uno, el texto se corta justo antes de él, y el `snippet` termina con su `…` de siempre.
- **A2 por segmento.** Con el corte, A2 se aplica por separado a cada cita y a cada tramo de texto propio; con `--keep-quoted`, a todo el cuerpo, como hoy.
- **Conteos de A5.** Los conteos de `W_EXTERNAL_LINKS`, `W_NON_ASCII_DOMAIN`, `W_LONG_URL` y `W_SCRIPT_LINK` se hacen sobre el cuerpo ya cortado, antes del `snippet` y del truncado: un enlace que solo está en una cita quitada no cuenta.
- **Reglas del núcleo.** Las reglas de "Formatos de cita" son del núcleo y valen igual en macOS y en Windows. Una marca nueva se añade al núcleo y vale para todos los drivers.
- **Marcas en un plugin.** En el cuerpo de un driver de plugin, el núcleo busca las marcas de texto plano en el `body_text` que el plugin entrega. Los plugins no definen reglas.
- **Prueba en un plugin.** En un mensaje de un driver de plugin, la única prueba de respuesta es el prefijo del asunto.
- **Servidor MCP.** `--keep-quoted` es el parámetro `keep_quoted`, `boolean`, de las herramientas `search`, `new` y `show`, generado del parser como cualquier indicador (RF-85).

Se comprueba con AC-97, AC-98, AC-99, AC-100, AC-101, AC-102, AC-103, AC-104, AC-105, AC-106, AC-107, AC-108 y AC-109.

### Decisión de arquitectura

**ADR-52. Las citas las marca la conversión compartida del cuerpo y las quita el núcleo.**

La conversión del cuerpo que comparten los drivers nativos (`output.py`) reconoce las marcas de cita y de reenvío mientras convierte el HTML o lee el texto plano, y entrega el texto partido en segmentos que dicen si son texto propio, una marca envolvente HTML, unas líneas citadas de texto plano o un tramo que empieza en un separador, junto con si llevan marca de reenvío. El driver nativo pasa esos segmentos y sus pruebas de respuesta en el cuerpo que entrega. Para un plugin, el núcleo obtiene los segmentos aplicando las mismas reglas de texto plano a su `body_text`. El núcleo decide con el asunto, las pruebas de respuesta, las marcas de reenvío de los segmentos y `--keep-quoted` qué segmentos quita, y los sustituye por el marcador.

- **Motivo.** Las marcas de un cuerpo HTML solo existen durante la conversión, que ya es compartida: reconocerlas ahí da las mismas reglas en Apple Mail y en Outlook. Que el núcleo decida evita pasar opciones al driver, y que el núcleo marque el cuerpo de un plugin mantiene `plugin_api = 1` sin cambios.
- **Alternativas descartadas.** Cortar en cada driver (reglas duplicadas y riesgo de cortes distintos por plataforma); quitar la cita de `body_text` ya convertido (las marcas HTML ya no existen); segmentos entregados por los plugins (cada plugin definiría qué es una cita y cambiaría la API de plugin).

### Formatos de cita

**Marcas envolventes en un cuerpo HTML.** Se quita el elemento con todo su contenido.

- Apple Mail, Thunderbird y Roundcube: `<blockquote type="cite">`.
- Thunderbird: `<div class="moz-cite-prefix">`, la línea de atribución que va justo delante del `<blockquote type="cite">`.
- Gmail: `<div class="gmail_quote">`, que contiene la línea de atribución (`gmail_attr`) y el `<blockquote class="gmail_quote">`.
- Yahoo Mail: `<div class="yahoo_quoted">`.
- Proton Mail: `<blockquote class="protonmail_quote">`.
- Outlook en el móvil y el nuevo Outlook: `<div id="mail-editor-reference-message-container">` y `<div class="ms-outlook-mobile-reference-message">`.
- Una línea de atribución (las frases de "Marcas en un cuerpo de texto plano", en una o dos líneas) que va justo delante de una marca envolvente, con solo espacio en blanco entre las dos, se quita con ella, como hace Roundcube.
- `<blockquote>` sin atributos no es una marca.

**Separadores en un cuerpo HTML.** Se quita desde la marca hasta el final del cuerpo.

- Outlook en la web y el nuevo Outlook: `<div id="divRplyFwdMsg">`.
- Outlook de escritorio: un `<div>` cuyo atributo `style` declara `border` con el valor `none` y `border-top` con un valor que contiene `solid` (colores habituales `#E1E1E1` y `#B5C4DF`), y cuyo contenido empieza con un bloque de cabeceras.
- Cualquier cliente: un `<hr>` seguido de un bloque de cabeceras.

**Marcas en un cuerpo de texto plano.**

- Líneas citadas (envolvente): una o más líneas seguidas que empiezan con `>`. Se quitan esas líneas y no el resto.
- Las marcas de texto plano son líneas enteras.
- Atribución de unas líneas citadas: si justo antes de las líneas `>`, con como mucho una línea en blanco entre medias, hay una línea de atribución, se quita con ellas.
- Línea de atribución (separador cuando no le siguen líneas `>`): una línea entera con una de estas formas; la frase puede repartirse en dos líneas seguidas, y entonces son las dos la línea de atribución:
  - "On … wrote:"
  - "El … escribió:"
  - "Le … a écrit :"
  - "Am … schrieb …:"
  - "Il … ha scritto:"
  - "Em … escreveu:"
- Mensaje original (separador): `-----Original Message-----`, `----- Original Message -----` y sus traducciones `-----Mensaje original-----`, `-----Message d'origine-----`, `-----Ursprüngliche Nachricht-----`, `-----Messaggio originale-----` y `-----Mensagem original-----`.
- Línea de Outlook (separador): una línea de 32 guiones bajos (`________________________________`) seguida de un bloque de cabeceras.

**Bloque de cabeceras (HTML y texto plano).** Tres o más líneas seguidas que empiezan con estas etiquetas, en cualquier idioma del conjunto; la primera es siempre la del remitente, y entre las demás puede ir la de copia.

- Remitente: "From:", "De:", "Von:", "Da:".
- Fecha: "Sent:", "Date:", "Enviado:", "Enviado el:", "Fecha:", "Gesendet:", "Datum:", "Envoyé :", "Inviato:", "Data:", "Enviada em:", "Enviado em:".
- Destinatario: "To:", "Para:", "An:", "À :", "A:".
- Copia: "Cc:".
- Asunto: "Subject:", "Asunto:", "Betreff:", "Objet :", "Oggetto:", "Assunto:".

En texto plano se acepta la etiqueta entre asteriscos (`*From:*`).

**Marcas de reenvío.** Hacen que el mensaje no se corte (RF-93, "Reenvío por el cuerpo" y "Reenvío dentro de una envolvente"). Cada marca es una línea entera.

- Gmail: una de estas frases entre uno o más guiones a cada lado, con espacio en blanco entre los guiones y la frase: "Forwarded message", "Mensaje reenviado", "Message transféré", "Weitergeleitete Nachricht", "Messaggio inoltrato", "Mensagem encaminhada". Ejemplo: `---------- Forwarded message ---------`.
- Apple Mail: "Begin forwarded message:", "Inicio del mensaje reenviado:", "Début du message réexpédié :", "Anfang der weitergeleiteten Nachricht:", "Inizio messaggio inoltrato:", "Início da mensagem reencaminhada:", "Início da mensagem encaminhada:".
- Outlook reenvía con el mismo separador que usa al responder; su reenvío se reconoce por el prefijo del asunto.

**Prefijos del asunto.**

- Respuesta: `RE:`, `AW:`, `R:`, `RIF:`, `RES:`.
- Reenvío: `FW:`, `FWD:`, `RV:`, `TR:`, `WG:`, `I:`, `ENC:`.
- Forma: el prefijo va al principio del asunto, después de quitar el espacio inicial y las etiquetas entre corchetes que lo preceden (`[EXT] RE:`); admite espacio antes de los dos puntos (`RE :`) y un contador entre corchetes (`RE[2]:`). Cuenta solo el primer prefijo.

**Reglas comunes.**

- En HTML, una línea es el texto visible entre dos límites de bloque o `<br>`, leído a través de sus elementos en línea (como `<b>From:</b>` o un enlace `<a>`); esta definición aplica a los bloques de cabeceras, a las líneas de atribución y a las marcas de reenvío.
- Una clase se reconoce como una de las clases del atributo `class` (`class="gmail_quote gmail_quote_container"` es `gmail_quote`), y un `id` o una clase, también con el prefijo `x_` (`x_divRplyFwdMsg`, `x_gmail_quote`) que Outlook en la web añade al HTML citado.
- Las declaraciones de `style` se leen después del paso de hojas en línea y se comparan sin distinguir mayúsculas, sin espacios y sin `!important`.
- Las etiquetas, las frases y los prefijos se comparan sin distinguir mayúsculas y aceptan el espacio antes de los dos puntos del francés.

### Pruebas de respuesta

Un mensaje es una respuesta si tiene al menos una de estas pruebas:

- Apple Mail: la cabecera `In-Reply-To` o `References` con valor en el `.emlx`.
- Outlook: `PR_IN_REPLY_TO_ID` o `PR_INTERNET_REFERENCES` con valor, o un `PR_CONVERSATION_INDEX` de más de 22 bytes.
- Cualquier driver, también un plugin: un asunto cuyo primer prefijo es de respuesta.

### Contrato de salida

- **`show`.** `quoted_chars` (entero) es un campo nuevo del mensaje. Va después de `body_truncated` en el orden canónico de §12.4 y es un valor válido de `--fields`. Sale siempre que sale `body_text`, como `body_truncated`, también en la fila mínima, que queda `uid`, `subject`, `from`, `date_received`, `body_text`, `body_truncated`, `quoted_chars` y `attachments`.
- **`--fields quoted_chars`.** Sin `body_text` es válido y entrega `uid` y `quoted_chars`. Lee el cuerpo y cuenta como cuerpo entregado para los warnings: `quoted_chars` entra en la lista de campos que leen el cuerpo de RF-69 y en la de campos que entregan el cuerpo del punto 2 de RF-72.
- **`search` y `new`.** El objeto `body` tiene, en este orden, `available`, `readable`, `partial`, `truncated` y `quoted_chars`. `body.truncated` dice si el `snippet`, calculado sobre el cuerpo ya cortado, pasa de 200 caracteres.
- **Forma.** `quoted_chars` sale con las mismas opciones con y sin `--keep-quoted` (RF-28).

### Contrato del driver

El cuerpo que entrega un driver nativo (`BodyRow`, `docs/INTERFACES.md`) gana dos claves opcionales (`NotRequired`), como `hidden_chars`. Un plugin no las entrega y el núcleo no las consulta en el cuerpo de un plugin: obtiene sus segmentos con `output.plain_text_quotes(body_text)` y usa como prueba de respuesta solo el prefijo del asunto.

- `quote_segments: tuple[QuoteSegment, ...]`, con `QuoteSegment(text: str, kind: Literal["own", "wrap", "plain_wrap", "cut"], forward_mark: bool = False)`:
  - `own`: texto propio.
  - `wrap`: una marca envolvente HTML con su contenido, incluida la línea de atribución o el `<div class="moz-cite-prefix">` que la precede inmediatamente con solo espacio en blanco entre ambos.
  - `plain_wrap`: unas líneas citadas de texto plano, con su línea de atribución.
  - `cut`: un tramo que empieza en un separador, HTML o de texto plano, y llega hasta el principio del segmento siguiente o hasta el final.
- `reply_evidence: bool`: el driver encontró las pruebas de respuesta de su backend.

Reglas de los segmentos:

- **Invariante.** La concatenación de los `text`, en orden, es igual al `body_text` que entrega el driver. La conversión compartida produce los segmentos, así que la invariante se cumple por construcción.
- **Límites.** Los segmentos son tramos del texto ya convertido, con el espacio en blanco ya juntado. Un segmento que no es `own` empieza en su primer carácter que no es espacio en blanco y termina en el último; el espacio en blanco que lo rodea va en segmentos `own`.
- **Anidadas.** Una marca dentro de una marca envolvente no produce segmento.
- **Partes.** El `\n` con el que Apple Mail une las partes del cuerpo es un segmento `own`, y los segmentos de cada parte siguen en el orden de las partes; un `cut` de una parte llega hasta el final de la parte, y el núcleo quita también las partes siguientes.
- **Marca de reenvío.** `forward_mark` es `true` en un segmento `own` o `cut` si alguna de sus líneas (antes de juntar espacios en HTML) es una marca de reenvío, y en un segmento `wrap` si su primera línea visible no vacía es una marca de reenvío; en `plain_wrap` es `false`.
- **Decisión del núcleo.** Con prueba de respuesta, el núcleo quita los `wrap`, los `plain_wrap` y todo lo que va desde el primer `cut` hasta el final del cuerpo. Sin ella, quita solo los `wrap`, y los `plain_wrap` y los `cut` son texto propio. Si el primer prefijo del asunto es de reenvío, o si algún segmento que queda como texto propio o algún `wrap` que no va detrás de un `cut` que cuenta tiene `forward_mark` a `true`, el cuerpo no se corta.

La conversión compartida da los segmentos:

- `output.html_body_to_text(html) -> HtmlText`: `HtmlText` gana `segments: tuple[QuoteSegment, ...]`.
- `output.plain_text_quotes(text: str) -> tuple[QuoteSegment, ...]`, para un cuerpo de texto plano de un driver nativo y para el `body_text` de un plugin.

### Cadena del cuerpo

La cadena de §12.12 punto 3 queda así: HTML si existe (RF-53) → hojas `<style>` en línea → conversión HTML con marcas de cita → texto con A3 → A2 (por segmento con el corte) → conteo de `W_HIDDEN_CONTENT` → corte del texto citado y marcadores (RF-93, salvo con `--keep-quoted`) → conteos de A5 → A4 → `snippet` (`search` y `new`) o truncado a 20.000 caracteres (`show`).

### Ayuda

Cada texto es un solo `help` sin saltos de línea; aquí se parte solo para leerlo.

**Figura: Ayuda de `--keep-quoted` en `show`, `search` y `new`**

```text
deliver the body with the text quoted from earlier messages; by default each
quote is replaced by [quoted text omitted: N chars]
```

**Figura: Ayuda de `--fields` en `show`, que sustituye la de `show-varios-uid`**

```text
selects the fields of each message (uid is always included); without --fields:
uid, subject, from, date_received, body_text, body_truncated, quoted_chars,
attachments; body_truncated and quoted_chars always come with body_text;
comma-separated or repeatable; all selects every field; valid fields: uid,
message_id, subject, from, to, cc, date_sent, date_received, mailbox, is_read,
is_flagged, has_attachments, size_bytes, headers, body_text, body_truncated,
quoted_chars, attachments, partial, readable, source, all
```

### Ejemplos

El mensaje del primer ejemplo es una respuesta (`PR_IN_REPLY_TO_ID` con valor) cuyo HTML lleva la parte nueva "Yes." y, después, `<div id="divRplyFwdMsg">` con 9.840 caracteres de conversación anterior.

**Figura: `mailquery show outlook:k3f9q2m7xa`, respuesta de Outlook con el historial citado**

```json
{
  "ok": true,
  "command": "show",
  "generated_at": "2026-11-26T10:00:00-04:00",
  "content_notice": "…",
  "messages": [
    {
      "uid": "outlook:k3f9q2m7xa",
      "subject": "RE: Geo-blocking for the EU launch",
      "from": {"name": "Ana Pérez", "address": "ana.perez@example.com"},
      "date_received": "2026-11-25T16:20:11-04:00",
      "body_text": "Yes. [quoted text omitted: 9840 chars]",
      "body_truncated": false,
      "quoted_chars": 9840,
      "attachments": []
    }
  ],
  "failed": [],
  "not_delivered": [],
  "warnings": []
}
```

Con `--keep-quoted`, `body_text` es el cuerpo completo, con la conversación anterior, y `quoted_chars` es `0`.

**Figura: `mailquery search --subject Barclays --since 2w --fields snippet,body` (abreviado)**

```json
{
  "uid": "outlook:p7c2d9x4ra",
  "subject": "RE: Barclays onboarding",
  "…": "…",
  "snippet": "Yes. [quoted text omitted: 10112 chars]",
  "body": {"available": true, "readable": true, "partial": false, "truncated": false, "quoted_chars": 10112}
}
```

**Figura: Llamada MCP equivalente a `mailquery show outlook:k3f9q2m7xa --keep-quoted`**

```json
{"name": "show", "arguments": {"uid": ["outlook:k3f9q2m7xa"], "keep_quoted": true}}
```

### Elementos del PRD que cambian

- **Reglas comunes de RF-55–RF-61.** Las señales de URL cuentan el cuerpo entregado, cortado salvo con `--keep-quoted`, en lugar del cuerpo completo.
- **RF-53.** La última frase dice que A2, A4, A5 y el corte del texto citado se aplican al cuerpo de un plugin.
- **RF-55.** `W_EXTERNAL_LINKS` se cuenta después del corte del texto citado y antes del recorte del `snippet` o del truncado.
- **RF-69.** `quoted_chars` es un valor válido de `--fields` en `show`, va después de `body_truncated`, sale siempre que sale `body_text` y entra en la lista de campos que leen el cuerpo. El requisito se comprueba también con AC-107.
- **RF-72.** El punto 1 dice que los conteos de A5 se hacen sobre el cuerpo ya cortado; el punto 2 añade `quoted_chars` a los campos que entregan el cuerpo.
- **RF-73.** La ayuda de `search`, `new` y `show` describe `--keep-quoted`; la skill, `README.md`, `README.es.md` y las recetas explican el corte por defecto, el marcador, `quoted_chars` y cuándo usar `--keep-quoted`.
- **ADR-52.** Nueva.
- **Criterios de `show-varios-uid`.** AC-89 (fila mínima de `show`) y AC-92 (ayuda de `show`) incluyen `quoted_chars`.
- **§1 y §2.** El modelo de salida de F3 y los problemas que resuelve el producto dicen que el cuerpo sale sin el texto citado por defecto.
- **§9.** `output.py` marca las citas y las marcas de reenvío en la conversión; `emlx.py` y `backends/outlook.py` entregan los segmentos de cita y las pruebas de respuesta en el cuerpo; el núcleo (`search.py`) marca las citas en el cuerpo de un plugin, las quita y pone los marcadores; `cli.py` añade `--keep-quoted` a `search`, `new` y `show`; el diagrama de §9.5 muestra el corte entre A2 y el conteo de URLs A5 (manteniendo `W_HIDDEN_CONTENT` y el matching de `--text` sobre el cuerpo completo).
- **§11.** La entidad Cuerpo del modelo común gana los segmentos de cita y las pruebas de respuesta; la correspondencia de cada backend dice de dónde salen las pruebas de respuesta.
- **§12.2, §12.3 y §12.4.** La opción `--keep-quoted`; en §12.2, `--text` busca también en el texto citado; en §12.4, la fila mínima con `quoted_chars`.
- **§12.5.** `body.quoted_chars` en `search` y `new`, `quoted_chars` en `show`, y un ejemplo de cuerpo sin texto citado.
- **§12.12.** La cadena del cuerpo del punto 3 y, en el punto 5, que `--text` compara con el cuerpo completo.
- **§15.6.** Una fila de valores fijos para el texto citado.
- **§16.3.** El riesgo de una marca de cita falsa y cómo se ve un corte.
- **§22.** `--keep-quoted` en la fila de opciones de `search`, `new` y `show`, y la fila de `search` y `new` deja de decir que `--fields all` da la fila anterior.
- **§20, §22.3, §22.4, §23 y Anexo E,** según la tabla de conciliación.

### Lo que se elimina

- El cuerpo completo como `body_text` por defecto de `show`.
- El `snippet` calculado sobre el cuerpo completo por defecto en `search` y `new`.

### Cambios visibles

- Una fila nueva en la tabla de cambios visibles de `3.0.0` en ambas plataformas: `body_text` y `snippet` sin texto citado por defecto, con marcadores, `quoted_chars` y `--keep-quoted`.
- El corte por defecto entra en los cambios incompatibles de `3.0.0` para un harness que consume la 2.0.x.

### Riesgos

- **Reconocimiento heurístico.** Un formato que no está en "Formatos de cita" no se quita y el cuerpo sale entero; un separador falso, o texto propio escrito debajo de un separador, se pierde del cuerpo entregado. Mitigación: solo se quita con marcas conocidas y visibles, los separadores y las líneas citadas exigen una prueba de respuesta, los reenvíos no se cortan, el marcador y `quoted_chars` hacen visible cada corte y `--keep-quoted` da el cuerpo completo.
- **Contenido oculto tras una marca de cita falsa.** Un remitente malicioso puede poner texto que la persona ve en su cliente detrás de un separador falso, o dentro de una marca envolvente HTML, que no exige prueba de respuesta, para que el agente no lo lea. Mitigación: el marcador y `quoted_chars` dicen cuánto se quitó, `W_HIDDEN_CONTENT` sigue contando sobre todo el cuerpo y la skill explica que un mensaje sospechoso, o uno con `quoted_chars` alto, se revisa con `--keep-quoted` (RF-73).
- **Cuerpos de plugin.** RF-53 pide al plugin el texto convertido desde el HTML; si su conversión junta las líneas, las marcas de texto plano no se reconocen y el cuerpo sale entero. Mitigación: el cuerpo nunca pierde texto propio por esto, y un plugin que conserva los saltos de línea obtiene el corte.

## Criterios de aceptación

**AC-97.** En macOS y en Windows, `show` de una respuesta HTML con prueba de respuesta, parte nueva "Yes." y un separador `divRplyFwdMsg` devuelve `body_text` `Yes. [quoted text omitted: N chars]` y `quoted_chars` igual a `N`, la longitud de la cita después de A2; con un `U+200B` dentro de la cita, `N` no lo cuenta, y una cita que solo contiene `U+200B` se omite sin marcador y da `quoted_chars: 0`; con `--keep-quoted`, `body_text` es el cuerpo completo convertido (A3, A2, A4), con la cita y sin marcadores, y `quoted_chars` es `0`.

**AC-98.** Una respuesta HTML con texto propio, una cita `<blockquote type="cite">`, más texto propio y una cita `<div class="gmail_quote gmail_quote_container">` devuelve el texto propio de los dos tramos, en orden, con un marcador en el lugar de cada cita y `quoted_chars` igual a la suma de los dos `N`. Se quitan igual `x_gmail_quote`, `yahoo_quoted`, `protonmail_quote`, `mail-editor-reference-message-container` y `ms-outlook-mobile-reference-message`; `moz-cite-prefix` se quita junto con el `<blockquote type="cite">` que le sigue, con un solo marcador, y una línea "On …, X wrote:" justo delante de un `<blockquote type="cite">`, también. Un `<blockquote type="cite">x</blockquote>` deja `[quoted text omitted: 1 chars]`. Un mensaje sin prueba de respuesta con una cita `<div class="gmail_quote">` también la pierde. Un `<blockquote>` sin atributos no se quita.

**AC-99.** Una respuesta de Outlook de escritorio con un `<div style="border:none;border-top:solid #E1E1E1 1.0pt">` cuyo contenido empieza con `<b>De:</b>`, `<b>Enviado el:</b>`, `<b>Para:</b>`, `<b>CC:</b>` y `<b>Asunto:</b>` se corta en ese `div`; con "Enviada em:" en lugar de "Enviado el:", también; el mismo `div` sin bloque de cabeceras no corta.

**AC-100.** Un mensaje HTML con un `<hr>` seguido de un bloque de cabeceras y sin ninguna prueba de respuesta sale completo, con `quoted_chars: 0`. Se corta en el `<hr>` con cada prueba por separado: en macOS, `In-Reply-To` y `References`; en Windows, `PR_IN_REPLY_TO_ID`, `PR_INTERNET_REFERENCES` y un `PR_CONVERSATION_INDEX` de 27 bytes (con uno de 22 bytes no corta); en los dos, un asunto con cada prefijo de respuesta de "Prefijos del asunto", también con las formas `RE :`, `RE[2]:` y `[EXT] RE:`. Sin prueba de respuesta, un `<hr>` con su bloque de cabeceras seguido de un `<div class="gmail_quote">` conserva el `<hr>` y su bloque como texto y quita la cita `gmail_quote`. Con prueba de respuesta, un `<hr>` seguido de un bloque de cabeceras dentro de un elemento con `display:none` no corta.

**AC-101.** Un mensaje con prueba de respuesta y un separador sale completo, con `quoted_chars: 0`, si el primer prefijo de su asunto es cualquiera de los prefijos de reenvío de "Prefijos del asunto", o si su texto propio tiene `---------- Forwarded message ---------`, "Begin forwarded message:" o "Inicio del mensaje reenviado:". Sale completo también un reenvío de Gmail con asunto sin prefijo cuya cita `<div class="gmail_quote">` empieza con `---------- Forwarded message ---------`, y un reenvío de Apple Mail cuyo `<blockquote type="cite">` empieza con "Begin forwarded message:". Una respuesta con asunto `RE: FW: Contrato` se corta, y una respuesta `RE:` cuya cita contiene "Begin forwarded message:" después de su línea de atribución también.

**AC-102.** Una respuesta con texto propio, un `<div id="mail-editor-reference-message-container">` que contiene un `<div id="divRplyFwdMsg">`, y texto propio después del contenedor devuelve los dos tramos propios con un solo marcador en el lugar del contenedor. Una respuesta con un separador seguido de un `<blockquote type="cite">` devuelve un solo marcador, desde el separador hasta el final. Una respuesta de texto plano con texto propio y dos líneas `-----Original Message-----` devuelve un solo marcador, desde la primera.

**AC-103.** Una respuesta cuyo cuerpo es solo una cita reconocida sale completa, con `quoted_chars: 0`. Un mensaje con cuerpo no disponible o no legible da `quoted_chars: 0`.

**AC-104.** En una respuesta de texto plano:
- una atribución "El 25 nov 2026, Ana" con "escribió:" en la línea siguiente, una línea en blanco y líneas `>` se quita con su bloque, que deja un marcador en una línea propia;
- una respuesta intercalada entre dos bloques `>` se conserva;
- `-----Mensaje original-----`, una línea "On Mon, 23 Nov 2026, Bob wrote:" sin líneas `>` detrás y la línea de 32 guiones bajos seguida de un bloque `*De:*`, `Envoyé :`, `À :`, `Objet :` cortan hasta el final;
- la línea de 32 guiones bajos sin bloque de cabeceras no corta.
El mismo cuerpo en un mensaje sin prueba de respuesta sale completo.

**AC-105.** `search --fields snippet,body` y `new --fields snippet,body` calculan el `snippet` sobre el cuerpo cortado y entregan `body.quoted_chars`; con `--keep-quoted`, el `snippet` sale del cuerpo completo y `body.quoted_chars` es `0`. `search --text` encuentra un mensaje por un texto que solo está en su cita. `new` avanza el cursor igual con `--keep-quoted` o sin él.

**AC-106.** Una respuesta con 100 caracteres propios y una cita de 30.000 caracteres da `body_truncated: false` en `show`. `show` de cuatro respuestas así entrega las cuatro; con `--keep-quoted` entrega tres, con `body_truncated: true`, y pone la cuarta en `not_delivered[]`. Un cuerpo con 19.990 caracteres propios, una cita y más texto propio da en `show` un `body_text` que termina antes del marcador, `body_truncated: true` y `quoted_chars` con la longitud de la cita. Un `snippet` cuyo límite de 200 caracteres cae dentro de un marcador termina justo antes de él, con `…`. Si la cita tiene un elemento oculto, `W_HIDDEN_CONTENT` da el mismo conteo con `--keep-quoted` y sin él. Un enlace externo que solo está en la cita no cuenta en `W_EXTERNAL_LINKS` sin `--keep-quoted` y sí con él.

**AC-107.** Sin `--fields`, cada elemento de `messages[]` de `show` tiene `uid`, `subject`, `from`, `date_received`, `body_text`, `body_truncated`, `quoted_chars` y `attachments`, en ese orden; `--fields body_text` da `uid`, `body_text`, `body_truncated` y `quoted_chars`; `--fields quoted_chars` da `uid` y `quoted_chars` y emite los warnings del estado del cuerpo. En `tools/list`, `search`, `new` y `show` tienen el parámetro `keep_quoted` de tipo `boolean`.

**AC-108.** `show --help`, `search --help` y `new --help` muestran el texto de `--keep-quoted` de "Ayuda", y `show --help` muestra el de `--fields`.

**AC-109.** Con un driver de plugin y `plugin_api = 1`, un mensaje con asunto `RE: Contrato` cuyo `body_text` tiene `-----Original Message-----` devuelve el texto anterior y un marcador; el mismo mensaje con asunto `Contrato` sale completo, con `quoted_chars: 0`.

- El criterio AC-89 de `show-varios-uid` (fila mínima de `show`) pasa a decir `uid`, `subject`, `from`, `date_received`, `body_text`, `body_truncated`, `quoted_chars` y `attachments`, y que `--fields body_text` da `uid`, `body_text`, `body_truncated` y `quoted_chars`.
- El criterio AC-92 de `show-varios-uid` (ayuda de `show`) comprueba el texto de `--fields` de "Ayuda".
- `README.md`, `README.es.md`, la skill y las recetas explican el corte por defecto, el marcador, `quoted_chars` y cuándo usar `--keep-quoted`: al revisar un mensaje sospechoso, cuando `quoted_chars` es alto y hace falta el contexto del hilo y cuando la parte nueva remite a la cita.
- La suite completa pasa.

## IDs

- Crea: RF-93, ADR-52, AC-97…AC-109
- Elimina: —

## Dependencias

- campos-documentados
- show-varios-uid

## Decisiones

- **¿Se quita el texto citado por defecto?** (2026-11-26) Sí, en `show`, `search` y `new`; `--keep-quoted` entrega el cuerpo completo.
- **¿El `snippet` de `search` y `new` también se calcula sin el texto citado?** (2026-11-26) Sí, con el mismo `--keep-quoted` en los dos comandos.
- **¿Hay una clave de configuración para el texto citado?** (2026-11-26) No; `[content].quoted_display` queda descartada.
- **¿Qué formatos de cita se reconocen?** (2026-11-26) Las marcas envolventes y los separadores de Apple Mail, Thunderbird, Roundcube, Gmail, Yahoo Mail, Proton Mail y Outlook, los bloques de cabeceras y las líneas de atribución en inglés, español, francés, alemán, italiano y portugués; `<blockquote>` sin atributos no es una marca.

## Glosario

Términos nuevos del grupo "Términos generales":

- **Marca de cita:** elemento HTML o línea de texto plano de "Formatos de cita" que delimita texto citado. Una marca envolvente delimita la cita con su contenido; un separador marca el principio de una cita que llega hasta el final del cuerpo.
- **Prueba de respuesta:** dato del mensaje que dice que es una respuesta: las cabeceras `In-Reply-To` o `References`, sus equivalentes de Outlook, un índice de conversación de más de 22 bytes o un prefijo de respuesta en el asunto.
- **Texto citado:** parte del cuerpo de un mensaje que repite mensajes anteriores del hilo y que una marca de cita delimita. `show`, `search` y `new` la sustituyen por `[quoted text omitted: N chars]` salvo con `--keep-quoted`, en un reenvío, cuando un separador o unas líneas citadas no tienen prueba de respuesta y cuando el cuerpo se quedaría sin texto propio.

## Conciliación con el PRD

**Tabla: Conciliación con el PRD**

| ID | Contrato | Archivo | Ancla | Qué cambia | Estado |
|---|---|---|---|---|---|
| RC-01 | Modelo de salida de F3 | `01-resumen.md` | después de `` 8. **Plugins en `doctor`:** `` | Punto 9: el cuerpo sale sin el texto citado por defecto, con un marcador por cita, y `--keep-quoted` lo entrega completo (RF-93). | pendiente |
| RC-02 | Problemas que resuelve el producto | `02-problema.md` | después de `8. **Herramientas tipadas para el harness:**` | Punto 9: leer un hilo sin recibir en cada respuesta la conversación que ya se leyó (RF-93). | pendiente |
| RC-03 | Señales de URL | `06-requisitos-funcionales.md` | `Reglas comunes de RF-55–RF-61:` | Las señales de URL cuentan las URLs del cuerpo entregado, sin el texto citado salvo con `--keep-quoted`, en lugar del cuerpo completo (RF-93). | pendiente |
| RC-04 | Cuerpo de un plugin | `06-requisitos-funcionales.md` | RF-53 | La última frase dice que A2, A4, A5 y el corte del texto citado se aplican al cuerpo de un plugin (RF-93). | pendiente |
| RC-05 | Momento del conteo de enlaces | `06-requisitos-funcionales.md` | RF-55 | Se cuenta después de A3 y del corte del texto citado, y antes del recorte del `snippet` o del truncado de `show` (RF-93). | pendiente |
| RC-06 | `--fields` en `show` | `06-requisitos-funcionales.md` | RF-69 | `quoted_chars` es un valor válido, va después de `body_truncated`, entra en la fila mínima, sale siempre que sale `body_text` y lee el cuerpo; el requisito se comprueba también con AC-107. | pendiente |
| RC-07 | Warnings según lo entregado | `06-requisitos-funcionales.md` | RF-72 | El punto 1 dice que los conteos de A5 se hacen sobre el cuerpo ya cortado, antes del `snippet` y del truncado; el punto 2 añade `quoted_chars` a los campos que entregan el cuerpo (RF-93). | pendiente |
| RC-08 | Ayuda, skill, README y recetas | `06-requisitos-funcionales.md` | RF-73 | La ayuda de `search`, `new` y `show` describe `--keep-quoted`; la skill, `README.md`, `README.es.md` y las recetas explican el corte por defecto, el marcador, `quoted_chars` y cuándo usar `--keep-quoted`: al revisar un mensaje sospechoso, cuando `quoted_chars` es alto y hace falta el contexto del hilo y cuando la parte nueva remite a la cita (RF-93). | pendiente |
| RC-09 | Cuerpo sin texto citado | `06-requisitos-funcionales.md` | después de RF-89 | RF-93, después de RF-90 que añade `show-varios-uid`. | pendiente |
| RC-10 | Marcado y corte de las citas | `08-adr.md` | después de ADR-51 | ADR-52. | pendiente |
| RC-11 | Módulo de conversión | `09-arquitectura.md` | `` `output.py` `` | La conversión marca las citas y las marcas de reenvío en los segmentos del HTML y del texto plano (ADR-52). | pendiente |
| RC-12 | Módulo del núcleo | `09-arquitectura.md` | `` `search.py` `` | El armado del cuerpo marca las citas del cuerpo de un plugin, las quita según las pruebas de respuesta, el asunto y `--keep-quoted`, y pone los marcadores y `quoted_chars` (RF-93, ADR-52). | pendiente |
| RC-13 | Módulo de la CLI | `09-arquitectura.md` | `` `cli.py` `` | Opción `--keep-quoted` en `search`, `new` y `show`. | pendiente |
| RC-14 | Módulos de los backends nativos | `09-arquitectura.md` | `` `store.py`, `emlx.py`, `accounts.py` ``; `` `backends/outlook.py` `` | `emlx.py` y `backends/outlook.py` entregan `quote_segments` (desde la conversión compartida) y `reply_evidence` en el cuerpo (RF-93, ADR-52). | pendiente |
| RC-15 | Flujo de un mensaje | `09-arquitectura.md` | `### 9.5 Flujo de un mensaje` | El diagrama pone el corte del texto citado entre A2 (`S`) y el conteo de URLs A5 (`C`), manteniendo `W_HIDDEN_CONTENT` y `--text` desde `S` (RF-93). | pendiente |
| RC-16 | Entidad Cuerpo | `11-modelo-de-datos.md` | `**Tabla: Entidades del modelo común**` | La fila Cuerpo gana `quote_segments` y `reply_evidence`, claves opcionales que solo entregan los drivers nativos (ADR-52). | pendiente |
| RC-17 | Pruebas de respuesta por backend | `11-modelo-de-datos.md` | `**Tabla: Correspondencia de cada backend con el modelo común**` | La fila Cuerpo dice de dónde salen las pruebas de respuesta: `In-Reply-To` y `References` del `.emlx`; `PR_IN_REPLY_TO_ID`, `PR_INTERNET_REFERENCES` y la longitud de `PR_CONVERSATION_INDEX` en Outlook (RF-93). | pendiente |
| RC-18 | Búsqueda en el cuerpo | `12.02-search.md` | `` `--text PATRÓN` `` | El cuerpo incluye el texto citado. | pendiente |
| RC-19 | Opción de `search` | `12.02-search.md` | después de `` `--strip-links` `` | Fila `--keep-quoted`: entrega el `snippet` calculado sobre el cuerpo con el texto citado (RF-93). | pendiente |
| RC-20 | Opción de `new` | `12.03-new.md` | después de `` `--strip-links` `` | Fila `--keep-quoted`, como en `search`; el cursor avanza igual (RF-93). | pendiente |
| RC-21 | Salida de `show` | `12.04-show.md` | `Devuelve` | `body_text` sale sin el texto citado por defecto; `quoted_chars` va después de `body_truncated` en el orden canónico y en la fila mínima, y acompaña siempre a `body_text` (RF-93, RF-69). | pendiente |
| RC-22 | Opciones de `show` | `12.04-show.md` | `Opciones:` | `--keep-quoted` entrega `body_text` con el texto citado y vale para todos los mensajes de la llamada (RF-93). | pendiente |
| RC-23 | Objeto `body` | `12.05-1-contrato-json.md` | `` Sin `--group-by` ni `--count`, `count` es ``; `### 12.5 Contrato de salida (JSON)` | `body.truncated` se refiere al `snippet` del cuerpo cortado y `body.quoted_chars` dice cuántos caracteres de cita se quitaron; el ejemplo de la fila completa añade `quoted_chars` a `body` (RF-93). | pendiente |
| RC-24 | Ejemplos A e I de `show` | `12.05-2-ejemplos-show-attachment.md` | `#### A.`; `#### H.` | El mensaje de `#### A.` y los mensajes del Ejemplo I que añade `show-varios-uid` después de `#### H.` añaden `quoted_chars` después de `body_truncated`. | pendiente |
| RC-25 | Ejemplo de cuerpo sin texto citado | `12.05-3-ejemplos-contenido-salida.md` | después de `` **Ejemplo — `show --fields`.** `` | Ejemplo nuevo y abreviado: la respuesta de Outlook con `divRplyFwdMsg` de la unidad, con su `body_text` y su `quoted_chars`, y una frase sobre `--keep-quoted` (RF-93); si el archivo supera 300 líneas al conciliar, se parte según el protocolo. | pendiente |
| RC-26 | Cadena del cuerpo | `12.12-precedencia.md` | `3. Cuerpo:` | La cadena de "Cadena del cuerpo": A2 por segmento con el corte, el corte del texto citado después del conteo de `W_HIDDEN_CONTENT` y antes de los conteos de A5, y los topes sobre el texto cortado sin partir un marcador (RF-93). | pendiente |
| RC-27 | Búsqueda en el cuerpo | `12.12-precedencia.md` | `5. Búsqueda:` | `--text` compara con el cuerpo completo, con el texto citado. | pendiente |
| RC-28 | Valores fijos | `15-configuracion.md` | después de `` Cuerpo en `show` `` | Fila "Texto citado": omitido por defecto en `body_text` y `snippet`, con el marcador `[quoted text omitted: N chars]`; `--keep-quoted` lo entrega (RF-93). Va después de las filas que añade `show-varios-uid`. | pendiente |
| RC-29 | Prompt injection | `16-seguridad.md` | después de `El contenido de los correos (asunto` | Un separador falso, o una marca envolvente HTML, que no exige prueba de respuesta, pueden ocultar al agente texto que la persona ve; el marcador y `quoted_chars` hacen visible el corte, `W_HIDDEN_CONTENT` cuenta sobre todo el cuerpo y un mensaje sospechoso se revisa con `--keep-quoted` (RF-93, RF-73). | pendiente |
| RC-30 | Alcance de los criterios | `20-criterios-aceptacion.md` | `3. **Plugins, adjuntos` | El punto 3 añade el cuerpo sin texto citado a su enumeración y su rango incluye AC-97…AC-109. | pendiente |
| RC-31 | Criterios de `show` de `show-varios-uid` | `20-criterios-aceptacion.md` | AC-81 | De los criterios que `show-varios-uid` añade después de AC-81, AC-89 (fila mínima de `show`) y AC-92 (ayuda de `show`) incluyen `quoted_chars`, como dice "Criterios de aceptación". | pendiente |
| RC-32 | Criterios nuevos | `20-criterios-aceptacion.md` | después de AC-81 | AC-97…AC-109, después de AC-85…AC-92 que añade `show-varios-uid`. | pendiente |
| RC-33 | Cambios incompatibles de `3.0.0` | `22-versiones.md` | `` `3.0.0` (mayor) `` | El corte del texto citado por defecto en `show`, `search` y `new` entra en la lista de cambios incompatibles para un harness que consume la 2.0.x. | pendiente |
| RC-34 | Fila de `search` y `new` en los cambios visibles | `22-versiones.md` | `` Fila de `search` y `new` `` | El paréntesis dice que `--fields all --keep-quoted` da la fila anterior, con `quoted_chars` en `body` (RF-93). | pendiente |
| RC-35 | Cambios visibles del cuerpo | `22-versiones.md` | después de `` Fila de `search` y `new` `` | Fila nueva en la tabla de ambas plataformas: `body_text` y `snippet` sin texto citado por defecto, marcador, `quoted_chars` y `--keep-quoted`; va después de la fila que añade `show-varios-uid`. | pendiente |
| RC-36 | Opciones en los cambios visibles | `22-versiones.md` | `` Opciones de `search`, `new` y `show` `` | `--keep-quoted` se añade a las opciones de los tres comandos (RF-93). | pendiente |
| RC-37 | Riesgo de resultados MCP grandes | `23-riesgos.md` | `El harness trunca resultados MCP grandes` | La mitigación añade que el texto citado se quita por defecto (RF-93). | pendiente |
| RC-38 | Riesgo del reconocimiento de citas | `23-riesgos.md` | después de `El harness trunca resultados MCP grandes` | Fila nueva con los riesgos de "Riesgos": reconocimiento heurístico, contenido oculto tras una marca de cita falsa y cuerpos de plugin, con sus mitigaciones (RF-93). | pendiente |
| RC-39 | Ejemplos de invocación | `anexos/E-ejemplos-invocacion.md` | después de `mailquery show outlook:k3f9q2m7xa` | Ejemplo `mailquery show apple_mail:83143 --keep-quoted` con el comentario "cuerpo con el texto citado" (RF-93). | pendiente |

## Documentos consumidores

- README.md: pendiente
- README.es.md: pendiente
- skills/mailquery/SKILL.md: pendiente
- docs/INTERFACES.md: pendiente
- docs/config.example.toml: sin cambio
- docs/recipes/: pendiente
- docs/security/threat-model.md: pendiente
- docs/tests/TEST-CATALOG.md: pendiente
- docs/tests/acceptance-matrix.md: pendiente
- docs/tests/content.md: pendiente
- docs/tests/content-wiring.md: pendiente
- docs/tests/docs-packaging.md: pendiente
- docs/tests/end-to-end.md: pendiente
- docs/tests/mcp-server.md: pendiente
- docs/tests/outlook-data.md: pendiente
- docs/tests/outlook-runtime.md: pendiente
- docs/tests/output-shape.md: pendiente
- docs/tests/plugins.md: pendiente
- docs/tests/search.md: pendiente
- docs/tests/smoke.md: pendiente
- docs/tests/state-backends.md: pendiente

## Checklist de conciliación

**Tabla: Checklist de conciliación**

| ID | Ítem | Cómo se verifica | Estado |
|---|---|---|---|
| CL-01 | Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila | pendiente |
| CL-02 | El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial | pendiente |
| CL-03 | Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` | pendiente |
| CL-04 | Las decisiones están en el Anexo D y el glosario está aplicado | Revisión de "Decisiones" y "Glosario" | pendiente |
| CL-05 | Los documentos consumidores están actualizados | Ninguno está `pendiente` | pendiente |
| CL-06 | No quedan textos obsoletos en el PRD ni en los documentos consumidores: la cadena del cuerpo de §12.12 sin el corte del texto citado; la arista `S --> C[Conteo de URLs A5]` del diagrama de §9.5; la fila mínima de `show` sin `quoted_chars`; `body_truncated always comes with body_text`; listas de campos de `show` sin `quoted_chars`; `body` de `search` y `new` sin `quoted_chars`; "y el cuerpo completo" en las reglas comunes de RF-55–RF-61; "(`--fields all` da la fila anterior)" en §22 | Búsqueda de cada texto | pendiente |
| CL-07 | El defecto registrado está cerrado | Su entrada de `docs/KNOWN-DEFECTS.md` | no aplica |
| CL-08 | La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` | pendiente |
| CL-09 | La suite pasa | Suite completa, con `doc_14` y `doc_15` | pendiente |

## Desviaciones aprobadas

Ninguna
