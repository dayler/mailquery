# Defectos conocidos

Estado: **4 defectos abiertos** (BUG-02 a BUG-05, documentación y payload) y **2 observaciones registradas** (OBS-01 salida de errores, OBS-02 payload verboso). Seguimiento de defectos que el dueño reconoce en el producto actual. Este documento no cambia el PRD: [`PRD.md`](PRD.md) describe el comportamiento actual y enlaza cada defecto como "Pendiente conocido".

| ID | Título | Estado | Registrado |
|----|--------|--------|------------|
| BUG-01 | `attachment` no extrae adjuntos de plugins `attachments: "remote"` | Cerrado el 2026-11-14 | 2026-11-12 |
| BUG-02 | El skill no enseña `show UID --fields body_text` y `--fields` se lee como exclusivo de `search` | Abierto | 2026-11-16 |
| BUG-03 | "Qué mejoraría del skill": afirmaciones no verificadas y semánticas ausentes | Abierto | 2026-11-16 |
| BUG-04 | `mailbox` se repite completo en cada fila de `search` (24 veces, 3 valores) | Abierto | 2026-11-16 |
| BUG-05 | Correos masivos: `to`/`cc` entregan la lista completa de cientos de destinatarios | Abierto | 2026-11-17 |

---

## BUG-01 — `attachment` no extrae adjuntos de plugins `attachments: "remote"`

**Registrado:** 2026-11-12, por decisión del dueño. **Cerrado:** 2026-11-14,
corregido en `3.0.0` (en desarrollo).

**Comportamiento esperado** (RF-43, RF-46, ADR-22):

- Un plugin externo con `network: true` y `attachments: "remote"` obtiene los bytes del adjunto desde su origen. Su uso de red es responsabilidad del plugin.
- El núcleo no abre red. Valida, sanea, aplica límites, calcula el SHA-256 y escribe en la caché exactamente igual que con un driver `"local"` (RF-47).
- Un adjunto no recuperable responde `E_ATTACHMENT_UNAVAILABLE` con el `reason` del plugin (`network`, `not_local`, …), no `unsupported`.

**Comportamiento anterior (hasta la corrección):**

- `mailquery attachment <driver>:<native_id>` con un driver `attachments: "remote"` fallaba con `E_ATTACHMENT_UNAVAILABLE`, exit 3, mensaje `attachment recovery is unsupported by driver '<driver>'`, antes de abrir el store. Era el mismo tratamiento que `attachments: "none"`.
- `show` ya listaba los nombres que da el plugin.

**Origen:**

- `_require_attachment_capabilities` de `cli.py`, que rechazaba `mode not in ("none", "remote")`.
- `docs/INTERFACES.md`, sección de `cli.py` ("el núcleo no puede materializar adjuntos remotos").
- UT-ATC-10.03 ([`tests/retired.md`](tests/retired.md)), retirado; lo sustituyen `UT-RMT-01`–`UT-RMT-03`.

**Impacto:** ninguno en uso real mientras no existan plugins remotos, pero impedía implementar `mailquery-graph` u otro conector remoto con recuperación de adjuntos sin cambiar el núcleo.

**Corrección aplicada:** `_require_attachment_capabilities` rechaza solo `attachments: "none"` (con el hint que pide declarar un driver `"local"` o `"remote"`); un driver `"remote"` entrega sus bytes al mismo motor de adjuntos, con el mismo bloqueo, límites, SHA-256, staging, caché, manifiesto, `--force` y A7. Un fallo de origen del plugin se sigue reportando con su `reason` (`network`, `not_local`, …) como `E_ATTACHMENT_UNAVAILABLE`. UT-ATC-10.03 se retiró y lo sustituyen los casos `UT-RMT-01` a `UT-RMT-03`; `INTERFACES.md` y `TEST-CATALOG.md` se actualizan con la integración. En `PRD.md`, la conciliación debe admitir de nuevo los adjuntos remotos en RF-43, RF-46, §4 y la fila 5 de la precedencia de `attachment` (el texto anterior está en `docs/PRD-v2.1.md` del commit `3935ec5`) y retirar la nota "Pendiente conocido".

---

## BUG-02 — El skill no enseña `show UID --fields body_text`; `--fields` se lee como exclusivo de `search`

**Registrado:** 2026-11-16, por decisión del dueño. Detectado en una tarea real
(extraer montos de los avisos bancarios del 2026-11-15 desde el correo local).

**Comportamiento esperado** (grupo DOC-10 de [`tests/docs-packaging.md`](tests/docs-packaging.md)):

- La documentación que consume el agente (`skills/mailquery/SKILL.md`) explica el uso económico de `--fields` en los tres comandos, no solo en `search`/`new`.
- En particular, documenta que `show UID --fields body_text` entrega `uid` + el cuerpo sin `headers`, `source`, `attachments`, `partial` ni `readable`; es la vía barata para responder "cuánto, dónde y cuándo" de un mensaje concreto.
- La asimetría entre `body` (objeto de disponibilidad de la fila de `search`/`new`) y `body_text` (texto del cuerpo, solo en `show`) queda explícita, porque adivinarla cuesta una llamada fallida.

**Comportamiento observado (verificado el 2026-11-16, `mailquery` 3.0.0 en macOS):**

```
mailquery search --fields body        → ok
mailquery search --fields body_text   → E_USAGE: unknown field 'body_text' (exit 2)
mailquery show   --fields body        → E_USAGE: unknown field 'body'      (exit 2)
mailquery show   --fields body_text   → ok
```

- El CLI está correcto: `search -h` y `show -h` imprimen cada uno su lista de campos válidos (DOC-10.01 lo cubre). El defecto no está en la ayuda, sino en el skill, que no la reproduce ni la sugiere.
- `SKILL.md` §"Default row and `--fields`" (líneas 81–90) explica `--fields` desde la perspectiva de `search`/`new`; su único ejemplo de `show` es `--fields attachments`, que enseña justo lo contrario (omitir el cuerpo). No menciona `body_text` ni advierte que las listas difieren por comando.
- `test_doc_10_02` fija `--fields attachments` como el único ejemplo de `show` en ambos README y `test_doc_10_03` no menciona `body_text`: ninguna prueba detecta la omisión, y la prueba del README refuerza la lectura equivocada ("`--fields` en `show` sirve para no traer el cuerpo").

**Impacto medido:** en la tarea del 2026-11-15 (10 avisos bancarios), `show` sin `--fields` produjo 3.572 bytes en el caso mayor y 29,2 KB los 10 juntos; con `--fields body_text`, 2.116 bytes en ese caso (−41 %), es decir ≈12 KB / ≈3.300 tokens evitables (~13 % del total consumido en esa tarea). Además, un agente que intenta adivinar el nombre gasta una llamada fallida (exit 2) y ~200 tokens por intento, y solo obtiene el nombre correcto ejecutando `show -h`, que el skill no invita a correr ("no preparation step is needed: run the commands directly").

**Origen:**

- `skills/mailquery/SKILL.md`, líneas 81–90: el bloque de `--fields` está escrito a mano y solo cubre `search`/`new`.
- `src/mailquery/search.py:63-80` (`SEARCH_ROW_FIELDS` incluye `body`, no `body_text`) y `src/mailquery/search.py:93-114` (`SHOW_FIELDS` incluye `body_text`, no `body`); la asimetría es de diseño, pero no está explicada en prosa.
- `tests/test_fields.py:872-896` (DOC-10.02 y DOC-10.03): fijan ejemplos que no cubren la extracción del cuerpo.

**Remediación propuesta:**

1. En `SKILL.md` §"Default row and `--fields`", añadir el ejemplo que falta: `mailquery show UID --fields body_text` → cuerpo + `uid`, ~40 % menos de contexto que `show` completo; usarlo cuando el usuario pregunta montos, fechas o comercios y no pide cabeceras ni adjuntos.
2. Añadir una línea sobre la asimetría: en `search`/`new`, `body` es `{available, readable, partial, truncated}` y no lleva texto; el texto del cuerpo se llama `body_text` y solo existe en `show`.
3. Añadir la frase "las listas de campos difieren por comando; `search -h` y `show -h` las imprimen", para que el agente no dependa de adivinar.
4. Extender DOC-10.03 con `--fields body_text` y `body_text` en `SKILL.md`, y DOC-10.02 con `--fields body_text` en ambos README. Así la omisión no vuelve.
5. Opcional (mantenimiento): generar el bloque de campos del skill desde `SEARCH_ROW_FIELDS`/`SHOW_FIELDS` en lugar de mantenerlo a mano, con la misma disciplina que DOC-10.01 aplica a la ayuda.

**Criterios de aceptación:** esta entrada no define ACs propias para no duplicarlas; se cierra cuando pasan **AC-03.3** (el skill documenta `show UID --fields body_text` y la asimetría `body`/`body_text`) y **AC-03.4** (todo campo citado en el skill existe en la lista de `-h` del comando), definidas en BUG-03. Los puntos 1–4 de arriba son la guía de redacción; los ACs son el criterio de cierre.

**Observación relacionada (no registrada como defecto, requiere decisión del dueño):** en la misma tarea, `search --include-mailbox "<carpeta vacía>"` no produce error ni aviso: devuelve solo el conjunto base sin señalar que la carpeta no aportó nada. Una carpeta inexistente sí falla (`E_MAILBOX_NOT_FOUND`, exit 2), así que el silencio con una carpeta vacía es deliberado o accidental, pero no está documentado. Costó tres sondeos con `--count` para descubrir qué carpeta tenía contenido.

---

## BUG-03 — "Qué mejoraría del skill": afirmaciones no verificadas y semánticas ausentes

**Registrado:** 2026-11-16, por decisión del dueño. Detectado en la misma tarea real que
BUG-02 y en la conversación de revisión que siguió.

**Decisión de granularidad — por qué un solo defecto y no cinco.** Los puntos de mejora
comparten una sola causa (el skill se escribe a mano y ninguna prueba lo ata al CLI) y
una sola remediación (un test que derive del CLI lo que el skill afirma, DOC-11).
Registrarlos por separado crearía cinco entradas con el mismo origen, el mismo arreglo y
el mismo estado. Por eso este es un defecto *paraguas* con criterios de aceptación
numerados, uno por síntoma, de forma que cada uno se pueda cerrar por separado.
BUG-02 se mantiene como entrada propia porque ya estaba registrado como reclamación
concreta y conserva su remediación; AC-03.3 lo cierra desde el skill.

### Síntoma 1 — `--until` es exclusivo y el skill no lo dice

**Comportamiento esperado:** el skill describe la semántica temporal de `--since`/`--until`,
porque "ayer" se escribe de forma natural como `--since AYER --until AYER`, y esa forma
devuelve 0 mensajes.

**Comportamiento observado (2026-11-16, `mailquery` 3.0.0):**

```
mailquery search --since 2026-11-15 --until 2026-11-15 --count   → 0
mailquery search --since 2026-11-15 --until 2026-11-16 --count   → 15
```

- El CLI lo dice (`--until TIME  received before TIME (exclusive)`), así que la ayuda es correcta.
- `SKILL.md` líneas 74–78 solo enumera `--since`, `--until` entre los filtros, y los ejemplos 153–156 no muestran **ni un solo** rango con ambos: la forma que falla es justo la que el skill no ejemplifica.
- El `hint` de 0 resultados agrava el diagnóstico: sugiere `run "mailquery mailboxes"` en lugar de señalar que el rango está vacío.

**Impacto medido:** 2 llamadas perdidas en la tarea del 2026-11-15 y una pista de
diagnóstico engañosa que llevó a buscar carpetas en vez de corregir el rango.

**Texto propuesto** (en inglés, el skill está en inglés):

```markdown
`--since` is inclusive (received at or after TIME) and `--until` is exclusive
(received before TIME), so a whole day is `--since D --until D+1`:

    mailquery search --since 2026-11-15 --until 2026-11-16 --count
```

### Síntoma 2 — el skill no reproduce las listas de campos por comando

Ver BUG-02. Aquí solo se registra el criterio de aceptación AC-03.2 y AC-03.4.

### Síntoma 3 — `--include-mailbox` con una carpeta vacía no avisa

**Comportamiento observado:**

```
mailquery search --since 2026-11-01 --include-mailbox "Trash" --count      → 368  (idéntico al conjunto base)
mailquery search --since 2026-11-01 --include-mailbox "Carpeta Que No Existe" → E_MAILBOX_NOT_FOUND (exit 2)
```

Una carpeta inexistente falla con hint útil; una carpeta existente pero vacía se suma en
silencio y devuelve exactamente lo mismo que sin el flag. El agente no puede distinguir
"no existe", "está vacía" o "el flag no se aplicó" sin sondeos adicionales (en esta tarea
costaron tres `--count`).

**Decisión pendiente del dueño:** documentar el silencio en el skill, o emitir un aviso
`W_MAILBOX_EMPTY` en la respuesta. AC-03.5 acepta cualquiera de las dos.

### Síntoma 4 — el skill no se verifica contra el CLI

DOC-10.02 y DOC-10.03 comprueban que ciertas cadenas aparezcan en el skill y en los
README, no que correspondan a la salida real de `-h`. Por eso los síntomas 1–3 conviven
con una suite en verde: la prueba verifica presencia, no correspondencia.

**Impacto del conjunto:** en la tarea del 2026-11-15/16, los síntomas 1 y 2 costaron
4 llamadas fallidas o vacías (~7.700 caracteres de contexto, ≈2.100 tokens) y una
respuesta que hubo que corregir ante el dueño. El síntoma 4 es lo que permite que
vuelvan a aparecer.

**Origen:**

- `skills/mailquery/SKILL.md:74-78` (enumeración de filtros sin semántica), `:153-156` (ejemplos sin rango de un día), `:81-90` (bloque de `--fields`).
- `src/mailquery/search.py:63-114` (`SEARCH_ROW_FIELDS` y `SHOW_FIELDS`, fuente de las listas).
- `tests/test_fields.py:872-896` (DOC-10.02/10.03: presencia, no correspondencia).

### Criterios de aceptación

| AC | Criterio verificable | Prueba |
|----|----------------------|--------|
| AC-03.1 | `SKILL.md` afirma que `--until` es exclusivo y `--since` inclusivo, y muestra un rango de un día (`--since D --until D+1`) | `DOC-11.01`: el texto contiene "`--until` is exclusive", "`--since` is inclusive" y una línea `mailquery search --since … --until …` |
| AC-03.2 | El skill dice que las listas de campos difieren por comando y remite a `search -h` / `show -h` | `DOC-11.02` |
| AC-03.3 | El skill documenta `show UID --fields body_text` y la asimetría `body` / `body_text` (cierra BUG-02) | `DOC-11.03`, extensión de DOC-10.03 |
| AC-03.4 | Todo nombre de campo citado en el skill existe en la lista `-h` del comando al que se atribuye | `DOC-11.04`, parametrizado sobre `SEARCH_FIELDS_TEXT` y `SHOW_FIELDS_TEXT` |
| AC-03.5 | El comportamiento de `--include-mailbox` con carpeta vacía está documentado, o la respuesta lo avisa | `DOC-11.05` o un caso `UT-SRCH-…` |
| AC-03.6 | `pytest -k "DOC_10 or DOC_11"` en verde sin modificar los casos existentes | suite completa |

### Ejemplo completo de la remediación

Bloque propuesto para `SKILL.md` §"Default row and `--fields`", que cubre AC-03.2,
AC-03.3 y AC-03.4:

```markdown
The field lists differ per command; `search -h` and `show -h` print them:

- `search` / `new` (row): uid, message_id, duplicate_count, subject, from, to, cc,
  date_sent, date_received, mailbox, is_read, is_flagged, has_attachments,
  size_bytes, snippet, body, all
- `show` (message): uid, message_id, subject, from, to, cc, date_sent,
  date_received, mailbox, is_read, is_flagged, has_attachments, size_bytes,
  headers, body_text, body_truncated, attachments, partial, readable, source, all

In `search` / `new`, `body` is an availability object
(`{available, readable, partial, truncated}`) and carries no text; the body text is
`body_text` and only exists in `show`. To read a chosen message cheaply:

    mailquery show UID --fields body_text     # uid + body, ~40% less than a full show
```

Y el bloque de rangos que cubre AC-03.1:

```markdown
`--since` is inclusive and `--until` is exclusive, so a whole day needs the next
day as `--until`: `--since 2026-11-15 --until 2026-11-16`.
```

---

## BUG-04 — `mailbox` se repite completo en cada fila de `search` (24 veces, 3 valores)

**Registrado:** 2026-11-16, a petición del dueño, a partir de la auditoría del payload de
`search` de la tarea del 2026-11-15.

**Comportamiento esperado:** una respuesta `search` declara cada buzón **una vez** y cada
fila lo referencia por una clave que **incluye la cuenta**, de modo que dos cuentas con una
carpeta `INBOX` sigan siendo distinguibles.

**Comportamiento observado (2026-11-16, `mailquery` 3.0.0):**

```
mailquery search --since 2026-11-15 --until 2026-11-16 --fields snippet --limit 200
```

24 filas, 3 buzones distintos, y el objeto completo repetido en las 24:

| Medida | Valor |
|---|---|
| `mailbox` por fila | 224 chars |
| × 24 filas | 5.393 chars (**24 %** del payload de 22.732) |
| El mismo objeto serializado por separado (otra unidad) | 5.681 chars = 33 % de las filas |
| Valores distintos que representa | **3** |

Redundancias dentro del propio objeto:

- `name` == `path` en las 24 filas (`"INBOX"` / `"INBOX"`).
- `url` = `imap://<uuid>/<path>`: repite el `uuid` que ya está en `account.uuid`.

**Origen:** `_mailbox_payload` en `src/mailquery/search.py:2432-2447`, invocado por fila desde
`src/mailquery/search.py:2383`.

**Impacto:** el 24 % de cada listado no aporta información nueva: son ~1.500 tokens por una
constante de tres valores. Crece linealmente con el número de filas.

**Remediación propuesta:** mapa `mailboxes` a nivel de respuesta con clave `cuenta:path`; cada
fila lleva solo la referencia. Misma lista, mismo orden, mismo `--limit`.

```json
{"ok":true,"command":"search","count":24,
 "mailboxes":{
   "iCloud:INBOX":{"account":"iCloud (adayler@gmail.com)","path":"INBOX"},
   "Gmail:INBOX":{"account":"Gmail (ADayler@gmail.com)","path":"INBOX"},
   "iCloud:Deleted Messages":{"account":"iCloud (adayler@gmail.com)","path":"Deleted Messages"}},
 "messages":[
   {"uid":"apple_mail:83612","subject":"Notificaciones",
    "from":{"name":"Banco Mercantil Santa Cruz","address":"bmscsa@bmsc.com.bo"},
    "date_received":"2026-11-15T21:03:14-04:00","is_read":true,
    "has_attachments":false,"mailbox":"iCloud:INBOX"}]}
```

Medición sobre las 24 filas reales:

| Variante | bytes | % del actual |
|---|---|---|
| actual | 22.732 | 100 % |
| compacto | 17.951 | 79 % |
| **compacto + mapa** | **13.230** | **58 %** |
| `--group-by mailbox` (no equivalente) | 10.976 | 48 % |

En la muestra de 2 filas: 1.349 → 673 bytes (−50 %).

**No se resuelve agrupando.** `--group-by mailbox` es otra pregunta (el último mensaje por
buzón): anida los mensajes, ordena por grupo y aplica `--limit` por grupo. Normalizar mantiene
la lista plana, el orden cronológico y el `--limit` total.

**Criterios de aceptación:**

| AC | Criterio verificable | Prueba |
|----|----------------------|--------|
| AC-04.1 | 24 filas de 3 buzones producen 3 entradas en `mailboxes` y 24 referencias | `UT-ROW-01` |
| AC-04.2 | `iCloud:INBOX` y `Gmail:INBOX` dan claves distintas y cada fila se resuelve sin ambigüedad | `UT-ROW-02` |
| AC-04.3 | Frente a la misma respuesta sin normalizar, ≥25 % menos bytes (medido: 26 % sobre compacto) | `UT-ROW-03` |
| AC-04.4 | `--group-by mailbox` no cambia de comportamiento | `UT-GRP-01` (existente) |
| AC-04.5 | Contrato documentado en `INTERFACES.md` y `PRD.md` con nota de versión; suite en verde | suite |

**Nota de convivencia con OBS-02:** OBS-02 registra el mismo hecho (hallazgo #4) con un AC que
propone el `path` sin la cuenta y que por tanto es incorrecto. Por decisión del dueño no se
corrige ahora; **BUG-04 prevalece** hasta la depuración del documento.

---

## BUG-05 — Correos masivos: `to`/`cc` entregan la lista completa de cientos de destinatarios

**Registrado:** 2026-11-17, por decisión del dueño. Detectado en una tarea real (crear un
evento de calendario a partir de una invitación interna enviada a toda la oficina).

**Comportamiento esperado:** el tamaño de una respuesta depende de lo que el agente necesita,
no del número de destinatarios. En un correo masivo, la lista completa de `to`/`cc` casi nunca
sirve: basta con saber cuántos destinatarios hay, si la cuenta del usuario está en `to` o en
`cc` y unos pocos nombres de muestra. La lista completa debe pedirse de forma explícita.

**Comportamiento observado (2026-11-17, `mailquery` 3.0.0a1, Windows/Outlook):**

```
mailquery show <uid>                                   → 19.906 chars
mailquery search --subject "<asunto>" --fields to,cc   → 12.700 chars (1 fila)
mailquery search --subject "<asunto>"                  →    875 chars (1 fila, sin to/cc)
```

Mensaje de 106 destinatarios en `To`, 0 en `Cc` y un cuerpo de 1.116 chars:

| Parte del `show` | chars | % del payload |
|---|---|---|
| `to` (106 objetos `{name, address}`) | 9.672 | 48,6 % |
| `headers.To` (la misma lista en una cadena) | 5.644 | 28,4 % |
| **destinatarios en total** | **≈17.000** | **≈85 %** |
| `body_text` (el contenido útil) | 1.116 | 5,6 % |
| payload con `to` y `headers.To` vacíos | 2.887 | 14,5 % |

- `show` sin `--fields` entrega todos los campos de `SHOW_FIELDS`, incluidos `to`, `cc` y `headers`. Así, la lista se paga **dos veces** (objeto y cabecera).
- En `search`/`new`, `to`/`cc` no están en la fila por defecto, pero `--fields to,cc` o `--fields all` multiplican el tamaño de la fila (×14,5 en este caso) por cada mensaje masivo del listado.
- El filtro `--to` necesita la lista completa para buscar coincidencias, y debe seguir usándola. El defecto está en lo que se **entrega**, no en lo que se lee.

**Origen:**

- `src/mailquery/search.py:1541-1563` (`_recipient_lists` / `_sanitized_recipients`): copian todas las entradas sin límite.
- `src/mailquery/search.py:2632` (`_show_headers`): construye `headers.To`/`Cc` uniendo la lista completa.
- `src/mailquery/search.py:167-177` (`show_message_fields`): sin `--fields`, `show` entrega `to`, `cc` y `headers` a la vez.
- `src/mailquery/backends/outlook.py:743-773` (`recipients`): en Outlook, además, abre cada destinatario por COM (`PropertyAccessor` por entrada), así que el coste también crece en tiempo. No está medido.

**Impacto:** en la tarea, ≈17.000 chars (≈4.600 tokens) de un solo `show` no aportaron nada.
Para crear el evento bastaban el cuerpo y la fecha. Las invitaciones, los comunicados y los
boletines internos son justo el tipo de correo que un agente lee para extraer fechas y lugares,
así que el caso es frecuente. El coste crece linealmente con el número de destinatarios y no
tiene tope.

**Relación con otras entradas:** OBS-02 hallazgo #2 (`headers` duplica `from`/`to`/…) cubre la
duplicación en `headers`. Este defecto cubre el tamaño de la lista misma, que sigue presente
aunque `headers` pase a ser opt-in.

**Remediación propuesta:**

1. Tope por defecto de `N = 10` entradas en `to` y en `cc` (configurable en `[content].max_recipients`), en `show` y en las filas de `search`/`new` que pidan `to`/`cc`.
2. Con el tope activo, la respuesta añade `to_count`/`cc_count` (total real) y `recipients_truncated: true`, y emite el aviso `W_RECIPIENTS_TRUNCATED` con el total omitido.
3. Si la dirección de la cuenta propietaria del buzón está entre los destinatarios, va siempre en la muestra, en su lista real (`to` o `cc`), aunque quede fuera de las `N` primeras. Así "¿me lo mandaron directo o en copia?" se sigue respondiendo.
4. `headers.To`/`headers.Cc` aplican el mismo tope y terminan en `… (+96 more)`.
5. `--recipients all` (en `show`, `search` y `new`) devuelve la lista completa sin aviso, igual que hoy.
6. El filtro `--to`/`--cc` sigue evaluándose sobre la lista completa. El tope solo afecta a la salida.

**Criterios de aceptación propuestos:**

| AC | Criterio verificable | Prueba |
|----|----------------------|--------|
| AC-05.1 | `show` de un mensaje con 106 `To` entrega 10 entradas en `to`, `to_count: 106`, `recipients_truncated: true` y `W_RECIPIENTS_TRUNCATED` con "96" en el mensaje | `UT-RCP-01` |
| AC-05.2 | Si la dirección de la cuenta propietaria está en la posición 98 de `To`, aparece en la muestra de `to` (no en `cc`) y la muestra sigue teniendo 10 entradas | `UT-RCP-02` |
| AC-05.3 | `headers.To` del mismo mensaje contiene 10 direcciones y termina en `(+96 more)` | `UT-RCP-03` |
| AC-05.4 | `--recipients all` devuelve las 106 entradas, sin `recipients_truncated` ni aviso, byte a byte igual que la salida actual | `UT-RCP-04` |
| AC-05.5 | `search --to "<destinatario en la posición 98>"` encuentra el mensaje con el tope activo | `UT-RCP-05` |
| AC-05.6 | Un mensaje con ≤10 destinatarios no cambia: sin `to_count`, sin `recipients_truncated` y sin aviso | `UT-RCP-06` |
| AC-05.7 | Sobre el mensaje de 106 destinatarios, `show` sin `--fields` pesa ≤25 % del payload actual (medido: el piso sin listas es 14,5 %) | `UT-RCP-07` |
| AC-05.8 | `[content].max_recipients`, `--recipients all` y `W_RECIPIENTS_TRUNCATED` quedan en `INTERFACES.md`, `PRD.md` (nota de versión) y `SKILL.md`; suite en verde | suite, `DOC-11.…` |

**Decisión pendiente del dueño:** el valor de `N` (10 es la propuesta) y si `cc` comparte el
tope con `to` o tiene uno propio.

---

## Observaciones registradas

Observaciones que **no** son defectos —el comportamiento es intencional, o corregirlo cambia
un contrato— pero que costaron contexto medible y esperan una decisión del dueño.

| ID | Título | Estado | Registrado |
|----|--------|--------|------------|
| OBS-01 | `stderr` repite el error que ya va en el JSON de `stdout` | Registrada, pendiente de decisión | 2026-11-16 |
| OBS-02 | JSON verboso por defecto: en mensajes cortos el sobre supera al contenido | Registrada, pendiente de decisión | 2026-11-16 |

### OBS-01 — `stderr` repite el error que ya va en el JSON de `stdout`

**Registrado:** 2026-11-16, por decisión del dueño.

**Comportamiento esperado:** el CLI documenta un JSON único en `stdout` y "un resumen corto
del error a `stderr`". Para una persona en una terminal es correcto: la línea legible es la
de `stderr` y el JSON queda para la tubería.

**Comportamiento observado (medido el 2026-11-16, `--count` con `--limit`):**

| Por fallo | Bytes |
|---|---|
| `stdout` (JSON de error) | 229 |
| `stderr` (`code: message` + `hint`) | 152 |
| **total** | **381** |

En un harness que captura ambos flujos y los entrega al modelo —como esta sesión— el mismo
texto entra dos veces: **40 % de sobre por error**, 1.143 bytes en las tres llamadas
fallidas de la tarea del 2026-11-15 (≈300 tokens, 1,2 % del total consumido). No afecta al
resultado, solo al coste.

**Origen:** `_report_error` en `src/mailquery/cli.py:2518-2528`: escribe el payload con
`write_json` y después repite `code`, `message` y `hint` en `stderr`. Es deliberado
(docstring: "Write the error JSON and the human summary"), no un descuido.

**Opciones de remediación (el dueño decide):**

1. **No cambiar el código y documentarlo** en el skill: "los errores salen dos veces: JSON en `stdout` y resumen en `stderr`; ignora el resumen si ya leíste el JSON". Coste cero, pero el 40 % permanece.
2. **Silenciar el resumen cuando `stdout` no es un TTY** (`sys.stdout.isatty()`): conserva la experiencia humana y elimina la duplicación en el harness. Riesgo bajo, pero cambia el contrato para scripts que hoy leen solo `stderr`.
3. **Bandera `--quiet-errors` o variable de entorno**: control explícito, a costa de ampliar la superficie del CLI.

Recomendación: opción 2, con un caso `UT-ERR-…` que verifique que con `stdout` redirigido
`stderr` queda vacío y que con TTY conserva el resumen.

**Criterios de aceptación (condicionales a la opción que elija el dueño).** Mientras no se
elija una opción, esta entrada no tiene AC única: hoy el comportamiento coincide con el
contrato declarado (terminal). Al decidir, se activa la fila correspondiente y la entrada se
cierra con su prueba.

| AC | Opción elegida | Criterio verificable | Prueba |
|----|----------------|----------------------|--------|
| AC-OBS-01.1 | 1 — solo documentar | `SKILL.md` advierte que el error sale dos veces (JSON en `stdout`, resumen en `stderr`) y que el agente lea solo uno | `DOC-11.06` |
| AC-OBS-01.2 | 2 — silenciar sin TTY | Con `stdout` redirigido a archivo, `stderr` = 0 bytes y el JSON íntegro en `stdout` (229 bytes, misma clave `error.code`); con TTY, `stderr` conserva las dos líneas (`code: message` y `hint`) | `UT-ERR-01`, `UT-ERR-02` |
| AC-OBS-01.3 | 3 — `--quiet-errors` / env | La bandera elimina `stderr` por completo, `stdout` mantiene el JSON único, y `search -h` … `show -h` documentan la bandera | `UT-ERR-03`, `DOC-11.07` |
| AC-OBS-01.4 | cualquiera | La opción elegida queda anotada en esta entrada (estado "Cerrada" + fecha) y `pytest -k "DOC_10 or DOC_11 or ERR"` sigue en verde | suite |

Nota: no se recomienda la opción 3 para este caso; amplía el contrato para ahorrar 152 bytes
por error, cuando la opción 2 resuelve lo mismo sin superficie nueva.

**Nota de alcance:** la otra observación de la revisión —`--include-mailbox` con una carpeta
existente pero vacía, que se suma en silencio— ya quedó registrada como BUG-03 Síntoma 3
(decisión pendiente entre documentarla o avisar) y no se duplica aquí.

### OBS-02 — JSON verboso por defecto: en mensajes cortos el sobre supera al contenido

**Registrado:** 2026-11-16, por decisión del dueño, tras auditar los payloads de la tarea del
2026-11-15 (10 `show` + 1 `search`).

**Comportamiento esperado:** el payload está dimensionado para su uso real. Un mensaje corto
—un OTP, un aviso de dos líneas— no debería costar más de veinte veces su contenido en
caracteres, ni pagar en cada respuesta campos que solo sirven para depurar.

**Evidencia medida (2026-11-16, `mailquery` 3.0.0).** Reparto de los 10 `show` (26.279 chars):

| Campo | chars | % |
|---|---|---|
| `body_text` | 10.544 | 40,1 % |
| `mailbox` (cuenta + carpeta + url) | 2.555 | 9,7 % |
| `headers` | 2.406 | 9,2 % |
| `source` (ruta absoluta `.emlx`) | 1.889 | 7,2 % |
| `content_notice` | 1.580 | 6,0 % |
| `to` | 765 | 2,9 % |
| `message_id` | 557 | 2,1 % |
| `from` | 512 | 1,9 % |
| resto (fechas, flags, wrapper) | 5.471 | 20,9 % |

En `search` (24 filas, 16.993 chars), `mailbox` ocupa **5.681 (33 %)**: repite `account.uuid`,
`label` y `email` en cada fila, y el `url` repite el uuid otra vez.

**Curva del sobre** (mismo `show` real, `body_text` sustituido por un OTP de 83 chars):

| Cuerpo | Payload | Sobre | Ahorro con T1 |
|---|---|---|---|
| 83 | 1.935 | **95 %** | −53 % |
| 300 | 2.152 | 83 % | −47 % |
| 1.050 | 2.902 | 59 % | −35 % |
| 20.000 | 21.852 | 7 % | −5 % |

Descomposición de ese payload de 1.935 chars: valores 1.097 + nombres de claves 221 +
formato/estructura 420 + cabecera (`ok`, `command`, `generated_at`, `content_notice`,
`warnings`) 197. El contenido útil son 83 chars (4,3 %).

**Hallazgos y remediación:**

| # | Hallazgo | Ahorro medido | Remediación |
|---|---|---|---|
| 1 | Indentación de 2 espacios | 21 % en `search`, 18 % en un `show` corto | `--compact`, o pretty-print solo cuando `stdout` es TTY |
| 2 | `headers` duplica `from`/`to`/`cc`/`subject`/`date_sent`/`message_id` (253 vs 259 chars) | 9,2 % | opt-in `--fields headers` |
| 3 | `source` publica la ruta absoluta del `.emlx` | 7,2 % | opt-in `--fields source` |
| 4 | `mailbox` repite la cuenta en cada fila | 33 % de las filas de `search` | mapa `mailboxes` por respuesta + `mailbox` como string |
| 5 | `content_notice` de 158 chars fijos | 8,2 % de un payload corto | recortar a ≤80 chars sin cambiar el mensaje |
| 6 | Flags en su valor por defecto (`is_flagged`, `partial`, `readable`, `body_truncated`, `attachments: []`) | ~1 % | **no compensa**: rompe la lectura directa y gana poco |
| 7 | Bloque `scan` (~120 chars) | — | `--stats` opt-in |

**Descartado a propósito:** el nivel "defaults dispersos" (omitir todo campo en su valor por
defecto) aporta +1 % sobre el nivel 1 y obliga a cada consumidor a asumir "ausente = default".
El nivel "fila mínima en `show`" **ya existe** (`--fields body_text`); el problema es que no se
usa, y su causa está en BUG-02, no en el esquema.

**Impacto:** la tarea del 2026-11-15 pagó ~14.400 tokens en 11 payloads, de los que ~8.600 eran
sobre; con el nivel 1 habría pagado ~8.800. Con 20 OTP al día el sobre solo son ~20.400 chars
(~5.700 tokens) que no aportan nada.

**Nota de seguridad:** `source` no es solo peso: incluye `/Users/<usuario>/Library/Mail/V10/<uuid>/…`
en cada respuesta, es decir, expone el nombre de la cuenta del sistema, el home y la estructura
del store. El argumento de privacidad es independiente del de tamaño.

**Criterios de aceptación (nivel 1; el dueño decide si aplica parte o todo):**

| AC | Criterio verificable | Prueba |
|----|----------------------|--------|
| AC-OBS-02.1 | `--compact` deja el JSON sin indentación y semánticamente idéntico (`json.loads` igual); en un `search` de 20 filas ahorra ≥15 % | `UT-JSON-01`, `UT-JSON-02` |
| AC-OBS-02.2 | `headers` ausente por defecto; `--fields headers` devuelve exactamente el bloque actual | `UT-JSON-03` |
| AC-OBS-02.3 | `source` ausente por defecto y ningún payload por defecto contiene `"/Users/"` ni `"Library/Mail"`; `--fields source` lo devuelve | `UT-JSON-04` |
| AC-OBS-02.4 | 20 filas del mismo folder producen **una** entrada en `mailboxes` y `mailbox` es el path; la cuenta se resuelve por el mapa | `UT-JSON-05` |
| AC-OBS-02.5 | `content_notice` ≤80 chars, sigue apareciendo en `search`/`new`/`show`/`attachment` y sigue ausente en `errors`, `doctor` y `mailboxes` | `DOC-12.01`, `UT-JSON-06` |
| AC-OBS-02.6 | `scan` solo aparece con `--stats` (si se aprueba el punto 7) | `UT-JSON-07` |
| AC-OBS-02.7 | El cambio de contrato queda en `INTERFACES.md` y `PRD.md` con nota de versión, y `pytest -k "FLD or DOC or JSON"` en verde | suite |
