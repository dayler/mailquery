# Punta a punta

#### TC-01 — Goldens de Apple Mail

Requisitos: RNF-11 · Archivo: `tests/test_integration.py`

**Tabla: Casos de TC-01**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El golden `doctor` cambia a `pkg 3.0.0a3` (solo la versión). |
| .02 | P | `mailboxes` con la forma agrupada por cuenta (cada cuenta con `uuid`, `label`, `email`, `declared` y `mailboxes[]`, cada carpeta solo con `path` e `included`) ⇒ golden `mailboxes`; una segunda corrida con `--fields name,url,total,unread` valida nombre, URL y contadores de cada carpeta. |
| .03 | P | `search` por defecto devuelve todos los mensajes distintos con la fila de seis campos ⇒ golden `search_default`; una segunda corrida con `--fields all` valida los campos fuera de la fila y los warnings de cuerpo. |
| .04 | P | `search` con All Mail deduplica al canónico de INBOX con la fila de seis campos ⇒ golden `search_all_mail`; `duplicate_count`, `snippet` y `mailbox` se comprueban con `--fields all`. |
| .05 | P | Primera corrida de `new` emite la ventana `[D - lookback, D]` con la fila de seis campos ⇒ golden `new_first_run`. |
| .06 | P | Corrida con estado sembrado emite los mensajes nuevos con la fila de seis campos y avanza el cursor ⇒ golden `new_seeded`. |
| .07 | P | `show` de un mensaje de texto con adjunto ⇒ golden `show_2714`. |
| .08 | N | `show` con el `.emlx` ausente ⇒ golden `show_83170`. |
| .09 | N | `show` con el `.emlx` corrupto ⇒ golden `show_83180`. |
| .10 | N | `show_smime_encrypted`: S/MIME cifrado con adjuntos en el `Envelope Index` (`extended=True`). |
| .11 | N | `show_not_in_scope_error` (`extended=True`). |

#### TC-02 — Goldens de Outlook

Requisitos: RF-28 · Archivo: `tests/test_integration.py`

Perfil del fake para goldens: una cuenta Exchange en caché con INBOX (un mensaje normal con adjunto, uno solo con cabeceras y uno S/MIME cifrado) y un buzón compartido excluido. Cada caso compara con el golden `outlook/<nombre>`.

**Tabla: Casos de TC-02**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailboxes` con la forma agrupada sin contadores ⇒ golden `outlook/mailboxes`; una segunda corrida con `--fields name,url,total,unread` valida `name`, `url` y los contadores (INBOX 3/2). |
| .02 | P | `search` con la fila de seis campos ⇒ golden `outlook/search`; `date_sent` y las señales de contenido se comprueban con `--fields all`. |
| .03 | P | `show` |
| .04 | N | `show_header_only` |
| .05 | N | `show_smime` |
| .06 | P | `new` con la fila de seis campos ⇒ golden `outlook/new_first_run`. |
| .07 | P | El golden `outlook/doctor` cambia a `pkg 3.0.0a3` (solo la versión). |

#### TC-03 — Gate de solo lectura de Apple Mail

Requisitos: RNF-01 · Archivo: `tests/test_readonly.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Barrido de todos los comandos con `extended=True`, incluidos la primera corrida de `new` con emisión, `show` fuera de alcance y los S/MIME, `--strip-links` en cada `search`, `new` y `show`, `search --fields all`, `search --group-by from,month`, `search --count`, `new --fields all`, `show <uid> --fields attachments`, `mailboxes`, `mailboxes --fields total,unread` y `--fields name,url`, `doctor --json`, `doctor --json --failures` y `doctor --failures`: hashes y `mtime` del store sin cambios y ningún archivo nuevo. |
| .02 | N | Los flujos de `attachment` (éxito, caché, bloqueo, límite, S/MIME y mensaje vacío) dejan el store sin cambios. |

#### TC-04 — Recetas

Requisitos: PRD §21.2 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada línea `mailquery …` de `01-new-mail-digest.md` termina con exit 0 en ambos backends; `<uid>` = `messages[0].uid` de `new --peek` (o el que indique la receta). |
| .02 | P | Cada línea de `02-search-invoices.md` termina con exit 0 en ambos backends; cuando use `attachment`, el `<uid>` viene de un mensaje con adjunto conocido (fixture o búsqueda `--has-attachments`), no de `messages[0]` genérico. |
| .03 | N | Las recetas no prometen extracción remota, `--out` ni ejecución de archivos. |

#### TC-05 — Paridad de forma JSON

Requisitos: RF-22, RF-28 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search`, `new`, `show` y `mailboxes` tienen el mismo conjunto recursivo de claves en ambos backends. |
| .02 | P | `attachment` de éxito y de error tiene el mismo conjunto de claves en ambos backends (con `attachments: "local"`). |
| .03 | N | El objeto de error sigue siendo `{code, message, hint}` sin campos nuevos. |

#### TC-06 — Packaging

Requisitos: AC-01, AC-18 · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pyproject.toml` declara la versión vigente (sin bump), el console script y el grupo `mailquery.backends` con los dos backends internos. |
| .02 | P | `mailquery.__version__` coincide con la metadata del paquete; entry points resolubles con metadata inyectada. |
| .03 | P | Las dependencias de ejecución son exactamente `css-inline~=0.23.1` (sin marcador de plataforma) y `pywin32; sys_platform == "win32"`. |

#### TC-07 — Documentación y ayudas

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

**Tabla: Casos de TC-07**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Recorre la ayuda raíz + 7 subcomandos y `mcp serve --help` (9 invocaciones) y todas parsean. |
| .02 | P | `attachment --help` coincide con §12.7. |
| .03 | N | Ninguna ayuda o documento contiene las marcas retiradas de la guardia (cinco comandos, uid entero, `preflight`, `list accounts, folders, counters`, `standard library only`/`solo biblioteca estándar`, `--out`, entre otras) ni promete escritura fuera de `~/.mailquery`; las recetas cubren los exits 3, 5 y 6. |
| .04 | N | Ninguna ayuda ni documento muestra un uid entero ni promete escrituras fuera de `~/.mailquery`. |

#### TC-08 — Goldens de adjuntos Apple Mail

Requisitos: AC-07, AC-09, AC-12, AC-13 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `attachment --index 2` ⇒ `attachment_saved.json` (`cached:false`, ruta/tamaño/sha256). |
| .02 | P | Primera corrida que siembra la caché y segunda corrida ⇒ `attachment_cached.json` (`cached:true`, mismo hash); la siembra se documenta en el test. |
| .03 | N | Mensaje con adjunto de nombre hostil ⇒ `attachment_blocked_name.json` (exit 4, sin cambios en caché). |
| .04 | N | Mensaje con contenido ejecutable (`MZ`) ⇒ `attachment_blocked_content.json` (exit 4, sin cambios en caché). |
| .05 | N | `max_file_size_mb` excedido con tamaño conocido ⇒ `attachment_too_large.json` (exit 4). |
| .06 | P | `show` de un mensaje con caché previa ⇒ `show_2714_with_cache.json` con `cached_path` absoluto. |

#### TC-09 — Goldens de adjuntos Outlook

Requisitos: AC-07, AC-10, AC-12, AC-15 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `attachment_saved.json` (`cached:false`, ruta/tamaño/hash). |
| .02 | P | `attachment_cached.json` (`cached:true`; primera corrida documentada que siembra la caché). |
| .03 | N | `attachment_unavailable.json` (`not_downloaded`, exit 3). |
| .04 | N | `attachment_blocked.json` (contenido ejecutable, exit 4). |
| .05 | P | Los goldens `outlook/show*.json` tienen la forma `attachments[{index, name, cached_path}]`. |

#### TC-10 — Goldens multi-driver

Requisitos: AC-04 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search` con `apple_mail` y el plugin de prueba declarados ⇒ golden `search_multidriver`: resultados fusionados en orden total con la fila de seis campos. |
| .02 | P | `new` sobre la ventana de primera corrida fusionada de los dos drivers ⇒ golden `new_multidriver` con la fila de seis campos. |
