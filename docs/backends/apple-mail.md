# Backend Apple Mail (macOS) — anexo del PRD

**Documento padre:** [`docs/PRD.md`](../PRD.md) v1.2, que manda sobre este anexo.
**Plataforma:** macOS con Apple Mail.
**Estado:** implementado y validado (contenido trasladado desde el PRD v0.13).

Este anexo reúne lo específico del backend Apple Mail: cómo se cumple el
invariante I-1, cómo se localiza y lee el store, las reglas del modelo de datos
de origen y los permisos de macOS. Lo común a todas las plataformas (CLI,
contrato JSON, configuración, cursor, errores) vive en el PRD.

> **Regla de compatibilidad:** PRD RNF-11.

---

## A.1 Contexto y alternativas descartadas

- AppleScript: el diccionario de Mail expone el estado de lectura como
  propiedad escribible; no hay garantía estructural de no mutar, y exige Mail
  abierto y permiso de Automation.
- IMAP: PRD §2.
- Spotlight: `mdfind` no indexa el store (§A.11).

Herramientas existentes (p. ej. Fruitmail) confirman el camino técnico.
`mailquery` se diferencia en que **no usa AppleScript en ningún caso** y **no
ofrece ninguna operación de escritura**.

**Decisión:** ADR-01 (PRD §8).

---

## A.2 Cómo se cumple el invariante I-1 en macOS

Concreción del invariante general (PRD §4):

> `mailquery` no escribe, renombra, mueve, trunca, toca fechas ni borra ningún
> archivo dentro de `~/Library/Mail`. No lanza Mail.app. No ejecuta
> AppleScript/osascript sobre Mail. No abre conexiones IMAP/SMTP.

Además del store de Mail, la única otra base que se abre es
`~/Library/Accounts/Accounts4.sqlite` (solo lectura, para etiquetas de cuenta);
nunca se escribe en ella (lectura de cuentas: PRD §4).

Garantía **estructural** (la impone el sistema, no solo el código):

1. Las bases SQLite se abren en modo solo lectura y con escrituras
   deshabilitadas; los `.emlx` se abren solo para lectura.
2. Si Mail está cerrado, no se abre la base viva: se copia a
   `~/.mailquery/tmp/` y se lee la copia (evita que SQLite cree archivos dentro
   del store) (§A.4).

Leer un `.emlx` no toca el estado de Mail: el flag de lectura vive en el
`Envelope Index` y `mailquery` nunca lo modifica. Criterio de aceptación: §A.10.

---

## A.3 Localización de los mensajes

- La versión del store (`V9`/`V10`/`V11`) se toma de la que usa Mail
  (`PersistenceInfo.plist`), validando el esquema.
- La ruta de cada `.emlx` se obtiene a partir de la carpeta y el uid, sin
  escanear el store (§A.11); si el archivo no existe, `body.available=false` + `W_EMLX_MISSING`.
- Los `.emlx` sin fila en el índice (huérfanos) se ignoran.
- `.partial.emlx` no es un stub: el mensaje está completo salvo los adjuntos
  externalizados; se lee tal cual y se marca `partial=true`. De los adjuntos
  solo se reportan nombres; nunca se leen.

---

## A.4 Conexión SQLite read-only y WAL

El `Envelope Index` está en WAL. **No es necesario que Mail.app esté abierto**.

| Situación | Estrategia |
|-----------|-----------|
| Mail abierto (existe el `-shm`) | Abrir la base viva en solo lectura. Estrategia `live_ro`. |
| Mail cerrado (no existe el `-shm`) | Copiar la base (y su WAL) a `~/.mailquery/tmp/` y abrir la copia. Estrategia `copy_ro`. |
| Base bloqueada | Reintentar una vez tras 100 ms; si persiste, `E_DB_BUSY` (exit 5). |

Se prohíbe el modo `immutable` sobre la base viva: ignora el WAL y devolvería
datos obsoletos (§A.11).

---

## A.5 Modelo de datos de origen

### A.5.1 `Envelope Index` (solo lectura)

Reglas que determinan el comportamiento observable (verificadas en el equipo
de referencia):

- Membresía de carpeta = carpeta física **o** etiqueta: en Gmail todo el correo
  está físicamente en `[Gmail]/All Mail` y la pertenencia a INBOX y demás
  etiquetas sale de la tabla de etiquetas.
- Los contadores que guarda Mail no son fiables en carpetas virtuales: `total`
  y `unread` se recalculan.
- Estado leído/marcado/borrado desde sus columnas dedicadas; los borrados no
  son buscables.
- No hay cuerpos en la base: el contenido **siempre** se lee del `.emlx`.
- Fechas en segundos Unix.
- Las columnas obligatorias se detectan al abrir; si falta
  alguna, `E_SCHEMA_UNSUPPORTED`.

### A.5.2 Etiquetas de cuenta (`Accounts4.sqlite`, solo lectura)

Los UUID de cuenta del store de Mail coinciden con los identificadores de
`~/Library/Accounts/Accounts4.sqlite`. Reglas:

- Etiqueta: cuenta IMAP/Exchange → `"{proveedor} ({email})"`, con proveedor y
  email de la cuenta padre (p. ej. `iCloud (…)`, `Gmail (…)`). Cuenta local →
  `"On My Device"`. Si no hay email, se usa la descripción disponible.
- Si la base o su esquema no están disponibles, las etiquetas quedan
  deshabilitadas y solo funciona el UUID: `doctor` lo advierte con
  `accounts_db` en fallo y los comandos de datos añaden
  `W_ACCOUNT_LABELS_UNAVAILABLE`.

**Decisión:** ADR-09 (PRD §8).

### A.5.3 Correspondencia con el modelo común

| Concepto común (PRD §11) | Apple Mail |
|--------------------------|------------|
| `uid` | id de fila del mensaje en el `Envelope Index` (**entero**) |
| `message_id` | Message-ID RFC del mensaje |
| Clave de dedupe | `messages.global_message_id`, el identificador global de Mail; NULL o 0 ⇒ mensaje único (RF-07) |
| `account.uuid` | authority de la URL de carpeta (= identificador en `Accounts4.sqlite`) |
| `mailbox.url` | URL de la carpeta (`imap://…`, `local://…`) |
| INBOX | carpeta de primer nivel cuyo path es `INBOX` sin distinguir mayúsculas, o la etiqueta INBOX en Gmail |
| Buzón agregado | path que contiene `all mail` (`[Gmail]/All Mail`) |
| Cuerpo / `body.partial` | `.emlx` / `.partial.emlx` |
| `source.emlx_path` | ruta absoluta del `.emlx` |

---

## A.6 Permisos: TCC / Full Disk Access

- Leer `~/Library/Mail` requiere **Acceso total al disco (FDA)**; sin él, la
  lectura falla sin diálogo (`E_PERMISSION`). El mismo permiso cubre
  `~/Library/Accounts`: si falta, solo funcionan los UUID.
- El permiso se concede a la **app que lanza el proceso** (harness, Terminal,
  iTerm, VS Code…), **no** al venv de pipx, y se asocia a la identidad del
  binario: tras actualizar el intérprete o la app, verificar con `doctor`.

---

## A.7 `doctor` en macOS

Chequeos: PRD §12.8.

| Chequeo | Qué valida |
|---------|------------|
| `store` | Versión `V*` detectada y ruta del store. |
| `envelope_index` | Existe y se abre con la estrategia de §A.4 (`live_ro`/`copy_ro`), nunca de otra forma (FDA). |
| `schema` | Están todas las tablas/columnas obligatorias. |
| `readonly_strategy` | `live_ro` o `copy_ro` (§A.4). |
| `accounts_db` | `Accounts4.sqlite` legible y número de etiquetas disponibles. |

Dependencias (regla: PRD §12.8):

- `store` → `envelope_index`;
- `envelope_index` → `schema` y `readonly_strategy`;
- `schema` → resolución de bloques de `config`.
- `python`, `home`, `accounts_db`, `state` y `lock` no dependen de otro
  chequeo.

---

## A.8 Casos límite específicos

| Situación | Comportamiento |
|-----------|----------------|
| Store ausente o versión no soportada | `E_STORE_NOT_FOUND` / `E_SCHEMA_UNSUPPORTED`, exit 3, con rutas/versión detectada. |
| `.emlx` ausente, corrupto o ilegible, S/MIME o mensaje sin carpeta | Valores de `body` y warning: PRD §12.5. |

---

## A.9 Rendimiento medido

En el equipo de referencia (store vivo, ~66.000 mensajes, 2,5 GB): consulta de
metadatos de 500 filas en 0,1–1 ms, resolución `uid → ruta` en < 1 ms y
parseo de un `.emlx` medio en ~3,7 ms. Un escaneo de contenido sin acotar
costaría ~4 minutos: por eso RF-17 exige filtros y un máximo de candidatos
(`[search].max_scan`, PRD §15.1). Los presupuestos p95 están en PRD §19.

---

## A.10 Criterio de aceptación de solo lectura

Tras ejecutar todos los comandos sobre un store, ningún archivo del store cambia
de contenido ni de `mtime` y no aparece ningún archivo nuevo en él.

---

## A.11 Hechos verificados en el equipo de referencia

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

---

## A.12 Glosario específico

- **Envelope Index:** base SQLite de metadatos de Mail.
- **`.emlx` / `.partial.emlx`:** archivo por mensaje; `partial` indica adjuntos
  externalizados.
- **WAL:** journaling de SQLite; contiene cambios aún no consolidados.
- **TCC / Full Disk Access:** control de privacidad de macOS que protege
  `~/Library/Mail`.
