---
aliases: ["Sección 22", "Versiones"]
tags: [prd]
---

## 22. Versiones

### 22.1 v1 (macOS + Apple Mail)

Implementada y validada (PRD v0.13). La búsqueda de contenido sin filtros (índice FTS local) queda fuera del alcance y requeriría un ADR nuevo.

### 22.2 Cambios de comportamiento en macOS (únicos)

Por ADR-16, la versión 2.0.0 cambia en macOS exactamente esto; todo lo demás debe quedar idéntico:

**Tabla: Cambios de comportamiento de 2.0.0 en macOS**

| Cambio | Antes (1.x, PRD v0.13) | Después (2.0.0) |
|--------|---------------|----------------|
| `show` fuera de las cuentas declaradas | Busca el uid en todo el store y no lee `[scope]` | Solo cuentas declaradas; fuera ⇒ `E_ACCOUNT_NOT_IN_SCOPE`; un `[scope]` que no resuelve falla como en `search` (§12.4) |
| Primera corrida de `new` sin estado | No emite nada (baseline); sin cuentas declaradas, solo `W_NO_ACCOUNTS` | Emite `[más reciente − lookback, más reciente]`; `warnings` según §12.3 paso 6 |
| Mensajes con fecha futura en `new` | Entran en la ventana y pueden mover el cursor al futuro | Se ignoran hasta que su fecha deja de ser futura (§12.3) |
| `[new].lookback` | Solo se toma en la corrida base | Se aplica en cada corrida |
| Warning de cuerpo ilegible | `W_EMLX_UNREADABLE` | `W_BODY_UNREADABLE` (mismo texto de motivo) |
| `mailboxes` | Sin `excluded_stores` | `excluded_stores: []` |
| Codificación de salida | La del sistema | UTF-8 siempre |
| Formato del JSON | Compacto, en una línea (`{"ok":true,…}`) | Formateado con indentación de 2 espacios en todas las salidas JSON (§12.5) |
| Rotación de logs | Diaria, `[logging].retention_days` (default 7) | Por tamaño, `[logging].max_size_mb` (default 10 MB, 5 rotados); un `config.toml` con `retention_days` ⇒ `E_CONFIG_INVALID` con el hint de §15.3 |
| Ayuda y versión | Sin `-v`; descripción "Apple Mail"; exit codes hasta 5; las ayudas de los subcomandos describen la primera corrida como baseline, los términos de filtro y el acotamiento de `--text` con las reglas anteriores | `-v`/`--version`; descripción multiplataforma; exit 6; la ayuda de la raíz y de cada subcomando sin contradicciones con este PRD (§12.7) |
| `body` en `search`/`new` | `{available, partial, truncated}`; un S/MIME sale con `available=true` y sin marca | `{available, readable, partial, truncated}` con la tabla de §12.5 (RF-04, §11.1) |
| Fecha nula, ≤ 0 o no representable | Una fecha no representable aborta la consulta con `E_INTERNAL` | `null` y la consulta continúa (RNF-08, §17); `new` ignora esos mensajes (§12.3) |
| INBOX | Cualquier carpeta cuyo último segmento es "Inbox" (sin distinguir mayúsculas) | Solo la carpeta de primer nivel cuyo path es `INBOX` sin distinguir mayúsculas, o la etiqueta INBOX de Gmail (§11.3) |
| Resolución de referencias de carpeta | Primera carpeta cuyo nombre, path o URL coincide, en el orden del catálogo | `INBOX` siempre la bandeja de entrada; una coincidencia exacta de path o URL gana a una de nombre (§15.3) |
| Términos de filtro | `--subject` con comodines no se parte en AND; `--text`/`--from`/`--to`/`--cc` se parten por espacios | `--subject` siempre AND por espacios; los demás, un único patrón (§12.2) |
| Primera corrida con `--limit` menor que la ventana | — | Los `--limit` más recientes, en orden ascendente (§12.3) |
| `doctor` | Sin `not evaluated`; `config` solo lista las claves; `envelope_index` solo comprueba permisos; `state` sin cursor no explica la primera corrida | `not evaluated: <chequeo> failed` según las dependencias de §12.8; `config` muestra la resolución real de cada bloque y, sin bloques y con su dependencia fallida, `available accounts: unknown (<chequeo> failed)`; `envelope_index` abre la base con la estrategia de §9.3 (`live_ro`/`copy_ro`); `state` sin cursor con el detalle de §12.8 (RF-23) |
| Hint de `E_STATE_CORRUPT` | Dice que la siguiente corrida es una línea base y no emite nada | Dice que la siguiente corrida es una primera corrida y emite la ventana de lookback (§11.2, §12.3, §17) |
| Errores y warnings en el log | Errores: solo el `code`; warnings: solo su número | Errores: `code` + mensaje; warnings: número y códigos `W_*`; siempre con la redacción de §14 |
| Permisos de archivos | Los logs rotados y las copias temporales del `Envelope Index` no se fuerzan a 0600 (la copia hereda el modo del original) | 0600 en todos los archivos que crea mailquery, incluidos los logs rotados y las copias de `tmp/` (RNF-05) |
| Formato del uid en `show` | `E_USAGE` con el mensaje genérico `invalid int value …` | `E_USAGE` con el mensaje `invalid uid …: expected an integer` (§12.4) |
| Warnings | `W_ACCOUNT_LABELS_UNAVAILABLE` solo en `mailboxes`; S/MIME con `W_EMLX_CORRUPT` espurio y sin `W_ATTACHMENTS_UNAVAILABLE` | `W_ACCOUNT_LABELS_UNAVAILABLE` también en `search`/`new`/`show` (§15.2); S/MIME solo con `W_BODY_UNREADABLE`, y `W_ATTACHMENTS_UNAVAILABLE` en `show` si el `Envelope Index` tiene adjuntos para el mensaje (§12.10) |
| Estado (`state.json`) | Acepta uid 0 y un cursor que es un objeto vacío | uids ≥ 1; `cursor` ausente o `null` = primera corrida; un objeto sin campos válidos es `E_STATE_CORRUPT` (§11.2) |
| Correcciones de conformidad | `--text` con un filtro vacío pasa sin acotar; `--include-mailbox` inexistente no lista carpetas; catálogo bloqueado ⇒ `E_INTERNAL`; disco lleno ⇒ exit 3; log sin `backend=` y con `.` en los milisegundos | `E_UNBOUNDED_SCAN` (RF-15); hint con las carpetas válidas (§15.3); `E_DB_BUSY` tras un reintento (§17); exit 1 con el cursor intacto (§17); formato de §14 con `backend=` |

### 22.3 Versión del paquete

`3.0.0` (mayor). El cambio de tipo y forma de `uid` (incluido `cursor.*.last_uid`), la forma de `show.attachments`, el esquema de `[scope]` y la semántica de errores son incompatibles para un harness que consume la 2.0.x. El formato de `--version` es aditivo. Se aplica la misma regla que justificó `2.0.0`, cuyos cambios (§22.2) eran incompatibles para un harness que ya consumía la 1.x en macOS.

**Estado:** `develop` anuncia la pre-release `3.0.0a3` (forma PEP 440 normalizada de `3.0.0-alpha.3`) en `pyproject.toml`, `mailquery.__version__`, `--version` y `doctor`; se usa la forma normalizada porque los metadatos instalados (`pip`/`pipx`, `doctor`) siempre la normalizan y `--version` debe coincidir con ellos. Sigue sin publicarse: sin tag de release, sin merge a `main` y sin publicación; ningún documento debe presentar el `3.0.0` como publicado. El release llegará cuando se complete el resto del alcance del `3.0.0`.

### 22.4 Cambios visibles en 3.0.0 (amplían §22.2)

**Ambas plataformas.** `3.0.0` cambia en macOS y en Windows exactamente esto:

**Tabla: Cambios visibles de 3.0.0 en ambas plataformas**

| Cambio | Antes (2.0.x) | Después (3.0.0) |
|---|---|---|
| Campos de contenido (asunto, nombres, `headers`, cuerpo, `snippet`, nombres de adjuntos, warnings, errores) | Solo `body_text` y `snippet` sin ANSI, C0 ni DEL | Todos sin ANSI, C0 (salvo `\n`/`\t`), DEL, C1, `Cf`, selectores de variación (salvo `U+FE0E`/`U+FE0F`) ni rellenos Hangul |
| Cuerpo de un mensaje con HTML y texto plano | Sale del texto plano | Sale del HTML convertido, también para `--text` |
| Cuerpo HTML | Incluye el texto de elementos ocultos | Lo omite, también para `--text`, incluido el oculto por una hoja `<style>`, y lo señala con `W_HIDDEN_CONTENT` |
| Filtros de texto de `search` | Un carácter invisible en medio de una palabra impide la coincidencia | Se ignora |
| URLs del asunto, los nombres, `headers`, el cuerpo y `snippet` | Salen enteras | Salen neutralizadas (RF-54: `hxxps://`, `[:]`, `www[.]`, `[\\]`, dominio no ASCII en punycode y, si pasan de 2.048 caracteres, acortadas a 256 más `…[+N characters]`); con `[content].url_display = "keep"` salen como antes |
| `config.toml` | — | `[content].url_display` |
| Warnings de `search`, `new` y `show` | — | `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_HIDDEN_CONTENT`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED`, `W_REPLY_TO_MISMATCH` |
| Dependencias instaladas | macOS: ninguna; Windows: `pywin32` | macOS y Windows: `css-inline` `~=0.23.1` (parches: §13.3); Windows: además `pywin32` |
| Respuestas de éxito de `search`, `new`, `show` y `attachment` | — | Campo `content_notice` con un texto fijo de contenido no confiable |
| Fila de `search` y `new` | 16 campos, con `snippet` | `uid`, `subject`, `from`, `date_received`, `is_read` y `has_attachments`; el resto, con `--fields` (`--fields all` da la fila anterior) |
| Opciones de `search`, `new` y `show` | — | `--strip-links` y `--fields` en los tres; `--group-by` y `--count` en `search`; `--show-native-id`, opción de depuración, en `show` |
| Opciones de `doctor` | `--json` | `--json` y `--failures` |
| `hint` de `search` sin resultados | `null` | Cuántas carpetas y cuentas se buscaron y cómo ampliar el alcance |
| Skill y ayuda de `doctor` | `doctor` y `mailboxes` antes de usar `mailquery` en cada sesión; `doctor` como *preflight* | Sin *preflight*: `doctor` y `mailboxes` solo para diagnosticar; `doctor` como diagnóstico |
| Warnings del estado del cuerpo en `search` y `new` (`W_BODY_UNREADABLE`, `W_EMLX_MISSING`, `W_EMLX_CORRUPT`, `W_BODY_NOT_LOCAL`, `W_HTML_NO_TEXT`) | Siempre que el cuerpo falla | Solo con `--fields snippet`, `body` o `all` |
| Salida de `mailboxes` | `accounts[]` y un `mailboxes[]` de primer nivel con `account`, `name`, `path`, `url`, `total`, `unread` e `included` en cada carpeta | Cada cuenta de `accounts[]` con su `mailboxes[]`, cada carpeta con `path` e `included`; `name`, `url`, `total` y `unread` con `--fields` |
| Opciones de `mailboxes` | — | `--fields` (sin `all`) |
| Comandos | — | `mcp serve`: servidor MCP por stdio con una herramienta por comando de lectura (RF-84–RF-87) |
| Lock de ejecución ocupado | `E_LOCKED` (exit 5) al instante | Hasta 5 reintentos con pausas crecientes (4,65 s como mucho) antes de `E_LOCKED`; configurables en `[lock]` con `retries`, `initial_delay_ms` y `backoff_factor` (RF-89) |
| `config.toml` y logs | — | `[logging].json` (por defecto `false`, sin cambio en el log); con `true`, el log va a `mailquery.jsonl` en JSON Lines (RF-88) |

**macOS.** Además de lo que el §22.2 y la tabla común ya listan, `3.0.0` cambia en macOS exactamente esto:

**Tabla: Cambios visibles en macOS en 3.0.0**

| Cambio | Antes (2.0.x) | Después (3.0.0) |
|---|---|---|
| `uid` en `search`/`new`/`show` | Entero | String `"apple_mail:<n>"` |
| `uid` en `state.json` | Entero | String prefijado, `schema: 2` (migrado automáticamente) |
| `show.message.attachments[]` | `[{"name": "..."}]` | `[{"index", "name", "cached_path"}]` |
| `show.message.attachments[]` en S/MIME | Nombres del `Envelope Index` (`smime.p7m`) y `W_ATTACHMENTS_UNAVAILABLE` | `[]` sin nombres; el warning queda solo para cuerpo ilegible no S/MIME |
| `[scope]` | `[scope."<cuenta>"]` | `[scope."<driver>:<cuenta>"]` (el prefijo puede omitirse) |
| `doctor` | `python`, `home`, chequeos, `config`, `state`, `lock` | `python`, `home`, `driver`, chequeos, `config`, `state`, `lock` |
| `--version` | `... (backend apple_mail; Python x; macOS y)` | `... (backend apple_mail; Python x; macOS y; drivers: ...)` |
| Ayuda raíz | Cinco comandos | Siete comandos (`attachment` y `mcp`) |
| `uid` en `new` (`cursor.previous/current.last_uid`) | Entero | String `"apple_mail:<n>"` |
| Logs | `backend=` | `backend=` (nativo) y `drivers=` (lista declarada) |
| Errores nuevos | — | §12.6 (incluye `E_ATTACHMENT_UNAVAILABLE` y `E_IO`) |

Todo lo demás de macOS debe quedar idéntico.

**Windows.** Además de la tabla común, en Windows `3.0.0` cambia exactamente esto; el resto debe quedar idéntico:

**Tabla: Cambios visibles de 3.0.0 solo en Windows**

| Cambio | Antes (2.0.x) | Después (3.0.0) |
|---|---|---|
| `[scope]` | `[scope."<cuenta>"]` | `[scope."<driver>:<cuenta>"]` (el prefijo puede omitirse; nativo `outlook`) |
| `uid` | String `EntryID` hexadecimal | String `"outlook:<parte del uid>"`, de 18 caracteres, o 20 o más con sufijo (RF-81); el `EntryID` no se acepta como uid |
| Archivos de `~/.mailquery` | — | Carpeta `db/` con `cache.db`, la caché de ids nativos, desde el primer `search`, `new`, `show` o `attachment` con el driver `outlook` que lee un mensaje o resuelve un uid (§11.4) |
| `uid` en `state.json` | String `EntryID` | String prefijado, `schema: 2` (migrado automáticamente) |
| `show.message.attachments[]` | `[{"name": "..."}]` | `[{"index", "name", "cached_path"}]` |
| `doctor` | `python`, `home`, chequeos, `config`, `state`, `lock` | `python`, `home`, `driver`, chequeos, `config`, `state`, `lock` |
| `--version` | `... (backend outlook; Python x; Windows y)` | `... (backend outlook; Python x; Windows y; drivers: ...)` |
| Ayuda raíz | Cinco comandos | Siete comandos (`attachment` y `mcp`) |
| Logs | `backend=` | `backend=` (nativo) y `drivers=` (lista declarada) |
| Errores nuevos | — | §12.6 (incluye `E_ATTACHMENT_UNAVAILABLE` y `E_IO`) |

---

