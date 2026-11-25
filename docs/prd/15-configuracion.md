---
aliases: ["Sección 15", "Configuración"]
tags: [prd]
---

## 15. Configuración

**Archivo:** `~/.mailquery/config.toml` — **opcional** e idéntico en ambas plataformas. Es el único archivo de configuración: no hay flags de ruta ni variables de entorno.

**Reglas generales** (esta sección es la dueña de las reglas de alcance):

- Solo se admiten las claves documentadas; cualquier clave o sección desconocida ⇒ `E_CONFIG_INVALID` (exit 2), para que un typo no pase desapercibido.
- La aplicación **nunca** modifica este archivo.
- **Solo se buscan, emiten y muestran mensajes de las cuentas declaradas**: cada bloque `[scope."<driver>:<cuenta>"]` declara una cuenta observada (el prefijo `<driver>:` es opcional; sin él, el driver nativo, §15.2); las cuentas sin bloque quedan excluidas (`mailboxes` las lista con `included: false`).
- El alcance de una cuenta declarada es su INBOX más las carpetas de `mailbox_list` (aditivas; un bloque sin `mailbox_list` observa solo INBOX). Si la cuenta no tiene INBOX (p. ej. un PST de archivo), se observan solo las carpetas de `mailbox_list`, sin error.
- Si dos bloques resuelven a la misma cuenta, se combinan (unión sin duplicados).
- Sin ningún bloque `[scope.*]` (o sin archivo) no se observa ninguna cuenta: §15.3.
- **Precedencia**: flags de CLI > `config.toml` > defaults del producto.
- Un plugin externo puede tener su propia configuración en `~/.mailquery/<driver>.toml`; la gestiona el plugin y el núcleo no la lee ni la valida (RF-37).

### 15.1 Tabla de propiedades configurables

**Tabla: Propiedades configurables**

| Propiedad | Tipo | Obligatoria | Default | Valores válidos | Ejemplo | Qué hace |
|-----------|------|-------------|---------|-----------------|---------|----------|
| `[logging]` | tabla TOML | No | — | — | `[logging]` | Sección de logging. |
| `logging.level` | string | No | `"info"` | `error`, `warning`, `info`, `debug` | `"debug"` | Nivel mínimo del log; `--log-level` lo sobrescribe. |
| `logging.max_size_mb` | entero | No | `10` | 1–1024 | `50` | Tamaño en MB a partir del cual se rota el log; se conservan 5 archivos rotados (§14). |
| `logging.json` | booleano | No | `false` | `true`, `false` | `true` | `true` escribe el log en JSON Lines en `mailquery.jsonl` en lugar de `mailquery.log` (§14, RF-88). |
| `[search]` | tabla TOML | No | — | — | `[search]` | Defaults de búsqueda. |
| `search.default_limit` | entero | No | `20` | 1–200 | `50` | Límite por defecto de `search`; `--limit` lo sobrescribe; no aplica con `--group-by` (RF-70). |
| `search.max_scan` | entero | No | `5000` | 100–50000 | `10000` | Candidatos máximos al leer contenido: `--text` y, en Windows, `--to`/`--cc` (RF-15). |
| `[new]` | tabla TOML | No | — | — | `[new]` | Defaults de `new`. |
| `new.default_limit` | entero | No | `100` | 1–500 | `200` | Límite por defecto de `new`; `--limit` lo sobrescribe. |
| `new.lookback` | string | No | `"10min"` | duración (`min`, `h`, `d`), 1 min–1 día | `"15min"` | Solape del cursor al buscar mensajes nuevos. |
| `[attachments]` | tabla TOML | No | — | — | `[attachments]` | Configuración de recuperación local de adjuntos. |
| `attachments.enabled` | booleano | No | `true` | `true`, `false` | `false` | Habilita o deshabilita `mailquery attachment`. |
| `attachments.max_file_size_mb` | entero | No | `100` | 1–500 | `100` | Tamaño máximo por adjunto, en MB (1 MB = 1.048.576 bytes). |
| `attachments.max_total_size_mb` | entero | No | `200` | 1–1024 (`>= max_file_size_mb`) | `200` | Tamaño máximo acumulado por ejecución. Un valor menor que `max_file_size_mb` ⇒ `E_CONFIG_INVALID`. |
| `attachments.max_count` | entero | No | `50` | 1–500 | `20` | Máximo de adjuntos de `attachment --all` (incluye aciertos de caché). No aplica a `--index`. |
| `attachments.timeout_seconds` | entero | No | `60` | 10–600 | `180` | Segundos máximos para leer cada adjunto en `mailquery attachment`, en cualquier driver; al vencer, `E_CLIENT_TIMEOUT` (RF-49). |
| `[content]` | tabla TOML | No | — | — | `[content]` | Presentación del contenido no confiable. |
| `content.url_display` | string | No | `"neutralize"` | `"neutralize"`, `"keep"`, `"strip"` | `"keep"` | Modo de visualización de URLs en el asunto, los nombres de remitente y destinatarios, `headers`, `body_text` y `snippet`; `--strip-links` lo sobrescribe. |
| `[lock]` | tabla TOML | No | — | — | `[lock]` | Reintento del lock de ejecución ocupado (RF-89). |
| `lock.retries` | entero | No | `5` | 0–10 | `3` | Reintentos después del primer intento cuando el lock de ejecución está ocupado; `0` = un solo intento (RF-89). |
| `lock.initial_delay_ms` | entero | No | `150` | 10–5000 | `100` | Pausa en milisegundos antes del primer reintento (RF-89). |
| `lock.backoff_factor` | número (entero o decimal) | No | `2` | 1–10 | `1.5` | Factor por el que crece cada pausa respecto de la anterior; con `1`, todas las pausas son iguales. Ninguna pausa pasa de 5000 ms (§15.6, RF-89). |
| `[scope."<driver>:<cuenta>"]` | tabla TOML | No | `<driver>` nativo del SO | `<driver>`: `[a-z0-9_]{1,64}` instalado; `<cuenta>`: etiqueta/email/UUID de un backend interno o identificador opaco del plugin (resuelto dentro del driver) | `[scope."apple_mail:you@icloud.com"]` | Declara una cuenta observada y su driver. Si se omite `<driver>:`, usa el nativo del SO. |
| `mailbox_list` | array de strings | No | `[]` | `path` de carpeta tal como aparece en `mailquery mailboxes`, su nombre o su URL (`mailboxes --fields name,url`), o `INBOX`; case-insensitive (resolución: §15.3) | `["Facturas", "[Gmail]/Important"]` | Carpetas adicionales a INBOX para esa cuenta. |

El namespace `scope` es obligatorio en la ruta de las claves, pero **no hace falta escribir un encabezado `[scope]` vacío**: `[scope."<cuenta>"]` crea la tabla padre implícitamente. Las tablas de cuenta en el nivel superior no se admiten.

Dentro de un bloque `[scope."<cuenta>"]` la única clave es `mailbox_list`. Todo lo que no aparece en esta tabla son valores fijos del producto (§15.6).

### 15.2 Identificador de cuenta

La clave de cada bloque se divide en el **primer** `:`: la parte izquierda es el driver (`[a-z0-9_]{1,64}`, instalado) y la derecha, la cuenta dentro de ese driver; sin prefijo se usa el driver nativo del SO (RF-34). Para los backends internos se aceptan tres formas, en este orden de resolución:

1. **Etiqueta legible** mostrada por `mailquery mailboxes` (`account.label`), p. ej. `"iCloud (you@icloud.com)"`, `"Gmail (you@gmail.com)"`, `"On My Device"` (macOS) o `"Exchange (you@company.com)"`, `"PST (Archivo 2025)"` (Windows).
2. **Email** de la cuenta si es único (p. ej. `"you@gmail.com"`).
3. **UUID** completo o prefijo único de ≥ 8 caracteres (siempre válido, aunque las etiquetas no estén disponibles).

La comparación no distingue mayúsculas en ninguna forma.

Origen de etiquetas y UUID: en macOS, `Accounts4.sqlite` en solo lectura; en Windows, las cuentas y stores del perfil de Outlook (§11.3, §15.7). Las claves TOML con espacios, puntos o paréntesis deben ir entre comillas (`[scope."iCloud (you@icloud.com)"]`); los UUID (con guiones) se pueden escribir sin comillas.

Para un plugin externo, la cuenta es el `label`, el `email` o el `uuid` opacos y estables que expone el plugin, en ese orden (el prefijo ≥ 8 no aplica).

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
[scope."iCloud (you@icloud.com)"]
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
- Sin bloques `[scope.*]` (o sin `config.toml`) ⇒ `W_NO_ACCOUNTS` (warning, no error): `search`/`new` devuelven `count: 0`; `mailboxes` marca `included: false`; `doctor` lista las cuentas disponibles (§12.8).
- `mailquery doctor` reporta todos estos casos con los valores válidos.

Drivers en `[scope]`:

- El prefijo del driver se separa en el **primer** `:`; si la parte izquierda no cumple `[a-z0-9_]{1,64}` o no corresponde a un driver instalado, el bloque es inválido con `E_DRIVER_UNKNOWN` (exit 2). Una etiqueta de cuenta que contenga `:` debe declararse **con** el prefijo explícito (`[scope."<driver>:<etiqueta>"]`), porque el primer `:` se interpreta como separador de driver; una etiqueta con `:` sin prefijo produce `E_DRIVER_UNKNOWN` (limitación documentada).
- La parte de cuenta se resuelve dentro de los `accounts()` de ese driver: con las formas del §15.2 para los backends internos y por `label`, `email` o `uuid` opacos para plugins; una cuenta inexistente ⇒ `E_CONFIG_ACCOUNT_UNKNOWN`; ambigua ⇒ `E_ACCOUNT_AMBIGUOUS`; store excluido (solo Outlook) ⇒ `W_STORE_EXCLUDED`.
- Dos bloques que resuelven a la misma `(driver, cuenta)` se combinan (unión de `mailbox_list`, §15).
- Un bloque con un driver declarado pero no instalado hace fallar **todos** los comandos de datos con `E_DRIVER_UNKNOWN`; no se ignoran drivers declarados.

### 15.4 Archivo mínimo (opcional)

Para leer una cuenta hay que **declararla**. Un bloque sin `mailbox_list` ya observa su INBOX; `mailbox_list` solo añade carpetas extra. Este es el menor ejemplo útil:

```toml
# ~/.mailquery/config.toml — mínimo
# Declara la cuenta (INBOX siempre incluido) y añade una carpeta extra.
[scope."iCloud (you@icloud.com)"]
mailbox_list = ["Facturas"]
```

Equivalente en Windows:

```toml
[scope."Exchange (you@company.com)"]
mailbox_list = ["INBOX/Facturas"]
```

### 15.5 Archivo completo (todas las propiedades)

El ejemplo de macOS muestra **todo** lo que se puede configurar hoy, con las tres formas de identificar una cuenta. Las secciones `[logging]`, `[search]`, `[new]`, `[attachments]`, `[content]` y `[lock]` son idénticas en ambas plataformas; para Windows solo se muestran los bloques de cuenta. Cada equipo tiene su propio `config.toml`: en un archivo solo resuelven las cuentas del backend de ese equipo (una cuenta de otro backend ⇒ `E_CONFIG_ACCOUNT_UNKNOWN`). Son válidos tal cual, sustituyendo etiquetas y carpetas por las tuyas.

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
json = false                   # true: JSON Lines en mailquery.jsonl

[search]
default_limit = 20             # 1..200
max_scan = 5000                # 100..50000

[new]
default_limit = 100            # 1..500
lookback = "10min"             # 1min..1d

[attachments]
enabled = true                 # true | false
max_file_size_mb = 100         # 1..500
max_total_size_mb = 200        # 1..1024 (>= max_file_size_mb)
max_count = 50                 # 1..500
timeout_seconds = 60           # 10..600, segundos por adjunto en `attachment`

# --- Presentación del contenido no confiable --------------------------------
[content]
url_display = "neutralize"     # neutralize | keep | strip (--strip-links fuerza strip)

# --- Reintento del lock de ejecución ----------------------------------------
[lock]
retries = 5                    # 0..10; 0 = un solo intento
initial_delay_ms = 150         # 10..5000
backoff_factor = 2             # 1..10, entero o decimal

# --- Cuentas observadas (declararlas es lo que las activa) -----------------
[scope."iCloud (you@icloud.com)"]
mailbox_list = ["Facturas", "Archivo"]

[scope."Gmail (you@gmail.com)"]
mailbox_list = ["[Gmail]/Important"]

[scope."On My Device"]
mailbox_list = ["Recovered Messages (you@gmail.com)"]

# ----------------------------------------------------------------------------
# Formas alternativas de identificar la MISMA cuenta (usar UNA por bloque;
# si se repiten bloques para la misma cuenta, sus listas se unen):
#
#   [scope."you@gmail.com"]                          # por email único
#   [scope."apple_mail:you@gmail.com"]               # con el prefijo del driver explícito
#   [scope."D70DBCF6-02DD-454C-8049-F63796B2EFAC"]   # por UUID completo
#   [scope."D70DBCF6"]                               # por prefijo único (>= 8)
#
# Cada elemento de mailbox_list es el path de una carpeta tal como lo muestra
# `mailquery mailboxes`, o su nombre o URL (`mailboxes --fields name,url`).
# Deben existir en esa cuenta;
# si no, el comando falla con E_MAILBOX_NOT_FOUND.
# ----------------------------------------------------------------------------
```

**Windows (Outlook clásico)**, bloques de cuenta:

```toml
# ~/.mailquery/config.toml — Windows + Outlook clásico: solo cambian las cuentas
# ([logging], [search], [new], [attachments], [content] y [lock] como en el ejemplo de macOS).

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
#   [scope."you@company.com"]                         # por email único
#   [scope."<uuid de la cuenta>"]                    # por UUID completo (lo muestra `mailboxes`)
#   [scope."<8+ primeros caracteres del uuid>"]      # por prefijo único (>= 8)
#
# Los paths válidos son los que muestra `mailquery mailboxes`; los nombres y URLs,
# `mailquery mailboxes --fields name,url`.
# Una cuenta declarada que resulte excluida (motivos: PRD §15.7) no se lee y
# genera W_STORE_EXCLUDED con su motivo.
# ----------------------------------------------------------------------------
```

Ejemplo con plugin instalado (solo si el paquete está instalado; si se copia sin instalarlo, `E_DRIVER_UNKNOWN`):

```toml
[scope."graph:trabajo@empresa.com"]
mailbox_list = ["INBOX/Facturas"]

[scope."outlook:PST (Archivo 2025)"]
mailbox_list = ["Contabilidad"]
```

### 15.6 Valores fijos (no configurables)

Los valores configurables están en §15.1. Estos son los que se mantienen fijos en el producto para no abrir combinaciones que rompan el contrato; si alguna tarea necesita otro valor, se evalúa como una propiedad documentada nueva.

**Tabla: Valores fijos**

| Aspecto | Valor fijo | Nota |
|---------|-----------|------|
| Home de la app | `~/.mailquery` | Config, estado, logs, locks, temporales, caché de adjuntos y la carpeta `db/` con la caché de ids nativos. En Windows, `%USERPROFILE%\.mailquery`. |
| Backend nativo | Por plataforma (RF-24) | Sin flag ni configuración para cambiarlo; los demás drivers se eligen por `[scope]` (RF-34). |
| Store de Apple Mail | La versión que usa Mail (`~/Library/Mail/V9`/`V10`/`V11`) | Sin override. |
| Stores de Outlook | stores locales del perfil cargado en el Outlook en ejecución | §15.7; sin selección de perfil. |
| Alcance base | Cuentas declaradas en `[scope.*]` | Reglas en §15. |
| Snippet | 200 caracteres | Solo con `--fields snippet` (o `all`) en `search`/`new` (RF-67, RF-68). |
| Cuerpo en `show` | 20.000 caracteres | Truncado con aviso en el JSON. |
| HTML → texto | Activado | Según RF-53; para el cuerpo, la búsqueda por contenido y los snippets. |
| Logs | Rutas (`mailquery.log`, `mailquery.jsonl`) y 5 archivos rotados por formato (§14) | Nivel, tamaño de rotación y formato se configuran en `[logging]`. |
| Lock | `~/.mailquery/locks/mailquery.lock`; como mucho 5000 ms por pausa entre reintentos | Automático; evita corridas solapadas. Los reintentos, la primera pausa y el factor de crecimiento se configuran en `[lock]` (§15.1, RF-89). |
| Directorio de adjuntos | `~/.mailquery/attachments/<driver>/<native_id>/` | `native_id` se sustituye por un identificador estable de 32 hex derivado de `uid` solo si `<native_id>` o la ruta exceden los límites de la plataforma (límites y fórmula en §10.3.3). |
| Staging | subdirectorio transitorio bajo `~/.mailquery/tmp/` | Se limpia al terminar, con éxito o no; el núcleo no toca archivos de plugins ni cachés del backend. |
| Longitud de `driver` | ≤ 64 caracteres (`[a-z0-9_]{1,64}`) | Se usa como componente de archivo/directorio; 64 deja margen a `<driver>.toml`, `logs/<driver>.log` y `tmp/plugin-<driver>/`. |
| Longitud de `sanitized_name` | `sanitized_name` (con prefijo, en JSON y en el archivo) ≤ 153 bytes UTF-8; nombre sin prefijo (raíz + extensión) ≤ 150 bytes; extensión ≤ 20 bytes | Si el prefijo mide más de 3 bytes (índice ≥ 100), la raíz se reduce en la diferencia. |
| Unidad de tamaño | 1 MB = 1.048.576 bytes | Se aplica a `[logging].max_size_mb` y a todos los límites de `[attachments]`. |
| Timeouts | 30 s metadatos | Sin configuración; el tope por adjunto extraído es `[attachments].timeout_seconds` (RF-49). |
| Mensajes por grupo de `--group-by` | 5 por defecto (de 0 a 50 con `--limit`) | RF-70. |
| Grupos de `--group-by` | 50 como máximo | Si hay más, `truncated: true` y `W_RESULTS_TRUNCATED` (RF-70). |

---

