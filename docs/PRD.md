# PRD — mailquery

**Producto:** `mailquery` — CLI de solo lectura para leer y buscar el correo del cliente de escritorio local desde un harness de agentes (DeepSeek u otro similar): **Apple Mail en macOS** y **Outlook clásico en Windows**.
**Versión del documento:** 1.3 (un solo documento para ambas plataformas; amplía el producto a Windows + Outlook clásico).
**Fecha:** 2026-11-04.
**Repositorio:** <https://github.com/dayler/mailquery>.
**Estado:** v0.13 aprobado e implementado (macOS + Apple Mail). v1.0 **aprobado** por el dueño del producto el 2026-11-03. v1.3 es un solo documento según el estándar de un PRD, con la arquitectura como única excepción porque no hay TRD.

| Versión | Cambios |
|---------|---------|
| 0.1 | Propuesta inicial (relevamiento del store real, arquitectura y requisitos). |
| 0.2 | JSON como único formato; home `~/.mailquery`; `-h/--help`; cursor como primitiva de procesamiento único; configuración por cuenta; despliegue con `pipx`; logs en texto con rotación diaria; generalización a cualquier harness. |
| 0.3 | Configuración de cuentas por **etiqueta legible** (`iCloud (email)`, `Gmail (email)`, `On My Device`) resuelta en solo lectura desde `Accounts4.sqlite`; UUID como fallback. |
| 0.4 | Renombrada la bandera de inclusión ad-hoc a **`--include-mailbox`** (nombre explícito en inglés, repetible). |
| 0.5 | Documentación completa de `config.toml`: tabla de propiedades, archivo mínimo, archivo completo con todas las variantes y tabla de valores fijos no configurables. |
| 0.6 | Aclaradas las formas TOML inválidas y válidas para identificar cuentas (`[scope."..."]` con comillas; `[you@gmail.com]` no parsea). |
| 0.7 | Eliminado el encabezado `[scope]` redundante de los ejemplos: `[scope."<cuenta>"]` crea la tabla padre implícitamente. |
| 0.8 | Añadidas secciones configurables `[logging]`, `[search]` y `[new]` (incluye log level). |
| 0.9 | Cambio de alcance: una cuenta solo se observa si está declarada en `[scope.*]`; las cuentas no declaradas quedan excluidas. |
| 0.10 | Ayuda `-h/--help` rediseñada en inglés, en texto y formateada por secciones (comandos, opciones, ejemplos, configuración, salida y códigos de salida) para la raíz y los cinco subcomandos; sin colores. |
| 0.11 | `doctor` muestra por defecto un informe de texto human-readable (mismo estilo que `--help`), conservando `doctor --json` para automatización; la ayuda del CLI y las salidas de runtime siguen en inglés. |
| 0.12 | El chequeo `config` de `doctor` valida además la **resolución real** de cada bloque `[scope]` y su `mailbox_list` (cuenta, etiqueta/email/UUID y carpetas) contra el store y `Accounts4.sqlite`, reportando `code`/`hint`; distingue config ausente de config presente sin `[scope]`. |
| 0.13 | Cuando no hay cuentas declaradas, el chequeo `config` de `doctor` lista las cuentas disponibles (`0 account block(s) declared; available: …`) sin activarlas, manteniendo `ok=true` y el warning `W_NO_ACCOUNTS` en los comandos de datos. |
| **1.0** | **Cambio de alcance: soporte de Windows + Outlook clásico sin perder macOS + Apple Mail.** El PRD pasa a ser el núcleo común (CLI, contrato JSON, configuración, cursor, errores, invariante I-1 generalizado) y lo específico de cada cliente se traslada a anexos por backend. Nuevos: interfaz de backend (ADR-10), Outlook vía COM (ADR-11), `uid` string en Windows (ADR-12), sin lanzar Outlook y exit 6 `E_OUTLOOK_NOT_RUNNING` (ADR-13), `pywin32` solo en Windows (ADR-14), stores locales de cuentas + PST (ADR-15). Flag global `-v`/`--version` (RF-31, §12.9). Correcciones de paridad que **cambian macOS** (§22.2): `show` limitado a las cuentas declaradas, la primera corrida de `new` emite la ventana de lookback, `[new].lookback` aplica de inmediato, `W_EMLX_UNREADABLE` pasa a `W_BODY_UNREADABLE`, `mailboxes` añade `excluded_stores`, la salida es siempre UTF-8 y JSON formateado, y los logs rotan por tamaño (`max_size_mb` sustituye a `retention_days`). |
| **1.1** | Sin ampliar el alcance: completa la lista de todos los cambios de macOS que el PRD exige, resuelve las contradicciones y ambigüedades de tres revisiones independientes y elimina redundancias (cada regla tiene una sola sección dueña). |
| **1.2** | Sin cambiar el producto, ajusta el documento al estándar de un PRD, con la arquitectura como excepción porque no hay TRD: retira la planificación, la implementación y la estrategia de pruebas. |
| **1.3** | Sin cambiar el producto: un solo documento. Integra lo que es PRD de los anexos por backend y elimina el resto (implementación, escenarios y casos de prueba, mediciones); quedan como anexos (§24) el resumen del spike de Outlook, los hechos verificados en macOS, las alternativas evaluadas, el registro de decisiones, los ejemplos de invocación y el glosario. Elimina los escenarios de los criterios de aceptación. |

---

## 1. Resumen ejecutivo

`mailquery` es una utilidad de línea de comandos, escrita en Python, que lee el almacén local del cliente de correo de escritorio **sin modificar absolutamente nada**: no marca correos como leídos, no edita, no mueve, no borra y no cambia flags. Soporta dos plataformas mediante **backends** intercambiables:

| Plataforma | Cliente | Cómo lee |
|------------|---------|----------|
| macOS | Apple Mail | `Envelope Index` (SQLite read-only) + `.emlx` |
| Windows | Outlook clásico (16.0) | Outlook Object Model por COM, detrás de un proxy de solo lectura |

Toda su configuración, estado y logs viven en `~/.mailquery`; el repositorio del proyecto solo contiene código y documentación.

Devuelve **siempre un objeto JSON** por ejecución (no existe `--format`), con el **mismo contrato en ambas plataformas** (misma forma; las diferencias de valor, como el tipo de `uid`, están en §12.5), pensado para que un harness de agentes lo consuma bajo demanda: resúmenes de correo nuevo, búsquedas por asunto/contenido/remitentes/fechas, seguimiento de remitentes y reportes. Solo lee las cuentas declaradas en `~/.mailquery/config.toml` (alcance: §15).

Es deliberadamente pequeño: sin demonio, sin programador interno, sin base de datos propia de mensajes, sin red. La única fuente de verdad es el cliente de correo local, leído en modo estrictamente read-only.

---

## 2. Problema y contexto

El usuario usa un cliente de correo de escritorio (Apple Mail en macOS; Outlook clásico en Windows) y quiere que un agente (el harness de DeepSeek u otro similar) pueda:

1. Detectar y leer los correos **nuevos** de sus bandejas cuando el harness lo necesite (bajo demanda).
2. Buscar correos existentes por asunto, contenido, remitentes, destinatarios, fechas, carpeta y estado.
3. Hacerlo **sin alterar el estado** de los correos: leído/no leído, flags y organización deben quedar exactamente igual.
4. Usar **la misma herramienta y el mismo contrato** en los dos sistemas, para que las recetas del harness no dependan de la plataforma.

Las alternativas genéricas son frágiles o inseguras:

- Automatización de la UI del cliente (AppleScript en macOS, macros/VBA en Outlook): expone propiedades escribibles, exige el cliente abierto y no garantiza no mutar.
- IMAP / Microsoft Graph / EWS: duplicarían credenciales, red y superficie de escritura.
- Un índice propio de mensajes: duplicaría correo privado y añadiría sincronización, invalidación y desincronización.

Las alternativas descartadas para cada cliente están en ADR-01 y ADR-11 (detalle en el Anexo C).

---

## 3. Objetivos

### 3.1 Objetivo general

Entregar una herramienta local, simple y auditable, que permita a un harness de agentes leer y consultar los correos del cliente de escritorio local (Apple Mail o Outlook clásico) **sin ninguna posibilidad de modificar el almacén**, con un único contrato para ambas plataformas.

### 3.2 Objetivos específicos

| ID | Objetivo | Medida de éxito |
|----|----------|-----------------|
| O1 | Leer correos nuevos de forma incremental | `mailquery new` devuelve cada mensaje una sola vez, sin duplicados ni omisiones dentro del alcance configurado |
| O2 | Buscar por asunto, contenido, remitente, destinatarios, fechas, carpeta y estado | `mailquery search` con filtros combinables y JSON estable |
| O3 | Garantizar solo lectura | Invariante I-1 (§4) cumplido según los criterios de aceptación de §20 |
| O4 | Integrarse con el harness | JSON en `stdout`, logs aparte, códigos de salida estables, ejecución no interactiva, `-h/--help` |
| O5 | Mantener simplicidad | Sin demonio, sin scheduler, sin base de datos de mensajes; biblioteca estándar en macOS; en Windows solo `pywin32` (ADR-14) |
| O6 | Ser predecible y observable | `doctor` diagnostica el entorno; cada ejecución deja un log con duración, conteos y errores |
| O7 | Paridad entre plataformas | Todo lo que `mailquery` hace con macOS + Apple Mail funciona de forma equivalente con Windows + Outlook clásico: mismos comandos, flags, configuración, catálogo de warnings (§12.10), códigos de error y forma del JSON; las únicas diferencias son las declaradas en §11.3 y §12.5; cambios en macOS: RNF-11 |

### 3.3 No objetivos

- No escribir, mover, copiar, convertir, marcar leído/no leído, etiquetar ni borrar correos.
- No enviar, responder, reenviar ni poner en cola correos.
- No descargar adjuntos ni disparar descargas desde el servidor (IMAP, Exchange ni otras).
- No lanzar el cliente de correo (ni Mail.app ni Outlook).
- No crear reglas, buzones inteligentes ni cambiar preferencias del cliente.
- No construir una copia local de los correos (sin índice FTS, §22.1).
- No programar tareas: el harness decide cuándo invocar la herramienta (operación bajo demanda).
- No soportar otros clientes: ni el **nuevo Outlook** (`olk`, que no expone COM ni un store local y solo sería alcanzable por Microsoft Graph, con red y OAuth, contra I-1), ni Outlook en la web, ni Outlook para Mac, ni Thunderbird u otros. Linux no tiene backend de datos (solo desarrollo/CI).
- No incluir interfaz gráfica, servidor HTTP ni demonio.

---

## 4. Garantía de solo lectura (requisito de primer nivel)

> **Invariante I-1:** `mailquery` nunca modifica el almacén del cliente de correo ni el estado de ningún mensaje (leído/no leído, flags, carpeta, contenido). No lanza el cliente de correo. No abre conexiones de red ni provoca descargas desde el servidor. Solo escribe dentro de `~/.mailquery`; el repositorio no se modifica en ejecución. Excepción en Windows: leer propiedades de nivel store (etiqueta, tipo, ruta, identificador) de cualquier store del perfil está permitido, aunque para resolverlas Outlook pueda consultar al servidor; las carpetas e items solo se leen en los stores locales (§15.7).

Concreción por plataforma:

- **macOS:** no escribe, renombra, mueve, trunca, toca fechas ni borra ningún archivo dentro de `~/Library/Mail`; no lanza Mail.app; no ejecuta AppleScript/osascript sobre Mail; no abre conexiones IMAP/SMTP. Además del store de Mail, la única base que lee es `~/Library/Accounts/Accounts4.sqlite`, para las etiquetas de cuenta. Leer un mensaje no cambia su estado de lectura. Mail no necesita estar abierto.
- **Windows:** no modifica ningún item, carpeta ni store de Outlook; no lanza Outlook; no provoca descargas desde el servidor. Un item con solo cabeceras en local se reporta sin cuerpo (`W_BODY_NOT_LOCAL`) y nunca se pide su descarga. De un mensaje S/MIME no se leen cuerpo ni adjuntos (podrían pedir PIN o certificado). Leer un item no lo marca como leído.

Cómo lo garantiza cada backend: §9.3. `doctor` lo reporta en `readonly_strategy` (§12.8). Criterios de aceptación: §20.

Reglas comunes a ambos backends:

1. Solo se leen identificadores y nombres visibles de cuentas; **nunca** credenciales, contraseñas ni tokens.
2. Ningún módulo fuera del backend accede al almacén del cliente: el resto del código solo ve el modelo común (§11.1).

---

## 5. Usuarios y casos de uso

**Usuario primario:** un harness de agentes (DeepSeek u otro) que invoca la CLI **bajo demanda** y consume su JSON.
**Usuario secundario:** el usuario humano, que verifica resultados y define los preceptos de cada tarea.

La herramienta no programa nada: no hay frecuencias ni cron internos; el harness decide cuándo ejecutar cada comando.

| ID | Caso de uso | Comando típico | Desencadenante |
|----|-------------|----------------|----------------|
| CU-01 | Resumen de correo nuevo | `mailquery new` | Cuando el harness lo decida |
| CU-02 | Buscar facturas/recibos por contenido | `mailquery search --text "*factura*" --since 1mo` | Bajo demanda |
| CU-03 | Correos de un remitente específico | `mailquery search --from "*@banco.com*" --since 2w` | Bajo demanda |
| CU-04 | Correos no leídos de un periodo | `mailquery search --unread --since 1w` | Bajo demanda |
| CU-05 | Ver un correo completo | `mailquery show <uid>` (uid tomado de `search`/`new`) | Bajo demanda |
| CU-06 | Descubrir cuentas, carpetas y contadores | `mailquery mailboxes` | Al configurar |
| CU-07 | Diagnóstico antes de usar la herramienta | `mailquery doctor` | Al instalar / actualizar el sistema o el cliente de correo |

---

## 6. Requisitos funcionales

Prioridades: **M** = imprescindible, **S** = deseable. Los RF-01…RF-25 aplican a ambos backends salvo que se indique lo contrario.

### 6.1 Lectura y descubrimiento

| ID | Requisito | Prioridad |
|----|-----------|-----------|
| RF-01 | `mailquery new` devuelve los mensajes recibidos desde la última ejecución exitosa usando un cursor persistente `(last_date_received, last_uid)` con ventana de solape (*lookback* configurable) y anillo de uids emitidos. Primera corrida y lookback: §12.3. | M |
| RF-02 | `mailquery new --peek` devuelve los nuevos sin avanzar el cursor. | M |
| RF-03 | `mailquery mailboxes` lista cuentas y carpetas con `account` = `{uuid, label, email}` (etiqueta legible resuelta en solo lectura), `name`, `path`, `url`, total de mensajes, no leídos e `included` (true si la cuenta está declarada; dentro de ella, INBOX siempre y las carpetas de `mailbox_list`); `accounts[]` incluye `declared` (true si la cuenta está declarada). | M |
| RF-04 | `mailquery show <uid>` devuelve metadatos, cabeceras seleccionadas, cuerpo en texto, nombres de adjuntos, `partial` y origen (`source`), sin modificar nada. Solo encuentra mensajes de las **cuentas declaradas** (resolución: §12.4). | M |
| RF-05 | Un mensaje sin cuerpo legible en local no rompe la consulta: se entrega con `body.available=false` o `body.readable=false` y un warning con el motivo concreto. Los mensajes S/MIME (cifrados o solo firmados) no se leen en ninguna plataforma. Casos y warnings: §12.5 y §12.10. | M |
| RF-06 | Nunca se dispara una descarga para obtener un cuerpo o adjunto (casos: §4 y §12.5). | M |
| RF-07 | Resultados deduplicados por identificador global del mensaje (el mismo correo puede existir en varias cuentas/carpetas): canónico = copia de INBOX; si no, carpeta normal; si no, buzón agregado; el JSON reporta `duplicate_count`. Un mensaje sin identificador global (vacío o ausente) es único: no se agrupa con otros y su `duplicate_count` es 1. Clave por backend: §11.3. | M |

### 6.2 Búsqueda

| ID | Requisito | Prioridad |
|----|-----------|-----------|
| RF-08 | Alcance: **solo las cuentas declaradas en `~/.mailquery/config.toml`**; dentro de cada una, INBOX siempre más las carpetas de `mailbox_list` o de `--include-mailbox`. Las cuentas no declaradas quedan excluidas. | M |
| RF-09 | `--subject` con subcadena o comodines `*`/`?`; varios términos separados por espacios = AND (semántica de patrones: §12.2). | M |
| RF-10 | `--text`: subcadena o comodines sobre el cuerpo en texto (texto plano o HTML convertido). | M |
| RF-11 | `--from`, `--to`, `--cc`: subcadena o comodines sobre dirección o nombre visible. En Windows, `--to`/`--cc` siguen RF-17. | M |
| RF-12 | `--since` y `--until` con fechas ISO 8601 y relativos: `30min`, `24h`, `7d`, `1w`, `2w`, `1mo`, `2mo`, `6mo`, `1y`, `today`, `yesterday`, `now`. | M |
| RF-13 | `--unread`, `--flagged`, `--has-attachments`: filtros de estado. | M |
| RF-14 | `--include-mailbox`: lista (repetible o separada por comas) de carpetas a incluir en esa ejecución, además de las configuradas. Deben pertenecer a cuentas **declaradas**; no activan una cuenta. | S |
| RF-15 | Paginación simple: `--limit` (default configurable, §15.1; máx. 200 en `search` y 500 en `new`), `truncated` y `hint` para refinar; sin `--offset`. | M |
| RF-16 | Cada mensaje incluye `snippet` (longitud: §15.6) leyendo solo el cuerpo de la página devuelta. | S |
| RF-17 | `--text` exige al menos un filtro de acotamiento (fecha, remitente, destinatario, asunto o carpeta) y un máximo de candidatos (`[search].max_scan`, §15.1). Cuenta como "carpeta" una carpeta distinta de INBOX en `mailbox_list` o en `--include-mailbox`; un filtro con valor vacío no acota. Los candidatos son los mensajes del alcance que quedan tras los filtros de fecha, estado, `--subject` y `--from` (y en macOS también `--to`/`--cc`); `scan.candidates` reporta ese número. Si no hay acotamiento: `E_UNBOUNDED_SCAN`; si se supera el máximo: `E_SCAN_TOO_LARGE`. Nunca resultados parciales silenciosos. En Windows la regla se extiende a `--to`/`--cc` (abrir cada item es necesario para evaluarlos), que en esa plataforma no cuentan como acotamiento; con `--text` y `--to`/`--cc` a la vez, la validación se hace una sola vez. El mensaje de error nombra el flag que obliga a leer el contenido y el hint lista solo los filtros que acotan en esa plataforma. Sin `--text`, `scan.mode` es `metadata` y `scan.messages_read` cuenta los items abiertos. | M |

### 6.3 Integración y operación

| ID | Requisito | Prioridad |
|----|-----------|-----------|
| RF-18 | Único formato de salida: un objeto JSON por ejecución en `stdout`, **formateado** (indentación de 2 espacios, §12.5). No existe `--format`. Únicas excepciones documentadas: `-h`/`--help` (RF-19), `-v`/`--version` (RF-31) y el informe por defecto de `doctor` sin `--json` (RF-25). Codificación y fin de línea: RF-32. | M |
| RF-19 | `-h` / `--help` muestra uso, comandos, opciones y banderas (texto para humanos; excepción documentada a la regla JSON). | M |
| RF-20 | Logs en texto plano en `~/.mailquery/logs/mailquery.log`, con rotación por tamaño y sin contenido de correos (§14). | M |
| RF-21 | Configuración por `~/.mailquery/config.toml` (opcional y mínimo). Sin variables de entorno ni flags de ruta. | M |
| RF-22 | Lock de ejecución para evitar corridas concurrentes; si está ocupado, salir con código 5. | S |
| RF-23 | Cursor atómico: una escritura interrumpida nunca deja el estado corrupto; el estado previo queda intacto. | M |
| RF-24 | Errores también en JSON (`ok: false`, `code`, `message`, `hint`) con el código de salida correspondiente. | M |
| RF-25 | `mailquery doctor` muestra por defecto un informe de texto human-readable con los chequeos y el detalle de cualquier fallo, e incluye la **resolución real** de cada bloque `[scope]` y su `mailbox_list` (cuentas declaradas, etiquetas/email/UUID y carpetas existentes) además de la resolubilidad de etiquetas de cuenta; `--json` conserva el payload máquina con la lista de chequeos. Los chequeos de entorno dependen del backend (§12.8). | M |

### 6.4 Plataformas y backends (nuevo en v1.0)

| ID | Requisito | Prioridad |
|----|-----------|-----------|
| RF-26 | El backend se selecciona automáticamente por plataforma: `win32` ⇒ Outlook; cualquier otra ⇒ Apple Mail (comportamiento actual, incluido Linux para desarrollo/CI). Sin flag ni variable de entorno para elegirlo. | M |
| RF-27 | El `uid` es un **token opaco** para el harness: entero en macOS (sin cambios) y string hexadecimal en Windows (`EntryID`). `show` acepta el `uid` tal como lo devolvieron `search`/`new`. | M |
| RF-28 | En Windows, `mailquery` solo se conecta a un Outlook clásico ya abierto; si no lo está, falla con `E_OUTLOOK_NOT_RUNNING` (exit 6) sin lanzarlo. | M |
| RF-29 | En Windows, el alcance candidato son los stores **locales** del perfil; el resto se excluye (tabla de candidatos y excluidos: §15.7). | M |
| RF-30 | La forma del JSON es idéntica en ambas plataformas: los campos sin equivalente se rellenan con un valor neutro documentado en §11.3 y §12.5, nunca se omiten. | M |
| RF-31 | `mailquery -v` / `mailquery --version` imprime en `stdout` una línea de texto con la versión de la app, el backend, la versión de Python y la plataforma, sin efectos (§12.9). | M |
| RF-32 | `stdout` y `stderr` se escriben en UTF-8 y con fin de línea LF en ambas plataformas, independientemente de la página de códigos del sistema o de si están redirigidos a un pipe o archivo. | M |
| RF-33 | En Windows, toda llamada COM a Outlook que no responda en **30 s** se aborta con `E_CLIENT_TIMEOUT` (exit 3) y un hint que remite a `doctor` (posible aviso de seguridad en pantalla), salvo dentro de `doctor` (§12.8). En macOS no aplica (bloqueos: `E_DB_BUSY`, §17). | M |
| RF-34 | Cada store excluido se reporta con su **etiqueta, ruta y motivo**: en `mailboxes` (campo `excluded_stores`, §12.5), en el chequeo `stores` de `doctor` y, si una cuenta declarada resuelve a él, en el texto de `W_STORE_EXCLUDED`. | M |

---

## 7. Requisitos no funcionales

| ID | Requisito |
|----|-----------|
| RNF-01 | **Solo lectura**: invariante I-1 (§4) en ambos backends. |
| RNF-02 | **Simplicidad**: biblioteca estándar de Python (≥ 3.11); única excepción: ADR-14. Sin red, sin servicios, sin demonio. |
| RNF-03 | **Rendimiento**: presupuestos p95 por backend (§19). |
| RNF-04 | **Determinismo**: mismo estado del store + mismos filtros ⇒ mismo resultado, con orden total (`date_received`, `uid`). |
| RNF-05 | **Privacidad**: sin telemetría ni red; logs sin asunto/cuerpo/direcciones. macOS: `~/.mailquery` y sus subdirectorios 0700, y todo archivo que crea mailquery 0600 (estado, lock, logs y logs rotados, copias de `tmp/`); `config.toml` lo crea el usuario o el instalador y mailquery no lo modifica (§15). Windows: el home hereda la ACL privada del perfil de usuario y el instalador restringe la de `config.toml`. |
| RNF-06 | **Compatibilidad**: macOS con Apple Mail (store `V9`/`V10`/`V11`); Windows 10/11 con Outlook clásico 16.0 (§13.1). Ante algo no soportado se falla ruidosamente con un código documentado. |
| RNF-07 | **Observabilidad**: log en texto por ejecución con backend, duración, conteos, estrategia de conexión y errores. |
| RNF-08 | **Robustez**: un mensaje corrupto o ilegible no tumba la consulta; MIME raro, HTML sin texto o charset inválido se degradan con warning. |
| RNF-09 | **Seguridad**: el contenido de los correos es entrada no confiable para el LLM (prompt injection); debe tratarse como datos, nunca como instrucciones. |
| RNF-10 | **Mantenibilidad**: el comportamiento de cada backend se puede verificar sin acceder al correo real del usuario, en Linux, macOS y Windows. |
| RNF-11 | **Paridad sin regresión**: en macOS solo cambian las salidas listadas en §22.2; el refactor a backends no cambia ninguna otra. |

---

## 8. Decisiones de arquitectura (ADR resumidas)

| ID | Decisión | Alternativas descartadas | Motivo |
|----|----------|--------------------------|--------|
| ADR-01 | **Apple Mail:** leer el almacén en disco: `Envelope Index` (metadatos) + `.emlx` (cuerpo). | AppleScript/Mail.app; IMAP; Spotlight | Read-only estructural; sin credenciales ni red; AppleScript no garantiza no-mutar; `mdfind` no indexa el store. |
| ADR-02 | **Sin caché local de mensajes**: único estado = cursor en `~/.mailquery/state.json`. | Índice FTS5; SQLite de estado; `sync` | Evita duplicar correo privado y desincronización; menos código. |
| ADR-03 | **Python 3.11+**, stdlib por defecto; única dependencia extra: ADR-14. | Node/Go/Rust; otras dependencias de PyPI | Cero fricción de instalación con `pipx`. |
| ADR-04 | **JSON-only**: datos en `stdout`, logs a archivo, errores JSON; excepciones en texto: RF-18. | Tabla/texto/markdown; `--format` | Un solo contrato para el harness, sin flags de presentación. |
| ADR-05 | **Proceso de un solo disparo, bajo demanda**. | Daemon, watcher, scheduler interno | El harness decide cuándo ejecutar; el arranque es barato. |
| ADR-06 | **Alcance = solo cuentas declaradas en `[scope.*]`** (reglas: §15). | Leer todas las cuentas automáticamente (modelo anterior); excluir ruido; buscar en todas las carpetas | Control explícito de qué cuentas se leen: evita procesar cuentas no deseadas y mantiene el estado mínimo. |
| ADR-07 | **Cursor global** por fecha de recepción + lookback + anillo de uids. | Cursor por carpeta; set "visto" permanente | Simple y exacto en la práctica; estado mínimo (§18). |
| ADR-08 | **Despliegue con `pipx install .`** (comando `mailquery` en PATH) en ambas plataformas. | Scripts sueltos, Homebrew, /usr/local con sudo, MSI | Instalación/actualización/desinstalación de un paso, con venv aislado y dependencias declaradas. |
| ADR-09 | **Apple Mail:** etiquetas de cuenta desde `~/Library/Accounts/Accounts4.sqlite` en solo lectura; UUID como fallback. Reglas de etiqueta: §11.3. | Solo UUID; alias manual | Legibilidad sin trabajo manual. |
| ADR-10 | **Interfaz de backend**: el núcleo (CLI, config, filtros, dedupe, cursor, salida) es común y cada cliente implementa la misma interfaz. Un único PRD para ambas plataformas. | Fork por plataforma; dos PRDs; `if sys.platform` repartidos por el código | Un solo contrato y una sola lógica de negocio; el riesgo de regresión en macOS queda acotado al adaptador. |
| ADR-11 | **Outlook vía Outlook Object Model (COM)**, solo stores locales. | Parsear `.ost`/`.pst`; Microsoft Graph/EWS; MAPI de terceros; Windows Search | Única API local soportada; los OST son propietarios y están bloqueados; Graph exige red y OAuth. |
| ADR-12 | **`uid` con tipo por plataforma**: entero en macOS (sin cambios), string `EntryID` en Windows; el harness lo trata como token opaco. | Campo `id` nuevo en ambas (rompe macOS); entero sintético (colisiones, sin vuelta atrás para `show`) | Conserva intacto el contrato de macOS y evita un mapa local de ids (que sería una base de datos propia). |
| ADR-13 | **No lanzar Outlook**: solo se conecta a un Outlook ya abierto; si está cerrado, `E_OUTLOOK_NOT_RUNNING` con exit **6** dedicado. | Lanzarlo si está cerrado; lanzarlo solo con un flag | Equivalente a "no lanza Mail.app": sin efectos laterales ni sincronización disparada por la herramienta; el harness puede distinguir este caso del resto de errores de entorno. |
| ADR-14 | **`pywin32`** como única dependencia, solo en Windows. | `comtypes`; acceso COM propio | Estándar de facto con distribución oficial; un acceso COM propio sería mucho código frágil; macOS sigue sin dependencias. |
| ADR-15 | **Alcance de stores en Outlook = stores locales de las cuentas del perfil (incluidas EAS) + PST en disco local**; el resto se excluye y se reporta con ruta y motivo (RF-34). Tablas: §15.7. | Solo Exchange; todo el perfil | Todo lo incluido es local (sin red); los excluidos irían al servidor en cada lectura. |
| ADR-16 | **Paridad funcional estricta**: lo que `mailquery` hace con macOS + Apple Mail debe hacerse de forma equivalente con Windows + Outlook clásico, ni más ni menos. Cuando el comportamiento actual de macOS es incorrecto respecto a esa paridad o a lo decidido por el dueño del producto, se corrige en esta versión (§22.2). | Mantener macOS congelado | Un único contrato real para el harness. |

---

## 9. Arquitectura

### 9.1 Vista de componentes

```mermaid
flowchart LR
    H[Harness de agentes] -->|argv / JSON| CLI[cli.py]
    CLI --> CFG[config.py]
    CLI --> LOG[logging_setup.py]
    CLI --> SR[search.py]
    CLI --> OUT[output.py]
    CLI --> STT[state.py]
    CLI --> SEL[backends/__init__.py<br/>selección por plataforma]
    SR --> IF[[Interfaz de backend<br/>backends/base.py]]
    CFG --> IF
    SEL --> AM[backends/apple_mail.py]
    SEL --> OL[backends/outlook.py]
    AM -.implementa.-> IF
    OL -.implementa.-> IF
    AM --> ST[store.py / emlx.py / accounts.py]
    ST -->|solo lectura| EI[(Envelope Index)]
    ST -->|solo lectura| EM[.emlx]
    ST -->|solo lectura| ADS[(Accounts4.sqlite)]
    OL --> COM[backends/outlook_com.py<br/>proxy de solo lectura con lista blanca]
    COM -->|sin lanzar Outlook| OUTLOOK[(Outlook clásico en ejecución)]
    STT -->|atómico| STATE[(~/.mailquery/state.json)]
    LOG -->|texto, rotación por tamaño| LOGF[(~/.mailquery/logs/mailquery.log)]
```

### 9.2 Responsabilidades de módulos

| Módulo | Responsabilidad | No debe |
|--------|-----------------|---------|
| `cli.py` | Parsear argumentos (incl. `-h`), obtener el backend, despachar comandos, mapear errores a códigos de salida. | Contener SQL, COM ni parseo MIME. |
| `config.py` | Cargar y validar `~/.mailquery/config.toml`; resolver cuentas y carpetas permitidas contra la interfaz de backend. | Leer el store ni crear configuración. |
| `search.py` | Lógica común: filtros, comodines, acotamiento, dedupe, paginación, cursor de `new`, armado de mensajes en el modelo común. | Acceder al store directamente; renderizar. |
| `state.py` | Cursor, anillo de uids, lock no bloqueante (POSIX y Windows), escritura atómica. | Guardar contenido de correos. |
| `output.py` | Serializar JSON estable, snippets, truncados, sanitización de caracteres de control. | Escribir logs. |
| `logging_setup.py` | Logger en texto con rotación por tamaño; formato log4j; redacción. | Escribir en `stdout`. |
| `errors.py` | Errores del producto con `code`, código de salida y `hint` (§12.6). | — |
| `backends/__init__.py` | Selección del backend por plataforma (RF-26). | Importar `win32com` en macOS/Linux. |
| `backends/base.py` | Interfaz de backend y tipos del modelo común (§11.1). | Depender de un cliente concreto. |
| `backends/apple_mail.py` | Adaptador sobre `store.py`, `emlx.py` y `accounts.py`; contiene las consultas de búsqueda de Apple Mail. El adaptador no añade comportamiento propio. | Cambiar el contrato de macOS (RNF-11). |
| `store.py`, `emlx.py`, `accounts.py` | Acceso read-only al store de Apple Mail (§9.3). | Ser importados por el backend Outlook. |
| `backends/outlook.py` | Traducción Outlook → modelo común (§11.3), alcance de stores (§15.7), chequeos de `doctor` (§12.8). | Usar objetos COM sin el proxy. |
| `backends/outlook_com.py` | Único módulo que importa `win32com`; conexión sin lanzamiento, proxy de solo lectura con lista blanca (§9.3), reintento ante rechazo transitorio. | Exponer el objeto COM crudo. |

La reorganización detallada de firmas se documenta en `docs/INTERFACES.md`; este PRD manda sobre él.

### 9.3 Garantía de solo lectura de cada backend

- **Apple Mail:** lee el `Envelope Index` (metadatos), los `.emlx` (cuerpos) y `Accounts4.sqlite` (etiquetas de cuenta), todos en solo lectura impuesta por el sistema. Con Mail abierto lee la base viva (estrategia `live_ro`); con Mail cerrado lee una copia en `~/.mailquery/tmp/` (estrategia `copy_ro`), para no crear archivos dentro del store.
- **Outlook:** el Outlook Object Model es de lectura y escritura, así que la garantía se impone en capas: se conecta solo a un Outlook ya abierto (ADR-13); todo objeto de Outlook pasa por un proxy de solo lectura con lista blanca que rechaza cualquier otra operación con `E_INTERNAL` antes de que llegue a Outlook, y el resto del código nunca ve el objeto sin el proxy; solo se leen carpetas e items de stores locales (§15.7); la caché de `pywin32` queda en `~/.mailquery/tmp/gen_py`; y toda llamada tiene el timeout de RF-33. Estrategia `com_readonly`.

---

## 10. Estructura de carpetas

### 10.1 Repositorio

```text
mailquery/
├── README.md                       # instalación, permisos, ejemplos, --help
├── LICENSE
├── pyproject.toml                  # comando `mailquery` y dependencias (ADR-14)
├── docs/
│   ├── PRD.md                      # este documento
│   ├── INTERFACES.md               # contratos de implementación entre módulos
│   ├── config.example.toml
│   └── recipes/                    # recetas/preceptos para el harness
├── scripts/                        # install.sh, install.ps1, install.bat
├── src/mailquery/
│   ├── __init__.py, __main__.py
│   ├── cli.py, config.py, search.py, state.py
│   ├── output.py, logging_setup.py, errors.py
│   ├── store.py, emlx.py, accounts.py      # acceso Apple Mail
│   └── backends/
│       ├── __init__.py             # selección por plataforma
│       ├── base.py                 # interfaz de backend + modelo común
│       ├── apple_mail.py           # adaptador Apple Mail
│       ├── outlook.py              # backend Outlook
│       └── outlook_com.py          # único import de win32com; proxy de solo lectura
└── tests/                          # pruebas
```

### 10.2 Home de la aplicación (runtime, **no** en el repo)

```text
~/.mailquery/                       # macOS: 0700 | Windows: %USERPROFILE%\.mailquery
├── config.toml                     # opcional; lo crea el instalador o el usuario
├── state.json                      # cursor + anillo de uids (lo crea `new`)
├── locks/mailquery.lock
├── tmp/                            # macOS: copia temporal del Envelope Index | Windows: caché de pywin32 (tmp/gen_py)
└── logs/mailquery.log              # texto plano, rotación por tamaño (+ 5 rotados)
```

Reglas: I-1 y ADR-02. Permisos: RNF-05.

---

## 11. Modelo de datos

### 11.1 Modelo común

Lo que el núcleo y el JSON conocen; cada backend lo rellena (correspondencias en §11.3).

| Entidad | Campos | Notas |
|---------|--------|-------|
| Cuenta | `uuid`, `label`, `email`, `local` | `uuid` con forma de UUID en ambos backends (§11.3); `local` = cuenta sin servidor (p. ej. `On My Device`, un PST). |
| Carpeta | `id` interno, `account_uuid`, `name`, `path`, `url`, `is_inbox`, `is_aggregate`, `total`, `unread` | `id` no se expone en el JSON. |
| Mensaje (fila) | `uid`, `message_id`, clave global de dedupe, `subject`, remitente `{name, address}`, `date_sent`, `date_received` (epoch), carpeta, `is_read`, `is_flagged`, `has_attachments`, `size_bytes` | `uid`: `int` (Apple Mail) o `str` (Outlook). |
| Cuerpo | `available`, `readable`, `partial`, `headers`, `body_text`, `attachments[{name}]`, `source{emlx_path, partial}`, `warnings` | Valores por plataforma: §12.5. |

### 11.2 Estado local: `~/.mailquery/state.json`

Un único JSON atómico (ADR-02), con el mismo esquema en ambas plataformas:

```json
{
  "schema": 1,
  "updated_at": "2026-11-02T02:15:00-04:00",
  "last_run": {"command": "new", "at": "2026-11-02T02:15:00-04:00"},
  "cursor": {"last_date_received": 1793573649, "last_uid": 83143, "lookback_seconds": 600},
  "emitted_uids": [83135, 83138, 83143]
}
```

En Windows, `last_uid` y los elementos de `emitted_uids` son strings (`EntryID`).

- `emitted_uids`: anillo de los últimos 1.000 uids emitidos (suprime duplicados del solape).
- `cursor.lookback_seconds` registra el lookback con el que se calculó la última corrida; **no manda** (§12.3).
- Escritura atómica (RF-23); permisos: RNF-05.
- Nunca contiene cuerpos, asuntos, direcciones ni rutas.
- `cursor` ausente o `null` ⇒ no hay cursor guardado (primera corrida, §12.3).
- Es estado corrupto: un JSON inválido; un campo conocido con tipo o valor inválido (`schema` ≠ 1, `updated_at` o `last_run` mal formados, `cursor` que no es objeto ni `null`, `last_date_received` que no es entero ≥ 0, `lookback_seconds` que no es entero ≥ 1, `emitted_uids` que no es lista); un `cursor` objeto sin `last_date_received` y `last_uid` válidos; o un uid inválido. Uid válido: en macOS, entero ≥ 1; en Windows, el formato de §12.4. Cualquier otro valor o tipo (incluidos uids del otro backend) es inválido.
- Si está corrupto, `new` falla con `E_STATE_CORRUPT` (exit 3) y un hint que sugiere renombrarlo y avisa de que la siguiente corrida será una primera corrida (§12.3). `search`/`show`/`mailboxes` no se ven afectadas; `doctor` lo reporta en el chequeo `state` con `ok=false`.

### 11.3 Correspondencia de cada backend con el modelo común

| Concepto | Apple Mail (macOS) | Outlook clásico (Windows) |
|----------|--------------------|---------------------------|
| `uid` | Identificador del mensaje en el `Envelope Index` (entero). | Identificador permanente del item en Outlook (`EntryID`), en hexadecimal en mayúsculas; cambia si el mensaje se mueve de carpeta (§18). |
| `message_id` | Message-ID del mensaje. | Message-ID de Internet. |
| Clave de dedupe (RF-07) | Identificador global del mensaje en Mail; nulo o 0 ⇒ mensaje único. | Message-ID; ausente o vacío ⇒ mensaje único. |
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
| `total` / `unread` | Recuento real de los mensajes de la carpeta (no los contadores que guarda Mail). | Recuento de los items buscables de la carpeta. |
| `date_received` / `date_sent` | Fechas de recepción y envío de Mail. | Hora real de entrega y de envío. |
| `from` / `to` / `cc` | Dirección y nombre del mensaje. | Dirección SMTP que trae el propio item, nunca una dirección interna de Exchange; si el item no la trae, `address` es `""` y se conserva `name`. Nunca se consulta la libreta de direcciones. |
| `is_flagged` | Marcado. | Marcado y no completado; un marcado como completado es `false`. |
| Cabeceras de `show` | Las del mensaje. | Las de transporte; si faltan (correo interno), From/To/Cc/Subject/Date/Message-ID con los datos del item. |
| Cuerpo | Del `.emlx`: texto plano o HTML convertido a texto. | Texto plano; si está vacío, HTML convertido a texto. |
| `body.partial` / `source.partial` | `true` si el mensaje es un `.partial.emlx` (completo salvo los adjuntos externalizados). | Siempre `false`. |
| Adjuntos | Solo nombres; nunca se leen. | Solo adjuntos no ocultos (los ocultos no cuentan ni se listan); solo nombres; nunca se guardan. |
| `source.emlx_path` | Ruta absoluta del `.emlx`. | `null`. |

Todas las fechas del JSON (incluido `generated_at`) son ISO 8601 con el offset local del sistema en ambas plataformas. En Outlook, `--since` incluye y `--until` excluye al segundo, y a igual fecha el `uid` se compara como texto (RNF-04).

---

## 12. CLI

Invocación: `mailquery <comando> [opciones]`. Comandos, opciones y semántica son idénticos en ambas plataformas.

| Comando | Descripción | Salida |
|---------|-------------|--------|
| `doctor` | Diagnóstico del entorno y de la garantía read-only. | Informe de texto (JSON con `--json`) |
| `mailboxes` | Cuentas, carpetas, contadores y si están incluidas. | JSON con `accounts[]`, `mailboxes[]` |
| `search` | Búsqueda por metadatos y/o contenido. | JSON con `messages[]` |
| `new` | Mensajes recibidos desde la última ejecución (cursor). | JSON con `messages[]`, `cursor` |
| `show <uid>` | Detalle de un mensaje. | JSON con `message` |

### 12.1 Opciones comunes

| Opción | Descripción |
|--------|-------------|
| `-h`, `--help` | Muestra uso, comandos, opciones y banderas; termina con código 0. Disponible también por comando (`mailquery search --help`). |
| `-v`, `--version` | Muestra la versión de la app y el entorno en una línea de texto; termina con código 0 (§12.9). |
| `--log-level {error,warning,info,debug}` | Nivel de log de esta ejecución (§15.1). |

No existen `--format`, `--config`, `--home`, `--quiet`, `--verbose`, `--no-color`, `--timeout` ni `--backend`. `-v` significa `--version`, no *verbose*.

### 12.2 `search`

| Opción | Descripción |
|--------|-------------|
| `--subject PATRÓN` | Asunto: subcadena o comodines `*`/`?`; términos separados por espacios = AND. |
| `--text PATRÓN` | Cuerpo del mensaje: subcadena o comodines. |
| `--from PATRÓN`, `--to PATRÓN`, `--cc PATRÓN` | Dirección o nombre visible: subcadena o comodines. |
| `--since TIEMPO`, `--until TIEMPO` | Fecha de recepción (incluye `since`, excluye `until`). |
| `--unread`, `--flagged`, `--has-attachments` | Filtros de estado. |
| `--include-mailbox LISTA` | Carpetas extra a incluir en esta ejecución (repetible o coma-separada; nombre, `path` o URL; `INBOX` como alias). Deben pertenecer a una cuenta **declarada** en config. |
| `--limit N` | Máximo de resultados (default: §15.1; máximo: RF-15). |

Semántica de comodines: `*` = cualquier secuencia, `?` = un carácter; sin comodines se busca como subcadena. Siempre insensible a mayúsculas y acentos (`Factura` = `factura` = `fáctura`).

Términos: en `--subject`, los términos separados por espacios son AND, tengan o no comodines (RF-09). En `--text`, `--from`, `--to` y `--cc`, el valor entero es un único patrón (RF-10, RF-11). Repetir un flag también es AND.

Alcance: RF-08 y §15.

Orden de `messages[]`: `date_received` descendente y, a igualdad, `uid` descendente. La deduplicación (RF-07) se aplica antes de `--limit`.

### 12.3 `new`

| Opción | Descripción |
|--------|-------------|
| `--peek` | Devuelve los nuevos sin avanzar el cursor. |
| `--limit N` | Máximo de mensajes de esta corrida (default: §15.1; máximo: RF-15); el cursor avanza hasta el último emitido. |

`new` usa el alcance configurado (§15), sin filtros por carpeta: el cursor es global. Si se añade una cuenta o carpeta a la config, sus correos históricos no se emiten por `new`; para eso se usa `search`.

**Primera corrida** (no hay cursor guardado: no existe `state.json`, se borró, o su `cursor` falta o es `null`, §11.2):

1. Se toma el mensaje más reciente del alcance (fecha `D`).
2. Se emiten, en orden ascendente `(date_received, uid)` y respetando `--limit`, los mensajes del alcance con `date_received` en `[D − lookback, D]`. Si el alcance no está vacío, se emite al menos el más reciente.
3. Se añade `W_FIRST_RUN: first run: emitted the messages received in the last <lookback> before the newest message`.
4. Sin `--peek`, el cursor avanza al último emitido y los uids emitidos entran al anillo, igual que en una corrida normal. Con `--peek` no se escribe estado.
5. Si el alcance no tiene mensajes con fecha válida y no futura, `count: 0` y no se escribe estado.
6. `W_FIRST_RUN` va siempre al final de `warnings`; antes van los warnings de alcance de cualquier corrida (`W_NO_ACCOUNTS`, `W_STORE_EXCLUDED`, `W_ACCOUNT_LABELS_UNAVAILABLE`, §12.10).

Si `--limit` es menor que el número de mensajes de la ventana, se emiten los `--limit` más recientes de la ventana, en orden ascendente. En el texto de `W_FIRST_RUN` y en el chequeo `state` de `doctor`, `<lookback>` se muestra tal como está escrito en `[new].lookback` (§15.1).

Los mensajes con fecha de recepción nula, ≤ 0 o no representable no entran en la ventana de `new` (ni en la primera corrida ni en las siguientes) y no mueven el cursor; siguen visibles en `search` y `show` con `date_received: null` (§17). Los mensajes con fecha de recepción posterior al momento de la corrida tampoco entran ni mueven el cursor (tampoco cuentan como "el más reciente" de la primera corrida); entran en la primera corrida de `new` en la que su fecha ya no sea futura, y siguen visibles en `search` y `show` con su fecha.

**Lookback:** cada corrida usa el `[new].lookback` de la config actual; un cambio en la config aplica en la siguiente corrida.

Re-emisiones puntuales aceptadas: §18.

### 12.4 `show`

```bash
mailquery show 83143                    # macOS: uid entero
mailquery show 00000000A1B2C3D4…        # Windows: uid = EntryID hexadecimal
```

Devuelve `{"ok", "command", "generated_at", "message", "warnings"}`. `message` tiene, en este orden: `uid`, `message_id`, `subject`, `from`, `to`, `cc`, `date_sent`, `date_received`, `mailbox`, `is_read`, `is_flagged`, `has_attachments`, `size_bytes` (mismos valores que en `search`, §12.5), `headers` (From, To, Cc, Subject, Date, Message-ID), `body_text` (truncado según §15.6), `body_truncated` (true si se truncó, con `W_BODY_TRUNCATED`), `attachments: [{"name": "..."}]`, `partial`, `readable` (mismo significado que `body.readable`, §12.5) y `source: {"emlx_path": "..." | null, "partial": bool}`. Si el cuerpo no está disponible o no es legible, `body_text` es `""` y el warning indica el motivo (§12.5).

El formato del uid se valida antes de crear `~/.mailquery`, leer la config o abrir el cliente de correo: un uid inválido da `E_USAGE` aunque el cliente no esté disponible.

`show` resuelve `[scope]` igual que `search` y `new` (§15.3): un bloque o una carpeta de `mailbox_list` que no resuelve da el mismo error que en `search`, aunque el mensaje pedido no esté en esa carpeta.

Resolución del uid (igual en ambas plataformas):

| Caso | Resultado |
|------|-----------|
| `uid` con formato inválido para el backend (en macOS, no es un entero; en Windows, no es hex en mayúsculas `^[0-9A-F]+$`) | `E_USAGE` (exit 2), mensaje `invalid uid …: expected an integer` (macOS) o `invalid uid …: expected an uppercase hexadecimal EntryID` (Windows) |
| `uid` que no existe, está borrado, no es un correo (p. ej. un acuse de entrega en Outlook) o está en una carpeta oculta (§15.7) | `E_USAGE` (exit 2), mensaje `message uid … was not found`; en Windows, el hint remite a `excluded_stores` de `mailboxes` |
| `uid` que existe en una cuenta **no declarada** en `config.toml` (o no hay cuentas declaradas) | `E_ACCOUNT_NOT_IN_SCOPE` (exit 2), hint para declarar la cuenta |
| `uid` cuyo `EntryID` identifica a un store **excluido** (solo Windows, §15.7), aunque sea de una cuenta declarada | `E_ACCOUNT_NOT_IN_SCOPE` (exit 2), con el motivo de la exclusión. Si el store no se puede identificar sin leer sus items, el caso es "no encontrado" (`E_USAGE`) |
| `uid` en una cuenta declarada, en cualquiera de sus carpetas | Éxito |

`show` no exige que la carpeta esté en `mailbox_list`: basta con que la cuenta esté declarada.

### 12.5 Contrato de salida (JSON)

Un objeto por ejecución, con la misma forma en ambas plataformas y siempre **formateado**: indentación de 2 espacios, un espacio después de `:`, un campo por línea y caracteres no ASCII sin escapar, seguido de un salto de línea LF (RF-32). Aplica a todas las salidas JSON: comandos de datos, errores y `doctor --json`. Los ejemplos de este documento que aparecen en una sola línea muestran solo el contenido, no el formato. Éxito:

```json
{
  "ok": true,
  "command": "search",
  "generated_at": "2026-11-02T02:15:00-04:00",
  "count": 1,
  "truncated": false,
  "hint": null,
  "warnings": [],
  "messages": [
    {
      "uid": 83143,
      "message_id": "<2b6a6efcfe5b9efe30bce5e30.8c63f4dcfa.20231128200729.b515836745.adb9ff76@example.net>",
      "duplicate_count": 1,
      "subject": "Información mensual a Octubre de 2026",
      "from": {"name": "Fortaleza SAFI", "address": "example@example.com"},
      "to": [{"name": "", "address": "me@example.com"}],
      "cc": [],
      "date_sent": "2026-11-01T22:54:03-04:00",
      "date_received": "2026-11-01T22:54:09-04:00",
      "mailbox": {"account": {"uuid": "D70DBCF6-...", "label": "iCloud (you@gmail.com)", "email": "you@gmail.com"}, "name": "INBOX", "path": "INBOX", "url": "imap://D70DBCF6-.../INBOX"},
      "is_read": false,
      "is_flagged": false,
      "has_attachments": false,
      "size_bytes": 202913,
      "snippet": "Estimado cliente, adjuntamos la información mensual…",
      "body": {"available": true, "readable": true, "partial": true, "truncated": false}
    }
  ],
  "scan": {"mode": "metadata", "candidates": 1, "messages_read": 1, "duration_ms": 211}
}
```

`hint` es `null` salvo cuando `truncated` es `true` (RF-15). `body.truncated` indica que el `snippet` se cortó (RF-16). Campos de `scan`: RF-17.

Valores de `body` en `search`/`new`:

| Caso | `available` | `readable` | `partial` | Warning |
|------|-------------|------------|-----------|---------|
| Texto normal | true | true | false | — |
| `.partial.emlx` | true | true | true | — |
| `.emlx` ausente | false | false | false | `W_EMLX_MISSING` |
| `.emlx` que no se puede abrir, ruta no resoluble o mensaje sin carpeta | false | false | false | `W_BODY_UNREADABLE` |
| `.emlx` corrupto recuperable | true | true | false | `W_EMLX_CORRUPT` |
| `.emlx` corrupto irrecuperable | true | false | false | `W_EMLX_CORRUPT` |
| S/MIME (macOS) | true | false | false | `W_BODY_UNREADABLE` |
| Outlook: item con solo cabeceras | false | false | false | `W_BODY_NOT_LOCAL` |
| Outlook: S/MIME | true | false | false | `W_BODY_UNREADABLE` |
| Outlook: item que no se puede abrir | false | false | false | `W_BODY_UNREADABLE` |

Diferencias de valor por plataforma: §11.3 (ningún campo se omite, RF-30).

`new` añade `"cursor": {"previous": {...}, "current": {...}}`. `mailboxes` tiene estructura propia (`accounts[]`/`mailboxes[]`/`excluded_stores[]`):

```json
{"ok": true, "command": "mailboxes", "generated_at": "…",
 "accounts": [{"uuid": "…", "label": "Exchange (you@company.com)", "email": "you@company.com", "declared": true}],
 "mailboxes": [{"account": {"uuid": "…", "label": "…", "email": "…"}, "name": "INBOX", "path": "INBOX", "url": "outlook://…/INBOX", "total": 1318, "unread": 0, "included": true}],
 "excluded_stores": [{"label": "PST (Archivo 2019)", "path": "\\\\nas01\\backup\\archivo2019.pst", "reason": "network_path"},
                     {"label": "Exchange shared (Soporte)", "path": null, "reason": "shared_mailbox"}],
 "warnings": []}
```

`excluded_stores[].reason` es uno de `shared_mailbox`, `public_folders`, `online_mode`, `network_path`, `unsupported_account_type`, `unavailable` (significado de cada uno: §15.7); `path` es la ruta del archivo de datos o `null` si el store no tiene archivo local o no se pudo leer. En macOS el campo existe y siempre es `[]`. `doctor` imprime un informe de texto por defecto y solo con `--json` devuelve el payload máquina con `checks[]`. Error:

```json
{"ok": false, "command": "search", "error": {"code": "E_UNBOUNDED_SCAN", "message": "…", "hint": "…"}}
```

Los warnings son strings con código `W_*` (p. ej. `W_NO_ACCOUNTS: no accounts are declared in config.toml; nothing is observed`; catálogo en §12.10). Los errores se emiten en `stdout` como JSON y además un resumen legible en `stderr`.

### 12.6 Códigos de salida y diccionario de errores

| Exit | Significado | Códigos `E_*` |
|------|-------------|----------------|
| 0 | Éxito (incluye 0 resultados, `--help` y `--version`) | — |
| 1 | Error interno inesperado | `E_INTERNAL` |
| 2 | Uso o configuración inválidos | `E_USAGE`, `E_CONFIG_INVALID`, `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE`, `E_ACCOUNT_NOT_IN_SCOPE`, `E_MAILBOX_NOT_FOUND`, `E_BAD_TIME`, `E_BAD_FILTER` |
| 3 | Entorno no válido | `E_STORE_NOT_FOUND`, `E_SCHEMA_UNSUPPORTED`, `E_PERMISSION`, `E_STATE_CORRUPT`, `E_CLIENT_UNSUPPORTED` *(nuevo)*, `E_DEPENDENCY_MISSING` *(nuevo)*, `E_CLIENT_TIMEOUT` *(nuevo)* |
| 4 | Consulta rechazada | `E_UNBOUNDED_SCAN`, `E_SCAN_TOO_LARGE` |
| 5 | Ocupado/transitorio | `E_LOCKED`, `E_DB_BUSY`, `E_CLIENT_BUSY` *(nuevo)* |
| 6 *(nuevo)* | Cliente de correo no disponible | `E_OUTLOOK_NOT_RUNNING` |

Errores propios de cada plataforma:

| Código | Plataforma | Cuándo |
|--------|-----------|--------|
| `E_STORE_NOT_FOUND` | macOS | No hay store de Mail; el detalle incluye las rutas buscadas. |
| `E_SCHEMA_UNSUPPORTED` | macOS | Versión del store o esquema no soportados (falta una tabla o columna obligatoria); el detalle incluye la versión detectada. |
| `E_DB_BUSY` | macOS | El `Envelope Index` sigue bloqueado tras un reintento (§17). |
| `E_PERMISSION` | ambas | macOS: falta el Acceso total al disco (§16.1). Windows: Outlook deniega el acceso COM, p. ej. por directiva. |
| `E_CLIENT_BUSY` | Windows | Outlook sigue rechazando la llamada de forma transitoria tras un reintento (§17). |
| `E_CLIENT_TIMEOUT` | Windows | RF-33. |

Los existentes no cambian de exit en macOS. Errores de `show`: §12.4.

Cuando el Outlook clásico no está disponible, la detección sigue este orden: (1) `pywin32` no está disponible ⇒ `E_DEPENDENCY_MISSING`; (2) Outlook clásico no está registrado en COM o su versión es < 16.0 ⇒ `E_CLIENT_UNSUPPORTED`; (3) está registrado pero no hay una instancia en ejecución accesible ⇒ `E_OUTLOOK_NOT_RUNNING` (exit 6). Hints: `E_DEPENDENCY_MISSING` ⇒ `pipx reinstall mailquery`; `E_CLIENT_UNSUPPORTED` ⇒ instalar Outlook clásico (el nuevo Outlook no está soportado); `E_OUTLOOK_NOT_RUNNING` ⇒ abrir Outlook clásico con el mismo usuario, sin elevar, y reintentar.

Cada error debe incluir un `hint` accionable (p. ej. "añade --since 7d", "concede Acceso total al disco a la app del harness", "abre Outlook clásico con el mismo usuario y sin elevar", "revisa `mailquery mailboxes`").

### 12.7 Ayuda (`-h` / `--help`)

La ayuda es texto para humanos (excepción de RF-18), está en inglés y se
organiza por secciones y ejemplos. Aplica a `mailquery --help` y a
`mailquery <comando> --help` de los cinco comandos, sin colores para que la
salida sea estable en pipes. Es la misma en ambas plataformas y ningún
texto de ayuda puede contradecir este PRD.

Ejemplo ilustrativo de salida (raíz; ancho de 100 columnas):

```text
usage: mailquery [-h] [-v] [--log-level LEVEL] <command> ...

Read-only CLI to read and search local mail (Apple Mail on macOS, classic Outlook on Windows).

Commands:
  doctor             diagnose the environment and verify the read-only guarantee
  mailboxes          list accounts, folders, counters and included folders
  search             search messages by subject, body, sender, date or state
  new                messages received since the last run (cursor)
  show               show one message by uid

Global options:
  -h, --help         show this help message and exit
  -v, --version      show the app version, backend, Python and platform, and exit
  --log-level LEVEL  minimum log level: error, warning, info or debug (overrides [logging].level;
                     default: info)

Examples:
  mailquery doctor                     environment and read-only preflight
  mailquery mailboxes                  accounts, folders and included flags
  mailquery search --since 1w --unread
  mailquery search --text "*factura*" --since 1mo
  mailquery new --peek
  mailquery show <uid>

Configuration: ~/.mailquery/config.toml (optional; see README.md)
Output: one JSON object on stdout for every command, in UTF-8 (this help,
        --version and the default doctor report are the only non-JSON output);
        logs go to ~/.mailquery/logs/mailquery.log
Exit codes: 0 ok | 2 usage or config error | 3 environment error
            | 4 rejected query | 5 busy or transient error | 6 mail client not running
```

Cada subcomando añade sus secciones `Options`, `Examples` y `Notes` (por
ejemplo, `mailquery search --help` documenta comodines, fechas relativas y el
acotamiento obligatorio de `--text`).

### 12.8 `doctor`

`doctor` combina chequeos comunes y chequeos del backend; `checks[].name` es estable **por backend**:

| Backend | Chequeos |
|---------|----------|
| Apple Mail | `python`, `home`, `store`, `envelope_index`, `schema`, `readonly_strategy`, `accounts_db`, `config`, `state`, `lock` (cambios en §22.2) |
| Outlook | `python`, `home`, `pywin32`, `outlook`, `stores`, `readonly_strategy`, `object_model_guard`, `config`, `state`, `lock` |

Chequeos propios de cada backend:

| Chequeo | Backend | Qué valida | Depende de |
|---------|---------|------------|------------|
| `store` | Apple Mail | Versión `V*` detectada y ruta del store. | — |
| `envelope_index` | Apple Mail | Existe y se abre con la estrategia de §9.3 (`live_ro`/`copy_ro`), nunca de otra forma (FDA). | `store` |
| `schema` | Apple Mail | Están todas las tablas y columnas obligatorias. | `envelope_index` |
| `readonly_strategy` | Apple Mail | `live_ro` o `copy_ro` (§9.3). | `envelope_index` |
| `accounts_db` | Apple Mail | `Accounts4.sqlite` legible y número de etiquetas disponibles. | — |
| `pywin32` | Outlook | `pywin32` disponible en el intérprete de mailquery. | — |
| `outlook` | Outlook | Outlook clásico registrado, versión ≥ 16.0, en ejecución y accesible. | `pywin32` |
| `stores` | Outlook | Stores candidatos (etiqueta y tipo) y excluidos (etiqueta, ruta y motivo). | `outlook` |
| `readonly_strategy` | Outlook | `com_readonly`: proxy de lista blanca activo, conexión sin lanzamiento y caché de `pywin32` confinada (§9.3). | `outlook` |
| `object_model_guard` | Outlook | Criterio de abajo. | — |

La resolución de bloques de `config` depende de `schema` (Apple Mail) o de `stores` (Outlook). `python`, `home`, `state` y `lock` no dependen de otro chequeo.

Reglas comunes:

- `python`, `config`, `state` y `lock` tienen la misma semántica en ambos backends.
- `config` valida la existencia y sintaxis de `config.toml`, la resolución de cada bloque `[scope]` y su `mailbox_list`, y lista las cuentas disponibles si no hay ninguna declarada (RF-25). La sintaxis se valida siempre; la resolución depende de un chequeo del backend (tabla anterior) y, si ese chequeo falló, sale como `not evaluated: <chequeo> failed`. Sin bloques declarados y con esa dependencia fallida, `config` sale con `ok=true` y `0 account block(s) declared; available accounts: unknown (<chequeo> failed)`. En macOS, si esa dependencia está bien pero `accounts_db` falló, el detalle es `available accounts: unknown (Accounts4.sqlite unavailable)`, como en 1.x.
- `home` valida en macOS que el home existe con modo `0700`; en Windows, que existe y es escribible por el usuario.
- Sin cursor guardado, `state` sale con `ok=true` y el detalle `no state yet; the next new run is a first run and emits the messages received in the last <lookback> before the newest message`.
- Un chequeo que no se puede evaluar sale con `ok=false` y `detail` = `not evaluated: <motivo>`: `<chequeo del que depende> failed` si depende de otro que falló (tabla anterior), o la causa concreta si no (p. ej. `not evaluated: SecurityCenter2 unavailable`).
- En Windows, si una llamada a Outlook no responde en 30 s durante `doctor`, no se aborta (RF-33): el chequeo en curso sale con `ok=false` y `timeout after 30 s: Outlook did not respond (possible security prompt)`, y los que dependen de él salen como `not evaluated`.
- `doctor` siempre sale con exit 0 si puede diagnosticar, y nunca lanza el cliente de correo.

**Criterio de `object_model_guard`** (decisión del dueño del producto). Outlook muestra un aviso de seguridad cuando un proceso externo lee direcciones, cuerpos o destinatarios y no hay un antivirus activo reconocido, o una directiva endurece la protección; en modo no interactivo ese aviso bloquearía al harness (el timeout de RF-33 evita el bloqueo). El chequeo lee en solo lectura las directivas de Outlook y el estado del antivirus:

- **Falla** si una directiva fuerza preguntar siempre o denegar el acceso programático, o si ninguna directiva lo decide y no hay un antivirus activo.
- **Pasa** si una directiva lo permite siempre, o si ninguna lo decide y hay un antivirus activo.
- Si ninguna directiva lo decide y el estado del antivirus no se puede consultar (p. ej. Windows Server): `ok=false`, `not evaluated: SecurityCenter2 unavailable`. Si una directiva lo decide, el antivirus no se consulta.

### 12.9 `--version` (`-v`)

Opción global que imprime **una sola línea de texto** en `stdout` y termina con exit 0 (excepción de RF-18).

```text
$ mailquery --version
mailquery 2.0.0 (backend apple_mail; Python 3.14.6; macOS 27.0.1 arm64)

$ mailquery -v          # en Windows
mailquery 2.0.0 (backend outlook; Python 3.14.7; Windows 10.0.26200 AMD64)
```

Formato: `mailquery <versión> (backend <backend>; Python <x.y.z>; <plataforma>)`.

| Campo | Origen |
|-------|--------|
| `<versión>` | Versión del paquete instalado (§22.3). |
| `<backend>` | Nombre del backend que se seleccionaría en esta plataforma (RF-26): `apple_mail` u `outlook`. No se abre ni se consulta. |
| `<x.y.z>` | Versión del intérprete que ejecuta mailquery. |
| `<plataforma>` | macOS: `macOS <versión> <arquitectura>`; Windows: `Windows <versión> <arquitectura>`; otras: `<sistema> <release> <arquitectura>`. |

Reglas:

- Sin efectos: no crea `~/.mailquery`, no escribe en el log, no toma el lock, no lee `config.toml`, no necesita `pywin32` y no accede al cliente de correo. Funciona aunque Outlook esté cerrado o falte FDA.
- Solo como opción global (antes del subcomando). Con un subcomando, `-v`/`--version` es un argumento no reconocido ⇒ `E_USAGE` (exit 2).
- Puede combinarse con otras opciones globales: `mailquery --log-level debug -v` muestra la versión (y no escribe log).
- Con `-h` y `-v` a la vez gana la primera que aparece: `-v -h` muestra la versión y `-h -v` la ayuda; ambos exit 0.

### 12.10 Catálogo de warnings

Los warnings son strings `"W_CODIGO: detalle"`; el detalle es en inglés y siempre indica el motivo concreto.

| Código | Plataforma | Cuándo |
|--------|-----------|--------|
| `W_NO_ACCOUNTS` | ambas | No hay cuentas declaradas válidas: `search`/`new` devuelven `count: 0`; también en `mailboxes`. |
| `W_FIRST_RUN` | ambas | Primera corrida de `new`: no hay cursor guardado (§12.3). |
| `W_RESULTS_TRUNCATED` | ambas | Hay más resultados que `--limit`. |
| `W_BODY_TRUNCATED` | ambas | `show` truncó el cuerpo (§15.6). |
| `W_HTML_NO_TEXT` | ambas | El cuerpo HTML no produjo texto. |
| `W_BODY_UNREADABLE` | ambas | El cuerpo no se puede leer; el detalle dice por qué (archivo o item que no se puede abrir, mensaje sin carpeta). Para S/MIME, en ambas plataformas, el texto es `W_BODY_UNREADABLE: S/MIME encrypted content is not supported` o `W_BODY_UNREADABLE: S/MIME signed content is not supported`. **Sustituye a `W_EMLX_UNREADABLE`** en todos sus usos. |
| `W_ATTACHMENTS_UNAVAILABLE` | ambas | En `show`, solo si el cuerpo no se pudo leer **y** el mensaje tiene adjuntos; sin adjuntos no se emite. macOS: "tiene adjuntos" = el `Envelope Index` tiene nombres de adjuntos para el mensaje, y `attachments` lista esos nombres (como en 1.x). Windows: "tiene adjuntos" = `has_attachments` (se lee sin abrir el item), y `attachments` es `[]` porque los nombres no se pueden leer sin abrirlo (§11.3). Diferencia documentada: en Windows un S/MIME siempre trae un adjunto técnico (`smime.p7m`), así que `has_attachments` no indica adjuntos reales; para S/MIME, `attachments` es `[]` y este warning no se emite. |
| `W_ACCOUNT_LABELS_UNAVAILABLE` | macOS | `Accounts4.sqlite` no está disponible; solo funcionan los UUID. |
| `W_EMLX_MISSING` | macOS | No existe el `.emlx` del mensaje (`body.available=false`). |
| `W_EMLX_CORRUPT` | macOS | El `.emlx` está corrupto. |
| `W_BODY_NOT_LOCAL` | Windows | El item solo tiene cabeceras en local (`body.available=false`); nunca se descarga. |
| `W_STORE_EXCLUDED` | Windows | Una cuenta declarada resuelve a un store excluido (§15.3). |

---

## 13. Despliegue e instalación

### 13.1 Requisitos

| Requisito | macOS | Windows |
|-----------|-------|---------|
| Sistema | macOS con Apple Mail (store `V9`/`V10`/`V11`; `V10` validada) | Windows 10/11 x64 |
| Cliente | Apple Mail; no necesita estar abierto | Outlook **clásico** 16.0 (x86 o x64), en ejecución y con un perfil cargado; cuentas Exchange en modo caché y las demás con su archivo de datos en un disco local (§15.7) |
| Python | ≥ 3.11 (el intérprete que use `pipx`) | ≥ 3.11 (el intérprete que use `pipx`) |
| `pipx` | Instalado (instrucciones en el README) | Instalado (instrucciones en el README) |
| Dependencias de runtime | Ninguna | La de ADR-14 (la instala `pipx`) |
| Permisos | **Acceso total al disco (FDA)** para la app que ejecuta la CLI (§16.1) | Misma sesión interactiva y mismo nivel de integridad que Outlook: un proceso elevado o un servicio de Windows no ve el Outlook del usuario y obtiene `E_OUTLOOK_NOT_RUNNING`; Object Model Guard sin avisos (§12.8) |

### 13.2 Instalación

Se instala con `pipx install .` desde la raíz del repositorio en ambas plataformas (ADR-08); el primer `mailquery doctor` crea `~/.mailquery` y valida el entorno. Los instaladores `scripts/install.sh` (macOS/Linux) y `scripts/install.ps1` / `install.bat` (Windows) automatizan `pipx` y siembran `config.toml` desde `docs/config.example.toml` si no existe.

Al terminar, `install.ps1` comprueba que `pywin32` quedó instalado y que `mailquery -v` muestra `backend outlook`; si la comprobación falla, muestra el problema con el hint `pipx reinstall mailquery` y termina con un código distinto de 0.

Después de instalar, declara al menos una cuenta en `~/.mailquery/config.toml` (§15).

### 13.3 Actualización y desinstalación

Se actualiza con `pipx reinstall mailquery` tras actualizar el repositorio y se desinstala con `pipx uninstall mailquery`. Desinstalar no borra `~/.mailquery` (estado, logs y configuración); el usuario puede borrarlo a mano o, en Windows, con `scripts\install.ps1 -Uninstall -Purge`.

### 13.4 Notas de permisos

Permisos: §13.1 y §16.1. En ambos casos, verificar con `mailquery doctor` tras actualizar el intérprete, el sistema o el cliente.

---

## 14. Logs

**Archivo:** `~/.mailquery/logs/mailquery.log` (permisos: RNF-05), en **texto plano**. Cuando supera `[logging].max_size_mb` (default 10 MB) se rota: pasa a `mailquery.log.1`, los anteriores se desplazan y se conservan **5** archivos rotados; el más antiguo se borra. El tamaño máximo en disco es, por tanto, unas 6 veces `max_size_mb`.
**Regla:** `stdout` es solo el JSON de datos; nada de logs en `stdout`.

Formato (estilo log4j):

```text
2026-11-02 02:15:00,123 INFO  mailquery.cli run=abc123 event=start command=search backend=apple_mail
2026-11-02 02:15:00,214 INFO  mailquery.store run=abc123 strategy=live_ro version=V10 schema_ok=true
2026-11-02 02:15:00,427 INFO  mailquery.cli run=abc123 event=end exit_code=0 count=1
```

- Niveles: `error`, `warning`, `info`, `debug` (§15.1).
- Se registran: comando, backend, estrategia de conexión, versión del store o del cliente, conteos, duración, número de warnings y sus códigos `W_*` (sin el detalle), y errores (`code` + mensaje).
- **Nunca** se registran asuntos, cuerpos, direcciones, nombres de personas, carpetas o cuentas, etiquetas de cuenta, rutas, términos de búsqueda ni identificadores de mensajes o stores (uids, `EntryID`, `StoreID`); si el mensaje de un error los contiene, se omiten al escribirlo en el log.
- Un error inesperado (`E_INTERNAL`) registra además su traceback.

---

## 15. Configuración

**Archivo:** `~/.mailquery/config.toml` — **opcional** e idéntico en ambas plataformas. Es el único archivo de configuración: no hay flags de ruta ni variables de entorno.

**Reglas generales** (esta sección es la dueña de las reglas de alcance):

- Solo se admiten las claves documentadas; cualquier clave o sección desconocida ⇒ `E_CONFIG_INVALID` (exit 2), para que un typo no pase desapercibido.
- La aplicación **nunca** modifica este archivo.
- **Solo se buscan, emiten y muestran mensajes de las cuentas declaradas**: cada bloque `[scope.<cuenta>]` declara una cuenta observada; las cuentas sin bloque quedan excluidas (`mailboxes` las lista con `included: false`).
- El alcance de una cuenta declarada es su INBOX más las carpetas de `mailbox_list` (aditivas; un bloque sin `mailbox_list` observa solo INBOX). Si la cuenta no tiene INBOX (p. ej. un PST de archivo), se observan solo las carpetas de `mailbox_list`, sin error.
- Si dos bloques resuelven a la misma cuenta, se combinan (unión sin duplicados).
- Sin ningún bloque de cuenta válido (o sin archivo) no se observa ninguna cuenta: §15.3.
- **Precedencia**: flags de CLI > `config.toml` > defaults del producto.

### 15.1 Tabla de propiedades configurables

| Propiedad | Tipo | Obligatoria | Default | Valores válidos | Ejemplo | Qué hace |
|-----------|------|-------------|---------|-----------------|---------|----------|
| `[logging]` | tabla TOML | No | — | — | `[logging]` | Sección de logging. |
| `logging.level` | string | No | `"info"` | `error`, `warning`, `info`, `debug` | `"debug"` | Nivel mínimo del log; `--log-level` lo sobreescribe. |
| `logging.max_size_mb` | entero | No | `10` | 1–1024 | `50` | Tamaño en MB a partir del cual se rota el log; se conservan 5 archivos rotados (§14). |
| `[search]` | tabla TOML | No | — | — | `[search]` | Defaults de búsqueda. |
| `search.default_limit` | entero | No | `20` | 1–200 | `50` | Límite por defecto de `search`; `--limit` lo sobreescribe. |
| `search.max_scan` | entero | No | `5000` | 100–50000 | `10000` | Candidatos máximos al escanear contenido (`--text`). |
| `[new]` | tabla TOML | No | — | — | `[new]` | Defaults de `new`. |
| `new.default_limit` | entero | No | `100` | 1–500 | `200` | Límite por defecto de `new`; `--limit` lo sobreescribe. |
| `new.lookback` | string | No | `"10min"` | duración (`min`, `h`, `d`), 1 min–1 día | `"15min"` | Solape del cursor al buscar mensajes nuevos. |
| `[scope.<account-id>]` | tabla TOML | No | — | etiqueta de cuenta, email único o UUID/prefijo (≥ 8) | `[scope."iCloud (you@gmail.com)"]` | **Declara una cuenta observada**; si no existe, la cuenta queda excluida. La clave identifica la cuenta (§15.2). |
| `mailbox_list` | array de strings | No | `[]` | nombre, `path` o URL de carpeta tal como aparece en `mailquery mailboxes`, o `INBOX`; case-insensitive (resolución: §15.3) | `["Facturas", "[Gmail]/Important"]` | Carpetas adicionales a INBOX para esa cuenta. |

El namespace `scope` es obligatorio en la ruta de las claves, pero **no hace falta escribir un encabezado `[scope]` vacío**: `[scope."<cuenta>"]` crea la tabla padre implícitamente. Las tablas de cuenta en el nivel superior no se admiten.

Dentro de un bloque `[scope.<cuenta>]` la única clave es `mailbox_list`. Todo lo que no aparece en esta tabla son valores fijos del producto (§15.6).

### 15.2 Identificador de cuenta

Se aceptan tres formas, en este orden de resolución:

1. **Etiqueta legible** mostrada por `mailquery mailboxes` (`account.label`), p. ej. `"iCloud (you@gmail.com)"`, `"Gmail (you@gmail.com)"`, `"On My Device"` (macOS) o `"Exchange (you@company.com)"`, `"PST (Archivo 2025)"` (Windows).
2. **Email** de la cuenta si es único (p. ej. `"you@gmail.com"`).
3. **UUID** completo o prefijo único de ≥ 8 caracteres (siempre válido, aunque las etiquetas no estén disponibles).

Origen de etiquetas y UUID: en macOS, `Accounts4.sqlite` en solo lectura; en Windows, las cuentas y stores del perfil de Outlook (§11.3, §15.7). Las claves TOML con espacios, puntos o paréntesis deben ir entre comillas (`[scope."iCloud (you@gmail.com)"]`); los UUID (con guiones) se pueden usar como clave bare.

Si las etiquetas no están disponibles (solo puede ocurrir en macOS), las etiquetas/emails no se resuelven: solo funciona el UUID, `doctor` lo advierte en `accounts_db` y los comandos de datos añaden `W_ACCOUNT_LABELS_UNAVAILABLE`.

**Errores de sintaxis frecuentes:** el `@` y los puntos no son válidos en claves TOML sin comillas, y los bloques de cuenta siempre cuelgan de `[scope]`:

```text
# INVÁLIDO (sintaxis TOML): el email sin comillas no es una clave válida
[you@gmail.com]

# INVÁLIDO (esquema): tabla de nivel superior; debe colgar de [scope]
["you@gmail.com"]

# VÁLIDO (email como identificador, solo si es único)
[scope."you@gmail.com"]

# VÁLIDO (etiqueta; recomendado cuando dos cuentas comparten email)
[scope."iCloud (you@gmail.com)"]
```

### 15.3 Validación y errores

- Cuenta inexistente ⇒ `E_CONFIG_ACCOUNT_UNKNOWN` (exit 2).
- Etiqueta/email que coincide con más de una cuenta ⇒ `E_ACCOUNT_AMBIGUOUS` (exit 2) con la lista `label (uuid)` para desambiguar.
- Etiqueta/email sin base de cuentas disponible ⇒ `E_ACCOUNT_LABELS_UNAVAILABLE` (exit 2; usar el UUID que muestra `mailboxes`).
- Una referencia de `mailbox_list` se resuelve dentro de la cuenta de su bloque. Una de `--include-mailbox` se prueba en las cuentas declaradas, en el orden de sus bloques en `config.toml`, y se usa la primera que la resuelve (así, `--include-mailbox INBOX` es la bandeja de la primera cuenta declarada). Si no la resuelve ninguna: `E_ACCOUNT_NOT_IN_SCOPE` (exit 2; hint: declarar la cuenta en `config.toml`) si la resuelve una cuenta no declarada; si no, `E_MAILBOX_NOT_FOUND` con las carpetas de todas las cuentas declaradas.
- Dentro de una cuenta, la referencia se resuelve sin distinguir mayúsculas: `INBOX` es siempre la bandeja de entrada de la cuenta; si no, una coincidencia exacta de `path` o URL gana a una de nombre; si varias carpetas coinciden por nombre, se usa la primera en el orden de `mailboxes[]` (macOS: orden del catálogo de carpetas de Mail; Windows: stores en el orden del perfil y, dentro de cada uno, carpetas en recorrido en profundidad en el orden en que Outlook las enumera).
- Carpeta de `mailbox_list` (o de `--include-mailbox`) que no existe en esa cuenta ⇒ `E_MAILBOX_NOT_FOUND` (exit 2) con la lista de carpetas válidas.
- Tipo incorrecto (p. ej. `mailbox_list = "Facturas"` en lugar de un array) o clave desconocida ⇒ `E_CONFIG_INVALID` (exit 2). La clave retirada `[logging].retention_days` es una clave desconocida más, con el hint `retention_days was replaced by max_size_mb`.
- Valor fuera de rango (p. ej. `default_limit = 0` o `max_size_mb = 0`) o nivel/duración inválidos ⇒ `E_CONFIG_INVALID` (exit 2), con el rango válido en el `hint`.
- Cuenta declarada que resuelve a un store excluido (solo Windows, §15.7) ⇒ warning `W_STORE_EXCLUDED: <etiqueta> at <ruta> is excluded: <reason>` (sin ` at <ruta>` si `path` es `null`); la cuenta no se lee. Aparece en `warnings` de `search`, `new`, `show` y `mailboxes`, y en el `detail` del chequeo `config` de `doctor`, que sigue con `ok=true`. Si todas las cuentas declaradas están excluidas, `search`/`new` devuelven `count: 0` con `W_STORE_EXCLUDED` y `W_NO_ACCOUNTS`. Las claves de `[scope]` resuelven contra las cuentas candidatas **y** las excluidas, para poder reportarlas en vez de dar `E_CONFIG_ACCOUNT_UNKNOWN`.
- Sin bloques `[scope.*]` válidos (o sin `config.toml`) ⇒ `W_NO_ACCOUNTS` (warning, no error): `search`/`new` devuelven `count: 0`; `mailboxes` marca `included: false`; `doctor` lista las cuentas disponibles (§12.8).
- `mailquery doctor` reporta todos estos casos con los valores válidos.

### 15.4 Archivo mínimo (opcional)

Para leer una cuenta hay que **declararla**. Un bloque sin `mailbox_list` ya observa su INBOX; `mailbox_list` solo añade carpetas extra. Este es el menor ejemplo útil:

```toml
# ~/.mailquery/config.toml — mínimo
# Declara la cuenta (INBOX siempre incluido) y añade una carpeta extra.
[scope."iCloud (you@gmail.com)"]
mailbox_list = ["Facturas"]
```

Equivalente en Windows:

```toml
[scope."Exchange (you@company.com)"]
mailbox_list = ["INBOX/Facturas"]
```

### 15.5 Archivo completo (todas las propiedades)

El ejemplo de macOS muestra **todo** lo que se puede configurar hoy, con las tres formas de identificar una cuenta. Las secciones `[logging]`, `[search]` y `[new]` son idénticas en ambas plataformas; para Windows solo se muestran los bloques de cuenta. Cada equipo tiene su propio `config.toml`: en un archivo solo resuelven las cuentas del backend de ese equipo (una cuenta de otro backend ⇒ `E_CONFIG_ACCOUNT_UNKNOWN`). Son válidos tal cual, sustituyendo etiquetas y carpetas por las tuyas.

**macOS (Apple Mail)**, archivo completo:

```toml
# ============================================================================
# ~/.mailquery/config.toml — EJEMPLO COMPLETO (macOS + Apple Mail)
# ============================================================================
# Este archivo es OPCIONAL: sin él no se observa ninguna cuenta.
# Solo se leen las cuentas declaradas aquí; las demás quedan excluidas.
# Dentro de cada cuenta declarada, INBOX se incluye SIEMPRE.
# Claves desconocidas ⇒ E_CONFIG_INVALID (exit 2).
# ============================================================================

# El namespace `scope` es obligatorio en las claves, pero no hace falta
# escribir [scope] por separado: [scope."..."] crea la tabla padre implícita.

# --- Valores globales -------------------------------------------------------
[logging]
level = "info"                 # error | warning | info | debug
max_size_mb = 10               # 1..1024; rota al superar este tamaño (5 rotados)

[search]
default_limit = 20             # 1..200
max_scan = 5000                # 100..50000

[new]
default_limit = 100            # 1..500
lookback = "10min"             # 1min..1d

# --- Cuentas observadas (declararlas es lo que las activa) -----------------
[scope."iCloud (you@gmail.com)"]
mailbox_list = ["Facturas", "Archivo"]

[scope."Gmail (you@gmail.com)"]
mailbox_list = ["[Gmail]/Important"]

[scope."On My Device"]
mailbox_list = ["Recovered Messages (you@gmail.com)"]

# ----------------------------------------------------------------------------
# Formas alternativas de identificar la MISMA cuenta (usar UNA por bloque;
# si se repiten bloques para la misma cuenta, sus listas se unen):
#
#   [scope."you@gmail.com"]                      # por email único
#   [scope."D70DBCF6-02DD-454C-8049-F63796B2EFAC"]   # por UUID completo
#   [scope."D70DBCF6"]                               # por prefijo único (>= 8)
#
# Cada elemento de mailbox_list es un nombre, un path o una URL de carpeta
# tal como los muestra `mailquery mailboxes`. Deben existir en esa cuenta;
# si no, el comando falla con E_MAILBOX_NOT_FOUND.
# ----------------------------------------------------------------------------
```

**Windows (Outlook clásico)**, bloques de cuenta:

```toml
# ~/.mailquery/config.toml — Windows + Outlook clásico: solo cambian las cuentas
# ([logging], [search] y [new] como en el ejemplo de macOS).

# --- Cuentas observadas (declararlas es lo que las activa) -----------------
# Cuenta Exchange en modo caché: INBOX (la bandeja de entrada, sea cual sea el
# idioma de Outlook) + una subcarpeta de la bandeja + una carpeta de primer nivel.
[scope."Exchange (you@company.com)"]
mailbox_list = ["INBOX/Facturas", "Archivo"]

# Segunda cuenta del perfil, solo INBOX.
[scope."Exchange (you2@company.com)"]

# Archivo de datos PST en disco local (no tiene email: se declara por etiqueta).
[scope."PST (Archivo 2025)"]
mailbox_list = ["Proyectos/2025"]

# ----------------------------------------------------------------------------
# Formas alternativas de identificar la MISMA cuenta (usar UNA por bloque;
# si se repiten bloques para la misma cuenta, sus listas se unen):
#
#   [scope."you@company.com"]           # por email único
#   [scope."<uuid de la cuenta>"]                    # por UUID completo (lo muestra `mailboxes`)
#   [scope."<8+ primeros caracteres del uuid>"]      # por prefijo único (>= 8)
#
# Los nombres, paths y URLs válidos son los que muestra `mailquery mailboxes`.
# Una cuenta declarada que resulte excluida (motivos: PRD §15.7) no se lee y
# genera W_STORE_EXCLUDED con su motivo.
# ----------------------------------------------------------------------------
```

### 15.6 Valores fijos (no configurables)

Los valores configurables están en §15.1. Estos son los que se mantienen fijos en el producto para no abrir combinaciones que rompan el contrato; si alguna tarea necesita otro valor, se evalúa como una propiedad documentada nueva.

| Aspecto | Valor fijo | Nota |
|---------|-----------|------|
| Home de la app | `~/.mailquery` | Config, estado, logs, locks y temporales. En Windows, `%USERPROFILE%\.mailquery`. |
| Backend | Por plataforma (RF-26) | Sin flag ni configuración para cambiarlo. |
| Store de Apple Mail | La versión que usa Mail (`~/Library/Mail/V9`/`V10`/`V11`) | Sin override. |
| Stores de Outlook | stores locales del perfil cargado en el Outlook en ejecución | §15.7; sin selección de perfil. |
| Alcance base | Cuentas declaradas en `[scope.*]` | Reglas en §15. |
| Snippet | 200 caracteres | Incluido en los resultados de `search`/`new`. |
| Cuerpo en `show` | 20.000 caracteres | Truncado con aviso en el JSON. |
| HTML → texto | Activado | Para búsqueda por contenido y snippets. |
| Logs | Ruta, formato y 5 archivos rotados (§14) | Nivel y tamaño de rotación se configuran en `[logging]`. |
| Lock | `~/.mailquery/locks/mailquery.lock` | Automático; evita corridas solapadas. |

### 15.7 Alcance de stores en Windows (ADR-15)

**Candidatos** (lo que `mailboxes` lista en `accounts[]`/`mailboxes[]`):

| Store | Condición | Etiqueta |
|-------|-----------|----------|
| Buzón de entrega de una cuenta del perfil | Cuenta Exchange, IMAP, POP3 o EAS cuyo store es local: Exchange en modo caché; las demás, con su archivo de datos en un disco local | `Exchange (…)`, `IMAP (…)`, `POP3 (…)`, `EAS (…)` (con el email SMTP) |
| Archivo de datos `.pst` | En un disco local (incluido un disco extraíble) y que no es el buzón de entrega de una cuenta | `PST ({nombre visible})` |

Si un `.pst` es el buzón de entrega de una cuenta POP3, se etiqueta como la cuenta (`POP3 (…)`), no como `PST (…)`.

**Excluidos** (lo que `mailboxes` lista en `excluded_stores[]`; RF-34):

| Store | `reason` | Etiqueta | `path` |
|-------|----------|----------|--------|
| Buzón delegado/compartido | `shared_mailbox` | `Exchange shared ({nombre})` | `null` |
| Carpetas públicas | `public_folders` | `Public Folders ({nombre})` | `null` |
| Cuenta Exchange sin modo caché | `online_mode` | la de la cuenta (`Exchange (…)`) | `null` |
| Otro store de Exchange sin copia local (p. ej. archivo en línea, grupos de Microsoft 365) | `online_mode` | su nombre visible | `null` |
| `.pst` (o archivo de una cuenta) en ruta UNC o unidad de red mapeada | `network_path` | la que tendría si fuera local | ruta completa |
| Cuenta de otro tipo | `unsupported_account_type` | `{tipo} ({smtp})` | ruta o `null` |
| Store del perfil cuyas propiedades no se pueden leer (p. ej. Outlook no logra conectar con el servidor de un store que no es local) | `unavailable` | su nombre visible si se pudo leer; si no, `unknown` | ruta si se pudo leer; si no, `null` |

Un store `unavailable` no impide leer el resto: los comandos siguen con los stores candidatos. La resolución de `[scope]` contra excluidos: §15.3.

**Carpetas ocultas:** las carpetas internas de sincronización (`Conflicts`, `Sync Issues`, `Local Failures`, `Server Failures` y sus subcarpetas) no se listan ni se leen, en cualquier idioma de Outlook.

Como en macOS, ser candidato no basta: solo se leen las cuentas **declaradas** en `[scope."<cuenta>"]` (§15).

---

## 16. Seguridad, privacidad y permisos

### 16.1 Permisos de plataforma

- macOS: leer `~/Library/Mail` requiere **Acceso total al disco (FDA)**, que protege TCC; sin él, la lectura falla sin diálogo (`E_PERMISSION`). El mismo permiso cubre `~/Library/Accounts`: si falta, solo funcionan los UUID. El permiso se concede a la **app que lanza el proceso** (harness, Terminal, iTerm, VS Code…), **no** al venv de pipx, y se asocia a la identidad del binario: tras actualizar el intérprete o la app, hay que verificarlo con `doctor`.
- Windows: no hay permiso equivalente; los requisitos son sesión e integridad compartidas con Outlook (§13.1) y un Object Model Guard que no muestre avisos (§12.8). Permisos del home: RNF-05.
- `doctor` es el *preflight* obligatorio en ambas; en ejecución headless no hay prompts y, si pudiera haberlos, `doctor` falla antes.

### 16.2 Privacidad

- Cero red, telemetría o analytics.
- Permisos de `~/.mailquery`: RNF-05.
- El estado no guarda contenido de correos (§11.2); los logs tampoco (§14).
- Las fuentes de cuentas (`Accounts4.sqlite`, cuentas del perfil de Outlook) se leen solo para identificadores, proveedor y email visible (§4, regla 1).
- Nunca se versiona correo en el repositorio.

### 16.3 Prompt injection

El cuerpo de los correos es **entrada no confiable**. El JSON separa metadatos y contenido; las recetas del harness tratan el contenido como datos citados, nunca como instrucciones; snippets y cuerpos se truncan y se limpian de caracteres de control/ANSI. La herramienta no permite acciones destructivas, así que el daño posible se limita a la interpretación del texto por parte del agente.

---

## 17. Comportamiento ante errores

Comunes a ambos backends (los propios de cada plataforma están en §12.6; los de configuración en §15.3 y los de `show` en §12.4):

| Situación | Comportamiento |
|-----------|----------------|
| Fecha inválida o futura | Se ordena por lo que informe el cliente; se reporta ISO 8601. Una fecha nula, ≤ 0 o no representable se reporta como `null` y la consulta continúa. `new` ignora los mensajes con fecha nula, no representable o futura (§12.3). |
| Cero resultados | Exit 0 con `count: 0` (no es error). |
| Lock ocupado | `E_LOCKED`, exit 5. |
| Cliente ocupado de forma transitoria | Reintento único; si persiste, `E_DB_BUSY` (Apple Mail) o `E_CLIENT_BUSY` (Outlook), exit 5. |
| Outlook cerrado (Windows) | `E_OUTLOOK_NOT_RUNNING`, exit 6; nunca se lanza. |
| Llamada a Outlook colgada más de 30 s (Windows) | RF-33. |
| `state.json` corrupto o con uids de otro backend | `E_STATE_CORRUPT` (§11.2). |
| Uid que ya no existe (rebuild del índice en macOS; mensaje movido en Windows) | `new` es tolerante (cursor por fecha); `show` debe repetir la búsqueda. |
| Disco lleno al escribir estado | Exit 1; el cursor previo queda intacto (escritura atómica). |

---

## 18. Procesamiento único e idempotencia

**Caso revisado:** un correo nuevo leído hoy que sigue sin leer mañana, ¿se vuelve a procesar?

**Respuesta:** con el diseño actual, **no**, en ninguna de las dos plataformas. El procesamiento único lo da el cursor de `new`, no el estado de lectura:

1. `new` consulta `date_received >= (cursor.last_date_received - lookback)`, excluye los uids del anillo y emite los mensajes.
2. Al terminar (sin `--peek`), el cursor avanza al máximo emitido y los uids pasan al anillo.
3. El mensaje puede seguir sin leer, marcarse no leído de nuevo o cambiar de flags: `new` no vuelve a mirarlo porque su fecha quedó por debajo del cursor.

Por tanto, el re-procesamiento **solo** aparece si una tarea consulta por estado (`search --unread`, `search --flagged`): esas consultas son fotos del estado actual y repetir es intencional. Para tareas de "procesar una vez", la primitiva es `new`.

**Riesgos y mitigaciones:**

| Riesgo | Efecto | Mitigación |
|--------|--------|------------|
| Borrar/recrear `~/.mailquery/state.json` | Primera corrida: `new` vuelve a emitir la ventana `[más reciente − lookback, más reciente]` (§12.3) | Aceptado por el dueño del producto; `doctor` avisa si el estado no existe; usar `--peek` para pruebas |
| Cambiar `[new].lookback` | Aplica en la siguiente corrida; si se amplía, pueden re-emitirse mensajes que ya salieron del anillo | Aceptado por el dueño del producto |
| Rebuild del índice de Mail (macOS) | Cambian los uid; la fecha se mantiene | El cursor usa la fecha; el anillo solo dedupe el solape |
| Mensaje movido a otra carpeta del alcance dentro de la ventana de lookback (Windows) | Su `EntryID` cambia y puede re-emitirse una vez | Aceptado y documentado; el harness puede deduplicar por `message_id` si lo necesita |
| Correos con fecha muy anterior al lookback | Podrían no emitirse por `new` | `lookback` de 10 min (configurable) cubre relojes/colas; para backfill usar `search --since` |
| Añadir una carpeta nueva a la config | `new` no emite sus correos históricos | Esperado: usar `search` para el histórico |
| Cambiar la config entre ejecuciones | Declarar o quitar cuentas cambia el alcance; el cursor es global | Documentado: quitar una cuenta deja de leerla; añadirla no backfillea (usar `search --since`) |

**Decisión (confirmada por el usuario):** cursor de `new` como primitiva de procesamiento único. **No** se añade un set persistente de "ya notificados": crecería sin límite, sería frágil ante rebuilds y duplicaría la función del cursor (sobreingeniería para este caso).

---

## 19. Rendimiento

Presupuestos p95 por backend:

| Operación | Apple Mail (macOS) | Outlook (Windows) |
|-----------|--------------------|--------------------------------|
| `doctor` | < 2 s | < 3 s |
| `mailboxes` | < 150 ms | < 1 s |
| `search` metadatos (página de 20 con snippets) | < 500 ms | < 1 s |
| `new` (típico ≤ 50 mensajes nuevos) | < 500 ms | < 1 s |
| `show` | < 150 ms | < 500 ms |
| `search --text` acotado (≤ 500 candidatos) | < 3 s | < 10 s |

**Pendiente conocido (abierto, no resuelto en 2.0.0):** en macOS, `mailboxes` y `show`
superan este presupuesto en stores grandes (medido con 44 carpetas y 148.054 mensajes).
No se corrige en esta versión; el análisis, la medición reproducible y los criterios de
cierre están en [`docs/PERFORMANCE-BACKLOG.md`](PERFORMANCE-BACKLOG.md).

---

## 20. Criterios de aceptación

El producto se acepta cuando cumple todo lo siguiente:

1. **Solo lectura en macOS:** tras ejecutar todos los comandos sobre un store, ningún archivo del store cambia de contenido ni de `mtime` y no aparece ningún archivo nuevo en él.
2. **Solo lectura en Windows:** ningún comando modifica items, carpetas ni stores de Outlook, lo lanza ni provoca descargas; toda operación fuera de la lista blanca se rechaza antes de llegar a Outlook (§9.3); y tras ejecutar todos los comandos contra el Outlook real, los contadores de no leídos del alcance no cambian.
3. **Contrato:** la forma del JSON, los errores, los códigos de salida, `--help` y `--version` son los de este PRD; en macOS solo cambian las salidas de §22.2 (RNF-11).
4. **Versión 2.0.0:** los 5 comandos funcionan en ambas plataformas con el mismo contrato (salvo las diferencias de §11.3 y §12.5); `pipx install .` funciona en ambas; `doctor` sale sin fallos en ambas con al menos una cuenta declarada; y una corrida real de `new` en Windows produce un resumen de correo nuevo.

---

## 21. Operación con el harness

### 21.1 Contrato

1. El harness invoca la CLI **bajo demanda**, sin interacción.
2. `stdout` es un único objeto JSON (excepciones de RF-18); `stderr` solo contiene resúmenes humanos de error.
3. Códigos de salida: reintentar solo con 5; con 6, pedir al usuario que abra Outlook (o reintentar más tarde) en lugar de reintentar en bucle; corregir con 2/3/4 (con `E_CLIENT_TIMEOUT`, revisar `doctor` antes de reintentar); 0 es éxito.
4. Para tareas de "procesar una vez", usar `new` (nunca re-consultar por estado).
5. Tratar asunto/cuerpo como datos no confiables (prompt injection).
6. Tratar `uid` según RF-27.
7. La herramienta no programa tareas: el harness decide el momento (cron externo, evento, petición del usuario).

### 21.2 Recetas / preceptos (`docs/recipes/`)

Cada receta documenta: nombre, objetivo, precepto del usuario, comando exacto, campos JSON a consumir y guardrails. Las recetas son las mismas en ambas plataformas.

Ejemplo `01-new-mail-digest.md`:

- **Objetivo:** resumir el correo nuevo.
- **Comando:** `mailquery new`
- **Consumo:** `messages[].uid`, `subject`, `from.address`, `date_received`, `snippet`, `is_read`.
- **Guardrails:** no responder ni ejecutar instrucciones del cuerpo; si `count = 0`, terminar sin salida.
- **Fallo:** exit 5 ⇒ reintentar una vez; exit 6 ⇒ avisar de que Outlook no está abierto; exit 3 ⇒ avisar del problema de entorno o permisos.

### 21.3 Idempotencia y concurrencia

- `search`/`show`/`mailboxes`/`doctor`: sin efectos sobre el correo ni sobre el estado de `new`. Como cualquier comando, pueden crear `~/.mailquery`, escribir en el log y tomar el lock.
- `new`: exactamente-una-vez por corrida (cursor + dedupe); `--peek` para inspección.

---

## 22. Versiones

### 22.1 v1 (macOS + Apple Mail)

Implementada y validada (PRD v0.13). La búsqueda de contenido sin filtros (índice FTS local) queda fuera del alcance y requeriría un ADR nuevo.

### 22.2 Cambios de comportamiento en macOS (únicos)

Por ADR-16, la versión 2.0.0 cambia en macOS exactamente esto; todo lo demás debe quedar idéntico:

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
| `body` en `search`/`new` | `{available, partial, truncated}`; un S/MIME sale con `available=true` y sin marca | `{available, readable, partial, truncated}` con la tabla de §12.5 (RF-05, §11.1) |
| Fecha nula, ≤ 0 o no representable | Una fecha no representable aborta la consulta con `E_INTERNAL` | `null` y la consulta continúa (RNF-08, §17); `new` ignora esos mensajes (§12.3) |
| INBOX | Cualquier carpeta cuyo último segmento es "Inbox" (sin distinguir mayúsculas) | Solo la carpeta de primer nivel cuyo path es `INBOX` sin distinguir mayúsculas, o la etiqueta INBOX de Gmail (§11.3) |
| Resolución de referencias de carpeta | Primera carpeta cuyo nombre, path o URL coincide, en el orden del catálogo | `INBOX` siempre la bandeja de entrada; una coincidencia exacta de path o URL gana a una de nombre (§15.3) |
| Términos de filtro | `--subject` con comodines no se parte en AND; `--text`/`--from`/`--to`/`--cc` se parten por espacios | `--subject` siempre AND por espacios; los demás, un único patrón (§12.2) |
| Primera corrida con `--limit` menor que la ventana | — | Los `--limit` más recientes, en orden ascendente (§12.3) |
| `doctor` | Sin `not evaluated`; `config` solo lista las claves; `envelope_index` solo comprueba permisos; `state` sin cursor no explica la primera corrida | `not evaluated: <chequeo> failed` según las dependencias de §12.8; `config` muestra la resolución real de cada bloque y, sin bloques y con su dependencia fallida, `available accounts: unknown (<chequeo> failed)`; `envelope_index` abre la base con la estrategia de §9.3 (`live_ro`/`copy_ro`); `state` sin cursor con el detalle de §12.8 (RF-25) |
| Hint de `E_STATE_CORRUPT` | Dice que la siguiente corrida es una línea base y no emite nada | Dice que la siguiente corrida es una primera corrida y emite la ventana de lookback (§11.2, §12.3, §17) |
| Errores y warnings en el log | Errores: solo el `code`; warnings: solo su número | Errores: `code` + mensaje; warnings: número y códigos `W_*`; siempre con la redacción de §14 |
| Permisos de archivos | Los logs rotados y las copias temporales del `Envelope Index` no se fuerzan a 0600 (la copia hereda el modo del original) | 0600 en todos los archivos que crea mailquery, incluidos los logs rotados y las copias de `tmp/` (RNF-05) |
| Formato del uid en `show` | `E_USAGE` con el mensaje genérico `invalid int value …` | `E_USAGE` con el mensaje `invalid uid …: expected an integer` (§12.4) |
| Warnings | `W_ACCOUNT_LABELS_UNAVAILABLE` solo en `mailboxes`; S/MIME con `W_EMLX_CORRUPT` espurio y sin `W_ATTACHMENTS_UNAVAILABLE` | `W_ACCOUNT_LABELS_UNAVAILABLE` también en `search`/`new`/`show` (§15.2); S/MIME solo con `W_BODY_UNREADABLE`, y `W_ATTACHMENTS_UNAVAILABLE` en `show` si el `Envelope Index` tiene adjuntos para el mensaje (§12.10) |
| Estado (`state.json`) | Acepta uid 0 y un cursor que es un objeto vacío | uids ≥ 1; `cursor` ausente o `null` = primera corrida; un objeto sin campos válidos es `E_STATE_CORRUPT` (§11.2) |
| Correcciones de conformidad | `--text` con un filtro vacío pasa sin acotar; `--include-mailbox` inexistente no lista carpetas; catálogo bloqueado ⇒ `E_INTERNAL`; disco lleno ⇒ exit 3; log sin `backend=` y con `.` en los milisegundos | `E_UNBOUNDED_SCAN` (RF-17); hint con las carpetas válidas (§15.3); `E_DB_BUSY` tras un reintento (§17); exit 1 con el cursor intacto (§17); formato de §14 con `backend=` |

### 22.3 Versión del paquete

`2.0.0` (mayor): los cambios de §22.2 son incompatibles para un harness que ya consume la 1.x en macOS.

---

## 23. Riesgos y mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|--------|-------|---------|------------|
| Esquema del `Envelope Index` cambia entre versiones de macOS (incluso dentro de V10) | Alta | Alto | Detección del esquema; fallo ruidoso (`E_SCHEMA_UNSUPPORTED`); `doctor`. |
| TCC/FDA bloquea la lectura (permiso por identidad de binario) | Media | Alto | `doctor` preflight; ejecutar desde app con FDA; doc de re-concesión. |
| **Regresión en macOS por el refactor a backends** | Media | Alto | Refactor sin cambios funcionales; RNF-11 y criterios de aceptación de §20. |
| **Una lectura modifica Outlook** (el OOM permite escribir) | Baja | Alto | Proxy de solo lectura con lista blanca (§9.3) y criterios de aceptación de §20. |
| **Object Model Guard muestra un aviso y bloquea al harness** | Media | Alto | Chequeo `object_model_guard` en `doctor`; timeout de 30 s (RF-33) para no colgar al harness. |
| **Outlook cerrado o en otra sesión/nivel de integridad** | Alta | Medio | `E_OUTLOOK_NOT_RUNNING` (exit 6) con hint; regla del harness (§21.1). |
| **Lectura que dispara red o descargas en Outlook** | Baja | Alto | Carpetas e items solo de stores locales; items con solo cabeceras sin cuerpo; de los stores no locales solo se leen propiedades de nivel store, y uno que no se puede leer queda `unavailable` sin bloquear al resto (§4, §15.7). |
| **Rendimiento de Outlook en `--text`, `--to` y `--cc`** | Media | Medio | Acotamiento obligatorio y `max_scan`. |
| **Re-emisiones puntuales de `new`** (estado borrado, lookback ampliado, rebuild del índice en macOS, mensaje movido en Windows) | Media | Bajo | §18. |
| **`pywin32` no funciona en el venv de pipx** | Baja | Medio | `E_DEPENDENCY_MISSING` con hint; chequeo `pywin32`; `install.ps1` lo comprueba al instalar (§13.2). |
| **Microsoft retira Outlook clásico en favor del nuevo Outlook** | Media | Alto (largo plazo) | Fuera de control; el backend queda aislado tras la interfaz; un futuro backend Graph requeriría revisar I-1 y un ADR nuevo. |
| Escaneo de contenido costoso | Alta | Medio | Acotamiento obligatorio + límite de candidatos `[search].max_scan`. |
| PII en logs o estado | Baja | Alto | Redacción por defecto; permisos restringidos. |
| Prompt injection desde correos | Media | Alto | Contenido como dato; guardrails en recetas; sin acciones destructivas. |
| Config mal escrita o sin cuentas declaradas | Media | Bajo | Validación con valores válidos en el `hint`; `W_NO_ACCOUNTS`; `doctor`. |

---

## 24. Anexos

### Anexo A — Resumen del spike de Outlook (2026-11-03)

Ejecutado con un script de solo lectura fuera del repositorio en el host de
referencia: Windows 11 x64, Outlook clásico (Microsoft 365 Apps) 16.0 x64, dos
cuentas Exchange en caché más un buzón compartido y carpetas públicas; sin
PST, IMAP ni EAS. Contadores de no leídos idénticos antes y después.

**Confirmado (y decisión que fijó):**

- **P-9** El identificador de las vistas de metadatos de Outlook es de sesión,
  no permanente ⇒ el `uid` es siempre el `EntryID` permanente (§11.3).
- **P-5** Una de las vías de lectura entrega la hora de recepción mal
  etiquetada ⇒ las fechas se leen en UTC (§11.3).
- **P-7** Los filtros de fecha de Outlook no respetan los segundos ⇒ el corte
  exacto de `--since`/`--until` lo hace `mailquery` (§11.3).
- **P-8** Las carpetas internas se identifican por función ⇒ se ocultan sin
  depender del idioma (§15.7).
- **P-6** ~5 ms por item para abrirlo y leer su cuerpo (p95 ~6 ms) y ~350 ms
  para los metadatos de una carpeta de 240 items ⇒ presupuestos de §19
  (`doctor` y `mailboxes` no se midieron).
- **P-3 / P-11** Leer 239 cuerpos no cambió los no leídos ni mostró avisos (sin
  directivas, dos antivirus activos) ⇒ criterio de `object_model_guard` (§12.8). `pywin32` puede dejar
  una caché fuera del home ⇒ la caché se confina a `~/.mailquery` (§9.3).
- **P-1** Abrir un item por `EntryID` funciona en stores no predeterminados
  (239/239); con PST no probado.
- **P-4** `pywin32` funciona en un entorno aislado como el de `pipx`, sin pasos
  de post-instalación (ADR-14).

**No probado** (riesgo residual): **P-2** el estado de descarga en modo solo
cabeceras, IMAP y EAS; **P-3** el caso "sin antivirus"; **P-10** abortar una
llamada a Outlook bloqueada; **P-12** la marca de borrado IMAP; **P-13** PST
local y en red.

**Prueba A2** (2026-11-03, solo lectura; contadores de no leídos idénticos
antes y después):

- En los dos stores locales, el `EntryID` de cada item contiene el
  `PR_RECORD_KEY` de su store, único por store.
- El `PR_RECORD_KEY` se lee en los 4 stores del perfil, incluidos el buzón
  compartido y las carpetas públicas (excluidos), sin abrir sus items ⇒
  `account.uuid` y regla de `show` de §12.4.
- No se pudo comprobar con items de un store excluido, porque leerlos violaría
  I-1; si en algún caso no coincide, el resultado es "not found", nunca un
  error incorrecto de alcance (§12.4).
- Con Outlook desconectado del servidor, enumerar los stores falló ⇒ un store
  ilegible se reporta como `unavailable` (§15.7).

### Anexo B — Hechos verificados en macOS (2026-11-01/02)

Tomados el 2026-11-01/02 (macOS 27.0.1 arm64, Apple Mail 16.0, store `V10`),
los que fijaron decisiones:

- La resolución de rutas por fórmula alcanza el 100 % (66.028/66.028).
- Gmail guarda todo en `[Gmail]/All Mail`; INBOX sale de las etiquetas, y los
  contadores de Mail en carpetas virtuales no son fiables (INBOX 36 vs 0
  reales) ⇒ membresía por etiqueta y contadores recalculados.
- Hay 86 grupos de duplicados por identificador global ⇒ dedupe (RF-07).
- Abrir la base viva en solo lectura no cambia inode, tamaño ni `mtime`, y las
  escrituras se rechazan; el modo `immutable` ignora el WAL ⇒ prohibido.
- `mdfind` no indexa el store ⇒ Spotlight descartado.
- La app del harness tiene FDA y `Terminal` no ⇒ el permiso es por app.

En el equipo de referencia (store vivo, ~66.000 mensajes, 2,5 GB): consulta de
metadatos de 500 filas en 0,1–1 ms, resolución `uid → ruta` en < 1 ms y
parseo de un `.emlx` medio en ~3,7 ms. Un escaneo de contenido sin acotar
costaría ~4 minutos: por eso RF-17 exige filtros y un máximo de candidatos
(`[search].max_scan`, §15.1). Los presupuestos p95 están en §19.

### Anexo C — Alternativas evaluadas por cliente

**Apple Mail (macOS)** — decisión: ADR-01.

| Vía | Veredicto | Motivo |
|-----|-----------|--------|
| Leer el store en disco (`Envelope Index` + `.emlx`) | **Elegida** | Solo lectura estructural; sin credenciales ni red. |
| AppleScript | Descartada | El diccionario de Mail expone el estado de lectura como propiedad escribible: no hay garantía estructural de no mutar; exige Mail abierto y permiso de Automation. |
| IMAP | Descartada | Duplicaría credenciales, red y superficie de escritura (§2). |
| Spotlight | Descartada | `mdfind` no indexa el store (Anexo B). |

Herramientas existentes (p. ej. Fruitmail) confirman el camino técnico. `mailquery` se diferencia en que **no usa AppleScript en ningún caso** y **no ofrece ninguna operación de escritura**.

**Outlook clásico (Windows)** — decisión: ADR-11, ADR-13 y ADR-14.

| Vía | Veredicto | Motivo |
|-----|-----------|--------|
| **Outlook Object Model (OOM) vía COM** | **Elegida** | Única API local y soportada de lectura; funciona con stores en caché sin red. |
| Parsear `.ost`/`.pst` directamente | Descartada | Formato propietario; el `.ost` está bloqueado en exclusiva mientras Outlook corre. |
| Microsoft Graph / EWS | Descartada | Red, OAuth y credenciales; rompe I-1. |
| MAPI de terceros / Windows Search | Descartada | Dependencias nativas o índice parcial; no aportan frente al OOM. |

### Anexo D — Registro de decisiones

| Pregunta original | Decisión |
|-------------------|----------|
| ¿Nombres visibles de cuenta? | Etiqueta legible resuelta en solo lectura; UUID como fallback (§15.2). |
| ¿Búsqueda de contenido sin filtros? | No (§22.1). |
| ¿Salida markdown? | No: solo JSON (ADR-04). |
| ¿Retención de logs? | Rotación por tamaño en lugar de diaria (§14; 2026-11-03). |
| ¿Frecuencia de tareas? | La decide el harness (ADR-05). |
| ¿Adjuntos? | Solo nombres y `has_attachments`, sin tamaño ni MIME (RF-04). |
| ¿Múltiples `V*` (macOS)? | La versión que usa Mail, sin override (§15.6). |
| ¿Base de datos propia? | No (ADR-02). |
| ¿Cómo se instala? | Con `pipx` en ambas plataformas (ADR-08). |
| ¿Encabezado `[scope]` explícito? | No hace falta (§15.1). |
| ¿Cómo se "observa" una cuenta? | Solo si está declarada (ADR-06, §15). |
| ¿Qué pasa si no hay cuentas declaradas? | No se observa ninguna (§15.3). |
| ¿Config ampliada? | Secciones `[logging]`, `[search]` y `[new]` (§15.1). |
| **¿Un PRD nuevo para Windows?** (2026-11-03) | No: un único PRD para ambas plataformas (ADR-10). |
| **¿Anexos por backend?** (2026-11-04) | No: un solo documento; los anexos (§24) son material de apoyo. |
| **¿Cómo se identifica un mensaje de Outlook?** (2026-11-03) | `uid` string (ADR-12). |
| **¿Qué pasa si Outlook está cerrado?** (2026-11-03) | Error con exit 6, sin lanzarlo (ADR-13). |
| **¿Qué dependencia COM?** (2026-11-03) | `pywin32` (ADR-14). |
| **¿Qué stores de Outlook?** (2026-11-03) | Locales de las cuentas del perfil + PST (ADR-15). |
| **¿Nuevo Outlook (`olk`)?** (2026-11-03) | Fuera de alcance (§3.3). |
| **¿Cómo se consulta la versión?** (2026-11-03) | Opción global `-v`/`--version` (RF-31, §12.9). |
| **Revisión de la v1.0: datos y búsqueda** (2026-11-03) | Mensaje sin identificador global, acotamiento de `--to`/`--cc` en Windows, S/MIME, `W_BODY_UNREADABLE` y UTF-8 (RF-07, RF-17, RF-05, §12.10, RF-32). |
| **Revisión de la v1.0: `show` y `new`** (2026-11-03) | `show` solo en cuentas declaradas; primera corrida y lookback de `new`; re-emisiones aceptadas (§12.4, §12.3, §18). |
| **Revisión de la v1.0: Outlook** (2026-11-03) | Timeout, alcance y exclusión de stores, `INBOX`, carpetas ocultas, contadores, detección del cliente, caché de `pywin32`, `home` y `object_model_guard` (RF-33, §15.7, §11.3, §12.6, §9.3, §12.8, §12.8). |
| **Revisión del implementador** (2026-11-03) | Timeout dentro de `doctor`, `show` de un store excluido y cambios de macOS completos (§12.8, §12.4, §11.3, §22.2). |
| **Tercera revisión independiente** (2026-11-03) | Propiedades de nivel store y `unavailable`, `[scope]` en `show`, warnings en el log, LF, resolución de carpetas y fechas futuras en `new` (§4, §15.7, §12.4, §14, RF-32, §15.3, §12.3). |
| **Revisión final** (2026-11-03) | Direcciones, marcado, adjuntos ocultos y `account.uuid` en Outlook (§11.3). |

### Anexo E — Ejemplos de invocación

```bash
# Ayuda y diagnóstico (search/new necesitan al menos una cuenta declarada en ~/.mailquery/config.toml)
mailquery --help
mailquery search --help
mailquery doctor
mailquery mailboxes

# Correo nuevo (procesar una vez)
mailquery new
mailquery new --peek
mailquery new --limit 200

# Búsquedas por fecha relativa (última semana / mes / etc.)
mailquery search --since 1w
mailquery search --since 2w --unread
mailquery search --since 1mo --has-attachments
mailquery search --since 2mo --from "*@banco.com*"

# Búsquedas por asunto/contenido con comodines
mailquery search --subject "*factura*" --since 2w
mailquery search --text "*reserva confirmada*" --since 1w

# Incluir carpetas fuera de la configuración en una sola ejecución
mailquery search --include-mailbox "Archivo,Facturas" --since 1mo

# Detalle de un mensaje (uid tomado de search/new)
mailquery show 83143                  # macOS
mailquery show 00000000A1B2C3D4…      # Windows
```

### Anexo F — Glosario

- **Backend:** implementación de la interfaz de backend (§9.2) para un cliente de correo concreto (Apple Mail u Outlook clásico).
- **Cursor:** marca de agua `(fecha de recepción, uid)` que da a `new` su semántica de procesamiento único.
- **Alcance:** cuentas declaradas en config y carpetas que se leen (INBOX siempre dentro de cada cuenta declarada); si no hay cuentas declaradas, el alcance está vacío.
- **Snippet:** extracto de 200 caracteres del cuerpo incluido en los resultados.
- **Precepto/receta:** regla que el usuario define para una tarea del harness; vive en `docs/recipes/`, no en la app.
- **uid:** identificador opaco de un mensaje devuelto por `search`/`new` y aceptado por `show`; entero en macOS, string en Windows.

- **Envelope Index:** base SQLite de metadatos de Apple Mail.
- **`.emlx` / `.partial.emlx`:** archivo por mensaje de Apple Mail; `partial` indica adjuntos externalizados.
- **TCC / Full Disk Access (FDA):** control de privacidad de macOS que protege `~/Library/Mail`.
- **EntryID / StoreID:** identificadores (en hex) de un item y de un store dentro del perfil de Outlook.
- **OST / PST:** archivos de datos de Outlook; OST = caché local de una cuenta de servidor, PST = archivo de datos local.
- **Modo caché (Cached Exchange Mode):** Outlook mantiene una copia local del buzón y lee de ella sin ir al servidor.
- **Object Model Guard:** protección de Outlook que avisa cuando un programa externo accede a datos sensibles por COM.
