---
aliases: ["Sección 11", "Modelo de datos"]
tags: [prd]
---

## 11. Modelo de datos

### 11.1 Modelo común

Lo que el núcleo y el JSON conocen; cada backend lo rellena (correspondencias en §11.3).

**Tabla: Entidades del modelo común**

| Entidad | Campos | Notas |
|---------|--------|-------|
| Cuenta | `uuid`, `label`, `email`, `local` | `uuid` con forma de UUID en los backends internos (§11.3) e identificador opaco y estable en un plugin; `local` = cuenta sin servidor (p. ej. `On My Device`, un PST). |
| Carpeta | `id` interno, `account_uuid`, `name`, `path`, `url`, `is_inbox`, `is_aggregate`, `total`, `unread` | `id` no se expone en el JSON. |
| Mensaje (fila) | `uid`, `message_id`, clave global de dedupe, `subject`, remitente `{name, address}`, `date_sent`, `date_received` (epoch), carpeta, `is_read`, `is_flagged`, `has_attachments`, `size_bytes` | `uid`: `str` `"<driver>:<native_id>"` (RF-38). Los campos de contenido se emiten saneados (A2, RF-52); en `search`/`new`, la fila del JSON tiene por defecto seis campos y el resto sale con `--fields` (RF-67, RF-68). |
| Cuerpo | `available`, `readable`, `partial`, `headers`, `body_text`, `attachments[{index, name, cached_path}]`, `source{emlx_path, partial}`, `warnings` | Valores por plataforma: §12.5. Selección y conversión del cuerpo: RF-53. |

### 11.2 Estado local: `~/.mailquery/state.json`

Un único JSON atómico (ADR-02), con el mismo esquema (`schema: 2`) en todas las plataformas:

```json
{
  "schema": 2,
  "updated_at": "2026-11-09T21:00:00-04:00",
  "last_run": {"command": "new", "at": "2026-11-09T21:00:00-04:00"},
  "cursor": {"last_date_received": 1793573649, "last_uid": "apple_mail:83143", "lookback_seconds": 600},
  "emitted_uids": ["apple_mail:83135", "apple_mail:83138", "apple_mail:83143"]
}
```

En todas las plataformas, `last_uid` y los elementos de `emitted_uids` son strings `"<driver>:<native_id>"`.

- `emitted_uids`: anillo de los últimos 1.000 uids emitidos (suprime duplicados del solape).
- `cursor.lookback_seconds` registra el lookback de la última corrida que escribió estado; **no manda** (§12.3).
- Escritura atómica (RF-21); permisos: RNF-05.
- Nunca contiene cuerpos, asuntos, direcciones ni rutas.
- `cursor` ausente o `null` ⇒ no hay cursor guardado (primera corrida, §12.3).
- Es estado corrupto: un JSON inválido; un campo conocido con tipo o valor inválido (`schema` ausente o distinto de 1 y de 2, `updated_at` o `last_run` mal formados, `cursor` que no es objeto ni `null`, `last_date_received` que no es entero ≥ 0, `lookback_seconds` que no es entero ≥ 1, `emitted_uids` que no es lista); un `cursor` objeto sin `last_date_received` y `last_uid` válidos; o un uid inválido. Uid válido: string `"<driver>:<native_id>"` con el formato de RF-38 (en `schema: 1`, los uids legados que admite la migración). Cualquier otro valor o tipo es inválido.
- **Migración `schema 1 → 2`:** al cargar un `state.json` con `schema: 1`, el núcleo convierte los uids legados de forma determinista **según el tipo del valor, sin depender del SO**: entero ≥ 1 ⇒ `"apple_mail:<n>"`; string hexadecimal en mayúsculas ⇒ `"outlook:<HEX>"`; `0`, negativos, cualquier otro valor o formato ⇒ `E_STATE_CORRUPT` (exit 3) con hint de renombrar el archivo. El resultado se persiste como `schema: 2` en la siguiente escritura de estado (una corrida de `new` sin `--peek` que emite al menos un mensaje; una corrida sin mensajes no escribe estado). `--peek` migra en memoria y no escribe. La validación de `schema: 2` (punto siguiente) aplica la cota de 1024 caracteres; un valor migrado que la exceda ⇒ `E_STATE_CORRUPT` con hint; un uid migrado cuyo driver no está instalado se valida después como en el punto siguiente. Mientras la migración no se haya persistido, el chequeo `state` de `doctor` muestra `schema: 1 (migration pending)`.
- **Validación de `schema: 2`:** un uid que no sea `string` con formato válido ⇒ `E_STATE_CORRUPT`. Un `cursor.last_uid` cuyo driver no está instalado ⇒ `E_STATE_CORRUPT` (hint: reinstalar el plugin o renombrar el estado). Los elementos de `emitted_uids` cuyo driver no está instalado se **podan** en silencio (no rompen `new`) y se informa en `doctor` (`state`).
- **Cursor multi-driver:** el cursor es global (un solo `last_date_received`/`last_uid`) y el anillo almacena uids prefijados. Cada driver declarado se consulta con el mismo `last_date_received` y `lookback`; el anillo global filtra duplicados por `uid`. La primera corrida emite la ventana `[más reciente − lookback, más reciente]` sobre el conjunto fusionado, como en el §12.3. Si el driver del `last_uid` está instalado pero ya no declarado, el cursor se conserva y se usa `last_date_received` como marca (no es `E_STATE_CORRUPT`); los uids de drivers no declarados permanecen en el anillo y no se comparan.
- **Ciclo de vida del plugin:** actualizar un plugin dentro de la API 1 no cambia `config.toml`, `state.json` ni la caché. Desinstalarlo deja sus bloques `[scope]` en `E_DRIVER_UNKNOWN` y su cursor en `E_STATE_CORRUPT` (el anillo se poda y la caché se conserva). `plugin_api = 1` está cerrada para la línea 3.x; un cambio incompatible requiere una nueva versión de API y un PRD/ADR nuevo.
- Si está corrupto, `new` falla con `E_STATE_CORRUPT` (exit 3) y un hint que sugiere renombrarlo y avisa de que la siguiente corrida será una primera corrida (§12.3). `search`/`show`/`mailboxes` no se ven afectadas; `doctor` lo reporta en el chequeo `state` con `ok=false`.

### 11.3 Correspondencia de cada backend con el modelo común

**Tabla: Correspondencia de cada backend con el modelo común**

| Concepto | Apple Mail (macOS) | Outlook clásico (Windows) |
|----------|--------------------|---------------------------|
| `uid` | `"apple_mail:<n>"`: identificador del mensaje en el `Envelope Index` (entero) con el prefijo del driver. | `"outlook:<EntryID>"`: identificador permanente del item en Outlook (`EntryID`), en hexadecimal en mayúsculas, con el prefijo del driver; cambia si el mensaje se mueve de carpeta (§18). |
| `message_id` | Message-ID del mensaje. | Message-ID de Internet. |
| Clave de dedupe (RF-06) | Identificador global del mensaje en Mail; nulo o 0 ⇒ mensaje único. | Message-ID; ausente o vacío ⇒ mensaje único. |
| `account.uuid` | Identificador de la cuenta en Mail (el mismo que en `Accounts4.sqlite`). | Identificador del store con forma de UUID en mayúsculas (`8-4-4-4-12`): único por store y estable aunque se mueva un PST. |
| `account.label` | Cuenta IMAP/Exchange: `{proveedor} ({email})` (p. ej. `iCloud (…)`, `Gmail (…)`); cuenta local: `On My Device`; sin email, la descripción disponible. | Según el tipo de store (§15.7). |
| `account.email` | Email de la cuenta. | Dirección SMTP de la cuenta; `null` para PST. |
| `mailbox.path` / `mailbox.name` | Path y nombre de la carpeta en Mail (`INBOX`, `[Gmail]/All Mail`). | Ruta de la carpeta dentro del store, con `/` como separador; dentro de cada segmento, `%` se escribe `%25` y `/` se escribe `%2F`; la bandeja de entrada se escribe siempre `INBOX`, también como prefijo (`INBOX/Facturas`). `name` es el último segmento, con la misma codificación. |
| `mailbox.url` | URL de la carpeta (`imap://…`, `local://…`). | `outlook://<account-uuid>/<path>`, con los segmentos de `path` decodificados y luego percent-encoded en UTF-8 (todo carácter que no sea *unreserved* según RFC 3986). |
| INBOX | Carpeta de primer nivel cuyo path es `INBOX` sin distinguir mayúsculas, o la etiqueta INBOX de Gmail. | La carpeta que Outlook tiene asignada como bandeja de entrada del store, en cualquier idioma. |
| Pertenencia a carpeta | Carpeta física o etiqueta (en Gmail todo el correo está en `[Gmail]/All Mail` y la pertenencia a INBOX y demás carpetas sale de las etiquetas). | Carpeta física. |
| Buzón agregado | Carpeta cuyo path contiene `all mail` (`[Gmail]/All Mail`). | No existe: `is_aggregate = false` siempre. |
| Carpetas listadas | Las carpetas de Mail. | Solo carpetas de correo, sin las ocultas (§15.7): no calendario, contactos, tareas ni carpetas de búsqueda. |
| Mensajes buscables | Los no borrados. | Correos (incluidos S/MIME) y convocatorias de reunión, sin marca de borrado IMAP; el resto (acuses, tareas, etc.) se ignora en `search`, `new`, `show` y contadores. |
| `total` / `unread` (con `mailboxes --fields`, RF-78) | Recuento real de los mensajes de la carpeta (no los contadores que guarda Mail). | Recuento de los items buscables de la carpeta. |
| `date_received` / `date_sent` | Fechas de recepción y envío de Mail. | Hora real de entrega y de envío. |
| `from` / `to` / `cc` | Dirección y nombre del mensaje. | Dirección SMTP que trae el propio item, nunca una dirección interna de Exchange; si el item no la trae, `address` es `""` y se conserva `name`. Nunca se consulta la libreta de direcciones. |
| `is_flagged` | Marcado. | Marcado y no completado; un marcado como completado es `false`. |
| Cabeceras de `show` | Las del mensaje. | Las de transporte; si faltan (correo interno), From/To/Cc/Subject/Date/Message-ID con los datos del item. |
| Cabeceras de A6 (RF-60, RF-61) | La primera `Authentication-Results` y `Reply-To` del `.emlx`. | La primera `Authentication-Results` y `Reply-To` de las cabeceras de transporte; ninguna en un item S/MIME, que no se abre. |
| Cuerpo | Del `.emlx`: las partes `text/html` convertidas a texto cuando existen y, si no, las `text/plain` (RF-53). | `HTMLBody` convertido a texto cuando `BodyFormat` es HTML y, si no o si `BodyFormat` o `HTMLBody` no se pueden leer, el texto plano (RF-53). |
| `body.partial` / `source.partial` | `true` si el mensaje es un `.partial.emlx` (completo salvo los adjuntos externalizados). | Siempre `false`. |
| Adjuntos | Lista con `index`, `name` y `cached_path` (RF-41); los bytes se leen del store local solo con `attachment`. | Solo adjuntos no ocultos (los ocultos no cuentan ni se listan); lista con `index`, `name` y `cached_path` (RF-41); los bytes se materializan en staging solo con `attachment` (§4). |
| `source.emlx_path` | Ruta absoluta del `.emlx`. | `null`. |

Todas las fechas del JSON (incluido `generated_at`) son ISO 8601 con el offset local del sistema en ambas plataformas. En Outlook, `--since` incluye y `--until` excluye al segundo. A igual fecha, el orden lo fija el orden total de abajo (RNF-04).

**Plugins externos y semántica multi-driver:**

- **`account.label`:** sin cambios respecto a la tabla anterior para los backends internos (`iCloud (you@icloud.com)`, `PST (Archivo 2025)`, …). Para un plugin, `label` es un string opaco estable definido por el plugin; `uuid` es un identificador opaco estable (no se exige forma de UUID a los plugins).
- **Orden total:** en `search` es `(date_received DESC, driver ASC, native_order_key DESC)`; en `new`, `(date_received ASC, driver ASC, native_order_key ASC)`; un mensaje sin fecha cuenta como fecha 0. `native_order_key` lo define el driver: Apple Mail entero, Outlook texto hexadecimal en mayúsculas, plugins según `native_order`. No hay deduplicación cross-driver: si dos drivers ven el mismo correo, aparecen dos resultados con `duplicate_count` calculado dentro de cada driver. El avance del cursor y del anillo usan este mismo orden total, no la comparación lexicográfica del uid.
- **Composición JSON multi-driver:** `mailboxes` concatena drivers en el orden de aparición de sus bloques en la config; dentro de cada driver, `accounts[]` sigue el orden de RF-77, y las `mailboxes[]` de cada cuenta y `excluded_stores[]`, el orden del driver (un plugin devuelve `excluded_stores: []`). En `search`/`new`, `--limit` se aplica tras el merge, `scan.candidates` suma por driver, y `truncated`/`hint` siguen el §12.5. `duplicate_count` es por driver; no hay dedupe cross-driver.

---

